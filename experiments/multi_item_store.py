# -*- coding: utf-8 -*-
"""Synthetic-only SQLite review experiment; fake identities, NOT production CRM."""
import json
import sqlite3
from contextlib import contextmanager

FIELDS={'device','model','quantity','symptom','requested_action','delivery_request'}
STATES={'client_reported','needs_clarification','conflicting','employee_confirmed'}

class Conflict(Exception): pass
class Unavailable(Exception): pass
class DuplicateEvent(Exception): pass

@contextmanager
def connect(path):
    db=sqlite3.connect(path,timeout=5,isolation_level=None)
    db.execute('PRAGMA foreign_keys=ON')
    try:yield db
    finally:db.close()

def init(path):
    with connect(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY,owner TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS messages (case_id TEXT NOT NULL REFERENCES cases(id),id TEXT NOT NULL,text TEXT NOT NULL,PRIMARY KEY(case_id,id));
        CREATE TABLE IF NOT EXISTS items (case_id TEXT NOT NULL REFERENCES cases(id),id TEXT NOT NULL,PRIMARY KEY(case_id,id));
        CREATE TABLE IF NOT EXISTS proposals (case_id TEXT NOT NULL REFERENCES cases(id),id TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(case_id,id));
        CREATE TABLE IF NOT EXISTS facts (case_id TEXT NOT NULL,item_id TEXT NOT NULL,key TEXT NOT NULL,value TEXT,state TEXT NOT NULL,message_id TEXT NOT NULL,quote TEXT NOT NULL,
          PRIMARY KEY(case_id,item_id,key),FOREIGN KEY(case_id,item_id) REFERENCES items(case_id,id),FOREIGN KEY(case_id,message_id) REFERENCES messages(case_id,id));
        CREATE TABLE IF NOT EXISTS events (case_id TEXT NOT NULL REFERENCES cases(id),event_id TEXT NOT NULL,version INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(case_id,event_id));
        ''')

def create(path,case_id,owner):
    with connect(path) as db:db.execute('INSERT INTO cases(id,owner) VALUES (?,?)',(case_id,owner))

def check_owner(db,case_id,actor):
    row=db.execute('SELECT version FROM cases WHERE id=? AND owner=?',(case_id,actor)).fetchone()
    if row is None:raise Unavailable()
    return row[0]

def add_message(path,case_id,actor,message_id,text):
    with connect(path) as db:
        check_owner(db,case_id,actor)
        db.execute('INSERT INTO messages(case_id,id,text) VALUES (?,?,?)',(case_id,message_id,text))

def add_item(path,case_id,actor,item_id):
    with connect(path) as db:
        check_owner(db,case_id,actor)
        db.execute('INSERT INTO items(case_id,id) VALUES (?,?)',(case_id,item_id))

def stage_proposal(path,case_id,actor,proposal_id,proposal):
    """Quarantine a synthetic output; deliberately never change facts or execute actions."""
    data=json.dumps(proposal,ensure_ascii=False,sort_keys=True)
    with connect(path) as db:
        check_owner(db,case_id,actor)
        db.execute('INSERT INTO proposals(case_id,id,data) VALUES (?,?,?)',(case_id,proposal_id,data))

def review(path,case_id,actor,reviewer,proposal_id,event_id,expected_version,item_id,key,value,state,message_id,quote):
    """Synthetic manual review. actor and reviewer are fake strings, not authenticated."""
    if reviewer not in {'test_reviewer','test_employee'}:raise ValueError('Test reviewer required')
    if state=='employee_confirmed' and reviewer!='test_employee':raise ValueError('Test employee required')
    if key not in FIELDS or state not in STATES:raise ValueError('Invalid field/state')
    if state in {'needs_clarification','conflicting'}:
        if value is not None:raise ValueError('Unknown must not be a final value')
    elif not isinstance(value,str) or not value.strip():raise ValueError('Value required')
    if not isinstance(quote,str) or not quote.strip():raise ValueError('Quote required')
    payload=json.dumps({'proposal_id':proposal_id,'item_id':item_id,'key':key,'value':value,'state':state,
                        'message_id':message_id,'quote':quote,'reviewer':reviewer},ensure_ascii=False,sort_keys=True)
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            version=check_owner(db,case_id,actor)
            old=db.execute('SELECT version,payload FROM events WHERE case_id=? AND event_id=?',(case_id,event_id)).fetchone()
            if old:
                if old[1]!=payload:raise DuplicateEvent()
                db.execute('COMMIT');return {'version':old[0],'replayed':True}
            if version!=expected_version:raise Conflict()
            if not db.execute('SELECT 1 FROM proposals WHERE case_id=? AND id=?',(case_id,proposal_id)).fetchone():raise ValueError('Proposal not found')
            if not db.execute('SELECT 1 FROM items WHERE case_id=? AND id=?',(case_id,item_id)).fetchone():raise ValueError('Item not found')
            message=db.execute('SELECT text FROM messages WHERE case_id=? AND id=?',(case_id,message_id)).fetchone()
            if not message or quote not in message[0]:raise ValueError('Quote not found')
            new_version=version+1
            db.execute('INSERT INTO facts(case_id,item_id,key,value,state,message_id,quote) VALUES (?,?,?,?,?,?,?) '
                       'ON CONFLICT(case_id,item_id,key) DO UPDATE SET value=excluded.value,state=excluded.state,message_id=excluded.message_id,quote=excluded.quote',
                       (case_id,item_id,key,value,state,message_id,quote))
            db.execute('INSERT INTO events(case_id,event_id,version,payload) VALUES (?,?,?,?)',(case_id,event_id,new_version,payload))
            db.execute('UPDATE cases SET version=? WHERE id=?',(new_version,case_id))
            db.execute('COMMIT');return {'version':new_version,'replayed':False}
        except Exception:
            db.execute('ROLLBACK');raise

def read(path,case_id,actor):
    with connect(path) as db:
        version=check_owner(db,case_id,actor)
        items={r[0]:{} for r in db.execute('SELECT id FROM items WHERE case_id=? ORDER BY id',(case_id,))}
        for item,key,value,state,msg,quote in db.execute('SELECT item_id,key,value,state,message_id,quote FROM facts WHERE case_id=?',(case_id,)):
            items[item][key]={'value':value,'state':state,'message_id':msg,'quote':quote}
        proposals=[{'id':r[0],'data':json.loads(r[1])} for r in db.execute('SELECT id,data FROM proposals WHERE case_id=? ORDER BY id',(case_id,))]
        events=[{'id':r[0],'version':r[1],'payload':json.loads(r[2])} for r in db.execute('SELECT event_id,version,payload FROM events WHERE case_id=? ORDER BY version',(case_id,))]
        return {'version':version,'items':items,'proposals':proposals,'events':events}
