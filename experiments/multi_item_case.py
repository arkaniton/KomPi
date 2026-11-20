# -*- coding: utf-8 -*-
"""Synthetic in-memory case model. Not authentication, CRM or production code.

Model output is untrusted: proposal creation never confirms or changes the case.
The caller identifies each source message and manually selects a review state.
"""
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

ALLOWED_FIELDS = {'device', 'model', 'quantity', 'symptom', 'requested_action', 'delivery_request'}
REVIEW_STATES = {'client_reported', 'needs_clarification', 'conflicting', 'employee_confirmed'}

@dataclass(frozen=True)
class Evidence:
    message_id: str
    quote: str

@dataclass(frozen=True)
class Fact:
    field: str
    value: Optional[str]
    state: str
    evidence: Tuple[Evidence, ...]
    reviewer_note: str = ''

@dataclass
class Item:
    item_id: str
    facts: Dict[str, Fact] = field(default_factory=dict)

@dataclass
class Case:
    case_id: str
    messages: Dict[str, str] = field(default_factory=dict)
    items: Dict[str, Item] = field(default_factory=dict)
    history: list = field(default_factory=list)

    def add_message(self, message_id, text):
        if not isinstance(message_id, str) or not message_id or message_id in self.messages:
            raise ValueError('Unique message ID required')
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Non-empty message required')
        self.messages[message_id] = text

    def add_item(self, item_id):
        if not isinstance(item_id, str) or not item_id or item_id in self.items:
            raise ValueError('Unique item ID required')
        self.items[item_id] = Item(item_id)

    def review_fact(self, item_id, key, value, state, evidence, *, reviewer, note=''):
        """Apply an explicitly reviewed synthetic fact; caller role is NOT authenticated."""
        if item_id not in self.items or key not in ALLOWED_FIELDS or state not in REVIEW_STATES:
            raise ValueError('Item, field, or state not allowed')
        if reviewer not in {'test_reviewer', 'test_employee'}:
            raise ValueError('Test reviewer required')
        if state == 'employee_confirmed' and reviewer != 'test_employee':
            raise ValueError('Employee-confirmed requires test employee')
        if not isinstance(note, str):
            raise ValueError('Invalid note')
        if state in {'needs_clarification', 'conflicting'}:
            if value is not None:
                raise ValueError('Uncertain/conflicting facts must not have a final value')
        elif not isinstance(value, str) or not value.strip():
            raise ValueError('Known value required')
        if not isinstance(evidence, (tuple, list)) or not evidence:
            raise ValueError('Evidence is required')
        checked = []
        for entry in evidence:
            if not isinstance(entry, Evidence) or not isinstance(entry.message_id, str) or not isinstance(entry.quote, str) or not entry.quote.strip():
                raise ValueError('Invalid evidence')
            if entry.message_id not in self.messages or entry.quote not in self.messages[entry.message_id]:
                raise ValueError('Quote missing from source message')
            checked.append(entry)
        fact = Fact(key, value, state, tuple(checked), note)
        prior = self.items[item_id].facts.get(key)
        self.items[item_id].facts[key] = fact
        self.history.append({'item_id': item_id, 'field': key, 'before': prior, 'after': fact, 'reviewer': reviewer})
        return fact
