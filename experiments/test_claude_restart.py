# -*- coding: utf-8 -*-
"""Paid, synthetic-only experiment; creates and destroys a temporary SQLite DB."""
import json, os, subprocess, sys, tempfile
from pathlib import Path
import synthetic_store as store

HERE=Path(__file__).resolve().parent

def worker(path,step):
    import test_case_memory as ai
    if step=='first':
        current=store.read_case(path,'client-a','case-a')
        message='Хочу заправить два картриджа TestCart T-100. Принесу сам.'
        event='message-1'
    else:
        current=store.read_case(path,'client-a','case-a')
        message='Поправка: картридж только один, а не два.'
        event='message-2'
    proposals=ai.propose(message,current['facts'])
    facts,rejected=ai.filter_proposals(message,proposals)
    if not facts: raise ValueError('No valid facts proposed')
    result=store.save(path,'client-a','case-a',event,current['version'],message,facts)
    print(json.dumps({'step':step,'usage':ai.usage,'accepted':facts,'rejected':rejected,'save':result},ensure_ascii=False))

def main():
    if len(sys.argv)>1:
        worker(sys.argv[2],sys.argv[1]);return
    if not os.environ.get('ANTHROPIC_API_KEY'):sys.exit('Set ANTHROPIC_API_KEY outside repository')
    with tempfile.TemporaryDirectory(prefix='kompi-live-restart-') as tmp:
        db=str(Path(tmp)/'synthetic.sqlite3');store.initialize(db);store.create_case(db,'case-a','client-a')
        runs=[]
        for step in ('first','second'):
            proc=subprocess.run([sys.executable,str(Path(__file__).resolve()),step,db],capture_output=True,text=True,env=os.environ.copy(),cwd=str(HERE))
            if proc.returncode: print(json.dumps({'step':step,'error':'worker failed','code':proc.returncode}));sys.exit(1)
            runs.append(json.loads(proc.stdout))
        case=store.read_case(db,'client-a','case-a')
        result={'runs':runs,'case':case,'checks':{
          'two_processes_saved_separately':case['version']==2,
          'corrected_quantity':case['facts'].get('quantity',{}).get('value')=='1',
          'preserved_model':case['facts'].get('model',{}).get('value')=='TestCart T-100',
          'history_has_both_events':len(case['history'])==2},
          'warning':'Temporary synthetic database; actor identity is only a test string, not authentication.'}
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if not all(result['checks'].values()):sys.exit(2)
if __name__=='__main__':main()
