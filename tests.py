from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
import io
import json
import os
import shutil
import sqlite3
import tempfile
import time
import unicodedata
import unittest
from unittest.mock import patch, MagicMock

import bricbooks as bb
import load_test_data


CHECKING = load_test_data.CHECKING
CHECKING_NFD = unicodedata.normalize('NFD', CHECKING)
CHECKING_NFC = unicodedata.normalize('NFC', CHECKING)


def get_test_account(id_=None, commodity=None, name=CHECKING, type_=bb.AccountType.ASSET, number=None, parent=None, other_data=None):
    return bb.Account(id_=id_, commodity=commodity, type_=type_, number=number, name=name, parent=parent, other_data=other_data)


class TestUtils(unittest.TestCase):

    def test_get_date(self):
        self.assertEqual(bb.get_date(date(2018, 1, 1)), date(2018, 1, 1))
        self.assertEqual(bb.get_date('2018-01-01'), date(2018, 1, 1))
        with self.assertRaises(RuntimeError):
            bb.get_date(10)

    def test_increment_month(self):
        new_date = bb.increment_month(date(2018, 1, 1))
        self.assertEqual(new_date, date(2018, 2, 1))
        new_date = bb.increment_month(date(2018, 12, 1))
        self.assertEqual(new_date, date(2019, 1, 1))
        new_date = bb.increment_month(date(2018, 1, 31))
        self.assertEqual(new_date, date(2018, 2, 28))
        new_date = bb.increment_month(date(2018, 3, 31))
        self.assertEqual(new_date, date(2018, 4, 30))

    def test_increment_half_month(self):
        new_date = bb.increment_half_month(date(2018, 1, 1))
        self.assertEqual(new_date, date(2018, 1, 16))
        new_date = bb.increment_half_month(date(2018, 1, 16))
        self.assertEqual(new_date, date(2018, 2, 1))
        new_date = bb.increment_half_month(date(2018, 1, 30))
        self.assertEqual(new_date, date(2018, 2, 14))
        new_date = bb.increment_half_month(date(2018, 1, 31))
        self.assertEqual(new_date, date(2018, 2, 14))
        new_date = bb.increment_half_month(date(2018, 2, 1))
        self.assertEqual(new_date, date(2018, 2, 15))
        new_date = bb.increment_half_month(date(2018, 2, 15))
        self.assertEqual(new_date, date(2018, 3, 1))
        new_date = bb.increment_half_month(date(2018, 2, 28))
        self.assertEqual(new_date, date(2018, 3, 15))
        new_date = bb.increment_half_month(date(2020, 2, 29))
        self.assertEqual(new_date, date(2020, 3, 15))
        new_date = bb.increment_half_month(date(2018, 12, 16))
        self.assertEqual(new_date, date(2019, 1, 1))
        new_date = bb.increment_half_month(date(2018, 12, 31))
        self.assertEqual(new_date, date(2019, 1, 15))

    def test_increment_quarter(self):
        new_date = bb.increment_quarter(date(2018, 1, 31))
        self.assertEqual(new_date, date(2018, 4, 30))
        new_date = bb.increment_quarter(date(2018, 12, 31))
        self.assertEqual(new_date, date(2019, 3, 31))
        new_date = bb.increment_quarter(date(2018, 11, 30))
        self.assertEqual(new_date, date(2019, 2, 28))

    def test_find_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path1 = os.path.join(tmp, 'file.txt')
            path2 = os.path.join(tmp, 'file.sqlite3')
            path3 = os.path.join(tmp, 'db.sqlite3')
            path4 = os.path.join(tmp, 'file.sql')
            for path in [path1, path2, path3, path4]:
                with open(path, 'wb') as f: pass
            self.assertEqual(sorted([str(f) for f in bb.get_files(tmp)]), [path3, path2])


class TestAccount(unittest.TestCase):

    def test_init(self):
        a = bb.Account(id_=1, type_=bb.AccountType.ASSET, number='400', name='Checking')
        self.assertEqual(a.type, bb.AccountType.ASSET)
        self.assertEqual(a.name, 'Checking')
        self.assertEqual(a.parent, None)
        self.assertEqual(a.number, '400')

    def test_str(self):
        a = bb.Account(id_=1, type_=bb.AccountType.ASSET, number='400', name='Checking')
        self.assertEqual(str(a), '400 - Checking')

    def test_account_type(self):
        with self.assertRaises(bb.InvalidAccountError) as cm:
            bb.Account(id_=1, name='Checking')
        self.assertEqual(str(cm.exception), 'Account must have a type')
        with self.assertRaises(bb.InvalidAccountError) as cm:
            bb.Account(id_=1, type_='asdf', name='Checking')
        self.assertEqual(str(cm.exception), 'Invalid account type "asdf"')
        a = bb.Account(id_=1, type_='asset', name='Checking')
        self.assertEqual(a.type, bb.AccountType.ASSET)

    def test_eq(self):
        a = bb.Account(id_=1, type_=bb.AccountType.ASSET, name='Checking')
        a2 = bb.Account(id_=2, type_=bb.AccountType.ASSET, name='Savings')
        self.assertNotEqual(a, a2)
        self.assertEqual(a, a)
        a3 = bb.Account(type_=bb.AccountType.ASSET, name='Other')
        with self.assertRaises(bb.InvalidAccountError) as cm:
            a == a3
        self.assertEqual(str(cm.exception), "Can't compare accounts without an id")

    def test_parent(self):
        housing = bb.Account(id_=1, type_=bb.AccountType.EXPENSE, name='Housing')
        rent = bb.Account(id_=2, type_=bb.AccountType.EXPENSE, name='Rent', parent=housing)
        self.assertEqual(rent.parent, housing)

    def test_empty_strings_for_non_required_elements(self):
        a = bb.Account(id_=1, type_=bb.AccountType.EXPENSE, name='Test', number='')
        self.assertEqual(a.number, None)

    def test_securities_account(self):
        a = bb.Account(id_=1, type_=bb.AccountType.SECURITY, name='test')
        self.assertEqual(list({a: 1}.keys())[0], a)


class TestTransaction(unittest.TestCase):

    def setUp(self):
        self.checking = get_test_account(id_=1)
        self.savings = get_test_account(id_=2, name='Savings')
        self.valid_splits = [{'account': self.checking, 'amount': '100', 'payee': ''},
                             {'account': self.savings, 'amount': '-100', 'payee': 'Burgers'}]

    def test_invalid_split_amounts(self):
        with self.assertRaises(bb.InvalidTransactionError) as cm:
            bb.Transaction(splits=[{'account': self.checking, 'amount': 101.1}, {'account':self.savings, 'amount': '-101.1'}])
        self.assertEqual(str(cm.exception), 'invalid split: invalid value type: <class \'float\'> 101.1')
        with self.assertRaises(bb.InvalidTransactionError) as cm:
            bb.Transaction(splits=[{'account': self.checking, 'amount': '123.456'}, {'account': self.savings, 'amount': '-123.45'}])
        self.assertEqual(str(cm.exception), 'invalid split: no fractions of cents allowed: 123.456')
        with self.assertRaises(bb.InvalidTransactionError) as cm:
            bb.Transaction(splits=[{'account': self.checking, 'amount': '123.456'}, {'account': self.savings, 'amount': 123}])
        self.assertEqual(str(cm.exception), 'invalid split: no fractions of cents allowed: 123.456')

    def test_invalid_txn_date(self):
        with self.assertRaises(bb.InvalidTransactionError) as cm:
            bb.Transaction(splits=self.valid_splits)
        self.assertEqual(str(cm.exception), 'transaction must have a txn_date')
        with self.assertRaises(bb.InvalidTransactionError) as cm:
            bb.Transaction(splits=self.valid_splits, txn_date=10)
        self.assertEqual(str(cm.exception), 'invalid txn_date "10"')

    def test_txn_date(self):
        t = bb.Transaction(splits=self.valid_splits, txn_date=date.today())
        self.assertEqual(t.txn_date, date.today())
        t = bb.Transaction(splits=self.valid_splits, txn_date='2018-03-18')
        self.assertEqual(t.txn_date, date(2018, 3, 18))
        t = bb.Transaction(splits=self.valid_splits, txn_date='3/18/2018')
        self.assertEqual(t.txn_date, date(2018, 3, 18))

    def test_init(self):
        payee = bb.Payee('payee 1')
        splits = [{'account': self.checking, 'amount': '100', 'status': 'c'},
                  {'account': self.savings, 'amount': '-100', 'payee': payee}]
        t = bb.Transaction(
                splits=splits,
                txn_date=date.today(),
                description='2 hamburgers',
            )
        expected_splits = [
                {'account': self.checking, 'amount': Fraction(100), 'quantity': Fraction(100), 'status': 'C'},
                {'account': self.savings, 'amount': Fraction(-100), 'quantity': Fraction(-100), 'payee': payee}
            ]
        self.assertEqual(t.splits, expected_splits)
        self.assertTrue(isinstance(t.splits[0]['amount'], Fraction))
        self.assertEqual(t.txn_date, date.today())
        self.assertEqual(t.description, '2 hamburgers')

    def test_sparse_init(self):
        #pass minimal amount of info into Transaction & verify values
        t = bb.Transaction(
                splits=self.valid_splits,
                txn_date=date.today(),
            )
        self.assertEqual(t.id, None)
        self.assertEqual(t.description, '')

    def test_splits(self):
        t = bb.Transaction(
                splits=[{'account': self.checking, 'amount': '-1'}, {'account': self.savings, 'amount': '1'}],
                txn_date=date.today(),
            )
        self.assertEqual(t.splits, [{'account': self.checking, 'amount': -1, 'quantity': -1}, {'account': self.savings, 'amount': 1, 'quantity': 1}])

    def test_txn_payee(self):
        t = bb.Transaction(
                splits=self.valid_splits,
                txn_date=date.today(),
            )
        self.assertNotIn('payee', t.splits[0])
        self.assertEqual(t.splits[1]['payee'].name, 'Burgers')

    def test_txn_status(self):
        t = bb.Transaction(
                splits=[
                    {'account': self.checking, 'amount': '-101', 'status': 'c'},
                    {'account': self.savings, 'amount': '101'},
                ],
                txn_date=date.today(),
            )
        self.assertEqual(t.splits[0]['status'], 'C')

    def test_get_display_strings(self):
        t = bb.Transaction(
                splits=[{'account': self.checking, 'amount': '-1.2', 'status': 'C'}, {'account': self.savings, 'amount': '1.2', 'payee': 'asdf'}],
                txn_date=date.today(),
                description='something',
            )
        t.balance = Fraction(5)
        self.assertDictEqual(
                bb.get_display_strings_for_ledger(account=self.checking, txn=t),
                {
                    'withdrawal': '1.20',
                    'deposit': '',
                    'quantity': '-1.2',
                    'description': 'something',
                    'txn_date': str(date.today()),
                    'payee': 'asdf',
                    'status': 'C',
                    'action': '',
                    'type': '',
                    'categories': 'Savings',
                    'balance': '5.00',
                }
            )
        self.assertDictEqual(
                bb.get_display_strings_for_ledger(account=self.savings, txn=t),
                {
                    'withdrawal': '',
                    'deposit': '1.20',
                    'quantity': '1.2',
                    'description': 'something',
                    'txn_date': str(date.today()),
                    'payee': 'asdf',
                    'status': '',
                    'action': '',
                    'type': '',
                    'categories': CHECKING,
                    'balance': '5.00',
                }
            )

    def test_get_display_strings_sparse(self):
        t = bb.Transaction(
                splits=self.valid_splits,
                txn_date=date.today(),
            )
        self.assertDictEqual(bb.get_display_strings_for_ledger(account=self.checking, txn=t),
                {
                    'withdrawal': '',
                    'deposit': '100.00',
                    'quantity': '100',
                    'description': '',
                    'txn_date': str(date.today()),
                    'payee': 'Burgers',
                    'status': '',
                    'action': '',
                    'type': '',
                    'categories': 'Savings',
                }
            )

    def test_txn_categories_display(self):
        a = get_test_account(id_=1)
        a2 = get_test_account(id_=2, name='Savings')
        a3 = get_test_account(id_=3, name='Other')
        t = bb.Transaction(
                splits=[
                    {'account': a, 'amount': -100},
                    {'account': a2, 'amount': 65},
                    {'account': a3, 'amount': 35},
                ],
                txn_date=date.today(),
            )
        self.assertEqual(bb._categories_display(t.splits, main_account=a), 'multiple')
        t = bb.Transaction(
                splits=[
                    {'account': a, 'amount': -100},
                    {'account': a2, 'amount': 100},
                ],
                txn_date=date.today(),
            )
        self.assertEqual(bb._categories_display(t.splits, main_account=a), 'Savings')


class TestScheduledTransaction(unittest.TestCase):

    def setUp(self):
        self.checking = get_test_account(id_=1)
        self.savings = get_test_account(id_=2, name='Savings')
        self.valid_splits=[
                {'account': self.checking, 'amount': -101},
                {'account': self.savings, 'amount': 101, 'payee': 'restaurant'},
            ]

    def test_invalid_frequency(self):
        with self.assertRaises(bb.InvalidScheduledTransactionError) as cm:
            bb.ScheduledTransaction(
                name='w',
                frequency=1,
                next_due_date='2019-01-01',
                splits=self.valid_splits,
            )
        self.assertEqual(str(cm.exception), 'invalid frequency "1"')

    def test_invalid_next_due_date(self):
        with self.assertRaises(bb.InvalidScheduledTransactionError) as cm:
            bb.ScheduledTransaction(
                name='w',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='abcd',
                splits=self.valid_splits,
            )
        self.assertEqual(str(cm.exception), 'invalid date "abcd"')

    def test_init(self):
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=self.valid_splits,
                description='something',
            )
        self.assertEqual(st.name, 'weekly 1')
        self.assertEqual(st.frequency, bb.ScheduledTransactionFrequency.WEEKLY)
        self.assertEqual(st.next_due_date, date(2019, 1, 2))
        self.assertEqual(st.splits, self.valid_splits)
        self.assertEqual(st.description, 'something')

    def test_init_frequency(self):
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency='quarterly',
                next_due_date='2019-01-02',
                splits=self.valid_splits,
            )
        self.assertEqual(st.frequency, bb.ScheduledTransactionFrequency.QUARTERLY)

    def test_payee(self):
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency='quarterly',
                next_due_date='2019-01-02',
                splits=self.valid_splits,
            )
        self.assertEqual(st.splits[1]['payee'].name, 'restaurant')

    def test_display_strings(self):
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=self.valid_splits,
                description='something',
            )
        tds = bb.get_display_strings_for_ledger(account=self.checking, txn=st)

    def test_advance_to_next_due_date(self):
        #WEEKLY
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=self.valid_splits,
            )
        st.advance_to_next_due_date()
        self.assertEqual(st.next_due_date, date(2019, 1, 9))
        #MONTHLY
        st = bb.ScheduledTransaction(
                name='monthly 1',
                frequency=bb.ScheduledTransactionFrequency.MONTHLY,
                next_due_date='2019-01-02',
                splits=self.valid_splits,
            )
        st.advance_to_next_due_date()
        self.assertEqual(st.next_due_date, date(2019, 2, 2))
        #QUARTERLY
        st = bb.ScheduledTransaction(
                name='quarterly 1',
                frequency=bb.ScheduledTransactionFrequency.QUARTERLY,
                next_due_date='2019-01-02',
                splits=self.valid_splits,
            )
        st.advance_to_next_due_date()
        self.assertEqual(st.next_due_date, date(2019, 4, 2))
        #YEARLY
        st = bb.ScheduledTransaction(
                name='annually 1',
                frequency=bb.ScheduledTransactionFrequency.YEARLY,
                next_due_date='2018-01-02',
                splits=self.valid_splits,
            )
        st.advance_to_next_due_date()
        self.assertEqual(st.next_due_date, date(2019, 1, 2))


class TestBudget(unittest.TestCase):

    def test_init_dates(self):
        with self.assertRaises(bb.BudgetError) as cm:
            bb.Budget()
        self.assertEqual(str(cm.exception), 'must pass in dates')
        b = bb.Budget(year=2018, account_budget_info={})
        self.assertEqual(b.start_date, date(2018, 1, 1))
        self.assertEqual(b.end_date, date(2018, 12, 31))
        b = bb.Budget(year='2018', account_budget_info={})
        self.assertEqual(b.start_date, date(2018, 1, 1))
        b = bb.Budget(start_date=date(2018, 1, 15), end_date=date(2019, 1, 14), account_budget_info={})
        self.assertEqual(b.start_date, date(2018, 1, 15))
        self.assertEqual(b.end_date, date(2019, 1, 14))

    def test_init(self):
        housing = get_test_account(id_=1, type_=bb.AccountType.EXPENSE, name='Housing')
        food = get_test_account(id_=2, type_=bb.AccountType.EXPENSE, name='Food')
        transportation = get_test_account(id_=3, type_=bb.AccountType.EXPENSE, name='Transportation')
        rent = get_test_account(id_=4, type_=bb.AccountType.EXPENSE, name='Rent')
        account_budget_info = {
                housing: {'amount': 15, 'carryover': 5, 'notes': 'some important info'},
                food: {'amount': '35', 'carryover': '0'},
                transportation: {},
                rent: {'amount': 0, 'notes': ''},
            }
        b = bb.Budget(year=2018, account_budget_info=account_budget_info)
        self.maxDiff = None
        self.assertEqual(b.get_budget_data(), {
                    housing: {'amount': Fraction(15), 'carryover': Fraction(5), 'notes': 'some important info'},
                    food: {'amount': Fraction(35)},
                    transportation: {},
                    rent: {},
                })

    def test_display(self):
        b = bb.Budget(id_=1, year=2018)
        self.assertEqual(b.display(), '1: 2018-01-01 - 2018-12-31')
        self.assertEqual(b.display(show_id=False), '2018-01-01 - 2018-12-31')
        b = bb.Budget(id_=1, name='2018', year=2018)
        self.assertEqual(b.display(), '1: 2018 (2018-01-01 - 2018-12-31)')

    def test_sparse_init(self):
        b = bb.Budget(year=2018)
        self.assertEqual(b.start_date, date(2018, 1, 1))

    def test_percent_rounding(self):
        self.assertEqual(bb.Budget.round_percent_available(Decimal('1.1')), 1)
        self.assertEqual(bb.Budget.round_percent_available(Decimal('1.8')), 2)
        self.assertEqual(bb.Budget.round_percent_available(Decimal('1.5')), 2)
        self.assertEqual(bb.Budget.round_percent_available(Decimal('2.5')), 3)

    def test_get_current_status(self):
        status = bb.Budget.get_current_status(current_date=date(2018, 7, 1), start_date=date(2018, 1, 1), end_date=date(2018, 12, 31), remaining_percent=Fraction(60))
        self.assertEqual(status, '-10%')
        status = bb.Budget.get_current_status(current_date=date(2018, 1, 1), start_date=date(2017, 7, 1), end_date=date(2018, 6, 30), remaining_percent=Fraction(60))
        self.assertEqual(status, '-10%')

    def test_get_report_display(self):
        self.maxDiff = None
        housing = get_test_account(id_=1, type_=bb.AccountType.EXPENSE, name='Housing', number='400')
        maintenance = get_test_account(id_=7, type_=bb.AccountType.EXPENSE, name='Maintenance', number='420', parent=housing)
        rent = get_test_account(id_=8, type_=bb.AccountType.EXPENSE, name='Rent', number='410', parent=housing)
        food = get_test_account(id_=2, type_=bb.AccountType.EXPENSE, name='Food', number='600')
        restaurants = get_test_account(id_=9, type_=bb.AccountType.EXPENSE, name='Restaurants', number='610', parent=food)
        groceries = get_test_account(id_=10, type_=bb.AccountType.EXPENSE, name='Groceries', number='620', parent=food)
        transportation = get_test_account(id_=3, type_=bb.AccountType.EXPENSE, name='Transportation')
        something = get_test_account(id_=4, type_=bb.AccountType.EXPENSE, name='Something')
        wages = get_test_account(id_=5, type_=bb.AccountType.INCOME, name='Wages')
        interest = get_test_account(id_=6, type_=bb.AccountType.INCOME, name='Interest')
        account_budget_info = {
                maintenance: {},
                rent: {},
                restaurants: {},
                food: {},
                housing: {'amount': 15, 'carryover': 5},
                groceries: {},
                transportation: {'amount': 10},
                something: {'amount': 0},
                wages: {'amount': 100, 'notes': 'note 1'},
                interest: {},
            }
        budget = bb.Budget(year=2018, account_budget_info=account_budget_info)
        with self.assertRaises(bb.BudgetError) as cm:
            budget.get_report_display()
        self.assertEqual(str(cm.exception), 'must pass in income_spending_info to get the report display')
        income_spending_info = {housing: {'income': 5, 'spent': 10}, food: {'income': ''}, wages: {'income': 80}}
        budget = bb.Budget(year=2018, account_budget_info=account_budget_info, income_spending_info=income_spending_info)
        budget_report = budget.get_report_display(current_date=date(2018, 7, 1))
        self.assertEqual(len(budget_report['income']), 3)
        self.assertEqual(len(budget_report['expense']), 11)
        housing_info = budget_report['expense'][0]
        self.assertEqual(housing_info['name'], 'Housing')
        self.assertEqual(housing_info['amount'], '15.00')
        self.assertEqual(housing_info['carryover'], '5.00')
        self.assertEqual(housing_info['income'], '5.00')
        self.assertEqual(housing_info['total_budget'], '25.00')
        self.assertEqual(housing_info['spent'], '10.00')
        self.assertEqual(housing_info['remaining'], '15.00')
        self.assertEqual(housing_info['remaining_percent'], '60%')
        self.assertEqual(housing_info['current_status'], '-10%')
        self.assertEqual(budget_report['expense'][1]['name'], 'Rent')
        self.assertEqual(budget_report['expense'][2]['name'], 'Maintenance')
        self.assertEqual(budget_report['expense'][3]['name'], 'Total Housing')
        self.assertEqual(budget_report['expense'][3]['amount'], '15.00')
        self.assertEqual(budget_report['expense'][3]['total_budget'], '25.00')
        food_info = budget_report['expense'][4]
        self.assertEqual(food_info, {'name': 'Food'})
        self.assertEqual(budget_report['expense'][5]['name'], 'Restaurants')
        self.assertEqual(budget_report['expense'][6]['name'], 'Groceries')
        self.assertEqual(budget_report['expense'][7]['name'], 'Total Food')
        transportation_info = budget_report['expense'][8]
        self.assertEqual(transportation_info,
                {
                    'name': 'Transportation',
                    'amount': '10.00',
                    'total_budget': '10.00',
                    'remaining': '10.00',
                    'remaining_percent': '100%',
                    'current_status': '-50%',
                }
            )
        self.assertEqual(budget_report['expense'][9], {'name': 'Something'})
        self.assertEqual(budget_report['expense'][10],
                {
                    'name': 'Total Expense',
                    'amount': '25.00',
                    'carryover': '5.00',
                    'income': '5.00',
                    'total_budget': '35.00',
                    'spent': '10.00',
                    'remaining': '25.00',
                    'remaining_percent': '71%',
                    'current_status': '-21%',
                }
            )
        wages_info = budget_report['income'][0]
        self.assertEqual(wages_info,
                {
                    'name': 'Wages',
                    'amount': '100.00',
                    'income': '80.00',
                    'remaining': '20.00',
                    'remaining_percent': '20%',
                    'notes': 'note 1',
                    'current_status': '+30%',
                }
            )
        self.assertEqual(budget_report['income'][1], {'name': 'Interest'})
        self.assertEqual(budget_report['income'][2],
                {
                    'name': 'Total Income',
                    'amount': '100.00',
                    'carryover': '',
                    'income': '80.00',
                    'remaining': '20.00',
                    'remaining_percent': '20%',
                    'current_status': '+30%',
                }
            )


TABLES = [('commodity_types',), ('commodities',), ('institutions',), ('account_types',), ('accounts',), ('budgets',), ('budget_values',), ('payees',), ('scheduled_transaction_frequencies',), ('scheduled_transactions',), ('scheduled_transaction_splits',), ('transaction_actions',), ('transactions',), ('transaction_splits',), ('misc',)]


class TestSQLiteStorage(unittest.TestCase):

    def setUp(self):
        self.storage = bb.SQLiteStorage(':memory:')

    def tearDown(self):
        self.storage._db_connection.close()

    def test_init(self):
        tables = self.storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, TABLES)
        misc_table_records = self.storage._db_connection.execute('SELECT key,value FROM misc').fetchall()
        self.assertEqual(misc_table_records, [('schema_version', 0)])
        commodities_table_records = self.storage._db_connection.execute('SELECT id,type,code,name FROM commodities').fetchall()
        self.assertEqual(commodities_table_records, [(1, 'currency', 'USD', 'US Dollar')])

    def test_init_no_filename(self):
        with self.assertRaises(bb.SQLiteStorageError) as exc_cm:
            bb.SQLiteStorage('')
        with self.assertRaises(bb.SQLiteStorageError) as exc_cm:
            bb.SQLiteStorage(None)

    def test_init_file_doesnt_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_name = os.path.join(tmp, 'test.sqlite3')
            storage = bb.SQLiteStorage(file_name)
            tables = storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
            storage._db_connection.close()
        self.assertEqual(tables, TABLES)

    def test_init_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_name = os.path.join(tmp, 'test.sqlite3')
            with open(file_name, 'wb') as f:
                pass
            storage = bb.SQLiteStorage(file_name)
            tables = storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
            storage._db_connection.close()
        self.assertEqual(tables, TABLES)

    def test_init_db_already_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_name = os.path.join(tmp, 'test.sqlite3')
            #set up file
            init_storage = bb.SQLiteStorage(file_name)
            tables = init_storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
            self.assertEqual(tables, TABLES)
            #and now open it again and make sure everything's fine
            storage = bb.SQLiteStorage(file_name)
            tables = storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
            init_storage._db_connection.close()
            storage._db_connection.close()
            self.assertEqual(tables, TABLES)

    def test_save_commodity(self):
        c = self.storage._db_connection.cursor()
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('INSERT INTO commodities(type, code, name, trading_currency_id) VALUES(?, ?, ?, ?)', (bb.CommodityType.SECURITY.value, 'ABC', 'A Big Co', 20))
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')

        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('INSERT INTO commodities(type, code, name) VALUES(?, ?, ?)', ('', 'ABC', 'A Big Co'))
        self.assertEqual(str(cm.exception), 'CHECK constraint failed: type != ""')

        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('INSERT INTO commodities(type, code, name) VALUES(?, ?, ?)', (bb.CommodityType.SECURITY.value, '', 'A Big Co'))
        self.assertEqual(str(cm.exception), 'CHECK constraint failed: code != ""')

        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('INSERT INTO commodities(type, code, name) VALUES(?, ?, ?)', (bb.CommodityType.SECURITY.value, 'ABC', ''))
        self.assertEqual(str(cm.exception), 'CHECK constraint failed: name != ""')

        commodity = bb.Commodity(type_=bb.CommodityType.CURRENCY, code='EUR', name='Euro')
        self.storage.save_commodity(commodity)
        record = c.execute('SELECT type, code, name, trading_currency_id FROM commodities WHERE id = ?', (commodity.id,)).fetchone()
        self.assertEqual(record, ('currency', 'EUR', 'Euro', None))

    def test_get_commodity(self):
        c = self.storage._db_connection.cursor()
        c.execute('INSERT INTO commodities(type, code, name, trading_currency_id) VALUES(?, ?, ?, ?)', (bb.CommodityType.SECURITY.value, 'ABC', 'A Big Co', 1))
        commodity_id = c.lastrowid
        commodity = self.storage.get_commodity(id_=commodity_id)
        self.assertEqual(commodity.name, 'A Big Co')
        commodity = self.storage.get_commodity(code='ABC')
        self.assertEqual(commodity.name, 'A Big Co')

    def test_institution_name_cant_be_empty(self):
        c = self.storage._db_connection.cursor()

        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('INSERT INTO institutions(name) VALUES(?)', ('',))
        self.assertEqual(str(cm.exception), 'CHECK constraint failed: name != ""')

    def test_account_type_cant_be_empty(self):
        c = self.storage._db_connection.cursor()
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('INSERT INTO account_types(type) VALUES(?)', ('',))
        self.assertEqual(str(cm.exception), 'CHECK constraint failed: type != ""')

    def test_save_account(self):
        assets = get_test_account(type_=bb.AccountType.ASSET, name='All Assets')
        self.storage.save_account(assets)
        checking = get_test_account(type_=bb.AccountType.ASSET, number='4010', name=CHECKING_NFD, parent=assets)
        self.storage.save_account(checking)
        #make sure we save the id to the account object
        self.assertEqual(assets.id, 1)
        self.assertEqual(checking.id, 2)
        c = self.storage._db_connection.cursor()
        account_fields = 'id,type,commodity_id,institution_id,number,name,parent_id,closed,created,updated'
        c.execute(f'SELECT {account_fields} FROM accounts WHERE id = ?', (checking.id,))
        db_info = c.fetchone()
        self.assertEqual(db_info[:len(db_info)-2],
                (checking.id, 'asset', 1, None, '4010', CHECKING_NFC, assets.id, 0))
        #check created/updated default timestamp fields (which are in UTC time)
        utc_now = datetime.now(timezone.utc)
        created = datetime.fromisoformat(f'{db_info[-2]}+00:00')
        self.assertTrue((utc_now - created) < timedelta(seconds=20))
        updated = datetime.fromisoformat(f'{db_info[-1]}+00:00')
        self.assertEqual(created, updated)
        time.sleep(1)

        checking.name = 'checking updated'
        self.storage.save_account(checking)
        c.execute(f'SELECT {account_fields} FROM accounts WHERE id = ?', (checking.id,))
        db_info = c.fetchone()
        self.assertEqual(db_info[:len(db_info)-2],
                (checking.id, 'asset', 1, None, '4010', 'checking updated', assets.id, 0))
        new_created = datetime.fromisoformat(f'{db_info[-2]}+00:00')
        self.assertEqual(created, new_created)
        new_updated = datetime.fromisoformat(f'{db_info[-1]}+00:00')
        self.assertTrue(new_updated > updated)

        savings = get_test_account(id_=checking.id, type_=bb.AccountType.ASSET, name='Savings')
        self.storage.save_account(savings)
        c.execute(f'SELECT {account_fields} FROM accounts WHERE id = ?', (savings.id,))
        db_info = c.fetchall()
        self.assertEqual(db_info[0][:len(db_info[0])-2],
                (savings.id, 'asset', 1, None, None, 'Savings', None, 0))

    def test_save_account_commodity(self):
        c = self.storage._db_connection.cursor()

        # no commodity - should just get default USD
        checking = get_test_account()
        self.storage.save_account(checking)
        db_info = c.execute(f'SELECT commodity_id FROM accounts WHERE id = ?', (checking.id,)).fetchone()
        self.assertEqual(db_info, (1,))

        euro = bb.Commodity(type_=bb.CommodityType.CURRENCY, code='EUR', name='Euro')
        self.storage.save_commodity(euro)

        # with commodity - should be saved properly
        acc = get_test_account(name='with commodity', commodity=euro)
        self.storage.save_account(acc)
        db_info = c.execute(f'SELECT commodity_id FROM accounts WHERE id = ?', (acc.id,)).fetchone()
        self.assertEqual(db_info, (euro.id,))

        # save Account object without specifying commodity - should leave commodity_id unchanged
        acc = bb.Account(id_=acc.id, type_=bb.AccountType.ASSET, name='with commodity')
        self.storage.save_account(acc)
        db_info = c.execute(f'SELECT commodity_id FROM accounts WHERE id = ?', (acc.id,)).fetchone()
        self.assertEqual(db_info, (euro.id,))

    def test_save_account_other_data(self):
        rate = Fraction(5)
        other_data = {'interest-rate-percent': rate}
        acc = get_test_account(name='Loan', type_=bb.AccountType.LIABILITY, other_data=other_data)
        self.storage.save_account(acc)
        c = self.storage._db_connection.cursor()
        data = c.execute(f'SELECT other_data FROM accounts WHERE id = ?', (acc.id,)).fetchone()[0]
        data = json.loads(data)
        self.assertEqual(data['interest-rate-percent'], '5/1')

        # verify it has to be valid json
        with self.assertRaises(Exception) as cm:
            c.execute('UPDATE accounts SET other_data = ? WHERE id = ?', ('asdf', acc.id))
        self.assertEqual(str(cm.exception), 'malformed JSON')

        # verify it has to be json object
        with self.assertRaises(Exception) as cm:
            c.execute('UPDATE accounts SET other_data = ? WHERE id = ?', (json.dumps([]), acc.id))
        self.assertEqual(str(cm.exception), 'CHECK constraint failed: json_type(other_data) IS "object"')

        acc.other_data['term'] = '360'
        with self.assertRaises(bb.InvalidAccountError) as cm:
            self.storage.save_account(acc)
        self.assertEqual(str(cm.exception), 'invalid term value: 360')

        acc.other_data['term'] = 'asdy'
        with self.assertRaises(bb.InvalidAccountError) as cm:
            self.storage.save_account(acc)
        self.assertEqual(str(cm.exception), 'invalid term value: asdy')

        acc.other_data['term'] = '30y'
        acc.other_data['fixed-interest'] = 'yes'
        with self.assertRaises(bb.InvalidAccountError) as cm:
            self.storage.save_account(acc)
        self.assertEqual(str(cm.exception), 'invalid fixed-interest value: yes')

        acc.other_data['fixed-interest'] = True
        acc.other_data['interest-rate-percent'] = 5.23
        with self.assertRaises(bb.InvalidAccountError) as cm:
            self.storage.save_account(acc)
        self.assertEqual(str(cm.exception), 'invalid interest-rate-percent value: 5.23')

        acc.other_data['interest-rate-percent'] = 5
        acc.other_data['wrong-key'] = 1
        with self.assertRaises(bb.InvalidAccountError) as cm:
            self.storage.save_account(acc)
        self.assertEqual(str(cm.exception), "invalid keys: {'wrong-key'}")

    def test_save_account_blank_out_other_data(self):
        rate = Fraction(5)
        acc = get_test_account(name='Loan', type_=bb.AccountType.LIABILITY, other_data={'interest-rate-percent': rate})
        self.storage.save_account(acc)
        c = self.storage._db_connection.cursor()
        data = c.execute(f'SELECT other_data FROM accounts WHERE id = ?', (acc.id,)).fetchone()[0]
        data = json.loads(data)
        self.assertIn('interest-rate-percent', data)

        acc.other_data = {}
        self.storage.save_account(acc)
        data = c.execute(f'SELECT other_data FROM accounts WHERE id = ?', (acc.id,)).fetchone()[0]
        self.assertEqual(data, '{}')

    def test_save_account_dont_update_other_data(self):
        rate = Fraction(5)
        acc = get_test_account(name='Loan', type_=bb.AccountType.LIABILITY, other_data={'interest-rate-percent': rate})
        self.storage.save_account(acc)
        c = self.storage._db_connection.cursor()
        data = c.execute(f'SELECT other_data FROM accounts WHERE id = ?', (acc.id,)).fetchone()[0]
        data = json.loads(data)
        self.assertIn('interest-rate-percent', data)

        acc = bb.Account(id_=acc.id, name='Loan', type_=bb.AccountType.LIABILITY)
        self.storage.save_account(acc)
        data = c.execute(f'SELECT other_data FROM accounts WHERE id = ?', (acc.id,)).fetchone()[0]
        data = json.loads(data)
        self.assertIn('interest-rate-percent', data)

    def test_save_account_closed(self):
        acc = get_test_account()
        acc.closed = True
        self.storage.save_account(acc)

        c = self.storage._db_connection.cursor()
        closed = c.execute('SELECT closed FROM accounts WHERE id = ?', (acc.id,)).fetchone()[0]
        self.assertEqual(closed, 1)

        # verify `closed` isn't updated if value wasn't set
        acc = self.storage.get_account(acc.id)
        acc.closed = None
        self.storage.save_account(acc)
        closed = c.execute('SELECT closed FROM accounts WHERE id = ?', (acc.id,)).fetchone()[0]
        self.assertEqual(closed, 1)

        # test updating the value of `closed`
        acc = self.storage.get_account(acc.id)
        self.assertEqual(acc.closed, True)
        acc.closed = False
        self.storage.save_account(acc)
        closed = c.execute('SELECT closed FROM accounts WHERE id = ?', (acc.id,)).fetchone()[0]
        self.assertEqual(closed, 0)

        # verify that we can't save an invalid value
        with self.assertRaises(Exception) as cm:
            c.execute('UPDATE accounts SET closed = ? WHERE id = ?', (2, acc.id))
        self.assertEqual(str(cm.exception), 'CHECK constraint failed: closed = 0 OR closed = 1')

    def test_save_account_error_invalid_id(self):
        checking = get_test_account(type_=bb.AccountType.ASSET, id_=1)
        #checking has an id, so it should already be in the DB...
        # it's not, so raise an exception
        with self.assertRaises(Exception) as cm:
            self.storage.save_account(checking)
        self.assertEqual(str(cm.exception), 'no account with id 1 to update')
        account_records = self.storage._db_connection.execute('SELECT * FROM accounts').fetchall()
        self.assertEqual(account_records, [])

    def test_save_account_parent_not_in_db(self):
        checking = get_test_account(type_=bb.AccountType.ASSET, id_=9)
        checking_child = get_test_account(type_=bb.AccountType.ASSET, name='Checking Child', parent=checking)
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            self.storage.save_account(checking_child)
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')

    def test_cant_delete_parent_account(self):
        checking = get_test_account(type_=bb.AccountType.ASSET)
        checking_child = get_test_account(type_=bb.AccountType.ASSET, name='Checking Child', parent=checking)
        self.storage.save_account(checking)
        self.storage.save_account(checking_child)
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            self.storage._db_connection.execute(f'DELETE FROM accounts WHERE id={checking.id}')
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')

    def test_cant_delete_account_with_txns(self):
        checking = get_test_account(type_=bb.AccountType.ASSET)
        savings = get_test_account(type_=bb.AccountType.ASSET, name='Savings')
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        txn = bb.Transaction(txn_date=date(2020,10,15), splits=[{'account': checking, 'amount': 10}, {'account': savings, 'amount': -10}])
        self.storage.save_txn(txn)
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            self.storage._db_connection.execute('DELETE FROM accounts WHERE id=1')
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')

    def test_account_number_must_be_unique(self):
        checking = get_test_account(type_=bb.AccountType.ASSET, number='4-1', name='Checking')
        checking2 = get_test_account(type_=bb.AccountType.ASSET, number='4-1', name='Checking')
        self.storage.save_account(checking)
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            self.storage.save_account(checking2)
        self.assertEqual(str(cm.exception), 'UNIQUE constraint failed: accounts.number')
        #make sure saving works once number is updated
        checking2 = get_test_account(type_=bb.AccountType.INCOME, number='5-1', name='Checking')
        self.storage.save_account(checking2)

    def test_account_name_and_parent_must_be_unique(self):
        bank_accounts = get_test_account(type_=bb.AccountType.ASSET, name='Bank Accounts')
        checking = get_test_account(type_=bb.AccountType.ASSET, name='Checking', parent=bank_accounts)
        self.storage.save_account(bank_accounts)
        self.storage.save_account(checking)
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            self.storage.save_account(
                    get_test_account(type_=bb.AccountType.ASSET, name='Checking', parent=bank_accounts)
                )
        self.assertEqual(str(cm.exception), 'UNIQUE constraint failed: accounts.name, accounts.parent_id')

    def test_account_institution_id_foreign_key(self):
        c = self.storage._db_connection.cursor()
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('INSERT INTO accounts(type, commodity_id, institution_id, number, name) VALUES (?, ?, ?, ?, ?)', (bb.AccountType.EXPENSE.value, 1, 1, '4010', 'Checking'))
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')

    def test_account_type_must_be_valid(self):
        checking = get_test_account(type_=bb.AccountType.ASSET)
        self.storage.save_account(checking)
        c = self.storage._db_connection.cursor()
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('UPDATE accounts SET type = ? WHERE id = ?', ('invalid', checking.id))
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')

    def test_account_number_and_name_not_empty(self):
        c = self.storage._db_connection.cursor()
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('INSERT INTO accounts(type, commodity_id, number, name) VALUES (?, ?, ?, ?)', (bb.AccountType.EXPENSE.value, 1, '', 'Checking'))
        self.assertEqual(str(cm.exception), 'CHECK constraint failed: number != ""')

        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('INSERT INTO accounts(type, commodity_id, number, name) VALUES (?, ?, ?, ?)', (bb.AccountType.EXPENSE.value, 1, '4010', ''))
        self.assertEqual(str(cm.exception), 'CHECK constraint failed: name != ""')

    def test_get_account(self):
        c = self.storage._db_connection.cursor()
        c.execute('INSERT INTO accounts(type, commodity_id, number, name) VALUES (?, ?, ?, ?)', (bb.AccountType.EXPENSE.value, 1, '4010', 'Checking'))
        account_id = c.lastrowid
        c.execute('INSERT INTO accounts(type, commodity_id, name, parent_id) VALUES (?, ?, ?, ?)', (bb.AccountType.EXPENSE.value, 1, 'Sub-Checking', account_id))
        sub_checking_id = c.lastrowid
        c.execute('INSERT INTO accounts(type, commodity_id, name, other_data) VALUES (?, ?, ?, ?)', (bb.AccountType.LIABILITY.value, 1, 'Mortgage', json.dumps({'interest-rate-percent': '5/1'})))
        mortgage_id = c.lastrowid
        account = self.storage.get_account(account_id)
        self.assertEqual(account.id, account_id)
        self.assertEqual(account.type, bb.AccountType.EXPENSE)
        self.assertEqual(account.number, '4010')
        self.assertEqual(account.name, 'Checking')
        self.assertEqual(account.parent, None)
        account = self.storage.get_account(number='4010')
        self.assertEqual(account.name, 'Checking')
        sub_checking = self.storage.get_account(sub_checking_id)
        self.assertEqual(sub_checking.parent, account)
        mortgage = self.storage.get_account(mortgage_id)
        self.assertEqual(mortgage.other_data, {'interest-rate-percent': Fraction(5)})

    def test_delete_account_existing_txns(self):
        checking = get_test_account()
        groceries = get_test_account(name='Groceries')
        self.storage.save_account(checking)
        self.storage.save_account(groceries)
        self.storage.save_txn(
            bb.Transaction(
                splits=[
                    {'account': checking, 'amount': '-101'},
                    {'account': groceries, 'amount': 101},
                ],
                txn_date=date.today(),
            )
        )
        with self.assertRaises(Exception) as cm:
            self.storage.delete_account(checking.id)
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')
        records = self.storage._db_connection.execute('SELECT id FROM accounts').fetchall()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0], (checking.id,))
        self.assertEqual(records[1], (groceries.id,))

    def test_delete_parent_account(self):
        checking = get_test_account()
        sub_checking = get_test_account(name='Sub', parent=checking)
        self.storage.save_account(checking)
        self.storage.save_account(sub_checking)
        with self.assertRaises(Exception) as cm:
            self.storage.delete_account(checking.id)
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')
        records = self.storage._db_connection.execute('SELECT id FROM accounts').fetchall()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0], (checking.id,))
        self.assertEqual(records[1], (sub_checking.id,))

    def test_delete_parent_account_unset_parent_id_from_children(self):
        checking = get_test_account()
        sub_checking = get_test_account(name='Sub', parent=checking)
        self.storage.save_account(checking)
        self.storage.save_account(sub_checking)
        self.storage.delete_account(checking.id, set_children_parent_id_to_null=True)
        records = self.storage._db_connection.execute('SELECT id,parent_id FROM accounts').fetchall()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0], (sub_checking.id, None))

    def test_delete_account(self):
        checking = get_test_account()
        self.storage.save_account(checking)
        self.storage.delete_account(checking.id)
        records = self.storage._db_connection.execute('SELECT * FROM accounts').fetchall()
        self.assertEqual(records, [])

    def test_payee_unique(self):
        payee = bb.Payee('payee')
        self.storage.save_payee(payee)
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            self.storage.save_payee(bb.Payee('payee'))
        self.assertEqual(str(cm.exception), 'UNIQUE constraint failed: payees.name')

        c = self.storage._db_connection.cursor()
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('UPDATE payees SET name = ? WHERE id = ?', ('', payee.id))
        self.assertEqual(str(cm.exception), 'CHECK constraint failed: name != ""')

    def test_save_txn(self):
        checking = get_test_account()
        groceries = get_test_account(name='Groceries')
        self.storage.save_account(checking)
        self.storage.save_account(groceries)
        restaurant_a = bb.Payee('Restaurant A')
        self.storage.save_payee(restaurant_a)
        today = date.today()
        today_str = today.strftime('%Y-%m-%d')
        tomorrow = today + timedelta(days=1)
        tomorrow_str = tomorrow.strftime('%Y-%m-%d')
        t = bb.Transaction(
                splits=[
                    {'account': checking, 'amount': '-101', 'status': bb.Transaction.CLEARED, 'type': '100'},
                    {'account': groceries, 'amount': 51, 'description': 'flour', 'status': bb.Transaction.RECONCILED, 'reconcile_date': today, 'payee': restaurant_a},
                    {'account': groceries, 'amount': 50, 'description': 'rice', 'status': bb.Transaction.RECONCILED, 'reconcile_date': today},
                    ],
                txn_date=today,
                entry_date=tomorrow,
                description='food',
                alternate_id='ID001',
            )
        self.storage.save_txn(t)
        self.assertEqual(t.id, 1) #make sure we save the id to the txn object
        c = self.storage._db_connection.cursor()
        c.execute('SELECT id,commodity_id,date,description,entry_date,alternate_id,created FROM transactions')
        db_info = c.fetchone()
        self.assertEqual(db_info[:len(db_info)-1],
                (1, 1, today_str, 'food', tomorrow_str, 'ID001'))
        utc_now = datetime.now(timezone.utc)
        created = datetime.fromisoformat(f'{db_info[-1]}+00:00')
        self.assertTrue((utc_now - created) < timedelta(seconds=20))
        c.execute('SELECT id,transaction_id,account_id,value_numerator,value_denominator,quantity_numerator,quantity_denominator,reconciled_state,reconcile_date,type,description,payee_id FROM transaction_splits')
        txn_split_records = c.fetchall()
        self.assertEqual(txn_split_records, [(1, 1, checking.id, -101, 1, -101, 1, 'C', None, '100', '', None),
                                             (2, 1, groceries.id, 51, 1, 51, 1, 'R', today_str, '', 'flour', restaurant_a.id),
                                             (3, 1, groceries.id, 50, 1, 50, 1, 'R', today_str, '', 'rice', None)])

    def test_save_txn_payee_string_and_none_description(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '-101'}, {'account': savings, 'amount': 101, 'payee': 'someone'}],
                txn_date=date.today(),
                description=None,
            )
        self.storage.save_txn(t)
        txn_from_db = self.storage.get_txn(t.id)
        self.assertEqual(txn_from_db.splits[1]['payee'].name, 'someone')

    def test_save_txn_blank_out_alternate_id(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '-101'}, {'account': savings, 'amount': 101}],
                txn_date=date.today(),
                alternate_id='asdf',
            )
        self.storage.save_txn(t)
        txn_id = t.id
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '-101'}, {'account': savings, 'amount': 101}],
                txn_date=date.today(),
                alternate_id='',
                id_=txn_id,
            )
        self.storage.save_txn(t)
        c = self.storage._db_connection.cursor()
        c.execute('SELECT alternate_id FROM transactions WHERE id = ?', (txn_id,))
        db_info = c.fetchone()
        self.assertEqual(db_info[0], '')

    def test_save_txn_dont_update_alternate_id(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '-101'}, {'account': savings, 'amount': 101}],
                txn_date=date.today(),
                alternate_id='asdf',
            )
        self.storage.save_txn(t)
        txn_id = t.id
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '-101'}, {'account': savings, 'amount': 101}],
                txn_date=date.today(),
                id_=txn_id,
            )
        self.storage.save_txn(t)
        c = self.storage._db_connection.cursor()
        c.execute('SELECT alternate_id FROM transactions WHERE id = ?', (txn_id,))
        db_info = c.fetchone()
        self.assertEqual(db_info[0], 'asdf')

    def test_save_txn_blank_out_action(self):
        checking = get_test_account()
        fund = get_test_account(name='Fund', type_=bb.AccountType.SECURITY)
        self.storage.save_account(checking)
        self.storage.save_account(fund)
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '-101'}, {'account': fund, 'amount': 101, 'action': 'share-buy'}],
                txn_date=date.today(),
            )
        self.storage.save_txn(t)
        txn_id = t.id
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '-101'}, {'account': fund, 'amount': 101, 'action': ''}],
                txn_date=date.today(),
                id_=txn_id,
            )
        self.storage.save_txn(t)
        c = self.storage._db_connection.cursor()
        c.execute('SELECT action FROM transaction_splits WHERE transaction_id = ? AND account_id = ?', (txn_id, fund.id))
        db_info = c.fetchone()
        self.assertEqual(db_info[0], '')

    def test_save_txn_dont_update_action(self):
        checking = get_test_account()
        fund = get_test_account(name='Fund', type_=bb.AccountType.SECURITY)
        self.storage.save_account(checking)
        self.storage.save_account(fund)
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '-101'}, {'account': fund, 'amount': 101, 'action': 'share-buy'}],
                txn_date=date.today(),
            )
        self.storage.save_txn(t)
        txn_id = t.id
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '-101'}, {'account': fund, 'amount': 101}],
                txn_date=date.today(),
                id_=txn_id,
            )
        self.storage.save_txn(t)
        c = self.storage._db_connection.cursor()
        c.execute('SELECT action FROM transaction_splits WHERE transaction_id = ? AND account_id = ?', (txn_id, fund.id))
        db_info = c.fetchone()
        self.assertEqual(db_info[0], 'share-buy')

    def test_save_transaction_error(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '-101'}, {'account': savings, 'amount': 101}],
                txn_date=date.today(),
                id_=1
            )
        #t has an id, so it should already be in the DB...
        # it's not, so raise an exception
        with self.assertRaises(Exception):
            self.storage.save_txn(t)
        c = self.storage._db_connection.cursor()
        c.execute('SELECT * FROM transactions')
        transaction_records = c.fetchall()
        self.assertEqual(transaction_records, [])
        c.execute('SELECT * FROM transaction_splits')
        txn_split_records = c.fetchall()
        self.assertEqual(txn_split_records, [])

    def test_splits_amounts_must_balance(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        txn = bb.Transaction(splits=[{'account': checking, 'amount': -100}, {'account': savings, 'amount': 90}], txn_date=date.today())
        with self.assertRaises(bb.InvalidTransactionError) as cm:
            self.storage.save_txn(txn)
        self.assertEqual(str(cm.exception), "splits don't balance: -100.00, 90.00")

    def test_splits_action_must_be_valid(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        fund = get_test_account(name='Fund', type_=bb.AccountType.SECURITY)
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        self.storage.save_account(fund)

        txn = bb.Transaction(splits=[{'account': checking, 'amount': -100, 'action': 'share-buy'}, {'account': fund, 'amount': 100}], txn_date=date.today())
        with self.assertRaises(bb.InvalidTransactionError) as cm:
            self.storage.save_txn(txn)
        self.assertEqual(str(cm.exception), 'actions can only be used with SECURITY accounts')

        txn = bb.Transaction(splits=[{'account': checking, 'amount': -100}, {'account': fund, 'amount': 100, 'action': 'asdf'}], txn_date=date.today())
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            self.storage.save_txn(txn)
        self.assertIn('FOREIGN KEY constraint failed', str(cm.exception))

    def test_cant_save_zero_denominator(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '101'}, {'account': savings, 'amount': '-101'}],
                txn_date=date.today(),
            )
        self.storage.save_txn(t)

        c = self.storage._db_connection.cursor()
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('UPDATE transaction_splits SET value_denominator = 0 WHERE transaction_id = ? AND account_id = ?', (t.id, checking.id))
        self.assertIn('value_denominator != 0', str(cm.exception))
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('UPDATE transaction_splits SET quantity_denominator = 0 WHERE transaction_id = ? AND account_id = ?', (t.id, checking.id))
        self.assertIn('quantity_denominator != 0', str(cm.exception))

        # check scheduled txns as well
        wendys = bb.Payee('Wendys')
        self.storage.save_payee(wendys)
        valid_splits = [
                {'account': checking, 'amount': -101},
                {'account': savings, 'amount': 101},
            ]
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
            )
        self.storage.save_scheduled_transaction(st)
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('UPDATE scheduled_transaction_splits SET value_denominator = 0 WHERE scheduled_transaction_id = ? AND account_id = ?', (t.id, checking.id))
        self.assertIn('value_denominator != 0', str(cm.exception))
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('UPDATE scheduled_transaction_splits SET quantity_denominator = 0 WHERE scheduled_transaction_id = ? AND account_id = ?', (t.id, checking.id))
        self.assertIn('quantity_denominator != 0', str(cm.exception))

    def test_save_transaction_db_transaction(self):
        # make invalid txns that will error when saving, and verify that no data was saved
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.storage.save_account(checking)
        self.storage.save_account(savings)

        # first have the splits error
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '101'}, {'account': savings, 'amount': '-101'}],
                txn_date=date.today(),
            )
        t.splits[0].pop('amount')
        try:
            self.storage.save_txn(t)
        except KeyError:
            pass

        c = self.storage._db_connection.cursor()
        results = c.execute('SELECT * FROM transaction_splits').fetchall()
        self.assertEqual(results, [])
        results = c.execute('SELECT * FROM transactions').fetchall()
        self.assertEqual(results, [])

        # now have the transaction record error
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '101'}, {'account': savings, 'amount': '-101'}],
                txn_date=date.today(),
            )
        t.txn_date = 'asdf'
        try:
            self.storage.save_txn(t)
        except AttributeError:
            pass
        c = self.storage._db_connection.cursor()
        results = c.execute('SELECT * FROM transaction_splits').fetchall()
        self.assertEqual(results, [])
        results = c.execute('SELECT * FROM transactions').fetchall()
        self.assertEqual(results, [])

    def test_dates_must_be_valid(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '101'}, {'account': savings, 'amount': '-101'}],
                txn_date=date.today(),
            )
        self.storage.save_txn(t)

        c = self.storage._db_connection.cursor()
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('UPDATE transactions SET date = ? WHERE id = ?', ('asdf', t.id))
        self.assertIn('OR date IS strftime(', str(cm.exception))

        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('UPDATE transactions SET entry_date = ? WHERE id = ?', ('asdf', t.id))
        self.assertIn('entry_date IS strftime(', str(cm.exception))

        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('UPDATE transaction_splits SET reconciled_state = ?, post_date = ? WHERE transaction_id = ? AND account_id = ?', ('C', 'asdf', t.id, checking.id))
        self.assertIn('post_date IS NULL OR (reconciled_state != "" AND post_date IS strftime', str(cm.exception))

        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('UPDATE transaction_splits SET reconciled_state = ?, reconcile_date = ? WHERE transaction_id = ? AND account_id = ?', ('R', 'asdf', t.id, checking.id))
        self.assertIn('reconcile_date IS NULL OR (reconciled_state = "R" AND reconcile_date IS strftime', str(cm.exception))

    def test_save_transaction_payee_foreignkey_error(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        payee = bb.Payee('payee', id_=1)
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '-101'}, {'account': savings, 'amount': 101, 'payee': payee}],
                txn_date=date.today(),
            )
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            self.storage.save_txn(t)
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')

    def test_cant_save_invalid_reconciled_state(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '-101', 'status': 'd'}, {'account': savings, 'amount': 101}],
                txn_date=date.today(),
            )
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            self.storage.save_txn(t)
        self.assertIn('reconciled_state = "" OR reconciled_state = "C" OR reconciled_state = "R"', str(cm.exception))

        t.splits[0].pop('status')
        self.storage.save_txn(t)

        c = self.storage._db_connection.cursor()

        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('UPDATE transaction_splits SET reconciled_state = "", post_date = "2010-01-31" WHERE account_id = ?', (checking.id,))
        self.assertIn('post_date IS NULL OR (reconciled_state != "" AND post_date IS strftime', str(cm.exception))

        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('UPDATE transaction_splits SET reconciled_state = "C", reconcile_date = "2010-01-31" WHERE account_id = ?', (checking.id,))
        self.assertIn('reconcile_date IS NULL OR (reconciled_state = "R" AND reconcile_date IS strftime', str(cm.exception))

    def test_save_sparse_txn(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        today = date.today()
        today_str = today.strftime('%Y-%m-%d')
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '101'}, {'account': savings, 'amount': '-101'}],
                txn_date=today,
            )
        self.storage.save_txn(t)
        c = self.storage._db_connection.cursor()
        c.execute('SELECT id,commodity_id,date,description,entry_date FROM transactions')
        db_info = c.fetchone()
        self.assertEqual(db_info,
                (1, 1, today_str, '', today_str))
        c.execute('SELECT id,transaction_id,account_id,value_numerator,value_denominator,quantity_numerator,quantity_denominator,payee_id FROM transaction_splits')
        txn_split_records = c.fetchall()
        self.assertEqual(txn_split_records, [(1, 1, 1, 101, 1, 101, 1, None),
                                             (2, 1, 2, -101, 1, -101, 1, None)])

    def test_round_trip(self):
        checking = get_test_account()
        self.storage.save_account(checking)
        savings = get_test_account(name='Savings')
        self.storage.save_account(savings)
        another_acct = get_test_account(name='Another')
        self.storage.save_account(another_acct)
        payee = bb.Payee('Some restaurant')
        self.storage.save_payee(payee)
        #create txn & save it
        t = bb.Transaction(
                splits=[{'account': checking, 'amount': '-101', 'status': 'C'}, {'account': savings, 'amount': 101, 'payee': payee}],
                txn_date=date.today(),
            )
        self.storage.save_txn(t)
        txn_id = t.id
        #verify db
        c = self.storage._db_connection.cursor()
        txn_fields = 'id,commodity_id,date,description'
        txn_db_info = c.execute(f'SELECT {txn_fields} FROM transactions').fetchall()
        self.assertEqual(txn_db_info,
                [(txn_id, 1, date.today().strftime('%Y-%m-%d'), '')])
        txn_split_fields = 'id,transaction_id,account_id,value_numerator,value_denominator,quantity_numerator,quantity_denominator,reconciled_state,description,action,payee_id'
        splits_db_info = c.execute(f'SELECT {txn_split_fields} FROM transaction_splits').fetchall()
        self.assertEqual(splits_db_info,
                [(1, txn_id, checking.id, -101, 1, -101, 1, 'C', '', '', None),
                 (2, txn_id, savings.id, 101, 1, 101, 1, '', '', '', payee.id)])
        #update it & save again
        splits = [
                {'account': checking, 'amount': '-101'},
                {'account': another_acct, 'amount': '101'},
            ]
        updated_txn = bb.Transaction(
                splits=splits,
                txn_date=date.today(),
                id_=txn_id,
            )
        time.sleep(1)
        self.storage.save_txn(updated_txn)
        c = self.storage._db_connection.cursor()
        c.execute(f'SELECT {txn_fields},created,updated FROM transactions')
        db_info = c.fetchall()
        self.assertEqual(db_info[0][:-2],
                (txn_id, 1, date.today().strftime('%Y-%m-%d'), ''))
        created = datetime.fromisoformat(f'{db_info[0][-2]}+00:00')
        updated = datetime.fromisoformat(f'{db_info[0][-1]}+00:00')
        self.assertTrue(updated > created)
        splits_db_info = c.execute(f'SELECT {txn_split_fields} FROM transaction_splits').fetchall()
        self.assertEqual(splits_db_info,
                [(1, txn_id, checking.id, -101, 1, -101, 1, '', '', '', None),
                 (2, txn_id, another_acct.id, 101, 1, 101, 1, '', '', '', None)])

    def test_get_txn(self):
        checking = get_test_account()
        self.storage.save_account(checking)
        fund = get_test_account(type_=bb.AccountType.SECURITY, name='Fund')
        self.storage.save_account(fund)
        c = self.storage._db_connection.cursor()
        txn_fields = 'id,commodity_id,date,payee_id,description'
        c.execute(f'INSERT INTO transactions(commodity_id,date,alternate_id) VALUES(?,?,?)', (1, '2019-05-10', 'ID001'))
        txn_id = c.lastrowid
        c.execute(f'INSERT INTO transaction_splits(transaction_id,account_id,type,action,value_numerator,value_denominator) VALUES(?,?,?,?,?, ?)',
                  (txn_id,checking.id, '1a', '', -100, 1))
        c.execute(f'INSERT INTO transaction_splits(transaction_id,account_id,type,action,value_numerator,value_denominator) VALUES(?,?,?,?,?, ?)',
                  (txn_id,fund.id, '', 'share-buy', 100, 1))
        txn = self.storage.get_txn(txn_id)
        self.assertEqual(txn.txn_date, date(2019, 5, 10))
        self.assertEqual(txn.alternate_id, 'ID001')
        self.assertEqual(txn.splits[0], {'account': checking, 'amount': -100, 'quantity': -100, 'type': '1a', 'action': ''})
        self.assertEqual(txn.splits[1], {'account': fund, 'amount': 100, 'quantity': 100, 'type': '', 'action': 'share-buy'})

    def test_delete_txn_from_db(self):
        checking = get_test_account()
        self.storage.save_account(checking)
        savings = get_test_account(name='Savings')
        self.storage.save_account(savings)
        txn = bb.Transaction(txn_date=date(2017, 1, 25),
                splits=[{'account': checking, 'amount': '101'}, {'account': savings, 'amount': '-101'}])
        self.storage.save_txn(txn)
        txn2 = bb.Transaction(txn_date=date(2017, 1, 28),
                splits=[{'account': checking, 'amount': '46.23'}, {'account': savings, 'amount': '-46.23'}])
        self.storage.save_txn(txn2)
        self.storage.delete_txn(txn.id)
        c = self.storage._db_connection.cursor()
        c.execute('SELECT date FROM transactions')
        txn_records = c.fetchall()
        self.assertEqual(len(txn_records), 1)
        self.assertEqual(txn_records[0][0], '2017-01-28')
        txn_splits_records = c.execute('SELECT transaction_id FROM transaction_splits').fetchall()
        self.assertEqual(len(txn_splits_records), 2)
        self.assertEqual([r[0] for r in txn_splits_records], [txn2.id, txn2.id])

    def test_save_budget(self):
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        self.storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        self.storage.save_account(food)
        account_budget_info = {
                housing: {'amount': '15.34', 'carryover': '0.34', 'notes': 'hello'},
                food: {'amount': 25}
            }
        b = bb.Budget(year=2018, account_budget_info=account_budget_info)
        self.storage.save_budget(b)
        cursor = self.storage._db_connection.cursor()
        records = cursor.execute('SELECT * FROM budgets WHERE start_date = "2018-01-01"').fetchall()
        self.assertEqual(len(records), 1)
        self.assertEqual(b.id, 1)
        records = cursor.execute('SELECT * FROM budget_values').fetchall()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0][1], 1)
        self.assertEqual(records[0][2], 1)
        self.assertEqual(records[0][3], 767)
        self.assertEqual(records[0][4], 50)
        self.assertEqual(records[0][5], 17)
        self.assertEqual(records[0][6], 50)
        self.assertEqual(records[0][7], 'hello')
        self.assertEqual(records[1][1], 1)
        self.assertEqual(records[1][2], 2)
        self.assertEqual(records[1][3], 25)
        self.assertEqual(records[1][4], 1)
        self.assertEqual(records[1][5], None)
        self.assertEqual(records[1][6], None)
        #test that start_date/end_date have to be valid dates
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            cursor.execute('UPDATE budgets SET start_date = ?', ('asdf',))
        self.assertIn('start_date IS strftime', str(cm.exception))
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            cursor.execute('UPDATE budgets SET end_date = ?', ('asdf',))
        self.assertIn('end_date IS strftime', str(cm.exception))
        #test that old budget values are deleted
        b = bb.Budget(start_date='2018-01-01', end_date='2018-12-24', account_budget_info={
                housing: {'amount': 35, 'carryover': 0},
                food: {'amount': 45, 'carryover': 0},
            }, id_=b.id)
        self.storage.save_budget(b)
        records = cursor.execute('SELECT id,name,start_date,end_date FROM budgets').fetchall()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0], (1, None, '2018-01-01', '2018-12-24'))
        records = cursor.execute('SELECT amount_numerator FROM budget_values ORDER BY amount_numerator').fetchall()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0][0], 35)
        self.assertEqual(records[1][0], 45)

    def test_save_budget_empty_category_info(self):
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        self.storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        self.storage.save_account(food)
        account_budget_info = {
                housing: {'amount': 15, 'carryover': 0},
                food: {},
            }
        b = bb.Budget(year=2018, account_budget_info=account_budget_info)
        self.storage.save_budget(b)
        cursor = self.storage._db_connection.cursor()
        records = cursor.execute('SELECT * FROM budgets').fetchall()
        self.assertEqual(len(records), 1)
        records = cursor.execute('SELECT amount_numerator FROM budget_values').fetchall()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][0], 15)

    def test_save_budget_sparse(self):
        b = bb.Budget(year=2018)
        self.storage.save_budget(b)
        cursor = self.storage._db_connection.cursor()
        records = cursor.execute('SELECT * FROM budgets').fetchall()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][2], '2018-01-01')
        self.assertEqual(records[0][3], '2018-12-31')
        records = cursor.execute('SELECT * FROM budget_values').fetchall()
        self.assertEqual(records, [])

    def test_save_budget_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_name = os.path.join(tmp, 'test.sqlite3')
            #test that save actually gets committed
            storage = bb.SQLiteStorage(file_name)
            housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
            storage.save_account(housing)
            food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
            storage.save_account(food)
            b = bb.Budget(year=2018, account_budget_info={
                housing: {'amount': 15, 'carryover': 0},
                food: {'amount': 25, 'carryover': 0},
            })
            storage.save_budget(b)
            storage._db_connection.close()
            storage = bb.SQLiteStorage(file_name)
            cursor = storage._db_connection.cursor()
            records = cursor.execute('SELECT * FROM budgets WHERE start_date = "2018-01-01"').fetchall()
            storage._db_connection.close()
        self.assertEqual(len(records), 1)

    def test_save_budget_account_foreignkey_error(self):
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        self.storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food', id_=5)
        account_budget_info = {
                housing: {'amount': '15.34', 'carryover': '0.34', 'notes': 'hello'},
                food: {'amount': 25, 'carryover': 0}
            }
        b = bb.Budget(year=2018, account_budget_info=account_budget_info)
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            self.storage.save_budget(b)
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')

    def test_save_budget_update_add_account_info(self):
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        self.storage.save_account(housing)
        b = bb.Budget(year=2018)
        self.storage.save_budget(b)
        account_budget_info = {housing: {'amount': '25'}}
        updated_budget = bb.Budget(id_=b.id, year=2018, account_budget_info=account_budget_info)
        self.storage.save_budget(updated_budget)
        cursor = self.storage._db_connection.cursor()
        records = cursor.execute('SELECT account_id FROM budget_values WHERE budget_id = ?', (b.id,)).fetchall()
        self.assertEqual(records, [(1,)])

    def test_get_budget(self):
        checking = get_test_account()
        self.storage.save_account(checking)
        savings = get_test_account(name='Savings')
        self.storage.save_account(savings)
        wages = get_test_account(name='Wages', type_=bb.AccountType.INCOME)
        self.storage.save_account(wages)
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        self.storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        self.storage.save_account(food)
        transportation = get_test_account(type_=bb.AccountType.EXPENSE, name='Transportation')
        self.storage.save_account(transportation)
        txn1 = bb.Transaction(txn_date=date(2018, 1, 25),
                splits=[{'account': checking, 'amount': '-101'}, {'account': housing, 'amount': '101'}])
        txn2 = bb.Transaction(txn_date=date(2018, 2, 28),
                splits=[{'account': checking, 'amount': '-46.23'}, {'account': food, 'amount': '46.23'}])
        txn3 = bb.Transaction(txn_date=date(2018, 3, 28),
                splits=[{'account': savings, 'amount': '-56.23'}, {'account': food, 'amount': '56.23'}])
        txn4 = bb.Transaction(txn_date=date(2018, 4, 28),
                splits=[{'account': checking, 'amount': '-15'}, {'account': savings, 'amount': 15}])
        txn5 = bb.Transaction(txn_date=date(2018, 5, 28),
                splits=[{'account': checking, 'amount': 15}, {'account': food, 'amount': '-15'}])
        txn6 = bb.Transaction(txn_date=date(2017, 1, 26),
                splits=[{'account': checking, 'amount': '-108'}, {'account': housing, 'amount': '108'}])
        txn7 = bb.Transaction(txn_date=date(2018, 2, 5),
                splits=[{'account': checking, 'amount': '100'}, {'account': wages, 'amount': '-100'}])
        for t in [txn1, txn2, txn3, txn4, txn5, txn6, txn7]:
            self.storage.save_txn(t)
        cursor = self.storage._db_connection.cursor()
        cursor.execute('INSERT INTO budgets (start_date, end_date) VALUES (?, ?)', ('2018-01-01', '2018-12-31'))
        budget_id = cursor.lastrowid
        cursor.execute('INSERT INTO budget_values (budget_id, account_id, amount_numerator, amount_denominator, notes) VALUES (?, ?, ?, ?, ?)', (budget_id, housing.id, 135, 1, 'hello'))
        cursor.execute('INSERT INTO budget_values (budget_id, account_id, amount_numerator, amount_denominator, carryover_numerator, carryover_denominator) VALUES (?, ?, ?, ?, ?, ?)', (budget_id, food.id, 70, 1, 15, 1))
        cursor.execute('INSERT INTO budget_values (budget_id, account_id, amount_numerator, amount_denominator) VALUES (?, ?, ?, ?)', (budget_id, wages.id, 70, 1))
        budget = self.storage.get_budget(budget_id)
        self.assertEqual(budget.id, budget_id)
        self.assertEqual(budget.start_date, date(2018, 1, 1))
        self.assertEqual(budget.end_date, date(2018, 12, 31))

        budget_data = budget.get_budget_data()
        self.assertEqual(budget_data[housing], {'amount': Fraction(135), 'notes': 'hello'})
        self.assertEqual(type(budget_data[housing]['amount']), Fraction)
        self.assertEqual(budget_data[wages], {'amount': Fraction(70)})

        report_display = budget.get_report_display(current_date=date(2018, 6, 30))
        expenses = report_display['expense']
        self.assertEqual(expenses[0]['name'], 'Food')
        self.assertEqual(expenses[0]['amount'], '70.00')
        self.assertEqual(expenses[0]['carryover'], '15.00')
        self.assertEqual(expenses[0]['income'], '15.00')
        self.assertEqual(expenses[0]['spent'], '102.46')

        self.assertEqual(expenses[1]['name'], 'Housing')
        self.assertEqual(expenses[1]['amount'], '135.00')
        self.assertEqual(expenses[1]['spent'], '101.00')
        self.assertEqual(expenses[1]['notes'], 'hello')

        self.assertEqual(expenses[2], {'name': 'Transportation'})

        incomes = report_display['income']
        self.assertEqual(incomes[0]['amount'], '70.00')
        self.assertEqual(incomes[0]['income'], '100.00')
        self.assertEqual(incomes[0]['remaining'], '-30.00')
        self.assertEqual(incomes[0]['current_status'], '+94%')

    def test_get_budgets(self):
        b = bb.Budget(year=2018)
        self.storage.save_budget(b)
        b2 = bb.Budget(year=2019)
        self.storage.save_budget(b2)
        budgets = self.storage.get_budgets()
        self.assertEqual(budgets[0].start_date, date(2019, 1, 1))
        self.assertEqual(budgets[1].start_date, date(2018, 1, 1))

    def test_get_budget_reports(self):
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        self.storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        self.storage.save_account(food)
        cursor = self.storage._db_connection.cursor()
        cursor.execute('INSERT INTO budgets (start_date, end_date) VALUES (?, ?)', ('2018-01-01', '2018-12-31'))
        budget_id = cursor.lastrowid
        cursor.execute('INSERT INTO budget_values (budget_id, account_id, amount_numerator, amount_denominator) VALUES (?, ?, ?, ?)', (budget_id, housing.id, 35, 1))
        cursor.execute('INSERT INTO budget_values (budget_id, account_id, amount_numerator, amount_denominator) VALUES (?, ?, ?, ?)', (budget_id, food.id, 70, 1))
        budgets = self.storage.get_budgets()
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets[0].start_date, date(2018, 1, 1))
        self.assertEqual(budgets[0].end_date, date(2018, 12, 31))
        self.assertEqual(budgets[0].get_report_display()['expense'][1]['name'], 'Housing')

    def test_save_scheduled_txn(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        restaurant = bb.Payee('Restaurant')
        self.storage.save_payee(restaurant)
        valid_splits = [
                {'account': checking, 'amount': -101, 'status': 'R'},
                {'account': savings, 'amount': 101, 'payee': restaurant},
            ]
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
                description='something',
            )
        self.storage.save_scheduled_transaction(st)
        self.assertEqual(st.id, 1)
        st_records = self.storage._db_connection.execute('SELECT id,name,frequency,next_due_date,description FROM scheduled_transactions').fetchall()
        self.assertEqual(len(st_records), 1)
        self.assertEqual(st_records[0],
                (1, 'weekly 1', bb.ScheduledTransactionFrequency.WEEKLY.value, '2019-01-02', 'something'))
        st_split_records = self.storage._db_connection.execute('SELECT scheduled_transaction_id,account_id,value_numerator,value_denominator,quantity_numerator,quantity_denominator,reconciled_state,payee_id FROM scheduled_transaction_splits').fetchall()
        self.assertEqual(len(st_split_records), 2)
        self.assertEqual(st_split_records[0], (st.id, checking.id, -101, 1, -101, 1, 'R', None))
        self.assertEqual(st_split_records[1], (st.id, savings.id, 101, 1, 101, 1, '', restaurant.id))

        # make sure next_due_date has to be valid date
        c = self.storage._db_connection.cursor()
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('UPDATE scheduled_transactions SET next_due_date = ? WHERE id = ?', ('asdf', st.id))
        self.assertIn('next_due_date IS strftime', str(cm.exception))

        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('UPDATE scheduled_transactions SET name = ? WHERE id = ?', ('', st.id))
        self.assertEqual(str(cm.exception), 'CHECK constraint failed: name != ""')

    def test_save_scheduled_transaction_error(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        valid_splits = [
                {'account': checking, 'amount': -101},
                {'account': savings, 'amount': 101},
            ]
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
                id_=1
            )
        #st has an id, so it should already be in the DB...
        # it's not, so raise an exception
        with self.assertRaises(Exception):
            self.storage.save_scheduled_transaction(st)
        c = self.storage._db_connection.cursor()
        c.execute('SELECT * FROM scheduled_transactions')
        scheduled_transaction_records = c.fetchall()
        self.assertEqual(scheduled_transaction_records, [])
        c.execute('SELECT * FROM scheduled_transaction_splits')
        scheduled_txn_split_records = c.fetchall()
        self.assertEqual(scheduled_txn_split_records, [])

    def test_save_scheduled_txn_split_amounts_dont_balance(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        st = bb.ScheduledTransaction(
                name='w',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-01',
                splits=[
                    {'account': checking, 'amount': -101},
                    {'account': savings, 'amount': 25},
                ]
            )
        with self.assertRaises(bb.InvalidTransactionError) as cm:
            self.storage.save_scheduled_transaction(st)
        self.assertEqual(str(cm.exception), 'splits don\'t balance: -101.00, 25.00')

    def test_save_scheduled_txn_account_foreignkey_error(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings', id_=2)
        self.storage.save_account(checking)
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=[
                    {'account': checking, 'amount': -101},
                    {'account': savings, 'amount': 101},
                ]
            )
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            self.storage.save_scheduled_transaction(st)
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')

    def test_update_scheduled_txn(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        another_acct = get_test_account(name='Another')
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        self.storage.save_account(another_acct)
        restaurant = bb.Payee('Restaurant')
        self.storage.save_payee(restaurant)
        valid_splits=[
                {'account': checking, 'amount': -101},
                {'account': savings, 'amount': 101, 'payee': restaurant},
            ]
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
                description='something',
            )
        self.storage.save_scheduled_transaction(st)
        st_id = st.id
        #update due date & save
        st.next_due_date = date(2019, 1, 9)
        self.storage.save_scheduled_transaction(st)
        st_records = self.storage._db_connection.execute('SELECT * FROM scheduled_transactions').fetchall()
        self.assertEqual(len(st_records), 1)
        retrieved_scheduled_txn = self.storage.get_scheduled_transaction(st_id)
        self.assertEqual(retrieved_scheduled_txn.next_due_date, date(2019, 1, 9))
        #now create a ScheduledTransaction object for the same record
        new_st = bb.ScheduledTransaction(
                name='monthly 1 updated',
                frequency=bb.ScheduledTransactionFrequency.MONTHLY,
                next_due_date=date(2019, 1, 16),
                splits=[
                    {'account': checking, 'amount': -101},
                    {'account': another_acct, 'amount': 101},
                ],
                id_=st_id
            )
        self.storage.save_scheduled_transaction(new_st)
        st_records = self.storage._db_connection.execute('SELECT * FROM scheduled_transactions').fetchall()
        self.assertEqual(len(st_records), 1)
        retrieved_scheduled_txn = self.storage.get_scheduled_transaction(st_id)
        self.assertEqual(retrieved_scheduled_txn.next_due_date, date(2019, 1, 16))
        split_records = self.storage._db_connection.execute('SELECT id,scheduled_transaction_id,account_id,value_numerator,value_denominator,quantity_numerator,quantity_denominator,reconciled_state,description FROM scheduled_transaction_splits').fetchall()
        self.assertEqual(split_records,
                [(1, st_id, checking.id, -101, 1, -101, 1, '', ''),
                 (2, st_id, another_acct.id, 101, 1, 101, 1, '', '')])

    def test_get_scheduled_transaction(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        restaurant = bb.Payee('Restaurant')
        self.storage.save_payee(restaurant)
        valid_splits = [
                {'account': checking, 'amount': -101, 'status': bb.Transaction.CLEARED},
                {'account': savings, 'amount': 101, 'payee': restaurant},
            ]
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
                description='something',
                status='C',
            )
        self.storage.save_scheduled_transaction(st)
        scheduled_txn = self.storage.get_scheduled_transaction(st.id)
        self.assertEqual(scheduled_txn.name, 'weekly 1')
        self.assertEqual(scheduled_txn.frequency, bb.ScheduledTransactionFrequency.WEEKLY)
        self.assertEqual(scheduled_txn.next_due_date, date(2019, 1, 2))
        self.assertEqual(scheduled_txn.description, 'something')
        self.assertEqual(scheduled_txn.splits, valid_splits)

    def test_get_scheduled_transaction_sparse(self):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.storage.save_account(checking)
        self.storage.save_account(savings)
        valid_splits = [
                {'account': checking, 'amount': -101},
                {'account': savings, 'amount': 101},
            ]
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
            )
        self.storage.save_scheduled_transaction(st)
        scheduled_txn = self.storage.get_scheduled_transaction(st.id)
        self.assertEqual(scheduled_txn.next_due_date, date(2019, 1, 2))


def create_test_accounts(engine):
    accounts = {
        'Bank Accounts': {'type': bb.AccountType.ASSET},
        'Checking': {'type': bb.AccountType.ASSET, 'parent': 'Bank Accounts'},
        'Savings': {'type': bb.AccountType.ASSET, 'parent': 'Bank Accounts'},
        'House Down Payment': {'type': bb.AccountType.ASSET, 'parent': 'Savings'},
        'Retirement 401k': {'type': bb.AccountType.ASSET},
        'Stock A': {'type': bb.AccountType.SECURITY, 'parent': 'Retirement 401k'},
        'Mortgage': {'type': bb.AccountType.LIABILITY},
        'Wages': {'type': bb.AccountType.INCOME},
        'Housing': {'type': bb.AccountType.EXPENSE},
        'Mortgage Interest': {'type': bb.AccountType.EXPENSE, 'parent': 'Housing'},
        'Food': {'type': bb.AccountType.EXPENSE},
        'Opening Balances': {'type': bb.AccountType.EQUITY},
    }
    for name, info in accounts.items():
        parent = None
        if 'parent' in info:
            parent = accounts[info['parent']]['account']
        account = get_test_account(type_=info['type'], name=name, parent=parent)
        engine.save_account(account)
        info['account'] = account
    closed_account = bb.Account(type_=bb.AccountType.ASSET, name='closed account', closed=True)
    engine.save_account(closed_account)


class TestEngine(unittest.TestCase):

    def setUp(self):
        self.engine = bb.Engine(':memory:')

    def tearDown(self):
        self.engine._storage._db_connection.close()

    def test_get_currencies(self):
        create_test_accounts(self.engine)
        currencies = self.engine.get_currencies()
        self.assertEqual(len(currencies), 1)
        self.assertEqual(currencies[0].type, bb.CommodityType.CURRENCY)
        self.assertEqual(currencies[0].code, 'USD')

    def test_save_commodity(self):
        self.engine.save_commodity(
                bb.Commodity(type_=bb.CommodityType.CURRENCY, code='ABC', name='Some Currency')
            )
        currencies = self.engine.get_currencies()
        self.assertEqual(len(currencies), 2)
        self.assertEqual(currencies[1].type, bb.CommodityType.CURRENCY)
        self.assertEqual(currencies[1].code, 'ABC')
        self.assertEqual(currencies[1].name, 'Some Currency')

    def test_get_accounts(self):
        create_test_accounts(self.engine)
        accounts = self.engine.get_accounts()
        self.assertEqual(len(accounts), 12)
        self.assertEqual(accounts[0].name, 'Bank Accounts')
        self.assertEqual(accounts[0].child_level, 0)
        self.assertEqual(accounts[1].name, 'Checking')
        self.assertEqual(accounts[1].parent, accounts[0])
        self.assertEqual(accounts[1].child_level, 1)
        self.assertEqual(accounts[2].name, 'Savings')
        self.assertEqual(accounts[2].parent, accounts[0])
        self.assertEqual(accounts[2].child_level, 1)
        self.assertEqual(accounts[3].name, 'House Down Payment')
        self.assertEqual(accounts[3].parent, accounts[2])
        self.assertEqual(accounts[3].child_level, 2)
        self.assertEqual(accounts[4].name, 'Retirement 401k')
        self.assertEqual(accounts[5].name, 'Stock A')

    def test_payees(self):
        self.engine.save_payee(bb.Payee('New Payee'))
        self.engine.save_payee(bb.Payee('A Payee obj'))
        self.engine.save_payee(bb.Payee('A New Payee'))
        payees = self.engine.get_payees()
        self.assertEqual(len(payees), 3)
        self.assertEqual(payees[0].name, 'A New Payee')
        self.assertEqual(payees[2].name, 'New Payee')

    def test_get_transactions(self):
        create_test_accounts(self.engine)
        checking = self.engine.get_account(name='Checking')
        savings = self.engine.get_account(name='Savings')
        wages = self.engine.get_account(name='Wages')
        food = self.engine.get_account(name='Food')
        stock = self.engine.get_account(name='Stock A')
        txn = bb.Transaction(
                splits=[
                    {'account': checking, 'amount': -5, 'status': bb.Transaction.CLEARED},
                    {'account': food, 'amount': 5, 'payee': 'Some payee'}
                ],
                txn_date=date(2017, 1, 15),
                description='description'
            )
        txn2 = bb.Transaction(
                splits=[
                    {'account': checking, 'amount': 5},
                    {'account': savings, 'amount': -5}
                ],
                txn_date=date(2017, 1, 2)
            )
        txn3 = bb.Transaction(
                splits=[
                    {'account': wages, 'amount': -100},
                    {'account': savings, 'amount': 100}
                ],
                txn_date=date(2017, 1, 31)
            )
        txn4 = bb.Transaction(
                splits=[
                    {'account': stock, 'amount': 100, 'quantity': '5.23'},
                    {'account': checking, 'amount': -100},
                ],
                txn_date=date(2018, 2, 3)
            )
        txn5 = bb.Transaction(
                splits=[
                    {'account': stock, 'amount': 100, 'quantity': '6.71'},
                    {'account': checking, 'amount': -100},
                ],
                txn_date=date(2018, 3, 3)
            )
        self.engine.save_transaction(txn)
        self.engine.save_transaction(txn2)
        self.engine.save_transaction(txn3)
        self.engine.save_transaction(txn4)
        self.engine.save_transaction(txn5)
        #get txns for an account, with balance
        txns = self.engine.get_transactions(account=checking)
        self.assertEqual(len(txns), 4)
        self.assertEqual(txns[0].balance, Fraction(5))
        self.assertEqual(txns[1].balance, 0)
        self.assertEqual(txns[3].balance, -200)
        #get txns matching multiple accounts
        txns = self.engine.get_transactions(account=checking, filter_account=food)
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].txn_date, date(2017, 1, 15))
        #get txns with a status
        txns = self.engine.get_transactions(account=checking, status=bb.Transaction.CLEARED)
        self.assertEqual(len(txns), 1)
        #search txns in an account
        txns = self.engine.get_transactions(account=checking, query='some payee')
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].splits[1]['payee'].name, 'Some payee')
        #security ledger
        txns = self.engine.get_transactions(account=stock)
        self.assertEqual(len(txns), 2)
        self.assertEqual(txns[0].balance, Fraction('5.23'))
        self.assertEqual(txns[1].balance, Fraction('11.94'))

    def test_get_current_balances_for_display(self):
        create_test_accounts(self.engine)
        checking = self.engine.get_account(name='Checking')
        stock = self.engine.get_account(name='Stock A')
        txn = bb.Transaction(
                splits=[
                    {'account': checking, 'amount': -50, 'status': bb.Transaction.CLEARED},
                    {'account': stock, 'amount': 50, 'quantity': Fraction('5.25'), 'status': bb.Transaction.CLEARED}
                ],
                txn_date=date(2017, 1, 15),
            )
        txn2 = bb.Transaction(
                splits=[
                    {'account': checking, 'amount': -50},
                    {'account': stock, 'amount': 50, 'quantity': Fraction('4.5')}
                ],
                txn_date=date(2017, 1, 22)
            )
        txn3 = bb.Transaction(
                splits=[
                    {'account': checking, 'amount': -50},
                    {'account': stock, 'amount': 50, 'quantity': Fraction(3)}
                ],
                txn_date=date(2017, 1, 31)
            )
        self.engine.save_transaction(txn)
        self.engine.save_transaction(txn2)
        self.engine.save_transaction(txn3)
        balances = self.engine.get_current_balances_for_display(checking)
        expected_balances = bb.LedgerBalances(current='-150.00', current_cleared='-50.00')
        self.assertEqual(balances, expected_balances)
        stock_balances = self.engine.get_current_balances_for_display(stock)
        expected_stock_balances = bb.LedgerBalances(current='12.75', current_cleared='5.25')
        self.assertEqual(stock_balances, expected_stock_balances)

    def test_get_scheduled_transactions_due(self):
        create_test_accounts(self.engine)
        checking = self.engine.get_account(name='Checking')
        savings = self.engine.get_account(name='Savings')
        st1 = bb.ScheduledTransaction(
                name='st1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date=date(2024, 3, 14)
            )
        st2 = bb.ScheduledTransaction(
                name='st2',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
            )
        self.engine.save_scheduled_transaction(st1)
        self.engine.save_scheduled_transaction(st2)
        scheduled_txns_due = self.engine.get_scheduled_transactions_due()
        self.assertEqual(len(scheduled_txns_due), 1)
        self.assertEqual(scheduled_txns_due[0].id, st1.id)


class TestCLI(unittest.TestCase):

    ACCOUNT_FORM_OUTPUT = '  name:   type (asset,security,liability,equity,income,expense):   number:   parent account id: '

    def setUp(self):
        #https://realpython.com/python-print/#mocking-python-print-in-unit-tests
        self.memory_buffer = io.StringIO()
        self.cli = bb.CLI(':memory:', print_file=self.memory_buffer)

    def tearDown(self):
        self.cli._engine._storage._db_connection.close()

    @patch('builtins.input')
    def test_run(self, input_mock):
        checking = get_test_account(name='Checking account')
        self.cli._engine._storage.save_account(checking)
        input_mock.side_effect = ['h', 'a', 'q']
        self.cli.run()
        self.assertTrue('| Checking account' in self.memory_buffer.getvalue())

    def test_list_accounts(self):
        checking = get_test_account(name='Checking account with long name cut off')
        self.cli._engine._storage.save_account(checking)
        self.cli._list_accounts()
        output = '%s\n' % bb.CLI.ACCOUNT_LIST_HEADER
        output += ' 1    | ASSET       |         | Checking account with long nam |                               \n'
        self.assertEqual(self.memory_buffer.getvalue(), output)

    @patch('builtins.input')
    def test_create_account(self, input_mock):
        savings = get_test_account(name='Savings')
        self.cli._engine._storage.save_account(savings)
        input_mock.side_effect = ['Checking', 'asset', '400', str(savings.id)]
        self.cli._create_account()
        accounts = self.cli._engine._storage.get_accounts()
        self.assertEqual(accounts[1].name, 'Checking')
        self.assertEqual(accounts[1].type, bb.AccountType.ASSET)
        self.assertEqual(accounts[1].parent, savings)
        output = 'Create Account:\n%s' % self.ACCOUNT_FORM_OUTPUT
        self.assertEqual(self.memory_buffer.getvalue(), output)

    @patch('builtins.input')
    def test_edit_account(self, input_mock):
        input_mock.side_effect = ['1', 'Checking updated', 'asset', '400', '2']
        checking = get_test_account()
        self.cli._engine._storage.save_account(checking)
        savings = get_test_account(name='Savings')
        self.cli._engine._storage.save_account(savings)
        self.cli._edit_account()
        accounts = self.cli._engine.get_accounts()
        self.assertEqual(accounts[0].name, 'Savings')
        self.assertEqual(accounts[1].name, 'Checking updated')
        self.assertEqual(accounts[1].type, bb.AccountType.ASSET)
        self.assertEqual(accounts[1].number, '400')
        self.assertEqual(accounts[1].parent, savings)
        output = 'Account ID: %s' % self.ACCOUNT_FORM_OUTPUT
        self.assertEqual(self.memory_buffer.getvalue(), output)

    @patch('builtins.input')
    def test_list_account_txns(self, input_mock):
        self.maxDiff = None
        input_mock.return_value = '1'
        checking = get_test_account()
        self.cli._engine.save_account(checking)
        savings = get_test_account(name='Savings')
        self.cli._engine.save_account(savings)
        txn = bb.Transaction(splits=[{'account': checking, 'amount': 5}, {'account': savings, 'amount': -5}], txn_date=date(2017, 1, 1), description='description')
        txn2 = bb.Transaction(splits=[{'account': checking, 'amount': 5}, {'account': savings, 'amount': -5}], txn_date=date(2017, 1, 2))
        self.cli._engine.save_transaction(txn)
        self.cli._engine.save_transaction(txn2)
        self.cli._engine.save_scheduled_transaction(
                bb.ScheduledTransaction(
                    name='scheduled txn',
                    frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                    next_due_date=date(2019, 1, 13),
                    splits=[{'account': checking, 'amount': 14}, {'account': savings, 'amount': -14}],
                )
            )
        self.cli._list_account_txns()
        txn1_output = ' 1    | 2017-01-01 | description                    |                                | Savings                        |            | 5.00       | 5.00      \n'
        txn2_output = ' 2    | 2017-01-02 |                                |                                | Savings                        |            | 5.00       | 10.00     \n'
        printed_output = self.memory_buffer.getvalue()
        self.assertTrue(f'Account ID (or search string): {CHECKING} (Current balance: 10.00; Cleared: 0.00)' in printed_output)
        self.assertTrue('scheduled txn' in printed_output)
        self.assertTrue(bb.CLI.TXN_LIST_HEADER in printed_output)
        self.assertTrue(txn1_output in printed_output)
        self.assertTrue(txn2_output in printed_output)

    @patch('builtins.input')
    def test_list_account_txns_filter_status(self, input_mock):
        self.maxDiff = None
        input_mock.return_value = '1 status:C'
        checking = get_test_account()
        self.cli._engine.save_account(checking)
        savings = get_test_account(name='Savings')
        self.cli._engine.save_account(savings)
        txn = bb.Transaction(splits=[{'account': checking, 'amount': 5, 'status': bb.Transaction.CLEARED}, {'account': savings, 'amount': -5}], txn_date=date(2017, 1, 1), description='description')
        txn2 = bb.Transaction(splits=[{'account': checking, 'amount': 5}, {'account': savings, 'amount': -5}], txn_date=date(2017, 1, 2))
        self.cli._engine.save_transaction(txn)
        self.cli._engine.save_transaction(txn2)
        self.cli._list_account_txns()
        txn1_output = ' 1    | 2017-01-01 | description                    |                                | Savings                        |            | 5.00       |           \n'
        txn2_output = '2017-01-02'
        printed_output = self.memory_buffer.getvalue()
        self.assertTrue('Account ID (or search string)' in printed_output)
        self.assertTrue(bb.CLI.TXN_LIST_HEADER in printed_output)
        self.assertTrue(txn1_output in printed_output)
        self.assertFalse(txn2_output in printed_output)

    @patch('builtins.input')
    def test_list_account_txns_filter_account(self, input_mock):
        self.maxDiff = None
        checking = get_test_account()
        self.cli._engine.save_account(checking)
        savings = get_test_account(name='Savings')
        self.cli._engine.save_account(savings)
        rent = get_test_account(name='Rent')
        self.cli._engine.save_account(rent)
        input_mock.return_value = f'1 acc:{rent.id}'
        txn = bb.Transaction(splits=[{'account': checking, 'amount': 5}, {'account': savings, 'amount': -5}], txn_date=date(2017, 1, 1))
        txn2 = bb.Transaction(splits=[{'account': checking, 'amount': -5}, {'account': rent, 'amount': 5}], txn_date=date(2017, 1, 2))
        self.cli._engine.save_transaction(txn)
        self.cli._engine.save_transaction(txn2)
        self.cli._list_account_txns()
        txn1_output = '2017-01-01'
        txn2_output = '2017-01-02'
        printed_output = self.memory_buffer.getvalue()
        self.assertTrue('Account ID (or search string)' in printed_output)
        self.assertTrue(bb.CLI.TXN_LIST_HEADER in printed_output)
        self.assertTrue(txn2_output in printed_output)
        self.assertFalse(txn1_output in printed_output)

    @patch('builtins.input')
    def test_list_account_txns_paged(self, input_mock):
        input_mock.return_value = '1'
        checking = get_test_account()
        self.cli._engine._storage.save_account(checking)
        savings = get_test_account(name='Savings')
        self.cli._engine._storage.save_account(savings)
        txn = bb.Transaction(splits=[{'account': checking, 'amount': 5}, {'account': savings, 'amount': -5}], txn_date=date(2017, 1, 1), description='description')
        txn2 = bb.Transaction(splits=[{'account': checking, 'amount': 5}, {'account': savings, 'amount': -5}], txn_date=date(2017, 1, 2))
        self.cli._engine._storage.save_txn(txn)
        self.cli._engine._storage.save_txn(txn2)
        self.cli._list_account_txns(num_txns_in_page=1)
        printed_output = self.memory_buffer.getvalue()
        self.assertTrue('(o) older' in printed_output)

    def test_pager(self):
        self.assertEqual(bb.pager([1, 2, 3], num_txns_in_page=1, page=1), ([1], True))
        self.assertEqual(bb.pager([1, 2, 3], num_txns_in_page=1, page=3), ([3], False))
        self.assertEqual(bb.pager([1, 2, 3, 4, 5], num_txns_in_page=2, page=3), ([5], False))
        self.assertEqual(bb.pager([1, 2, 3, 4, 5], num_txns_in_page=2, page=2), ([3, 4], True))
        self.assertEqual(bb.pager([1, 2, 3, 4], num_txns_in_page=2, page=2), ([3, 4], False))

    @patch('builtins.input')
    def test_create_txn(self, input_mock):
        checking = get_test_account()
        self.cli._engine._storage.save_account(checking)
        fund = get_test_account(type_=bb.AccountType.SECURITY, name='Fund')
        self.cli._engine._storage.save_account(fund)
        payee = bb.Payee(name='payee 1')
        self.cli._engine._storage.save_payee(payee)
        input_mock.side_effect = ['2019-02-24',
                str(checking.id), '-15', 'C', 'type1', '', '',
                str(fund.id), '15', '', 'type2', 'share-buy', str(payee.id),
                '', 'description']
        self.cli._create_txn()
        txn = self.cli._engine.get_transactions(account=checking)[0]
        self.assertEqual(txn.txn_date, date(2019, 2, 24))
        self.assertEqual(txn.splits[0], {'account': checking, 'action': '', 'amount': -15, 'quantity': -15, 'type': 'type1', 'status': 'C'})
        self.assertEqual(txn.splits[1], {'account': fund, 'action': 'share-buy', 'amount': 15, 'quantity': 15, 'type': 'type2', 'payee': payee})
        self.assertEqual(txn.description, 'description')
        buffer_value = self.memory_buffer.getvalue()
        self.assertTrue('Create Transaction:\n' in buffer_value)

    @patch('builtins.input')
    def test_create_txn_new_payee(self, input_mock):
        checking = get_test_account()
        self.cli._engine._storage.save_account(checking)
        savings = get_test_account(name='Savings')
        self.cli._engine._storage.save_account(savings)
        input_mock.side_effect = ['2019-02-24',
                str(checking.id), '-15', '', '', '', '',
                str(savings.id), '15', '', '', '', "'payee 1",
                '', 'description']
        self.cli._create_txn()
        txn = self.cli._engine.get_transactions(account=checking)[0]
        self.assertEqual(txn.splits[1]['payee'].name, 'payee 1')

    @patch('builtins.input')
    def test_create_txn_existing_payee_by_name(self, input_mock):
        '''make sure the user can enter the payee's name, even if the payee is already
        in the DB'''
        checking = get_test_account()
        self.cli._engine._storage.save_account(checking)
        savings = get_test_account(name='Savings')
        self.cli._engine._storage.save_account(savings)
        payee = bb.Payee(name='payee 1')
        self.cli._engine._storage.save_payee(payee)
        input_mock.side_effect = ['2019-02-24',
                str(checking.id), '-15', '', '', '', '',
                str(savings.id), '15', '', '', '', "'payee 1",
                '', 'description']
        self.cli._create_txn()
        txn = self.cli._engine.get_transactions(account=checking)[0]
        self.assertEqual(txn.splits[1]['payee'].name, 'payee 1')

    @patch('builtins.input')
    def test_create_txn_list_payees(self, input_mock):
        '''make sure user can list payees if desired'''
        checking = get_test_account()
        self.cli._engine._storage.save_account(checking)
        savings = get_test_account(name='Savings')
        self.cli._engine._storage.save_account(savings)
        payee = bb.Payee(name='payee 1')
        self.cli._engine._storage.save_payee(payee)
        input_mock.side_effect = ['2019-02-24',
                str(checking.id), '-15', '', '', '', '',
                str(savings.id), '15', '', '', '', 'p', "'payee 1",
                '', 'description']
        self.cli._create_txn()
        buffer_value = self.memory_buffer.getvalue()
        self.assertTrue('1: payee 1' in buffer_value)
        txn = self.cli._engine.get_transactions(account=checking)[0]
        self.assertEqual(txn.splits[1]['payee'].name, 'payee 1')

    @patch('builtins.input')
    def test_edit_txn(self, input_mock):
        checking = get_test_account()
        self.cli._engine._storage.save_account(checking)
        savings = get_test_account(name='Savings')
        self.cli._engine._storage.save_account(savings)
        another_account = get_test_account(name='Another')
        self.cli._engine._storage.save_account(another_account)
        txn = bb.Transaction(splits=[{'account': checking, 'amount': 5}, {'account': savings, 'amount': -5}], txn_date=date(2017, 1, 1))
        self.cli._engine.save_transaction(txn)

        input_mock.side_effect = [str(txn.id), '2017-02-13',
                '-90', '', '', '', '',
                '50', '', '', '', '',
                str(another_account.id), '40', '', '', '', '',
                '', 'new description']
        self.cli._edit_txn()

        edited_txn = self.cli._engine.get_transaction(id_=txn.id)
        self.assertEqual(edited_txn.txn_date, date(2017, 2, 13))
        self.assertEqual(edited_txn.splits[0], {'account': checking, 'action': '', 'amount': -90, 'quantity': -90, 'type': ''})
        self.assertEqual(edited_txn.splits[1], {'account': savings, 'action': '', 'amount': 50, 'quantity': 50, 'type': ''})
        self.assertEqual(edited_txn.splits[2], {'account': another_account, 'action': '', 'amount': 40, 'quantity': 40, 'type': ''})
        self.assertEqual(edited_txn.description, 'new description')
        buffer_value = self.memory_buffer.getvalue()
        self.assertTrue(f'{CHECKING} amount' in buffer_value)
        self.assertTrue('Savings amount' in buffer_value)

    @patch('builtins.input')
    def test_list_scheduled_txns(self, input_mock):
        input_mock.side_effect = ['', '']
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.cli._engine._storage.save_account(checking)
        self.cli._engine._storage.save_account(savings)
        valid_splits = [
                {'account': checking, 'amount': -101},
                {'account': savings, 'amount': 101},
            ]
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
            )
        self.cli._engine._storage.save_scheduled_transaction(st)
        self.cli._list_scheduled_txns()
        output = '1: weekly 1'
        buffer_value = self.memory_buffer.getvalue()
        self.assertTrue(buffer_value.startswith(output))

    @patch('builtins.input')
    def test_display_scheduled_txn(self, input_mock):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.cli._engine._storage.save_account(checking)
        self.cli._engine._storage.save_account(savings)
        valid_splits = [
                {'account': checking, 'amount': -101},
                {'account': savings, 'amount': 101},
            ]
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
            )
        self.cli._engine._storage.save_scheduled_transaction(st)
        input_mock.side_effect = [str(st.id)]
        self.cli._display_scheduled_txn()
        buffer_value = self.memory_buffer.getvalue()
        self.assertTrue('2019-01-02' in buffer_value)

    @patch('builtins.input')
    def test_enter_scheduled_txn(self, input_mock):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.cli._engine._storage.save_account(checking)
        self.cli._engine._storage.save_account(savings)
        self.cli._engine._storage.save_txn(
            bb.Transaction(
                txn_date=date(2018, 5, 13),
                splits=[{'account': checking, 'amount': 175}, {'account': savings, 'amount': -175}]
            )
        )
        valid_splits = [
            {'account': checking, 'amount': -101},
            {'account': savings, 'amount': 101},
        ]
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
            )
        self.cli._engine._storage.save_scheduled_transaction(st)
        input_mock.side_effect = [str(st.id), '2019-01-02',
                                  '-101', '', '',
                                  '101', '', '',
                                  '', # blank for no new account splits
                                  'description',
                                  '', # no more scheduled txns to enter
                                  '', # no scheduled txns to skip
                              ]
        self.cli._list_scheduled_txns()
        txns = self.cli._engine.get_transactions(account=checking)
        self.assertEqual(len(txns), 2)
        self.assertEqual(txns[0].splits[0]['amount'], 175)
        self.assertEqual(txns[1].splits[0], {'account': checking, 'action': '', 'amount': -101, 'quantity': -101, 'type': ''})
        self.assertEqual(txns[1].splits[1], {'account': savings, 'action': '', 'amount': 101, 'quantity': 101, 'type': ''})
        self.assertEqual(txns[1].txn_date, date(2019, 1, 2))
        scheduled_txn = self.cli._engine.get_scheduled_transaction(st.id)
        self.assertEqual(scheduled_txn.next_due_date, date(2019, 1, 9))

    @patch('builtins.input')
    def test_skip_scheduled_txn(self, input_mock):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.cli._engine._storage.save_account(checking)
        self.cli._engine._storage.save_account(savings)
        valid_splits = [
                {'account': checking, 'amount': -101},
                {'account': savings, 'amount': 101},
            ]
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
            )
        self.cli._engine._storage.save_scheduled_transaction(st)
        input_mock.side_effect = ['', str(st.id), '']
        self.cli._list_scheduled_txns()
        scheduled_txn = self.cli._engine._storage.get_scheduled_transaction(st.id)
        self.assertEqual(scheduled_txn.next_due_date, date(2019, 1, 9))
        txns = self.cli._engine.get_transactions(account=checking)
        self.assertEqual(txns, [])

    @patch('builtins.input')
    def test_create_scheduled_txn(self, input_mock):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        storage = self.cli._engine._storage
        storage.save_account(checking)
        storage.save_account(savings)
        input_mock.side_effect = ['weekly 1', 'weekly', '2020-01-16',
                                  '1', '-15', 'R', '',
                                  '2', '15', '', "'payee",
                                  '', 'desc']
        self.cli._create_scheduled_txn()
        scheduled_txns = storage.get_scheduled_transactions()
        self.assertEqual(len(scheduled_txns), 1)
        scheduled_txn = scheduled_txns[0]
        self.assertEqual(scheduled_txn.name, 'weekly 1')
        self.assertEqual(scheduled_txn.frequency, bb.ScheduledTransactionFrequency.WEEKLY)
        self.assertEqual(scheduled_txn.splits[0]['account'], checking)
        self.assertEqual(scheduled_txn.splits[0]['amount'], -15)
        self.assertEqual(scheduled_txn.splits[0]['status'], 'R')
        self.assertEqual(scheduled_txn.splits[1]['account'], savings)
        self.assertEqual(scheduled_txn.splits[1]['amount'], 15)
        self.assertEqual(scheduled_txn.splits[1]['payee'].name, 'payee')
        self.assertEqual(scheduled_txn.description, 'desc')

    @patch('builtins.input')
    def test_edit_scheduled_txn(self, input_mock):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        storage = self.cli._engine._storage
        storage.save_account(checking)
        storage.save_account(savings)
        valid_splits = [
                {'account': checking, 'amount': -101},
                {'account': savings, 'amount': 101},
            ]
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
            )
        storage.save_scheduled_transaction(st)
        input_mock.side_effect = [str(st.id),
                                  'weekly 1', 'weekly', '2020-01-16',
                                  '-15', '', '',
                                  '15', '', '\'payee',
                                  '', 'desc']
        self.cli._edit_scheduled_txn()
        scheduled_txns = storage.get_scheduled_transactions()
        self.assertEqual(len(scheduled_txns), 1)
        scheduled_txn = scheduled_txns[0]
        self.assertEqual(scheduled_txn.splits[0]['account'], checking)
        self.assertEqual(scheduled_txn.splits[0]['amount'], -15)
        self.assertEqual(scheduled_txn.splits[1]['account'], savings)
        self.assertEqual(scheduled_txn.splits[1]['amount'], 15)
        self.assertEqual(scheduled_txn.splits[1]['payee'].name, 'payee')
        self.assertEqual(scheduled_txn.frequency, bb.ScheduledTransactionFrequency.WEEKLY)
        self.assertEqual(scheduled_txn.description, 'desc')

    def test_list_budgets(self):
        storage = self.cli._engine._storage
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        wages = get_test_account(type_=bb.AccountType.INCOME, name='Wages')
        storage.save_account(wages)
        b = bb.Budget(year=2018, account_budget_info={
            housing: {'amount': 15, 'carryover': 0},
            food: {'amount': 25, 'carryover': 0},
            wages: {'amount': 100},
        })
        storage.save_budget(b)
        self.cli._list_budgets()
        output = '1: 2018-01-01 - 2018-12-31\n'
        buffer_value = self.memory_buffer.getvalue()
        self.assertEqual(buffer_value, output)

    @patch('builtins.input')
    def test_display_budget(self, input_mock):
        storage = self.cli._engine._storage
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        wages = get_test_account(type_=bb.AccountType.INCOME, name='Wages')
        storage.save_account(wages)
        b = bb.Budget(year=2018, account_budget_info={
            housing: {'amount': 15, 'carryover': 0},
            food: {'amount': 25, 'carryover': 0},
            wages: {'amount': 100},
        })
        storage.save_budget(b)
        input_mock.side_effect = [str(b.id)]
        self.cli._display_budget()
        buffer_value = self.memory_buffer.getvalue()
        self.assertTrue('2018-01-01 - 2018-12-31' in buffer_value)

    @patch('builtins.input')
    def test_display_budget_report(self, input_mock):
        storage = self.cli._engine._storage
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        wages = get_test_account(type_=bb.AccountType.INCOME, name='Wages')
        storage.save_account(wages)
        b = bb.Budget(year=2018, account_budget_info={
            housing: {'amount': 15, 'carryover': 0},
            food: {'amount': 25, 'carryover': 0},
            wages: {'amount': 100},
        })
        storage.save_budget(b)
        storage.save_txn(
                bb.Transaction(
                    txn_date='2019-01-13',
                    splits=[{'account': wages, 'amount': '-101'}, {'account': housing, 'amount': 101}],
                )
            )
        input_mock.side_effect = [str(b.id)]
        self.cli._display_budget_report()
        buffer_value = self.memory_buffer.getvalue()
        self.assertTrue('2018-01-01 - 2018-12-31' in buffer_value)

    @patch('builtins.input')
    def test_create_budget(self, input_mock):
        storage = self.cli._engine._storage
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        wages = get_test_account(type_=bb.AccountType.INCOME, name='Wages')
        storage.save_account(wages)
        input_mock.side_effect = ['2019-01-10', '2019-11-30', str(housing.id), '100', '', '', '']
        self.cli._create_budget()
        budget = storage.get_budgets()[0]
        self.assertEqual(budget.start_date, date(2019, 1, 10))
        self.assertEqual(budget.end_date, date(2019, 11, 30))
        budget_data = budget.get_budget_data()
        self.assertEqual(budget_data[housing], {'amount': 100})
        self.assertEqual(budget_data[food], {})
        self.assertEqual(budget_data[wages], {})

    @patch('builtins.input')
    def test_edit_budget(self, input_mock):
        storage = self.cli._engine._storage
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        wages = get_test_account(type_=bb.AccountType.INCOME, name='Wages')
        storage.save_account(wages)
        b = bb.Budget(year=2018, account_budget_info={
            housing: {'amount': 15, 'carryover': 0},
            food: {},
            wages: {'amount': 100},
        })
        storage.save_budget(b)
        input_mock.side_effect = [str(b.id), '2019-01-10', '2019-11-30', '40', '', '', '', '', '', '100', '', '']
        self.cli._edit_budget()
        budget = storage.get_budgets()[0]
        self.assertEqual(budget.start_date, date(2019, 1, 10))
        budget_data = budget.get_budget_data()
        self.assertEqual(budget_data[food]['amount'], 40)
        self.assertEqual(budget_data[housing], {})
        self.assertEqual(budget_data[wages]['amount'], 100)


class TestLoadTestData(unittest.TestCase):

    def test_load(self):
        storage = bb.SQLiteStorage(':memory:')
        load_test_data._load_data(storage, many_txns=False)
        accounts = storage.get_accounts()
        storage._db_connection.close()


class TestExport(unittest.TestCase):

    def test_export(self):
        engine = bb.Engine(':memory:')
        load_test_data._load_data(engine._storage, many_txns=False)
        with tempfile.TemporaryDirectory() as tmp:
            engine.export(directory=tmp)
            export_dir = os.listdir(tmp)[0]
            export_dir = os.path.join(tmp, export_dir)
            export_files = sorted(os.listdir(export_dir))

            with open(os.path.join(export_dir, 'accounts.tsv'), 'rb') as f:
                data = f.read().decode('utf8')
            lines = data.split('\n')
            self.assertEqual(lines[1], f'asset\t\t{CHECKING}')

            with open(os.path.join(export_dir, 'acc_chcing  .tsv'), 'rb') as f:
                data = f.read().decode('utf8')
            lines = data.split('\n')
            self.assertEqual(lines[1], '2018-01-01\t\t1,000.00\tOpening Balances')
        engine._storage._db_connection.close()


class TestImport(unittest.TestCase):

    def test_kmymoney(self):
        filename = 'import_test.kmy'
        engine = bb.Engine(':memory:')
        with open(filename, 'rb') as f:
            bb.import_kmymoney(kmy_file=f, engine=engine)
        currencies = engine.get_currencies()
        accounts = engine.get_accounts()
        self.assertEqual(len(accounts), 38)
        assets = engine.get_accounts(types=[bb.AccountType.ASSET])
        self.assertEqual(len(assets), 8)
        liabilities = engine.get_accounts(types=[bb.AccountType.LIABILITY])
        self.assertEqual(len(liabilities), 2)
        expenses = engine.get_accounts(types=[bb.AccountType.EXPENSE])
        self.assertEqual(len(expenses), 17)
        incomes = engine.get_accounts(types=[bb.AccountType.INCOME])
        self.assertEqual(len(incomes), 9)
        equities = engine.get_accounts(types=[bb.AccountType.EQUITY])
        self.assertEqual(len(equities), 2)
        securities = engine.get_accounts(types=[bb.AccountType.SECURITY])
        self.assertEqual(len(securities), 0)
        payees = engine.get_payees()
        self.assertEqual(len(payees), 2)
        checking = engine.get_account(name='Checking')
        self.assertEqual(checking.parent.name, 'Asset')
        self.assertEqual(checking.alternate_id, 'A000025')
        txns = engine.get_transactions(account=checking)
        self.assertEqual(len(txns), 4)
        self.assertEqual(txns[1].splits[0]['account'].name, 'Checking')
        self.assertNotIn('payee', txns[1].splits[0])
        self.assertEqual(txns[1].splits[1]['account'].name, 'Recreation')
        self.assertEqual(txns[1].splits[1]['payee'].name, 'A restaurant')
        self.assertEqual(txns[1].entry_date, date(2021, 1, 29))
        self.assertEqual(txns[1].alternate_id, 'T000000000000000002')
        self.assertEqual(txns[2].description, 'check-up visit')
        self.assertEqual(txns[2].splits[0]['account'].name, 'Checking')
        self.assertNotIn('description', txns[2].splits[0])
        self.assertEqual(txns[2].splits[1]['account'].name, 'Health/Medical')
        self.assertNotIn('description', txns[2].splits[1])
        balances = engine.get_current_balances_for_display(account=checking)
        expected_balances = bb.LedgerBalances(current='742.78', current_cleared='842.78')
        self.assertEqual(balances, expected_balances)
        mortgage = engine.get_account(name='Mortgage')
        mortgage_data = {
            'interest-rate-percent': Fraction(5),
            'fixed-interest': True,
            'term': '360m',
        }
        self.assertEqual(mortgage.other_data, mortgage_data)
        scheduled_txns = engine.get_scheduled_transactions()
        self.assertEqual(len(scheduled_txns), 1)
        engine._storage._db_connection.close()


if __name__ == '__main__':
    import sys
    print(sys.version)
    print(f'sqlite3: {sqlite3.sqlite_version_info}')

    unittest.main()
