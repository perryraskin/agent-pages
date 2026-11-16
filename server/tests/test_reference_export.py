import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('send_page',Path(__file__).parents[1]/'send_page.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ExportTests(unittest.TestCase):
    def test_snapshot_contains_only_selected_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'src/demo').mkdir(parents=True)
            (root/'build').mkdir(); (root/'build/demo.html').write_text('<html><head></head><body>Selected Page only</body></html>')
            (root/'src/demo/meta.json').write_text(json.dumps({'title':'Demo','secret':'must not export'}))
            doc=m.reference('demo',root)
            self.assertEqual(doc['version'],2)
            self.assertEqual(doc['pageID'],'demo')
            self.assertIn('Selected Page only',doc['html'])
            self.assertNotIn('secret',doc)
            self.assertNotIn('server',doc)
    def test_path_and_url_rejection(self):
        for slug in ['../secret','a/b','https://evil','', 'a?x=1']:
            with self.assertRaises(ValueError):m.reference(slug)
    def test_attachment_filename(self):
        name=m.filename('../"Finance"\r\n/private')
        self.assertTrue(name.endswith('.hermespage'))
        for value in ['/', '\\', '"','\r','\n']:self.assertNotIn(value,name)

if __name__=='__main__':unittest.main()
