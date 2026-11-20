# -*- coding: utf-8 -*-
"""Synthetic SQLite experiment only; no real authentication or client data."""
import json
import sqlite3
from contextlib import contextmanager

ALLOWED = {'service', 'model', 'quantity', 'delivery_request', 'symptom'}

class CaseUnavailable(Exception):
    pass

class VersionConflict(Exception):
    pass

class DuplicateEvent(Exception):
    pass

@contextmanager
def connection(path):
    db = sqlite3.connect(path, timeout=5, isolation_level=None)
    db.execute('PRAGMA foreign_keys=ON')
    try:
        yield db
    finally:
        db.close()

def initialize(path):
    with connection(path) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, owner TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS facts(case_id TEXT NOT NULL REFERENCES cases(id), key TEXT NOT NULL,
          value TEXT NOT NULL, quote TEXT NOT NULL, PRIMARY KEY(case_id,key));
        CREATE TABLE IF NOT EXISTS events(case_id TEXT NOT NULL REFERENCES cases(id), event_id TEXT NOT NULL,
          version INTEGER NOT NULL, changes TEXT NOT NULL, PRIMARY KEY(case_id,event_id));
        ''')

def create_case(path, case_id, owner):
    with connection(path) as db:
        db.execute('INSERT INTO cases(id,owner) VALUES(?,?)', (case_id,owner))

def read_case(path, actor, case_id):
    with connection(path) as db:
        row=db.execute('SELECT version FROM cases WHERE id=? AND owner=?',(case_id,actor)).fetchone()
        if row is None: raise CaseUnavailable()
        fields=db.execute('SELECT key,value,quote FROM facts WHERE case_id=? ORDER BY key',(case_id,)).fetchall()
        history=db.execute('SELECT event_id,version,changes FROM events WHERE case_id=? ORDER BY version',(case_id,)).fetchall()
        return {'id':case_id,'version':row[0], 'facts':{k:{'value':v,'quote':q} for k,v,q in fields},
                'history':[{'event_id':e,'version':v,'changes':json.loads(c)} for e,v,c in history]}

def save(path, actor, case_id, event_id, expected_version, message, proposed):
    if not isinstance(proposed,dict) or not proposed or not isinstance(message,str): raise ValueError('Invalid update')
    for key,fact in proposed.items():
        if key not in ALLOWED or not isinstance(fact,dict): raise ValueError('Field not allowed')
        value,quote=fact.get('value'),fact.get('quote')
        if not isinstance(value,str) or not value.strip() or not isinstance(quote,str) or not quote.strip() or quote not in message:
            raise ValueError('Evidence missing')
        if value.strip().lower() in {'<unknown>','unknown','неизвестно','не знаю','неизвестна','неизвестен'}:
            raise ValueError('Unknown is not a known fact')
    payload=json.dumps({'message':message,'facts':proposed},ensure_ascii=False,sort_keys=True)
    with connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            row=db.execute('SELECT version FROM cases WHERE id=? AND owner=?',(case_id,actor)).fetchone()
            if row is None: raise CaseUnavailable()
            prior=db.execute('SELECT version,changes FROM events WHERE case_id=? AND event_id=?',(case_id,event_id)).fetchone()
            if prior:
                if prior[1]!=payload: raise DuplicateEvent('Event id reused with different contents')
                db.execute('COMMIT');return {'version':prior[0],'replayed':True}
            if row[0]!=expected_version: raise VersionConflict()
            version=row[0]+1
            for key,fact in proposed.items():
                db.execute('INSERT INTO facts(case_id,key,value,quote) VALUES(?,?,?,?) '
                           'ON CONFLICT(case_id,key) DO UPDATE SET value=excluded.value,quote=excluded.quote',
                           (case_id,key,fact['value'],fact['quote']))
            db.execute('INSERT INTO events(case_id,event_id,version,changes) VALUES(?,?,?,?)',(case_id,event_id,version,payload))
            db.execute('UPDATE cases SET version=? WHERE id=?',(version,case_id))
            db.execute('COMMIT');return {'version':version,'replayed':False}
        except Exception:
            db.execute('ROLLBACK');raise
