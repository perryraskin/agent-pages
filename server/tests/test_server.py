import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location('server', Path(__file__).parents[1] / 'server.py')
s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root/'src/demo').mkdir(parents=True); (root/'build').mkdir()
        (root/'src/demo/meta.json').write_text(json.dumps({'title':'Demo','updated_at':'2026-11-11T12:00:00Z'}))
        (root/'build/demo.html').write_text('<html><head><title>Secret title</title><meta property="og:image" content="https://private/image"></head><body><h1>Frozen</h1><script>fetch("secret")</script><img src="https://tracker/pixel" onerror="alert(1)"></body></html>')
        self.servers = s.serve(root,root/'state',0,0)
        self.private, self.public = ['http://127.0.0.1:'+str(x.server_port) for x in self.servers]
        self.store = self.servers[0].store
        (self.store.state/'public-url.txt').write_text('https://share.example')
    def tearDown(self):
        for server in self.servers: server.shutdown(); server.server_close()
        self.tmp.cleanup()
    def request(self, base, path, data=None, headers=None):
        req = Request(base+path, data=json.dumps(data).encode() if data is not None else None, headers=headers or {})
        try:
            with urlopen(req) as r: return r.status,r.read(),r.headers
        except HTTPError as e: return e.code,e.read(),e.headers
    def test_reader_tags_are_visible_and_refresh_after_retag(self):
        m = self.store.root / 'src/demo/meta.json'
        meta = json.loads(m.read_text()); meta['tags'] = ['seo', 'mjml']; m.write_text(json.dumps(meta))
        _, body, _ = self.request(self.private, '/v1/pages/demo/content')
        self.assertIn(b'aria-label="Page tags"', body)
        self.assertIn(b'<span>seo</span>', body)
        meta['tags'] = ['finance']; m.write_text(json.dumps(meta))
        _, body, _ = self.request(self.private, '/v1/pages/demo/content')
        self.assertIn(b'<span>finance</span>', body)
        self.assertNotIn(b'<span>seo</span>', body)
        snapshot = self.create()
        _, body, _ = self.request(self.public, '/s/' + snapshot['url'].split('/')[-1])
        self.assertIn(b'<span>finance</span>', body)

    def test_tag_discovery_is_private(self):
        m = self.store.root / 'src/demo/meta.json'
        meta = json.loads(m.read_text()); meta['tags'] = ['seo', 'mjml']; m.write_text(json.dumps(meta))
        status, body, _ = self.request(self.private, '/v1/pages?q=demo&tag=seo&tag=mjml')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['pages'][0]['tags'], ['mjml', 'seo'])
        _, body, _ = self.request(self.private, '/v1/pages?tags=seo,finance')
        self.assertEqual(json.loads(body)['pages'], [])
        _, body, _ = self.request(self.private, '/v1/tags')
        self.assertEqual(json.loads(body)['tags'], {'mjml': 1, 'seo': 1})
        for path in ('/v1/tags','/v1/pages?tag=seo'):
            self.assertEqual(self.request(self.public, path)[0], 404)

    def test_work_status_and_live_pulse(self):
        root = self.store.root
        _, body, _ = self.request(self.private, '/v1/pages')
        self.assertEqual(json.loads(body)['pages'][0]['status'], {'state': 'done'})
        self.assertEqual(self.request(self.private, '/v1/pages/demo/live')[0], 404)
        (root/'src/demo/work.json').write_text(json.dumps({'state': 'working', 'by': 'Larry', 'note': '14 of 30',
            'updated': '2026-11-13T15:00:00Z', 'stale_after': '2999-01-01T00:00:00Z'}))
        (root/'build/live').mkdir()
        (root/'build/live/demo.json').write_text(json.dumps({'slug': 'demo', 'rev': 'abc', 'work': {'state': 'working'}}))
        _, body, _ = self.request(self.private, '/v1/pages?q=demo')
        status = json.loads(body)['pages'][0]['status']
        self.assertEqual((status['state'], status['note']), ('working', '14 of 30'))
        code, body, headers = self.request(self.private, '/v1/pages/demo/live')
        self.assertEqual((code, json.loads(body)['rev'], headers['Cache-Control']), (200, 'abc', 'no-store'))
        for path in ('/v1/pages/demo/live', '/v1/pages/..%2fdemo/live'):
            self.assertEqual(self.request(self.public, path)[0], 404)
        self.assertEqual(self.request(self.private, '/v1/pages/..%2f..%2fx/live')[0], 404)
        self.assertEqual(self.request(self.private, '/v1/pages/demo/previous')[0], 404)
        (root/'build/live/demo.prev.html').write_text('<div id="root">older</div>')
        code, body, _ = self.request(self.private, '/v1/pages/demo/previous')
        self.assertEqual((code, body), (200, b'<div id="root">older</div>'))
        self.assertEqual(self.request(self.public, '/v1/pages/demo/previous')[0], 404)
        self.assertEqual(self.request(self.private, '/v1/pages/..%2fx/previous')[0], 404)

    def create(self):
        status,body,_=self.request(self.private,'/v1/shares',{'slug':'demo','days':7},{'X-Hermes-Client':'ios'})
        self.assertEqual(status,201)
        return json.loads(body)
    def test_library_private_only(self):
        self.assertEqual(self.request(self.private,'/v1/pages')[0],200)
        for path in ['/v1/pages','/v1/shares','/v1/pages/demo/content','/s/../v1/pages','/s/%2e%2e%2fv1%2fpages']:
            self.assertEqual(self.request(self.public,path)[0],404)
    def test_create_snapshot_revoke(self):
        share=self.create(); path='/s/'+share['url'].split('/s/')[1]
        status,body,headers=self.request(self.public,path)
        self.assertEqual(status,200); self.assertIn(b'Frozen',body)
        self.assertNotIn(b'<script',body); self.assertNotIn(b'onerror',body); self.assertNotIn(b'private/image',body)
        self.assertIn("default-src 'none'",headers['Content-Security-Policy'])
        (self.store.root/'build/demo.html').write_text('Changed')
        self.assertIn(b'Frozen',self.request(self.public,path)[1])
        self.assertEqual(self.request(self.private,'/v1/shares/'+share['id']+'/revoke',{}, {'X-Hermes-Client':'ios'})[0],200)
        self.assertEqual(self.request(self.public,path)[0],410)
    def test_expiration(self):
        share=self.create(); path='/s/'+share['url'].split('/s/')[1]
        with self.store.connect() as c: c.execute('UPDATE shares SET expires=?',(time.time()-1,))
        self.assertEqual(self.request(self.public,path)[0],410)
    def test_csrf_and_invalid_slug(self):
        self.assertEqual(self.request(self.private,'/v1/shares',{'slug':'demo'})[0],403)
        self.assertEqual(self.request(self.private,'/v1/shares',{'slug':'demo'}, {'X-Hermes-Client':'ios','Origin':'https://evil'})[0],403)
        for slug in ['../secret','demo/../../secret','%2fsecret','']:
            self.assertEqual(self.request(self.private,'/v1/shares',{'slug':slug}, {'X-Hermes-Client':'ios'})[0],400)
        self.assertEqual(self.request(self.public,'/v1/shares',{}, {'X-Hermes-Client':'ios'})[0],404)
    def test_token_hash_only(self):
        share=self.create(); token=share['url'].split('/s/')[1]
        self.assertNotIn(token,json.dumps(self.store.shares()))
        with self.store.connect() as c:
            row=c.execute('select token_hash from shares').fetchone()
        self.assertNotEqual(token,row[0])
    def test_unknown_token(self): self.assertEqual(self.request(self.public,'/s/'+'a'*43)[0],404)

if __name__=='__main__': unittest.main()
