# -*- coding: utf-8 -*-
"""Deterministic synthetic tests, including a real process restart."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import synthetic_store as store

class SyntheticStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='kompi-store-')
        self.db=str(Path(self.tmp.name)/'synthetic.sqlite3')
        store.initialize(self.db)
        store.create_case(self.db,'case-a','client-a')
        store.create_case(self.db,'case-b','client-b')
    def tearDown(self): self.tmp.cleanup()
    def test_persists_across_fresh_processes_and_keeps_history(self):
        msg='Заправить два картриджа TestCart T-100.'
        facts={'quantity':{'value':'2','quote':'два картриджа'},'model':{'value':'TestCart T-100','quote':'TestCart T-100'}}
        store.save(self.db,'client-a','case-a','evt-1',0,msg,facts)
        cmd=[sys.executable,'-c','import json,sys; import synthetic_store as s; print(json.dumps(s.read_case(sys.argv[1],"client-a","case-a")))',self.db]
        fresh=json.loads(subprocess.check_output(cmd,cwd=str(Path(__file__).parent),text=True))
        self.assertEqual(fresh['facts']['quantity']['value'],'2')
        store.save(self.db,'client-a','case-a','evt-2',fresh['version'],'Поправка: один картридж.',{'quantity':{'value':'1','quote':'один картридж'}})
        updated=json.loads(subprocess.check_output(cmd,cwd=str(Path(__file__).parent),text=True))
        self.assertEqual(updated['facts']['quantity']['value'],'1')
        self.assertEqual(updated['facts']['model']['value'],'TestCart T-100')
        self.assertEqual([e['changes']['facts']['quantity']['value'] for e in updated['history']],['2','1'])
    def test_isolation_for_mock_actor(self):
        with self.assertRaises(store.CaseUnavailable): store.read_case(self.db,'client-b','case-a')
        with self.assertRaises(store.CaseUnavailable): store.save(self.db,'client-b','case-a','evt',0,'один',{'quantity':{'value':'1','quote':'один'}})
    def test_unapproved_company_price_rejected_atomically(self):
        data={'quantity':{'value':'1','quote':'один'},'company_price':{'value':'0','quote':'бесплатно'}}
        with self.assertRaises(ValueError):store.save(self.db,'client-a','case-a','evt',0,'один бесплатно',data)
        self.assertEqual(store.read_case(self.db,'client-a','case-a')['facts'],{})
    def test_nonexistent_evidence_and_unknown_are_rejected(self):
        with self.assertRaises(ValueError):store.save(self.db,'client-a','case-a','evt',0,'модель неизвестна',{'model':{'value':'T-100','quote':'T-100'}})
        with self.assertRaises(ValueError):store.save(self.db,'client-a','case-a','evt',0,'модель неизвестна',{'model':{'value':'<UNKNOWN>','quote':'модель неизвестна'}})
    def test_prevents_lost_update(self):
        store.save(self.db,'client-a','case-a','evt-1',0,'один',{'quantity':{'value':'1','quote':'один'}})
        with self.assertRaises(store.VersionConflict):store.save(self.db,'client-a','case-a','evt-2',0,'два',{'quantity':{'value':'2','quote':'два'}})
        self.assertEqual(store.read_case(self.db,'client-a','case-a')['facts']['quantity']['value'],'1')
    def test_duplicate_event_is_idempotent_and_mismatch_rejected(self):
        facts={'quantity':{'value':'1','quote':'один'}}
        self.assertFalse(store.save(self.db,'client-a','case-a','evt',0,'один',facts)['replayed'])
        self.assertTrue(store.save(self.db,'client-a','case-a','evt',0,'один',facts)['replayed'])
        with self.assertRaises(store.DuplicateEvent):store.save(self.db,'client-a','case-a','evt',1,'два',{'quantity':{'value':'2','quote':'два'}})
        self.assertEqual(len(store.read_case(self.db,'client-a','case-a')['history']),1)

if __name__=='__main__': unittest.main(verbosity=2)
