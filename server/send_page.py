"""Send a Hermes Page through the configured bridge. Transport order: genuine iMessage card (needs the private API),
else the supported rich link card, else an explicitly requested snapshot file.
Default is local export, never sending. Does not enable reply monitoring or restart a gateway.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import tempfile

ROOT = Path(os.environ.get('AGENT_PAGES_ROOT', str(Path(__file__).resolve().parents[1] / 'apps/web')))
ENV = Path(os.environ.get('AGENT_PAGES_ENV', '.env'))
STATE = Path.home() / '.local/share/hermes-pages-ios/delivery'
PAGES_WEB = os.environ.get('AGENT_PAGES_BASE_URL', 'https://pages.example.invalid')
ID = re.compile(r'^[a-z0-9][a-z0-9-]{0,120}$')

def reference(slug, root=ROOT):
    if not ID.fullmatch(slug): raise ValueError('Invalid Page ID')
    meta = json.loads((root/'src'/slug/'meta.json').read_text())
    title = str(meta['title'])
    if len(title) >= 300: raise ValueError('Page title is too long')
    body=(root/'build'/f'{slug}.html').read_text()
    doc={'version':2, 'pageID':slug, 'title':title, 'html':body}
    if len(json.dumps(doc).encode()) >= 2_000_000: raise ValueError('Page is too large for a native preview')
    return doc

def filename(title):
    return (re.sub(r'[^\w .-]', '-', title).strip(' .')[:90] or 'Hermes Page') + '.hermespage'

def bridge(env, path, data=None, timeout=45):
    url = env['BLUEBUBBLES_SERVER_URL'].rstrip('/') + path + '?' + urllib.parse.urlencode({'password': env['BLUEBUBBLES_PASSWORD']})
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'} if body else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def env_values():
    return {k:v.strip().strip('\"\'') for line in ENV.read_text().splitlines() if '=' in line and not line.startswith('#') for k,v in [line.split('=',1)]}

def card_capability(env):
    """True only when BlueBubbles' private API + injected helper can carry a native balloon payload."""
    try:
        info = bridge(env, '/api/v1/server/info')
        data = info.get('data') or {}
        from native_support import available
        return bool(data.get('private_api')) and bool(data.get('helper_connected')) and available()
    except Exception:
        return False

def bridge_message(env, guid, deadline):
    """Read-only GET of the sent message from BlueBubbles (it has Full Disk Access; the gateway
    does not). BlueBubbles matches GUIDs case-sensitively, so try each case once; the key that
    answers is remembered in env. Gives up at `deadline` (time.monotonic()). Never logs the URL."""
    import time
    cached = env.get('_delivery_guid_key')
    for n, key in enumerate([cached] if cached else list(dict.fromkeys((guid, guid.upper(), guid.lower())))):
        left = deadline - time.monotonic()
        if left <= 0 and n:
            return None
        try:  # at least one short request even at the deadline, so a final check still happens
            data = (bridge(env, '/api/v1/message/' + urllib.parse.quote(key, safe=''), timeout=min(2.0, max(left, 0.25))) or {}).get('data')
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            return None
        if isinstance(data, dict):
            env['_delivery_guid_key'] = key
            return data
    return None

def delivered(guid, env=None):
    """Recipient delivery receipt for an already-sent row: True, False (send error) or None
    (no receipt yet). Read-only; never raises and never triggers a resend. Uses chat.db when
    readable, else the BlueBubbles message record, within one bounded wait."""
    try:
        from native_support import delivery_state
        fallback = None
        if env and env.get('BLUEBUBBLES_SERVER_URL'):
            bridge_env = dict(env)
            fallback = lambda g, deadline: bridge_message(bridge_env, g, deadline)
        return delivery_state(guid, fallback=fallback)
    except Exception:
        return None

def owner_for(env, device_id=None):
    return env.get('BLUEBUBBLES_HOME_CHANNEL', '')

def send_link(ref, request_id, env, device_id=None):
    """Supported transport: the bot line sends the Page URL; Messages renders the rich link card.
    Tapping opens the in-Messages browser drawer, not the extension."""
    owner=owner_for(env,device_id)
    if not owner: raise ValueError('Owner channel not configured')
    url = PAGES_WEB.rstrip('/') + '/' + ref['pageID'] + '.html'
    result = bridge(env, '/api/v1/message/text', {
        'chatGuid': owner if owner.startswith('iMessage;') else 'iMessage;-;'+owner,
        'tempGuid': request_id,
        'message': ref['title'] + '\n' + url,
        'method': 'apple-script'})
    if result.get('status') != 200: raise RuntimeError('No confirmed link send result')
    return {'status':'sent','transport':'link-card','pageID':ref['pageID'],'guid':(result.get('data') or {}).get('guid'),'url':url,'requestID':request_id}

def send(ref, request_id, device_id=None, transport='auto'):
    # The dedicated bot's configured home channel is the ONLY allowed recipient.
    env = {k:v.strip().strip('\"\'') for line in ENV.read_text().splitlines() if '=' in line and not line.startswith('#') for k,v in [line.split('=',1)]}
    base, owner = env.get('BLUEBUBBLES_SERVER_URL',''), env.get('BLUEBUBBLES_HOME_CHANNEL','')
    if urllib.parse.urlsplit(base).hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('Only the local BlueBubbles bridge is allowed')
    if transport not in ('auto','card','link','file'): raise ValueError('Unknown Page transport')
    capable = card_capability(env) if transport in ('auto','card') else False
    if transport == 'card' and not capable:
        raise RuntimeError('Native balloon helper unavailable; no file or link was sent. Run the recovery tool explicitly.')
    if transport == 'card' or (transport == 'auto' and capable):
        from native_support import send_card
        owner = owner_for(env, device_id)
        if not owner: raise ValueError('Owner channel not configured')
        if owner.startswith('iMessage;-;'): owner = owner.split(';', 2)[2]
        STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
        journal = STATE / (str(uuid.UUID(request_id)) + '.json')
        fd = os.open(journal, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f: json.dump({'status':'pending','transport':'native-card','pageID':ref['pageID']}, f)
        try:
            result = send_card(ref, request_id, owner)
        except Exception:
            journal.write_text(json.dumps({'status':'unknown','transport':'native-card','pageID':ref['pageID'],'requestID':request_id}))
            raise RuntimeError('Native card outcome uncertain/rejected. Reconcile this request; no fallback was sent.') from None
        result['delivered'] = delivered(result.get('guid'), env)
        journal.write_text(json.dumps(result)); print(json.dumps(result)); return
    if transport in ('link', 'auto'):
        if transport in ('auto','link'):
            STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
            journal = STATE / (str(uuid.UUID(request_id)) + '.json')
            fd = os.open(journal, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
            with os.fdopen(fd,'w') as f: json.dump({'status':'pending','transport':'link-card','pageID':ref['pageID']},f)
            try:
                record = send_link(ref, request_id, env, device_id)
            except Exception:
                journal.write_text(json.dumps({'status':'unknown','transport':'link-card','pageID':ref['pageID'],'requestID':request_id}))
                raise RuntimeError('Link-card outcome uncertain; reconcile this request before retrying') from None
            record['delivered'] = delivered(record.get('guid'), env)
            journal.write_text(json.dumps(record)); print(json.dumps(record)); return
        raise RuntimeError('True native cards need the BlueBubbles private API + connected helper (SIP disabled). Use --transport link for the supported card, or enable the private API.')
    if not owner: raise ValueError('Owner channel not configured')
    parsed = urllib.parse.urlparse(base)
    if parsed.hostname not in ('127.0.0.1','localhost'): raise ValueError('Only the local BlueBubbles bridge is allowed')
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    journal = STATE / (str(uuid.UUID(request_id)) + '.json')
    # Exclusive creation: never repeat a request with an uncertain or already confirmed outcome.
    fd = os.open(journal, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(fd,'w') as f: json.dump({'status':'pending','pageID':ref['pageID']},f)
    boundary='HermesPage'+secrets.token_hex(12)
    fields={'chatGuid':owner if owner.startswith('iMessage;') else 'iMessage;-;'+owner,'tempGuid':request_id,'name':filename(ref['title']),'method':'apple-script'}
    chunks=[]
    for key,value in fields.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    body=json.dumps(ref).encode()
    chunks += [f'--{boundary}\r\nContent-Disposition: form-data; name="attachment"; filename="page.hermespage"\r\nContent-Type: application/vnd.perryraskin.hermes-page+json\r\n\r\n'.encode(),body,f'\r\n--{boundary}--\r\n'.encode()]
    url=base.rstrip('/')+'/api/v1/message/attachment?'+urllib.parse.urlencode({'password':env['BLUEBUBBLES_PASSWORD']})
    req=urllib.request.Request(url,data=b''.join(chunks),headers={'Content-Type':'multipart/form-data; boundary='+boundary})
    try:
        with urllib.request.urlopen(req,timeout=45) as response: result=json.load(response)
        if result.get('status')!=200: raise RuntimeError('No confirmed delivery result')
        data=result.get('data') or {}
        record={'status':'sent','transport':'file-snapshot','pageID':ref['pageID'],'guid':data.get('guid'),'requestID':request_id}
        journal.write_text(json.dumps(record)); print(json.dumps(record))
    except Exception:
        # Do not print request URLs/exceptions: they can contain the bridge password.
        journal.write_text(json.dumps({'status':'unknown','pageID':ref['pageID']}))
        raise RuntimeError('Send outcome is uncertain. Check Messages before sending again; this request ID cannot be reused.') from None

if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('slug'); a.add_argument('--send',action='store_true'); a.add_argument('--transport',choices=['auto','card','link','file'],default='auto',help='auto = native card if the private API is live, else link card'); a.add_argument('--device-id', default=os.environ.get('AGENT_PAGES_DEVICE_ID')); a.add_argument('--request-id',default=None); a.add_argument('--output',type=Path)
    args=a.parse_args()
    try:
        ref=reference(args.slug)
        if args.transport == 'file':
            if not args.send: raise ValueError('--transport file needs --send')
            send(ref, args.request_id or str(uuid.uuid4()), device_id=args.device_id, transport='file')
        elif args.send: send(ref,args.request_id or str(uuid.uuid4()),device_id=args.device_id,transport=args.transport)
        else:
            fd, temporary = tempfile.mkstemp(suffix='.hermespage', dir=str(args.output.parent) if args.output else None)
            out = Path(temporary)
            with os.fdopen(fd, 'w') as f: f.write(json.dumps(ref))
            if args.output:
                os.replace(out, args.output)
                out = args.output
            print(json.dumps({'path':str(out),'bytes':out.stat().st_size,'sent':False}))
    except Exception as e:
        print(type(e).__name__+': '+str(e) if isinstance(e,(ValueError,RuntimeError)) else type(e).__name__+': could not complete Page delivery',file=sys.stderr);sys.exit(1)
