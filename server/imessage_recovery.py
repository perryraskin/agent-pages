"""Bounded post-update recovery. Never changes SIP, security settings or Hermes core."""
import argparse
import fcntl
import json
import os
import signal
from pathlib import Path
import socket
import subprocess
import sys
import time

from native_support import IPC, STATE, available, exchange
from send_page import bridge, env_values

ROOT = Path(__file__).resolve().parent
HOME = Path(os.environ.get('AGENT_PAGES_HERMES_HOME', './.unconfigured-hermes'))
BB_HELPER = Path('/Applications/BlueBubbles.app/Contents/Resources/appResources/private-api/macos11/BlueBubblesHelper.dylib')
LIBRARY = ROOT / 'native/HermesPageSender.dylib'
RECOVERY = STATE / 'recovery.json'


def run(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    return result.returncode, result.stdout.strip()


def control(verb, params=None):
    path = HOME / 'gateway.sock'
    if not path.exists() or path.stat().st_uid != os.getuid():
        raise RuntimeError('Owner gateway control socket unavailable')
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(35)
        sock.connect(str(path))
        sock.sendall(json.dumps({'verb': verb, 'id': 1, 'protocol': 1, 'params': params or {}}).encode() + b'\n')
        data = b''
        while b'\n' not in data and len(data) < 2_000_000:
            part = sock.recv(65536)
            if not part: break
            data += part
    result = json.loads(data)
    if not result.get('ok'):
        raise RuntimeError('Gateway rejected scoped recovery')
    return result['result']


def status():
    sip = run('/usr/bin/csrutil', 'status')[1]
    validation = run('/usr/bin/defaults', 'read', '/Library/Preferences/com.apple.security.libraryvalidation', 'DisableLibraryValidation')
    info = {}
    try: info = bridge(env_values(), '/api/v1/server/info')['data']
    except Exception: pass
    return {'osBuild': run('/usr/bin/sw_vers', '-buildVersion')[1],
            'sipDisabled': 'status: disabled.' in sip,
            'libraryValidationConfigured': validation == (0, '1'),
            'privateAPI': bool(info.get('private_api')),
            'bluebubblesHelper': bool(info.get('helper_connected')),
            'nativePageHelper': available()}


def refresh_profile():
    # Reconnect ONLY imessage after checking its live workload. No shared gateway
    # restart; Telegram, Signal, workers and other profiles stay running.
    work = control('active-work', {'profile': 'imessage'})
    if work.get('active_agents') != 0 or work.get('active_work'):
        raise RuntimeError('iMessage has active work; recovery deferred')
    answer = control('unserve-profile', {'name': 'imessage'})
    if answer.get('error'):
        raise RuntimeError('iMessage profile could not be detached')
    try:
        answer = control('serve-profile', {'name': 'imessage'})
        if answer.get('error'):
            raise RuntimeError('iMessage profile could not be reattached')
    except Exception:
        # Best effort reattach, never stop or restart the entire host.
        try: control('serve-profile', {'name': 'imessage'})
        except Exception: pass
        raise
    return answer


def build(force=False):
    source = ROOT / 'native/HermesPageSender.m'
    if force or not LIBRARY.exists() or source.stat().st_mtime > LIBRARY.stat().st_mtime:
        subprocess.run(['/usr/bin/xcrun', 'clang', '-arch', 'arm64e', '-dynamiclib', '-fobjc-arc', '-framework', 'Foundation',
                        '-o', str(LIBRARY), str(source)], check=True, timeout=90)
        subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(LIBRARY)], check=True, timeout=30)


def apply(current, *, refresh=True):
    if not current['sipDisabled']:
        return {**current, 'state': 'needs-manual-sip',
                'next': 'In Recovery Terminal run csrutil disable, then restart. Nothing changed automatically.'}
    if not current['libraryValidationConfigured']:
        return {**current, 'state': 'needs-manual-library-validation',
                'next': 'Review and run: sudo defaults write /Library/Preferences/com.apple.security.libraryvalidation.plist DisableLibraryValidation -bool true. This reduces macOS security.'}
    if not current['privateAPI']:
        return {**current, 'state': 'needs-bluebubbles-setting',
                'next': 'Enable Messages Private API in BlueBubbles Settings, then rerun --apply.'}
    source = ROOT/'native/HermesPageSender.m'
    outdated = LIBRARY.exists() and source.stat().st_mtime > LIBRARY.stat().st_mtime
    if not current['nativePageHelper'] or outdated:
        work = control('active-work', {'profile': 'imessage'})
        if work.get('active_agents') != 0 or work.get('active_work'):
            return {**current, 'state': 'deferred-active-imessage'}
        # A loaded older helper can still answer probes while lacking artwork.
        # Replace only a positively identified Page-only worker; never stock BB.
        try: previous = exchange('probe',timeout=2)
        except RuntimeError: previous = None
        if previous and previous.get('ok') and isinstance(previous.get('pid'),int):
            pid = previous['pid']
            code,mapped = run('/usr/sbin/lsof','-p',str(pid))
            if str(LIBRARY) not in mapped or str(BB_HELPER) in mapped:
                raise RuntimeError('Cannot safely identify the old Page-only worker')
            os.kill(pid,signal.SIGTERM)
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                try: os.kill(pid,0)
                except ProcessLookupError: break
                time.sleep(.1)
            else: raise RuntimeError('Old Page worker did not exit; no force kill attempted')
        if not BB_HELPER.is_file(): raise RuntimeError('BlueBubbles helper missing; reinstall BlueBubbles normally')
        # Recompile against the current SDK after each OS update, even when our
        # source is unchanged. Private API compatibility is still proven live.
        last = json.loads((STATE/'built-os.json').read_text()) if (STATE/'built-os.json').exists() else {}
        build(force=last.get('osBuild') != current['osBuild'])
        (STATE/'built-os.json').write_text(json.dumps({'osBuild':current['osBuild']}))
        IPC.mkdir(mode=0o700, parents=True, exist_ok=True)
        if IPC.is_symlink() or IPC.stat().st_uid != os.getuid() or IPC.stat().st_mode & 0o077:
            raise RuntimeError('Unsafe helper IPC directory')
        env = env_values()
        owner = env['BLUEBUBBLES_HOME_CHANNEL'].removeprefix('iMessage;-;')
        # A dedicated Messages-side worker loads ONLY our narrow helper. The
        # stock BB-managed Messages process keeps its one stock helper. Loading
        # that helper twice would broadcast every BB send twice.
        launch_env = {k:os.environ[k] for k in ('HOME','USER','LOGNAME','PATH','TMPDIR','LANG') if k in os.environ}
        launch_env.update(DYLD_INSERT_LIBRARIES=str(LIBRARY),
                          HERMES_PAGE_IPC=str(IPC), HERMES_PAGE_TARGETS=owner)
        # Never quit the stock Messages process or interrupt BB text/reactions.
        with open(STATE / 'messages-helper.log', 'ab') as log:
            subprocess.Popen(['/System/Applications/Messages.app/Contents/MacOS/Messages'], env=launch_env,
                             stdout=log, stderr=log, start_new_session=True)
        deadline = time.monotonic()+25
        while time.monotonic()<deadline:
            if available(): break
            time.sleep(.5)
        else: raise RuntimeError('Native Page helper did not become ready; text fallback remains available')
    if refresh: refresh_profile()
    # The stock helper performs its handshake asynchronously after Messages starts.
    deadline = time.monotonic()+15
    while time.monotonic()<deadline:
        try:
            data=bridge(env_values(),'/api/v1/server/info')['data']
            if data.get('helper_connected'): break
        except Exception: pass
        time.sleep(.5)
    result = status()
    result['state'] = 'ready' if all(result[k] for k in ('privateAPI','bluebubblesHelper','nativePageHelper')) else 'degraded'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Repair helpers and idle iMessage profile only')
    parser.add_argument('--auto', action='store_true', help='Once-per-boot recovery after prerequisites pass')
    parser.add_argument('--no-refresh', action='store_true', help='Install helper without reconnecting iMessage')
    args = parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(STATE / 'recovery.lock', 'a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return
        current = status()
        previous = json.loads(RECOVERY.read_text()) if RECOVERY.exists() else {}
        if not args.auto and not args.apply:
            print(json.dumps({**current,'state':'check-only'},indent=2))
            return  # A health check must not erase the once-per-boot repair guard.
        if args.auto:
            boot = run('/usr/sbin/sysctl', '-n', 'kern.boottime')[1]
            key = boot + ':' + current['osBuild']
            prerequisites = current['sipDisabled'] and current['libraryValidationConfigured'] and current['privateAPI']
            if prerequisites and previous.get('attemptBoot') != key:
                # Persist BEFORE recovery: incompatible updates cannot create restart loops.
                RECOVERY.write_text(json.dumps({**current,'attemptBoot':key,'state':'attempting'}))
                try: current = apply(current)
                except Exception as exc: current = {**current,'state':'repair-failed','error':type(exc).__name__}
                current['attemptBoot'] = key
            else:
                current['attemptBoot'] = previous.get('attemptBoot')
                current['state'] = ('ready' if current['nativePageHelper'] and current['bluebubblesHelper']
                                    else 'needs-manual-sip' if not current['sipDisabled'] else 'needs-review')
        elif args.apply:
            current = apply(current, refresh=not args.no_refresh)
            if previous.get('attemptBoot'): current['attemptBoot']=previous['attemptBoot']
        RECOVERY.write_text(json.dumps(current, indent=2))
        os.chmod(RECOVERY,0o600)
        print(json.dumps(current, indent=2))


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        print(json.dumps({'state':'failed','error':type(exc).__name__,'detail':str(exc) if isinstance(exc,RuntimeError) else 'Inspect local recovery logs'}))
        sys.exit(1)
