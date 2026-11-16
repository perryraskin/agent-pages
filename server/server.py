"""Hermes Pages companion sidecar. Private API and public snapshot server are SEPARATE listeners.
No Hermes core modifications. Never proxy the private library through the public listener.
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote, parse_qs
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from page_tags import catalog as page_catalog, tag_counts as page_tag_counts, decorate_content

SLUG = re.compile(r'^[a-z0-9][a-z0-9-]{0,120}$')
TOKEN = re.compile(r'^[A-Za-z0-9_-]{43}$')
CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"

def snapshot_html(raw, title):
    # Freeze the current rendered body; no scripts, frames, forms, remote resources or private OG metadata.
    raw = re.sub(r'<script\b[^>]*>[\s\S]*?</script\s*>', '', raw, flags=re.I)
    raw = re.sub(r'<(?:iframe|object|embed)\b[^>]*>[\s\S]*?</(?:iframe|object|embed)\s*>', '', raw, flags=re.I)
    raw = re.sub(r'<(?:meta|link|base)\b[^>]*>', '', raw, flags=re.I)
    raw = re.sub(r'\s+on[a-z]+\s*=\s*(?:"[^"]*"|\x27[^\x27]*\x27|[^\s>]+)', '', raw, flags=re.I)
    metadata = ('<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                '<meta name="robots" content="noindex,nofollow,noarchive">'
                '<meta name="referrer" content="no-referrer">'
                '<meta property="og:title" content="Hermes Page">'
                '<meta property="og:description" content="A privately shared, read-only snapshot.">')
    raw = re.sub(r'<head[^>]*>', '<head>' + metadata, raw, count=1, flags=re.I)
    raw = re.sub(r'<title>[\s\S]*?</title>', '<title>Shared Hermes Page</title>', raw, flags=re.I)
    return raw

class Store:
    def __init__(self, root, state):
        self.root, self.state = Path(root), Path(state)
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = self.state / 'shares.sqlite3'
        with self.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS shares (id TEXT PRIMARY KEY, token_hash TEXT UNIQUE, slug TEXT, title TEXT, body TEXT, created REAL, expires REAL, revoked INTEGER DEFAULT 0)')
        os.chmod(self.db, 0o600)

    def connect(self): return sqlite3.connect(self.db)

    def pages(self, query='', tags=None):
        return [{'id': p['slug'], 'title': p.get('title', p['slug']),
                 'updatedAt': p.get('updated_at', ''), 'automatic': bool(p.get('auto', False)),
                 'tags': p['tags'], 'status': p['status']}
                for p in page_catalog(self.root, query=query, tags=tags)
                if (self.root / 'build' / (p['slug'] + '.html')).is_file()]

    def page(self, slug):
        if not SLUG.fullmatch(slug): return None
        return next((p for p in self.pages() if p['id'] == slug), None)

    def live(self, slug):
        # The small JSON an open Page polls (content version + work status); written by the Pages builder.
        if not SLUG.fullmatch(slug): return None
        f = self.root / 'build' / 'live' / f'{slug}.json'
        try: return json.loads(f.read_text())
        except (OSError, ValueError): return None

    def previous(self, slug):
        # The version a Page's latest save replaced, so an open reader can show what that save changed.
        if not SLUG.fullmatch(slug): return None
        f = self.root / 'build' / 'live' / f'{slug}.prev.html'
        try: return f.read_bytes()
        except OSError: return None

    def content(self, slug):
        page = self.page(slug)
        if page is None: raise ValueError('Page not found')
        raw = (self.root / 'build' / f'{slug}.html').read_text()
        return decorate_content(raw, page['tags'])

    def create(self, slug, days):
        page = self.page(slug)
        if page is None: raise ValueError('Page not found')
        token, sid, now = secrets.token_urlsafe(32), secrets.token_hex(12), time.time()
        body = snapshot_html(self.content(slug), page['title'])
        with self.connect() as c:
            c.execute('INSERT INTO shares VALUES (?,?,?,?,?,?,?,0)', (sid, hashlib.sha256(token.encode()).hexdigest(), slug, page['title'], body, now, now + days*86400))
        return sid, token

    def shares(self):
        with self.connect() as c:
            c.row_factory = sqlite3.Row
            return [dict(r) for r in c.execute('SELECT id,slug,title,created,expires,revoked FROM shares ORDER BY created DESC')]

    def public(self, token):
        if not TOKEN.fullmatch(token): return None
        with self.connect() as c:
            return c.execute('SELECT body,expires,revoked FROM shares WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()

class Handler(BaseHTTPRequestHandler):
    server_version = 'HermesPages'
    def log_message(self, fmt, *args): pass  # Do not log token URLs, titles, content, or request bodies.
    def send(self, status, data, kind='application/json', extra=None):
        body = json.dumps(data).encode() if kind == 'application/json' else data.encode() if isinstance(data, str) else data
        self.send_response(status)
        for k,v in {'Content-Type': kind, 'Content-Length': str(len(body)), 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff', **(extra or {})}.items(): self.send_header(k,v)
        self.end_headers()
        if self.command != 'HEAD': self.wfile.write(body)

    @property
    def store(self): return self.server.store
    @property
    def route(self): return unquote(urlparse(self.path).path).rstrip('/')

    def read_json(self):
        length = int(self.headers.get('Content-Length', '0'))
        if length < 1 or length > 4096: raise ValueError('Invalid request size')
        return json.loads(self.rfile.read(length))

    def allowed(self):
        hosts = {'localhost', '127.0.0.1', '::1'} | {host.strip().lower() for host in os.environ.get('AGENT_PAGES_ALLOWED_HOSTS', '').split(',') if host.strip()}
        try:
            host = urlparse('//' + self.headers.get('Host', '')).hostname
            origin = self.headers.get('Origin')
            return host in hosts and (not origin or urlparse(origin).hostname in hosts)
        except ValueError:
            return False

    def do_HEAD(self): self.do_GET()
    def do_GET(self):
        if not self.allowed(): return self.send(403, {"error": "Forbidden"})
        r = self.route
        if self.server.public_only:
            if r == '/health': return self.send(200, {'ok': True})
            if r.startswith('/s/'):
                row = self.store.public(r[3:])
                if row is None: return self.send(404, 'Not found', 'text/plain')
                body, expires, revoked = row
                if revoked or expires <= time.time(): return self.send(410, 'This shared Page has expired or been revoked.', 'text/plain')
                return self.send(200, body, 'text/html; charset=utf-8', {'Content-Security-Policy': CSP, 'X-Robots-Tag': 'noindex, nofollow, noarchive'})
            return self.send(404, 'Not found', 'text/plain')
        if r == '/health': return self.send(200, {'ok': True})
        # Tailnet membership is the private API's access boundary. No public listener has these routes.
        if r in ('/v1/pages', '/v1/tags'):
            try:
                params = parse_qs(urlparse(self.path).query)
                if r == '/v1/tags':
                    return self.send(200, {'tags': page_tag_counts(self.store.pages())})
                tags = [tag for part in params.get('tag', []) + params.get('tags', []) for tag in part.split(',') if tag]
                return self.send(200, {'pages': self.store.pages(params.get('q', [''])[0], tags)})
            except ValueError as e:
                return self.send(400, {'error': str(e)})
        if r == '/v1/shares': return self.send(200, {'shares': self.store.shares()})
        if r.startswith('/v1/pages/') and r.endswith('/live'):
            pulse = self.store.live(r[len('/v1/pages/'):-len('/live')])
            if pulse is None: return self.send(404, {'error': 'Page not found'})
            return self.send(200, pulse)
        if r.startswith('/v1/pages/') and r.endswith('/previous'):
            body = self.store.previous(r[len('/v1/pages/'):-len('/previous')])
            if body is None: return self.send(404, {'error': 'No previous version'})
            return self.send(200, body, 'text/html; charset=utf-8')
        if r.startswith('/v1/pages/') and r.endswith('/content'):
            slug = r[len('/v1/pages/'):-len('/content')]
            if self.store.page(slug) is None: return self.send(404, {'error': 'Page not found'})
            return self.send(200, self.store.content(slug), 'text/html; charset=utf-8')
        return self.send(404, {'error': 'Not found'})

    def do_POST(self):
        if not self.allowed(): return self.send(403, {"error": "Forbidden"})
        if self.server.public_only: return self.send(404, {'error': 'Not found'})
        # Browser CSRF protection: neither cross-origin forms nor untrusted Pages can mutate snapshots.
        if self.headers.get('Origin') or self.headers.get('X-Hermes-Client') != 'ios': return self.send(403, {'error': 'Native client required'})
        try:
            data = self.read_json()
            if not isinstance(data, dict): raise ValueError('Expected a JSON object')
            if self.route == '/v1/shares':
                basefile = self.store.state / 'public-url.txt'
                base = basefile.read_text().strip() if basefile.exists() else ''
                if not base.startswith('https://'): return self.send(503, {'error': 'Public sharing is not configured. You can still export an HTML snapshot.'})
                days = data.get('days', 7)
                if type(days) is not int or days not in (1,7,30): raise ValueError('Choose 1, 7, or 30 days')
                sid, token = self.store.create(data.get('slug', ''), days)
                return self.send(201, {'id': sid, 'url': base.rstrip('/') + '/s/' + token})
            if self.route.startswith('/v1/shares/') and self.route.endswith('/revoke'):
                sid = self.route.split('/')[3]
                with self.store.connect() as c:
                    cur = c.execute('UPDATE shares SET revoked=1,body="" WHERE id=?', (sid,))
                return self.send(200 if cur.rowcount else 404, {'ok': bool(cur.rowcount)})
            return self.send(404, {'error': 'Not found'})
        except (ValueError, TypeError, OSError) as e: return self.send(400, {'error': 'Invalid request'})


def serve(root, state, private_port=9133, public_port=9134):
    store = Store(root, state)
    servers = []
    for port, public in ((private_port,False),(public_port,True)):
        server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        server.store, server.public_only = store, public
        servers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    return servers

if __name__ == '__main__':
    a = argparse.ArgumentParser()
    a.add_argument('--root', default=os.environ.get('AGENT_PAGES_ROOT', str(Path(__file__).resolve().parents[1] / 'apps/web')))
    a.add_argument('--state', default=os.environ.get('AGENT_PAGES_STATE', './.state'))
    a.add_argument('--private-port', type=int, default=int(os.environ.get('AGENT_PAGES_PRIVATE_PORT', '9133')))
    a.add_argument('--public-port', type=int, default=int(os.environ.get('AGENT_PAGES_PUBLIC_PORT', '9134')))
    args = a.parse_args()
    servers = serve(args.root,args.state,args.private_port,args.public_port)
    try: threading.Event().wait()
    except KeyboardInterrupt:
        for s in servers: s.shutdown()
