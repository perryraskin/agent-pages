import importlib.util
import json
import shutil
from pathlib import Path
import plistlib
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parents[1]))
import native_support as native
import send_page as sender
import imessage_recovery as recovery


class NativeTests(unittest.TestCase):
    def test_legacy_caption_only_helper_is_not_native_capability(self):
        with patch.object(native,'exchange',return_value={'ok':True,'balloon':True,'protocol':1}):
            self.assertFalse(native.available())

    def test_card_send_requires_confirmed_artwork_transfer(self):
        with patch.object(native,'page_payload',return_value=(b'archive','https://private/page')), \
             patch.object(native,'render_preview',return_value=Path('/test/preview.jpeg')), \
             patch.object(native,'exchange',return_value={'ok':True,'guid':'sent-but-no-artwork'}) as exchange:
            with self.assertRaisesRegex(RuntimeError,'lacks confirmed artwork'):
                native.send_card({'pageID':'fleet-roster-auto','title':'Fleet roster (auto)'},'test-id','owner')
            self.assertEqual(exchange.call_args.kwargs['previewPath'],'/test/preview.jpeg')

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('xcrun') and shutil.which('clang') and Path('/usr/bin/sips').is_file(), 'Requires macOS AppKit, xcrun, clang and sips')
    def test_per_page_preview_contains_different_artwork(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(native,'PREVIEWS',Path(tmp)):
            first=native.render_preview({'title':'Fleet roster (auto)'},'c12b23ce-010d-4cb2-9540-84311f845858')
            second=native.render_preview({'title':'A different Page title'},'cf64395a-c91a-44f0-a0ab-d0c4c0e683ab')
            self.assertTrue(first.read_bytes().startswith(b'\xff\xd8'))
            self.assertNotEqual(first.read_bytes(),second.read_bytes())
            info=subprocess.check_output(['/usr/bin/sips','-g','pixelWidth','-g','pixelHeight',str(first)],text=True)
            self.assertRegex(info, r'pixelWidth: (600|1200)');self.assertRegex(info, r'pixelHeight: (300|600)')

    def test_preview_rejects_symlink_staging_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            real=Path(tmp)/'real';real.mkdir()
            link=Path(tmp)/'link';link.symlink_to(real,target_is_directory=True)
            with patch.object(native,'PREVIEWS',link),self.assertRaisesRegex(ValueError,'Unsafe'):
                native.render_preview({'title':'Private'},'6fc4a0aa-97a8-4416-a645-81bff54ed1b7')

    def test_uid_preserving_rewrite(self):
        archive = {'$archiver':'NSKeyedArchiver', '$objects':[
            '$null', {'ref':plistlib.UID(4)},
            'https://pages.example.invalid/v1/pages/old/content?hermesPage=old',
            'Old', 'Hermes Page: Old', {'NS.uuidbytes': bytes(16)}]}
        data,url = native.page_payload({'pageID':'new-page','title':'New title'},archive)
        result = plistlib.loads(data)
        self.assertEqual(result['$objects'][1]['ref'],plistlib.UID(4))
        self.assertEqual(result['$objects'][3:5],['New title','Hermes Page: New title'])
        self.assertNotEqual(result['$objects'][5]['NS.uuidbytes'],bytes(16))
        self.assertIn('hermesPage=new-page',url)
        self.assertEqual(archive['$objects'][3],'Old')

    def test_private_api_alone_is_not_card_capability(self):
        with patch.object(sender,'bridge',return_value={'data':{'private_api':True,'helper_connected':True}}), patch.object(native,'available',return_value=False):
            self.assertFalse(sender.card_capability({}))

    def test_explicit_card_never_falls_through_to_file(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(sender,'card_capability',return_value=False):
            env = Path(tmp)/'.env'
            env.write_text('BLUEBUBBLES_SERVER_URL=http://127.0.0.1:1234\nBLUEBUBBLES_HOME_CHANNEL=+15550000001')
            with patch.object(sender,'bridge') as bridge:
                with patch.object(sender,'ENV',env), self.assertRaisesRegex(RuntimeError,'no file or link'):
                    sender.send({'pageID':'test','title':'Test'},'00000000-0000-4000-8000-000000000001',transport='card')
                bridge.assert_not_called()

    def test_timed_out_request_cannot_execute_later_or_repeat(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(native,'IPC',Path(tmp)):
            identity='00000000-0000-4000-8000-000000000002'
            with self.assertRaisesRegex(RuntimeError,'timed out'):
                native.exchange('send',request_id=identity,timeout=0)
            self.assertFalse((Path(tmp)/(identity+'.request.json')).exists())
            self.assertTrue((Path(tmp)/(identity+'.expired')).exists())
            with self.assertRaisesRegex(RuntimeError,'already used'):
                native.exchange('send',request_id=identity,timeout=0)

    def test_auto_checks_capability_once_and_never_falls_to_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env=Path(tmp)/'.env'
            env.write_text('BLUEBUBBLES_SERVER_URL=http://127.0.0.1:1234\nBLUEBUBBLES_HOME_CHANNEL=+15550000001')
            with patch.object(sender,'ENV',env),patch.object(sender,'STATE',Path(tmp)/'delivery'), \
                 patch.object(sender,'card_capability',side_effect=[False,True]) as capability, \
                 patch.object(sender,'send_link',return_value={'transport':'link-card'}) as link, \
                 patch.object(sender,'bridge') as bridge,patch('builtins.print'):
                sender.send({'pageID':'test','title':'Test'},'00000000-0000-4000-8000-000000000003')
                self.assertEqual(capability.call_count,1);link.assert_called_once();bridge.assert_not_called()

    def test_auto_recovery_runs_at_most_once_per_boot(self):
        current={'osBuild':'test','sipDisabled':True,'libraryValidationConfigured':True,
                 'privateAPI':True,'bluebubblesHelper':True,'nativePageHelper':True}
        with tempfile.TemporaryDirectory() as tmp, patch.object(recovery,'STATE',Path(tmp)), \
             patch.object(recovery,'RECOVERY',Path(tmp)/'state.json'), \
             patch.object(recovery,'status',return_value=current.copy()), \
             patch.object(recovery,'run',return_value=(0,'same-boot')), \
             patch.object(recovery,'apply',return_value={**current,'state':'ready'}) as apply, \
             patch.object(sys,'argv',['recovery','--auto']), patch('builtins.print'):
            recovery.main(); recovery.main()
            self.assertEqual(apply.call_count,1)

    def test_health_check_preserves_boot_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp)/'state.json';state.write_text('{"attemptBoot":"guard"}')
            with patch.object(recovery,'STATE',Path(tmp)),patch.object(recovery,'RECOVERY',state), \
                 patch.object(recovery,'status',return_value={}),patch.object(sys,'argv',['recovery']),patch('builtins.print'):
                recovery.main()
            self.assertEqual(json.loads(state.read_text())['attemptBoot'],'guard')

    def test_sip_never_changed_by_recovery(self):
        with patch.object(recovery,'run') as run, patch.object(recovery,'refresh_profile') as refresh:
            result = recovery.apply({'sipDisabled':False})
            self.assertEqual(result['state'],'needs-manual-sip')
            run.assert_not_called();refresh.assert_not_called()

    def test_security_setting_not_changed(self):
        with patch.object(recovery,'run') as run:
            result = recovery.apply({'sipDisabled':True,'libraryValidationConfigured':False})
            self.assertEqual(result['state'],'needs-manual-library-validation')
            run.assert_not_called()

    def test_active_profile_is_not_restarted(self):
        with patch.object(recovery,'control',return_value={'active_agents':1,'active_work':[{}]}) as control:
            with self.assertRaisesRegex(RuntimeError,'active work'):recovery.refresh_profile()
            self.assertEqual(control.call_count,1)

class DeliveryConfirmationTests(unittest.TestCase):
    def test_send_guid_is_uppercase_so_receipts_match(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(native,'IPC',Path(tmp)):
            Path(tmp).chmod(0o700)
            identity='0000000a-0000-4000-8000-00000000000b'
            with self.assertRaisesRegex(RuntimeError,'timed out'):
                native.exchange('send',request_id=identity,timeout=0)
            self.assertEqual([p.name for p in Path(tmp).iterdir()],[identity.upper()+'.expired'])
            self.assertEqual(native.message_guid(identity),identity.upper())

    def _db(self,tmp,**row):
        import sqlite3
        db=Path(tmp)/'chat.db'
        with sqlite3.connect(db) as c:
            c.execute('CREATE TABLE message (ROWID INTEGER PRIMARY KEY, guid TEXT UNIQUE, is_from_me INT, is_delivered INT, date_delivered INT, error INT)')
            c.execute('INSERT INTO message (guid,is_from_me,is_delivered,date_delivered,error) VALUES (?,?,?,?,?)',
                      (row['guid'],1,row.get('d',0),row.get('dd',0),row.get('e',0)))
        return db

    def test_delivery_state_true_false_none(self):
        g='AAAAAAAA-0000-4000-8000-000000000001'
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIs(native.delivery_state(g,wait=0,db=self._db(tmp,guid=g,d=1,dd=5)),True)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIs(native.delivery_state(g,wait=0,db=self._db(tmp,guid=g,e=22)),False)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(native.delivery_state(g,wait=0,db=self._db(tmp,guid=g.lower())))
        self.assertIsNone(native.delivery_state(g,wait=0,db='/nonexistent/chat.db'))
        self.assertIsNone(native.delivery_state(None,wait=0))

    def test_card_result_carries_delivered_without_resend(self):
        with tempfile.TemporaryDirectory() as tmp:
            env=Path(tmp)/'.env'
            env.write_text('BLUEBUBBLES_SERVER_URL=http://127.0.0.1:1234\nBLUEBUBBLES_HOME_CHANNEL=+15550000001')
            sent={'status':'sent','transport':'native-card','pageID':'test','guid':'G'}
            with patch.object(sender,'ENV',env),patch.object(sender,'STATE',Path(tmp)/'delivery'), \
                 patch.object(sender,'card_capability',return_value=True), \
                 patch.object(native,'send_card',return_value=dict(sent)) as card, \
                 patch.object(native,'delivery_state',side_effect=RuntimeError('db')), \
                 patch.object(sender,'send_link') as link,patch('builtins.print') as out:
                sender.send({'pageID':'test','title':'Test'},'00000000-0000-4000-8000-000000000009')
            card.assert_called_once();link.assert_not_called()
            result=json.loads(out.call_args.args[0])
            self.assertEqual(result['status'],'sent');self.assertIn('delivered',result);self.assertIsNone(result['delivered'])


class BridgeDeliveryFallbackTests(unittest.TestCase):
    """The launchd gateway has no Full Disk Access, so chat.db is unreadable from send_page.py;
    delivery state then comes from BlueBubbles' read-only message record."""
    G='FDD4CF72-0000-4000-8000-000000000001'
    MISSING='/nonexistent/hermes-test/chat.db'
    ENV={'BLUEBUBBLES_SERVER_URL':'http://127.0.0.1:1234','BLUEBUBBLES_PASSWORD':'test-secret'}

    def _state(self, data, wait=0):
        import io, contextlib
        err=io.StringIO()
        with patch.object(native,'CHAT_DB',Path(self.MISSING)), \
             patch.object(sender,'bridge',return_value={'status':200,'data':data}) as bridge, \
             contextlib.redirect_stderr(err):
            state=sender.delivered(self.G,dict(self.ENV)) if wait is None else \
                native.delivery_state(self.G,wait=wait,db=self.MISSING,
                    fallback=lambda g,d: sender.bridge_message(dict(self.ENV),g,d))
        return state,bridge,err.getvalue()

    def test_unreadable_db_uses_bridge_true_false_none(self):
        state,bridge,err=self._state({'isFromMe':True,'isDelivered':True,'dateDelivered':1794505521497,'error':0})
        self.assertIs(state,True); bridge.assert_called()
        self.assertEqual(bridge.call_args.args[1],'/api/v1/message/'+self.G)
        self.assertEqual(err.strip(),native.CHAT_DB_UNREADABLE)
        self.assertNotIn('test-secret',err); self.assertNotIn('127.0.0.1',err)
        self.assertIs(self._state({'isFromMe':True,'isDelivered':False,'dateDelivered':1794505521497,'error':0})[0],True)
        self.assertIs(self._state({'isFromMe':True,'isDelivered':False,'dateDelivered':None,'error':22})[0],False)
        self.assertIsNone(self._state({'isFromMe':True,'isDelivered':False,'dateDelivered':None,'error':0})[0])
        self.assertIsNone(self._state({'isFromMe':False,'isDelivered':True,'dateDelivered':1})[0])

    def test_wrapper_wires_bridge_from_env(self):
        state,bridge,_=self._state({'isFromMe':True,'isDelivered':True,'dateDelivered':5},wait=None)
        self.assertIs(state,True); bridge.assert_called()

    def test_bridge_lookup_tries_other_case_after_404(self):
        import urllib.error, time
        g='7ae7ef74-6b2e-4a09-99cd-581a776eb012'
        def fake(env,path,timeout=45):
            if path.endswith(g): return {'status':200,'data':{'isFromMe':True,'dateDelivered':7}}
            raise urllib.error.HTTPError('http://x',404,'nf',{},None)
        with patch.object(sender,'bridge',side_effect=fake) as bridge:
            data=sender.bridge_message({}, g.upper(), time.monotonic()+5)
        self.assertEqual(data['dateDelivered'],7)
        self.assertEqual([c.args[1].rsplit('/',1)[1] for c in bridge.call_args_list],[g.upper(),g])

    def test_readable_db_never_calls_bridge(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'chat.db'
            with sqlite3.connect(db) as c:
                c.execute('CREATE TABLE message (ROWID INTEGER PRIMARY KEY, guid TEXT UNIQUE, is_from_me INT, is_delivered INT, date_delivered INT, error INT)')
                c.execute('INSERT INTO message (guid,is_from_me,is_delivered,date_delivered,error) VALUES (?,?,?,?,?)',(self.G,1,0,0,0))
            fallback=unittest.mock.Mock()
            self.assertIsNone(native.delivery_state(self.G,wait=0.3,db=db,fallback=fallback))
            fallback.assert_not_called()
            with sqlite3.connect(db) as c: c.execute('UPDATE message SET is_delivered=1')
            self.assertIs(native.delivery_state(self.G,wait=0,db=db,fallback=fallback),True)
            fallback.assert_not_called()

    def test_total_wait_bounded_and_nothing_raised_when_both_fail(self):
        import time, io, contextlib
        def slow_fail(env,path,timeout=45):
            time.sleep(min(timeout,0.3)); raise OSError('bridge down')
        with patch.object(sender,'bridge',side_effect=slow_fail), contextlib.redirect_stderr(io.StringIO()) as err:
            start=time.monotonic()
            state=native.delivery_state(self.G,wait=1.0,db=self.MISSING,
                fallback=lambda g,d: sender.bridge_message(dict(self.ENV),g,d))
            elapsed=time.monotonic()-start
        self.assertIsNone(state); self.assertLess(elapsed,1.6)
        self.assertEqual(err.getvalue().count('chat.db unreadable'),1)
        with patch.object(native,'bridge_delivery',side_effect=RuntimeError('x')), contextlib.redirect_stderr(io.StringIO()):
            self.assertIsNone(native.delivery_state(self.G,wait=0,db=self.MISSING,fallback=lambda g,d:{}))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertIsNone(native.delivery_state(self.G,wait=0,db=self.MISSING,fallback=lambda g,d:1/0))
        with patch.object(native,'delivery_state',side_effect=RuntimeError('x')):
            self.assertIsNone(sender.delivered(self.G,dict(self.ENV)))

    def test_unreadable_db_without_bridge_returns_at_once(self):
        import time
        start=time.monotonic()
        self.assertIsNone(native.delivery_state(self.G,wait=5,db=self.MISSING))
        self.assertLess(time.monotonic()-start,1)


if __name__=='__main__':unittest.main()
