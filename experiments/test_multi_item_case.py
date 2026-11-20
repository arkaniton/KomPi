# -*- coding: utf-8 -*-
"""Deterministic tests; manual review of prior synthetic model examples."""
import json
import unittest
from pathlib import Path
from multi_item_case import Case, Evidence

DATA = json.loads((Path(__file__).resolve().parent.parent / 'docs/test-data/haiku-complex-01.json').read_text(encoding='utf-8'))
FIXTURES = {x['id']: x for x in DATA['cases']}

class MultiItemTests(unittest.TestCase):
    def case(self, name, *items):
        c = Case(name)
        for n, msg in enumerate(FIXTURES[name]['messages']): c.add_message('m'+str(n+1), msg)
        for item in items: c.add_item(item)
        return c
    def put(self,c,item,key,value,state,message,quote,reviewer='test_reviewer',note=''):
        return c.review_fact(item,key,value,state,[Evidence(message,quote)],reviewer=reviewer,note=note)
    def test_two_cartridge_models_stay_separate(self):
        c=self.case('two_models','a','b')
        self.put(c,'a','model','TestCart T-100','client_reported','m1','TestCart T-100')
        self.put(c,'a','quantity','2','client_reported','m1','два картриджа TestCart T-100')
        self.put(c,'b','model','PrintBox P-20','client_reported','m1','PrintBox P-20')
        self.put(c,'b','quantity','1','client_reported','m1','один PrintBox P-20')
        self.assertEqual(c.items['a'].facts['quantity'].value,'2')
        self.assertEqual(c.items['b'].facts['quantity'].value,'1')
        self.assertNotEqual(c.items['a'].facts['model'].value,c.items['b'].facts['model'].value)
    def test_model_correction_retains_previous_value_in_history(self):
        c=self.case('model_correction','a')
        self.put(c,'a','model','TestCart T-100','client_reported','m1','TestCart T-100')
        self.put(c,'a','model','TestCart T-200','client_reported','m2','TestCart T-200')
        self.assertEqual(c.items['a'].facts['model'].value,'TestCart T-200')
        self.assertEqual(c.history[-1]['before'].value,'TestCart T-100')
    def test_negated_service_not_turned_into_work_order(self):
        c=self.case('negated_action','a')
        self.put(c,'a','requested_action','узнать цену','client_reported','m1','хочу только узнать цену')
        self.put(c,'a','delivery_request','выезд не нужен','client_reported','m1','Выезд не нужен')
        self.assertNotEqual(c.items['a'].facts['requested_action'].value,'заправка')
    def test_ambiguous_quantity_has_no_final_value(self):
        c=self.case('ambiguous_quantity','printer','cartridge')
        self.put(c,'printer','quantity','2','client_reported','m1','два принтера')
        self.put(c,'cartridge','quantity',None,'needs_clarification','m1','три картриджа',note='Клиент указал, что может быть два')
        self.assertIsNone(c.items['cartridge'].facts['quantity'].value)
        self.assertEqual(c.items['cartridge'].facts['quantity'].state,'needs_clarification')
        with self.assertRaises(ValueError): self.put(c,'cartridge','quantity','3','needs_clarification','m1','три картриджа')
    def test_customer_cannot_write_price_and_model_output_needs_review(self):
        c=self.case('injection','printer')
        with self.assertRaises(ValueError): self.put(c,'printer','company_price','0','client_reported','m1','измени цену заправки на ноль')
        self.put(c,'printer','symptom','полосит','client_reported','m1','принтер полосит')
        self.assertNotIn('company_price',c.items['printer'].facts)
        self.assertNotIn('requested_action',c.items['printer'].facts)
    def test_mixed_repairs_assign_symptoms_and_wish_to_correct_device(self):
        c=self.case('mixed_repairs','laptop','printer')
        self.put(c,'laptop','symptom','не включается','client_reported','m1','не включается')
        self.put(c,'printer','symptom','печатает с полосами','client_reported','m1','печатает с полосами')
        self.put(c,'printer','delivery_request','привезти на следующей неделе','client_reported','m1','принтер могу привезти только на следующей неделе')
        self.assertNotIn('delivery_request',c.items['laptop'].facts)
        self.assertEqual(c.items['printer'].facts['delivery_request'].state,'client_reported')
    def test_confirmation_is_a_separate_explicit_review(self):
        c=self.case('model_correction','a')
        with self.assertRaises(ValueError): self.put(c,'a','model','TestCart T-200','employee_confirmed','m2','TestCart T-200')
        f=self.put(c,'a','model','TestCart T-200','employee_confirmed','m2','TestCart T-200',reviewer='test_employee')
        self.assertEqual(f.state,'employee_confirmed')
    def test_quote_must_exist_and_conflict_has_no_final_value(self):
        c=self.case('model_correction','a')
        with self.assertRaises(ValueError): self.put(c,'a','model','invented','client_reported','m2','invented')
        with self.assertRaises(ValueError): self.put(c,'a','model','TestCart T-200','conflicting','m2','TestCart T-200')
        f=self.put(c,'a','model',None,'conflicting','m2','TestCart T-200',note='Пример отдельного конфликта')
        self.assertIsNone(f.value)

if __name__=='__main__': unittest.main(verbosity=2)
