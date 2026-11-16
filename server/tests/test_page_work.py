import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import page_work as pw

T0 = dt.datetime(2026, 11, 13, 15, 0, tzinfo=dt.timezone.utc)


class RecordTest(unittest.TestCase):
    def test_lease_and_stalled(self):
        rec = pw.new_record(None, 'working', note='Backing up', by='Aster', lease_minutes=10, now=T0)
        self.assertEqual(rec['stale_after'], '2026-11-13T15:10:00Z')
        self.assertEqual(pw.derived_state(rec, T0 + dt.timedelta(minutes=9)), 'working')
        self.assertEqual(pw.derived_state(rec, T0 + dt.timedelta(minutes=11)), 'stalled')
        self.assertEqual(pw.public(rec, T0 + dt.timedelta(minutes=40))['state'], 'stalled')

    def test_heartbeat_keeps_since_and_note_state_change_clears_note(self):
        a = pw.new_record(None, 'working', note='14 of 30', by='Aster', now=T0)
        b = pw.new_record(a, 'working', now=T0 + dt.timedelta(minutes=5))
        self.assertEqual((b['since'], b['note'], b['by']), (a['since'], '14 of 30', 'Aster'))
        self.assertEqual(b['updated'], '2026-11-13T15:05:00Z')
        c = pw.new_record(b, 'done', now=T0 + dt.timedelta(minutes=6))
        self.assertEqual(c['note'], '')
        self.assertNotIn('stale_after', c)
        self.assertEqual(pw.derived_state(c, T0 + dt.timedelta(days=3)), 'done')
        self.assertEqual(pw.new_record(c, 'done', note='')['note'], '')

    def test_needs_input_never_stalls(self):
        rec = pw.new_record(None, 'needs_input', note='Need your OK', now=T0)
        self.assertEqual(pw.derived_state(rec, T0 + dt.timedelta(days=1)), 'needs_input')

    def test_validation(self):
        for bad in ({'state': 'paused'}, {'state': 'working', 'lease_minutes': 0.5}, {'state': 'working', 'lease_minutes': 99999}):
            with self.assertRaises((ValueError, TypeError)):
                pw.new_record(None, bad['state'], lease_minutes=bad.get('lease_minutes'))
        with self.assertRaises(ValueError):
            pw.normalize_sections(['ok', ''])
        with self.assertRaises(ValueError):
            pw.normalize_sections([{'label': 'x', 'state': 'maybe'}])

    def test_sections_forms(self):
        self.assertEqual(pw.normalize_sections(['Inventory=done', 'a=b', {'label': 'Summary', 'done': True}, {'title': 'X', 'state': 'Working'}]),
                         [{'label': 'Inventory', 'state': 'done'}, {'label': 'a=b', 'state': 'pending'},
                          {'label': 'Summary', 'state': 'done'}, {'label': 'X', 'state': 'working'}])

    def test_legacy_page_reads_as_done(self):
        self.assertEqual(pw.public(None), {'state': 'done'})

    def test_status_comment_round_trip(self):
        tsx = 'export default function X() { return null; }\n'
        rec = pw.new_record(None, 'working', note='*/ sneaky', now=T0)
        shown = pw.status_comment(rec) + tsx
        self.assertTrue(shown.startswith('/* hermes-page-status: {"state": "'))
        self.assertEqual(pw.strip_status_comment(shown), tsx)
        self.assertEqual(pw.strip_status_comment(pw.status_comment(rec) + shown), tsx)


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        d = self.root / 'src' / 'demo'
        d.mkdir(parents=True)
        (d / 'page.tsx').write_text('export default function X(){return null}')
        (d / 'meta.json').write_text(json.dumps({'title': 'Demo', 'tags': ['demo']}))
        (self.root / 'build').mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_block_escapes_and_sync_patches_without_rebuild(self):
        r = pw.rev(self.root, 'demo')
        raw = '<html><body>' + pw.block('demo', r, None) + '<div id="root">CONTENT</div><script>bundle()</script></body></html>'
        self.assertIn(' hidden>', raw)  # legacy Page: nothing visible
        (self.root / 'build' / 'demo.html').write_text(raw)
        rec = pw.new_record(None, 'working', note='<b>14</b> & "30"', by='Aster', sections=['Inventory=done', 'Backups'])
        pw.save(self.root, 'demo', rec)
        self.assertTrue(pw.sync(self.root, 'demo'))
        out = (self.root / 'build' / 'demo.html').read_text()
        self.assertEqual(out.count(pw.START), 1)
        self.assertIn('Being worked on', out)
        self.assertIn('&lt;b&gt;14&lt;/b&gt; &amp; &quot;30&quot;', out)
        self.assertNotIn('<b>14</b>', out)
        self.assertIn('<div id="root">CONTENT</div><script>bundle()</script>', out)
        self.assertEqual(pw.html_rev(out), r)
        pulse = json.loads((self.root / 'build' / 'live' / 'demo.json').read_text())
        self.assertEqual((pulse['rev'], pulse['work']['state']), (r, 'working'))

    def test_rev_follows_source(self):
        a = pw.rev(self.root, 'demo')
        (self.root / 'src' / 'demo' / 'page.tsx').write_text('export default function X(){return 1}')
        self.assertNotEqual(a, pw.rev(self.root, 'demo'))

    def test_edit_history_preserved_on_status_only_save(self):
        old = pw.block('demo', 'aaa', None) + '<div id="root">before</div>'
        new = pw.block('demo', 'bbb', None) + '<div id="root">after</div>'
        pw.record_edit(self.root, 'demo', old, new, 'Aster')
        previous = self.root / 'build/live/demo.prev.html'
        self.assertEqual(previous.read_text(), old)
        edit = json.loads(pw.edit_file(self.root, 'demo').read_text())
        self.assertEqual((edit['prev_rev'], edit['rev'], edit['by']), ('aaa', 'bbb', 'Aster'))
        pw.record_edit(self.root, 'demo', new, new, 'Other')
        self.assertEqual(previous.read_text(), old)
        self.assertEqual(json.loads(pw.edit_file(self.root, 'demo').read_text()), edit)
