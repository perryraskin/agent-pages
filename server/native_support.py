"""Local-only native balloon IPC and UID-preserving Page archive generation."""
import base64
import json
import os
from pathlib import Path
import plistlib
import sqlite3
import subprocess
import time
import uuid

IPC = Path.home() / 'Library/Containers/com.apple.MobileSMS/Data/.hermes-page-ipc'
BUNDLE = os.environ.get('AGENT_PAGES_BALLOON_BUNDLE', 'com.apple.messages.MSMessageExtensionBalloonPlugin::org.example.agentpages.messages')
STATE = Path.home() / '.local/share/hermes-pages-ios/native'
NATIVE = Path(__file__).resolve().parent / 'native'
PREVIEWS = Path.home() / 'Library/Messages/Attachments/HermesPages'
CHAT_DB = Path.home() / 'Library/Messages/chat.db'


def message_guid(request_id):
    # iMessage carries GUIDs as binary UUIDs; delivery receipts come back as UPPERCASE
    # strings and imagent matches them against chat.db case-sensitively. A lowercase
    # GUID is sent fine but its receipts never match, so is_delivered stays 0.
    return str(uuid.UUID(request_id)).upper()


def render_preview(ref, request_id):
    identity = message_guid(request_id)
    PREVIEWS.mkdir(parents=True,exist_ok=True,mode=0o700)
    if PREVIEWS.is_symlink() or PREVIEWS.stat().st_uid != os.getuid():
        raise ValueError('Unsafe Page preview staging directory')
    source, renderer = NATIVE/'RenderPagePreview.m', NATIVE/'RenderPagePreview'
    if not renderer.exists() or source.stat().st_mtime > renderer.stat().st_mtime:
        subprocess.run(['/usr/bin/xcrun','clang','-fobjc-arc','-framework','AppKit',
                        '-framework','CoreText','-o',str(renderer),str(source)],
                       check=True,capture_output=True,timeout=60)
    destination=PREVIEWS/(identity+'.jpeg')
    if destination.exists(): raise RuntimeError('Preview request ID already used')
    font=Path(__file__).resolve().parents[1]/'apps/ios/Resources/InstrumentSerif-Regular.ttf'
    subprocess.run([str(renderer),ref['title'],str(destination),str(font)],
                   check=True,capture_output=True,timeout=15)
    os.chmod(destination,0o600)
    if not 1000 < destination.stat().st_size < 1_000_000:
        raise ValueError('Page preview image is missing or unexpectedly large')
    return destination


def exchange(action, *, request_id=None, timeout=5, **fields):
    identity = message_guid(request_id) if request_id else str(uuid.uuid4())
    if not IPC.is_dir() or IPC.is_symlink() or IPC.stat().st_uid != os.getuid() or IPC.stat().st_mode & 0o077:
        raise RuntimeError('Native Page helper is not ready')
    target = IPC / (identity + '.request.json')
    # Idempotent: a claimed, response, or previous request is never overwritten.
    for suffix in ('.request.json', '.claimed', '.response.json', '.expired'):
        if any((IPC / (name + suffix)).exists() for name in (identity, identity.lower())):
            raise RuntimeError('Request already used; reconcile the existing GUID, never resend')
    temporary = IPC / (identity + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump({'id': identity, 'action': action, **fields}, f)
    os.rename(temporary, target)
    response = IPC / (identity + '.response.json')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if response.exists():
            result = json.loads(response.read_text())
            if action == 'probe':
                response.unlink(missing_ok=True)
                (IPC/(identity+'.claimed')).unlink(missing_ok=True)
            return result
        time.sleep(0.1)
    # Remove an UNCLAIMED request atomically so a later helper launch cannot send
    # a stale command. A claimed request has an uncertain outcome and stays so.
    try:
        os.rename(target, IPC / (identity + '.expired'))
    except FileNotFoundError:
        pass
    if action == 'probe':
        (IPC/(identity+'.expired')).unlink(missing_ok=True)
    raise RuntimeError('Native helper timed out; reconcile this request before resending')


def available():
    try:
        result = exchange('probe', timeout=1.5)
        return (result.get('ok') is True and result.get('balloon') is True
                and result.get('protocol',0) >= 2 and result.get('previewArtwork') is True)
    except Exception:
        return False


def template():
    cache = STATE / 'template.bplist'
    if cache.exists():
        return plistlib.loads(cache.read_bytes())
    db = Path.home() / 'Library/Messages/chat.db'
    with sqlite3.connect(f'file:{db}?mode=ro', uri=True) as conn:
        row = conn.execute('SELECT payload_data FROM message WHERE balloon_bundle_id=? AND payload_data IS NOT NULL ORDER BY ROWID DESC LIMIT 1', (BUNDLE,)).fetchone()
    if not row:
        raise RuntimeError('No trusted Hermes Pages template captured; send one from the QA iPhone first')
    archive = plistlib.loads(row[0])
    if archive.get('$archiver') != 'NSKeyedArchiver':
        raise ValueError('Unexpected Page archive')
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(cache, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(row[0])
    return archive


def page_payload(ref, archive=None):
    # Python's binary plist writer preserves plistlib.UID references. Never
    # unarchive arbitrary Objective-C objects or substitute binary bytes in place.
    import copy
    archive = copy.deepcopy(template() if archive is None else archive)
    objects = archive['$objects']
    urls = [s for s in objects if isinstance(s, str) and 'hermesPage=' in s]
    if len(urls) != 1 or not urls[0].startswith((os.environ.get('AGENT_PAGES_BASE_URL', 'https://pages.example.invalid').rstrip('/') + '/v1/pages/')):
        raise ValueError('Unexpected template destination')
    old_url = urls[0]
    old_summary = next((s for s in objects if isinstance(s, str) and s.startswith('Hermes Page: ')), None)
    if not old_summary:
        raise ValueError('Template summary missing')
    old_title = old_summary.removeprefix('Hermes Page: ')
    url = (os.environ.get('AGENT_PAGES_BASE_URL', 'https://pages.example.invalid').rstrip('/') + '/v1/pages/') + ref['pageID'] + '/content?hermesPage=' + ref['pageID']
    for i, value in enumerate(objects):
        if value == old_url: objects[i] = url
        elif value == old_title: objects[i] = ref['title']
        elif value == old_summary: objects[i] = 'Hermes Page: ' + ref['title']
        # Session identifier archives encode NSUUID as NS.uuidbytes.
        elif isinstance(value, dict) and isinstance(value.get('NS.uuidbytes'), bytes):
            value['NS.uuidbytes'] = uuid.uuid4().bytes
    data = plistlib.dumps(archive, fmt=plistlib.FMT_BINARY, sort_keys=False)
    assert plistlib.loads(data)['$archiver'] == 'NSKeyedArchiver'
    return data, url


def send_card(ref, request_id, target):
    data, url = page_payload(ref)
    preview = render_preview(ref, request_id)
    result = exchange('send', request_id=request_id, timeout=30,
                      target=target, payload=base64.b64encode(data).decode(),
                      previewPath=str(preview))
    if not result.get('ok'):
        raise RuntimeError(result.get('error', 'Native Page rejected'))
    if not result.get('previewTransferGUID'):
        raise RuntimeError('Native send lacks confirmed artwork; reconcile it before retrying')
    return {'status': 'sent', 'transport': 'native-card', 'pageID': ref['pageID'],
            'guid': result['guid'], 'url': url, 'requestID': request_id,
            'previewTransferGUID': result.get('previewTransferGUID')}


CHAT_DB_UNREADABLE = 'hermes-pages: chat.db unreadable, using bridge for delivery state'


def bridge_delivery(message):
    """Map a BlueBubbles message record (GET /api/v1/message/{guid} -> data) to the same
    True/False/None as the chat.db row: isDelivered/dateDelivered -> True, error -> False."""
    if not isinstance(message, dict) or message.get('isFromMe') is False:
        return None
    if message.get('isDelivered') is True or message.get('dateDelivered'):
        return True
    if message.get('error'):
        return False
    return None


def delivery_state(guid, wait=8.0, db=None, fallback=None):
    """Read-only check of the sent row. True: a recipient device's delivery receipt was
    recorded. False: Messages recorded a send error. None: no receipt yet (unconfirmed,
    e.g. the phone is offline). Never raises; the send has already happened.

    chat.db needs Full Disk Access, which the launchd gateway lacks. If it cannot be opened
    or queried (anything but a transient lock), stop retrying it and poll
    fallback(guid, deadline) -> BlueBubbles message dict | None instead, within the same
    overall `wait` budget. fallback must give up by `deadline` (time.monotonic())."""
    import contextlib
    import sys
    if not guid:
        return None
    keys = (guid, guid.upper(), guid.lower())
    deadline = time.monotonic() + wait
    unreadable = False
    while True:
        state = None
        if not unreadable:
            try:
                with contextlib.closing(sqlite3.connect(f'file:{db or CHAT_DB}?mode=ro', uri=True, timeout=1)) as c:
                    row = c.execute('SELECT is_delivered, date_delivered, error FROM message '
                                    'WHERE guid IN (?,?,?) AND is_from_me=1 ORDER BY ROWID DESC LIMIT 1', keys).fetchone()
                if row:
                    state = True if (row[0] or row[1]) else (False if row[2] else None)
            except Exception as e:
                if not ('locked' in str(e) or 'busy' in str(e)):
                    unreadable = True
                    if fallback is None:
                        return None
                    try:
                        print(CHAT_DB_UNREADABLE, file=sys.stderr, flush=True)
                    except Exception:
                        pass
        if unreadable:
            try:
                state = bridge_delivery(fallback(guid, deadline))
            except Exception:
                state = None
        if state is not None:
            return state
        if time.monotonic() >= deadline:
            return None
        time.sleep(min(0.5 if unreadable else 0.25, max(0.0, deadline - time.monotonic())))
