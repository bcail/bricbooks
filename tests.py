from datetime import date
from decimal import Decimal as D
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, Mock, MagicMock

import pft
import load_test_data


def get_test_account(id_=None, name=None, type_=pft.AccountType.ASSET):
    if not name:
        name = 'Checking'
    return pft.Account(id_=id_, type_=type_, name=name)


class TestUtils(unittest.TestCase):

    def test_get_date(self):
        self.assertEqual(pft.get_date(date(2018, 1, 1)), date(2018, 1, 1))
        self.assertEqual(pft.get_date('2018-01-01'), date(2018, 1, 1))
        with self.assertRaises(RuntimeError):
            pft.get_date(10)


class TestAccount(unittest.TestCase):

    def test_init(self):
        a = pft.Account(id_=1, type_=pft.AccountType.ASSET, user_id='400', name='Checking')
        self.assertEqual(a.type, pft.AccountType.ASSET)
        self.assertEqual(a.name, 'Checking')
        self.assertEqual(a.parent, None)
        self.assertEqual(a.user_id, '400')

    def test_str(self):
        a = pft.Account(id_=1, type_=pft.AccountType.ASSET, user_id='400', name='Checking')
        self.assertEqual(str(a), '400 - Checking')

    def test_account_type(self):
        with self.assertRaises(pft.InvalidAccountError) as cm:
            pft.Account(id_=1, name='Checking')
        self.assertEqual(str(cm.exception), 'Account must have a type')
        with self.assertRaises(pft.InvalidAccountError) as cm:
            pft.Account(id_=1, type_='asdf', name='Checking')
        self.assertEqual(str(cm.exception), 'Invalid account type "asdf"')

    def test_eq(self):
        a = pft.Account(id_=1, type_=pft.AccountType.ASSET, name='Checking')
        a2 = pft.Account(id_=2, type_=pft.AccountType.ASSET, name='Savings')
        self.assertNotEqual(a, a2)
        self.assertEqual(a, a)
        a3 = pft.Account(type_=pft.AccountType.ASSET, name='Other')
        with self.assertRaises(pft.InvalidAccountError) as cm:
            a == a3
        self.assertEqual(str(cm.exception), "Can't compare accounts without an id")

    def test_parent(self):
        housing = pft.Account(id_=1, type_=pft.AccountType.EXPENSE, name='Housing')
        rent = pft.Account(id_=2, type_=pft.AccountType.EXPENSE, name='Rent', parent=housing)
        self.assertEqual(rent.parent, housing)

    def test_empty_strings_for_non_required_elements(self):
        a = pft.Account(id_=1, type_=pft.AccountType.EXPENSE, name='Test', user_id='')
        self.assertEqual(a.user_id, None)


class TestTransaction(unittest.TestCase):

    def setUp(self):
        self.checking = get_test_account(id_=1)
        self.savings = get_test_account(id_=2, name='Savings')
        self.valid_splits = {self.checking: 100, self.savings: -100}
        self.txn_splits = {self.checking: D(100), self.savings: D('-100')}

    def test_splits_required(self):
        with self.assertRaises(pft.InvalidTransactionError) as cm:
            pft.Transaction()
        self.assertEqual(str(cm.exception), 'transaction must have at least 2 splits')

    def test_splits_must_balance(self):
        with self.assertRaises(pft.InvalidTransactionError) as cm:
            pft.Transaction(splits={self.checking: -100, self.savings: 90})
        self.assertEqual(str(cm.exception), "splits don't balance")

    def test_invalid_split_amounts(self):
        with self.assertRaises(pft.InvalidTransactionError) as cm:
            pft.Transaction(splits={self.checking: 101.1, self.savings: '-101.1'})
        self.assertEqual(str(cm.exception), 'invalid split amount: 101.1')
        with self.assertRaises(pft.InvalidTransactionError) as cm:
            pft.Transaction(splits={self.checking: '123.456', self.savings: '-123.45'})
        self.assertEqual(str(cm.exception), 'no fractions of cents in a transaction')
        with self.assertRaises(pft.InvalidTransactionError) as cm:
            pft.Transaction(splits={self.checking: D('123.456'), self.savings: D(123)})
        self.assertEqual(str(cm.exception), 'no fractions of cents in a transaction')

    def test_invalid_txn_date(self):
        with self.assertRaises(pft.InvalidTransactionError) as cm:
            pft.Transaction(splits=self.valid_splits)
        self.assertEqual(str(cm.exception), 'transaction must have a txn_date')
        with self.assertRaises(pft.InvalidTransactionError) as cm:
            pft.Transaction(splits=self.valid_splits, txn_date=10)
        self.assertEqual(str(cm.exception), 'invalid txn_date "10"')

    def test_txn_date(self):
        t = pft.Transaction(splits=self.valid_splits, txn_date=date.today())
        self.assertEqual(t.txn_date, date.today())
        t = pft.Transaction(splits=self.valid_splits, txn_date='2018-03-18')
        self.assertEqual(t.txn_date, date(2018, 3, 18))

    def test_init(self):
        t = pft.Transaction(
                splits=self.valid_splits,
                txn_date=date.today(),
                txn_type='1234',
                payee='McDonalds',
                description='2 big macs',
            )
        self.assertEqual(t.splits, self.txn_splits)
        self.assertTrue(isinstance(t.splits[self.checking], D))
        self.assertEqual(t.txn_date, date.today())
        self.assertEqual(t.txn_type, '1234')
        self.assertEqual(t.payee, 'McDonalds')
        self.assertEqual(t.description, '2 big macs')
        self.assertEqual(t.status, None)
        #test passing status in as argument
        t = pft.Transaction(
                splits=self.valid_splits,
                txn_date=date.today(),
                status=pft.Transaction.CLEARED,
            )
        self.assertEqual(t.status, pft.Transaction.CLEARED)

    def test_sparse_init(self):
        #pass minimal amount of info into Transaction & verify values
        t = pft.Transaction(
                splits=self.valid_splits,
                txn_date=date.today(),
            )
        self.assertEqual(t.id, None)
        self.assertEqual(t.txn_type, None)
        self.assertEqual(t.payee, None)
        self.assertEqual(t.description, None)
        self.assertEqual(t.status, None)

    def test_txn_from_user_info(self):
        #construct txn from user strings, as much as possible (except account & categories)
        t = pft.Transaction.from_user_info(
                account=self.checking,
                txn_type='1234',
                deposit='101',
                withdrawal='',
                txn_date='2017-10-15',
                description='something',
                payee='McDonalds',
                status='C',
                categories=self.savings, #what to call this? it's the other accounts, the categories, ... (& many times, it's just one expense account)
            )
        self.assertEqual(t.splits, {
            self.checking: D(101),
            self.savings: D('-101'),
        })

    def test_txn_status(self):
        splits={
            self.checking: '-101',
            self.savings: '101',
        }
        t = pft.Transaction(
                splits=splits,
                txn_date=date.today(),
                status='c',
            )
        self.assertEqual(t.status, 'C')
        t = pft.Transaction(
                splits=splits,
                txn_date=date.today(),
                status='',
            )
        self.assertEqual(t.status, None)
        with self.assertRaises(pft.InvalidTransactionError) as cm:
            pft.Transaction(
                    splits=splits,
                    txn_date=date.today(),
                    status='d',
                )
        self.assertEqual(str(cm.exception), 'invalid status "d"')

    def test_txn_splits_from_user_info(self):
        #test passing in list, just one account, ...
        house = get_test_account(id_=3, name='House')
        splits = pft.Transaction.splits_from_user_info(
                account=self.checking,
                deposit='',
                withdrawal='100',
                input_categories={self.savings: -45, house: -55}
            )
        self.assertEqual(splits,
                {
                    self.checking: '-100',
                    self.savings: -45,
                    house: -55,
                }
            )

    def test_get_display_strings(self):
        t = pft.Transaction(
                splits=self.valid_splits,
                txn_type='1234',
                txn_date=date.today(),
                description='something',
                payee='McDonalds',
                status='C',
            )
        self.assertDictEqual(
                t.get_display_strings_for_ledger(account=self.checking),
                {
                    'txn_type': '1234',
                    'withdrawal': '',
                    'deposit': '100',
                    'description': 'something',
                    'txn_date': str(date.today()),
                    'payee': 'McDonalds',
                    'status': 'C',
                    'categories': 'Savings',
                }
            )
        self.assertDictEqual(
                t.get_display_strings_for_ledger(account=self.savings),
                {
                    'txn_type': '1234',
                    'withdrawal': '100',
                    'deposit': '',
                    'description': 'something',
                    'txn_date': str(date.today()),
                    'payee': 'McDonalds',
                    'status': 'C',
                    'categories': 'Checking',
                }
            )

    def test_get_display_strings_sparse(self):
        t = pft.Transaction(
                splits=self.valid_splits,
                txn_date=date.today(),
            )
        self.assertDictEqual(t.get_display_strings_for_ledger(account=self.checking),
                {
                    'txn_type': '',
                    'withdrawal': '',
                    'deposit': '100',
                    'description': '',
                    'txn_date': str(date.today()),
                    'payee': '',
                    'status': '',
                    'categories': 'Savings',
                }
            )

    def test_txn_categories_display(self):
        a = get_test_account(id_=1)
        a2 = get_test_account(id_=2, name='Savings')
        a3 = get_test_account(id_=3, name='Other')
        t = pft.Transaction(
                splits={
                    a: -100,
                    a2: 65,
                    a3: 35
                },
                txn_date=date.today(),
            )
        self.assertEqual(t._categories_display(main_account=a), 'multiple')
        t = pft.Transaction(
                splits={
                    a: -100,
                    a2: 100
                },
                txn_date=date.today(),
            )
        self.assertEqual(t._categories_display(main_account=a), 'Savings')

    def test_update_values(self):
        t = pft.Transaction(
                splits=self.valid_splits,
                txn_date=date.today(),
                txn_type='BP',
                payee='Wendys',
                description='salad',
            )
        t.update_from_user_info(
                txn_type='1234',
                txn_date='2017-10-15',
            )
        self.assertEqual(t.txn_type, '1234')
        self.assertEqual(t.payee, 'Wendys')
        self.assertEqual(t.txn_date, date(2017, 10, 15))

    def test_update_values_make_it_empty(self):
        t = pft.Transaction(
                splits=self.valid_splits,
                txn_date=date.today(),
                txn_type='1234',
                payee='Arbys',
                description='roast beef',
            )
        t.update_from_user_info(payee='')
        self.assertEqual(t.payee, '')

    def test_update_values_errors(self):
        t = pft.Transaction(
                splits=self.valid_splits,
                txn_date=date.today(),
                txn_type='1234',
                payee='Cracker Barrel',
                description='meal',
            )
        with self.assertRaises(pft.InvalidTransactionError) as cm:
            t.update_from_user_info(account=self.checking, deposit='ab')
        self.assertEqual(str(cm.exception), 'invalid deposit/withdrawal')
        with self.assertRaises(pft.InvalidTransactionError) as cm:
            t.update_from_user_info(txn_date='ab')
        self.assertEqual(str(cm.exception), 'invalid txn_date "ab"')

    def test_update_values_deposit_withdrawal(self):
        t = pft.Transaction(
                splits=self.valid_splits,
                txn_date=date.today(),
            )
        t.update_from_user_info(account=self.savings, withdrawal='50', categories=self.checking)
        self.assertEqual(t.splits,
                {self.checking: D(50), self.savings: D('-50')})
        t.update_from_user_info(account=self.savings, deposit='25', categories=self.checking)
        self.assertEqual(t.splits,
                {self.checking: D('-25'), self.savings: D(25)})


class TestLedger(unittest.TestCase):

    def setUp(self):
        self.checking = get_test_account(id_=1)
        self.savings = get_test_account(id_=2, name='Savings')

    def test_init(self):
        with self.assertRaises(pft.InvalidLedgerError) as cm:
            pft.Ledger()
        self.assertEqual(str(cm.exception), 'ledger must have an account')
        ledger = pft.Ledger(account=self.checking)
        self.assertEqual(ledger.account, self.checking)

    def test_add_transaction(self):
        ledger = pft.Ledger(account=self.checking)
        self.assertEqual(ledger._txns, {})
        splits = {self.checking: 100, self.savings: -100}
        txn = pft.Transaction(id_=1, splits=splits, txn_date=date.today())
        ledger.add_transaction(txn)
        self.assertEqual(ledger._txns, {1: txn})

    def test_get_ledger_txns(self):
        ledger = pft.Ledger(account=self.checking)
        splits1 = {self.checking: '32.45', self.savings: '-32.45'}
        splits2 = {self.checking: -12, self.savings: 12}
        splits3 = {self.checking: 1, self.savings: -1}
        splits4 = {self.checking: 10, self.savings: -10}
        ledger.add_transaction(pft.Transaction(id_=1, splits=splits1, txn_date=date(2017, 8, 5)))
        ledger.add_transaction(pft.Transaction(id_=2, splits=splits2, txn_date=date(2017, 6, 5)))
        ledger.add_transaction(pft.Transaction(id_=3, splits=splits3, txn_date=date(2017, 7, 30)))
        ledger.add_transaction(pft.Transaction(id_=4, splits=splits4, txn_date=date(2017, 4, 25)))
        ledger_records = ledger.get_sorted_txns_with_balance()
        self.assertEqual(ledger_records[0].txn_date, date(2017, 4, 25))
        self.assertEqual(ledger_records[0].balance, D(10))
        self.assertEqual(ledger_records[1].txn_date, date(2017, 6, 5))
        self.assertEqual(ledger_records[1].balance, D(-2))
        self.assertEqual(ledger_records[2].txn_date, date(2017, 7, 30))
        self.assertEqual(ledger_records[2].balance, D(-1))
        self.assertEqual(ledger_records[3].txn_date, date(2017, 8, 5))
        self.assertEqual(ledger_records[3].balance, D('31.45'))

    def test_search(self):
        ledger = pft.Ledger(account=self.checking)
        splits1 = {self.checking: '32.45', self.savings: '-32.45'}
        splits2 = {self.checking: -12, self.savings: 12}
        splits3 = {self.checking: 1, self.savings: -1}
        splits4 = {self.checking: 10, self.savings: -10}
        ledger.add_transaction(pft.Transaction(id_=1, splits=splits1, payee='someone', txn_date=date(2017, 8, 5)))
        ledger.add_transaction(pft.Transaction(id_=2, splits=splits2, txn_date=date(2017, 6, 5)))
        ledger.add_transaction(pft.Transaction(id_=3, splits=splits3, description='Some description', txn_date=date(2017, 7, 30)))
        ledger.add_transaction(pft.Transaction(id_=4, splits=splits4, txn_date=date(2017, 4, 25)))
        results = ledger.search('some')
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].description, 'Some description')

    def test_get_txn(self):
        ledger = pft.Ledger(account=self.checking)
        splits1 = {self.checking: '-32.45', self.savings: '32.45'}
        splits2 = {self.checking: -12, self.savings: 12}
        ledger.add_transaction(pft.Transaction(id_=1, splits=splits1, txn_date=date(2017, 8, 5)))
        ledger.add_transaction(pft.Transaction(id_=2, splits=splits2, txn_date=date(2017, 6, 5)))
        txn = ledger.get_txn(id_=2)
        self.assertEqual(txn.splits[self.checking], D('-12'))

    def test_clear_txns(self):
        ledger = pft.Ledger(account=self.checking)
        splits = {self.checking: 100, self.savings: -100}
        ledger.add_transaction(pft.Transaction(id_=1, splits=splits, txn_date=date(2017, 8, 5)))
        ledger.clear_txns()
        self.assertEqual(ledger.get_sorted_txns_with_balance(), [])

    def test_get_payees(self):
        ledger = pft.Ledger(account=self.checking)
        splits = {self.checking: '12.34', self.savings: '-12.34'}
        ledger.add_transaction(pft.Transaction(id_=1, splits=splits, txn_date=date(2017, 8, 5), payee='McDonalds'))
        ledger.add_transaction(pft.Transaction(id_=2, splits=splits, txn_date=date(2017, 8, 5), payee='Burger King'))
        ledger.add_transaction(pft.Transaction(id_=3, splits=splits, txn_date=date(2017, 8, 5), payee='Burger King'))
        self.assertEqual(ledger.get_payees(), ['Burger King', 'McDonalds'])


class TestScheduledTransaction(unittest.TestCase):

    def setUp(self):
        self.checking = get_test_account(id_=1)
        self.savings = get_test_account(id_=2, name='Savings')
        self.valid_splits={
             self.checking: -101,
             self.savings: 101,
        }

    def test_invalid_frequency(self):
        with self.assertRaises(pft.InvalidScheduledTransactionError) as cm:
            pft.ScheduledTransaction(
                name='w',
                frequency='weekly',
                next_due_date='2019-01-01',
                splits=self.valid_splits,
            )
        self.assertEqual(str(cm.exception), 'invalid frequency "weekly"')

    def test_invalid_splits(self):
        with self.assertRaises(pft.InvalidTransactionError) as cm:
            pft.ScheduledTransaction(
                name='w',
                frequency=pft.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-01',
                splits={},
            )
        self.assertEqual(str(cm.exception), 'transaction must have at least 2 splits')

    def test_invalid_next_due_date(self):
        with self.assertRaises(pft.InvalidScheduledTransactionError) as cm:
            pft.ScheduledTransaction(
                name='w',
                frequency=pft.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='abcd',
                splits=self.valid_splits,
            )
        self.assertEqual(str(cm.exception), 'invalid date "abcd"')
        with self.assertRaises(pft.InvalidScheduledTransactionError) as cm:
            pft.ScheduledTransaction(
                name='w',
                frequency=pft.ScheduledTransactionFrequency.WEEKLY,
                next_due_date=None,
                splits=self.valid_splits,
            )
        self.assertEqual(str(cm.exception), 'invalid date "None"')

    def test_init(self):
        st = pft.ScheduledTransaction(
                name='weekly 1',
                frequency=pft.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=self.valid_splits,
                txn_type='a',
                payee='Wendys',
                description='something',
            )
        self.assertEqual(st.name, 'weekly 1')
        self.assertEqual(st.frequency, pft.ScheduledTransactionFrequency.WEEKLY)
        self.assertEqual(st.next_due_date, date(2019, 1, 2))
        self.assertEqual(st.splits, self.valid_splits)
        self.assertEqual(st.txn_type, 'a')
        self.assertEqual(st.payee, 'Wendys')
        self.assertEqual(st.description, 'something')


class TestBudget(unittest.TestCase):

    def test_init_dates(self):
        with self.assertRaises(pft.BudgetError) as cm:
            pft.Budget()
        self.assertEqual(str(cm.exception), 'must pass in dates')
        b = pft.Budget(year=2018, account_budget_info={})
        self.assertEqual(b.start_date, date(2018, 1, 1))
        self.assertEqual(b.end_date, date(2018, 12, 31))
        b = pft.Budget(year='2018', account_budget_info={})
        self.assertEqual(b.start_date, date(2018, 1, 1))
        b = pft.Budget(start_date=date(2018, 1, 15), end_date=date(2019, 1, 14), account_budget_info={})
        self.assertEqual(b.start_date, date(2018, 1, 15))
        self.assertEqual(b.end_date, date(2019, 1, 14))

    def test_init(self):
        housing = get_test_account(id_=1, type_=pft.AccountType.EXPENSE, name='Housing')
        food = get_test_account(id_=2, type_=pft.AccountType.EXPENSE, name='Food')
        transportation = get_test_account(id_=3, type_=pft.AccountType.EXPENSE, name='Transportation')
        account_budget_info = {
                housing: {'amount': D(15), 'carryover': D(5), 'notes': 'some important info'},
                food: {'amount': '35', 'carryover': ''},
                transportation: {},
            }
        b = pft.Budget(year=2018, account_budget_info=account_budget_info)
        self.assertEqual(b.get_budget_data(),
                {housing: {'amount': D(15), 'carryover': D(5), 'notes': 'some important info'}, food: {'amount': D(35)}, transportation: {}})

    def test_percent_rounding(self):
        self.assertEqual(pft.Budget.round_percent_available(D('1.1')), D(1))
        self.assertEqual(pft.Budget.round_percent_available(D('1.8')), D(2))
        self.assertEqual(pft.Budget.round_percent_available(D('1.5')), D(2))
        self.assertEqual(pft.Budget.round_percent_available(D('2.5')), D(3))

    def test_get_report_display(self):
        housing = get_test_account(id_=1, type_=pft.AccountType.EXPENSE, name='Housing')
        food = get_test_account(id_=2, type_=pft.AccountType.EXPENSE, name='Food')
        transportation = get_test_account(id_=3, type_=pft.AccountType.EXPENSE, name='Transportation')
        something = get_test_account(id_=4, type_=pft.AccountType.EXPENSE, name='Something')
        wages = get_test_account(id_=5, type_=pft.AccountType.INCOME, name='Wages')
        account_budget_info = {
                housing: {'amount': D(15), 'carryover': D(5)},
                food: {},
                transportation: {'amount': D(10)},
                something: {'amount': D(0)},
                wages: {'amount': D(100)},
            }
        budget = pft.Budget(year=2018, account_budget_info=account_budget_info)
        with self.assertRaises(pft.BudgetError) as cm:
            budget.get_report_display()
        self.assertEqual(str(cm.exception), 'must pass in income_spending_info to get the report display')
        income_spending_info = {housing: {'income': D(5), 'spent': D(10)}, food: {}, wages: {'income': D(80)}}
        budget = pft.Budget(year=2018, account_budget_info=account_budget_info, income_spending_info=income_spending_info)
        budget_report = budget.get_report_display()
        housing_info = budget_report['expense'][housing]
        self.assertEqual(housing_info['amount'], '15')
        self.assertEqual(housing_info['carryover'], '5')
        self.assertEqual(housing_info['income'], '5')
        self.assertEqual(housing_info['total_budget'], '25')
        self.assertEqual(housing_info['spent'], '10')
        self.assertEqual(housing_info['remaining'], '15')
        self.assertEqual(housing_info['percent_available'], '60%')
        food_info = budget_report['expense'][food]
        self.assertEqual(food_info,
                {
                    'amount': '',
                    'income': '',
                    'carryover': '',
                    'total_budget': '',
                    'spent': '',
                    'remaining': '',
                    'percent_available': '',
                }
            )
        transportation_info = budget_report['expense'][transportation]
        self.assertEqual(transportation_info,
                {
                    'amount': '10',
                    'income': '',
                    'carryover': '',
                    'total_budget': '10',
                    'spent': '',
                    'remaining': '10',
                    'percent_available': '100%',
                }
            )
        wages_info = budget_report['income'][wages]
        self.assertEqual(wages_info,
                {
                    'amount': '100',
                    'income': '80',
                    'percent': '80%',
                    'remaining': '20',
                }
            )


TABLES = [('accounts',), ('budgets',), ('budget_values',), ('scheduled_transactions',), ('scheduled_txn_splits',), ('transactions',), ('txn_splits',)]


class TestSQLiteStorage(unittest.TestCase):

    def setUp(self):
        self.file_name =  'testsuite.sqlite3'
        try:
            os.remove(self.file_name)
        except FileNotFoundError:
            pass

    def tearDown(self):
        try:
            os.remove(self.file_name)
        except FileNotFoundError:
            pass

    def test_init(self):
        storage = pft.SQLiteStorage(':memory:')
        tables = storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, TABLES)

    def test_init_no_file(self):
        storage = pft.SQLiteStorage(self.file_name)
        tables = storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, TABLES)

    def test_init_empty_file(self):
        with open(self.file_name, 'wb') as f:
            pass
        storage = pft.SQLiteStorage(self.file_name)
        tables = storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, TABLES)

    def test_init_db_already_setup(self):
        #set up file
        init_storage = pft.SQLiteStorage(self.file_name)
        tables = init_storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, TABLES)
        #and now open it again and make sure everything's fine
        storage = pft.SQLiteStorage(self.file_name)
        tables = init_storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, TABLES)

    def test_save_account(self):
        storage = pft.SQLiteStorage(':memory:')
        assets = pft.Account(type_=pft.AccountType.ASSET, name='All Assets')
        storage.save_account(assets)
        checking = pft.Account(type_=pft.AccountType.ASSET, user_id='4010', name='Checking', parent=assets)
        storage.save_account(checking)
        #make sure we save the id to the account object
        self.assertEqual(assets.id, 1)
        self.assertEqual(checking.id, 2)
        c = storage._db_connection.cursor()
        c.execute('SELECT * FROM accounts WHERE id = ?', (checking.id,))
        db_info = c.fetchone()
        self.assertEqual(db_info,
                (checking.id, pft.AccountType.ASSET.value, '4010', 'Checking', assets.id))
        savings = pft.Account(id_=checking.id, type_=pft.AccountType.ASSET, name='Savings')
        storage.save_account(savings)
        c.execute('SELECT * FROM accounts WHERE id = ?', (savings.id,))
        db_info = c.fetchall()
        self.assertEqual(db_info,
                [(savings.id, pft.AccountType.ASSET.value, None, 'Savings', None)])

    def test_get_account(self):
        storage = pft.SQLiteStorage(':memory:')
        c = storage._db_connection.cursor()
        c.execute('INSERT INTO accounts(type, user_id, name) VALUES (?, ?, ?)', (pft.AccountType.EXPENSE.value, '4010', 'Checking'))
        account_id = c.lastrowid
        c.execute('INSERT INTO accounts(type, name, parent_id) VALUES (?, ?, ?)', (pft.AccountType.EXPENSE.value, 'Sub-Checking', account_id))
        sub_checking_id = c.lastrowid
        account = storage.get_account(account_id)
        self.assertEqual(account.id, account_id)
        self.assertEqual(account.type, pft.AccountType.EXPENSE)
        self.assertEqual(account.user_id, '4010')
        self.assertEqual(account.name, 'Checking')
        self.assertEqual(account.parent, None)
        sub_checking = storage.get_account(sub_checking_id)
        self.assertEqual(sub_checking.parent, account)

    def test_get_accounts(self):
        storage = pft.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        savings = get_test_account(name='Savings')
        storage.save_account(savings)
        housing = get_test_account(type_=pft.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        accounts = storage.get_accounts()
        self.assertEqual(len(accounts), 3)
        self.assertEqual(accounts[0].name, 'Checking')
        self.assertEqual(accounts[1].name, 'Savings')
        self.assertEqual(accounts[2].name, 'Housing')
        accounts = storage.get_accounts(type_=pft.AccountType.EXPENSE)
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].name, 'Housing')

    def test_txn_to_db(self):
        storage = pft.SQLiteStorage(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        storage.save_account(checking)
        storage.save_account(savings)
        t = pft.Transaction(
                splits={checking: D('-101'), savings: D(101)},
                txn_date=date.today(),
                txn_type='',
                payee='Chick-fil-A',
                description='chicken sandwich',
                status=pft.Transaction.CLEARED,
            )
        storage.save_txn(t)
        #make sure we save the id to the txn object
        self.assertEqual(t.id, 1)
        c = storage._db_connection.cursor()
        c.execute('SELECT * FROM transactions')
        db_info = c.fetchone()
        self.assertEqual(db_info,
                (1, '', date.today().strftime('%Y-%m-%d'), 'Chick-fil-A', 'chicken sandwich', pft.Transaction.CLEARED))
        c.execute('SELECT * FROM txn_splits')
        txn_split_records = c.fetchall()
        self.assertEqual(txn_split_records, [(1, 1, 1, '-101'),
                                             (2, 1, 2, '101')])

    def test_sparse_txn_to_db(self):
        storage = pft.SQLiteStorage(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        storage.save_account(checking)
        storage.save_account(savings)
        t = pft.Transaction(
                splits={checking: '101', savings: '-101'},
                txn_date=date.today(),
            )
        storage.save_txn(t)
        c = storage._db_connection.cursor()
        c.execute('SELECT * FROM transactions')
        db_info = c.fetchone()
        self.assertEqual(db_info,
                (1, None, date.today().strftime('%Y-%m-%d'), None, None, None))
        c.execute('SELECT * FROM txn_splits')
        txn_split_records = c.fetchall()
        self.assertEqual(txn_split_records, [(1, 1, 1, '101'),
                                             (2, 1, 2, '-101')])

    def test_round_trip(self):
        storage = pft.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        savings = get_test_account(name='Savings')
        storage.save_account(savings)
        #create txn & save it
        t = pft.Transaction(
                splits={checking: D('-101'), savings: D(101)},
                txn_date=date.today(),
            )
        storage.save_txn(t)
        #read it back from the db
        txn = storage.get_txn(t.id)
        #update it & save it to db again
        self.assertEqual(txn.txn_type, None)
        self.assertEqual(txn.payee, None)
        txn.txn_type = '123'
        txn.payee = 'Five Guys'
        storage.save_txn(txn)
        #verify db record
        txn_records = storage._db_connection.cursor().execute('SELECT * FROM transactions').fetchall()
        self.assertEqual(len(txn_records), 1)
        new_txn = storage.get_txn(txn.id)
        self.assertEqual(new_txn.txn_type, '123')
        self.assertEqual(new_txn.payee, 'Five Guys')

    def test_get_account_ledger(self):
        storage = pft.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        savings = get_test_account(name='Savings')
        storage.save_account(savings)
        savings2 = get_test_account(name='Savings 2')
        storage.save_account(savings2)
        txn1 = pft.Transaction(txn_type='BP', txn_date=date(2017, 1, 25), payee='Pizza Hut', description='inv #1', status=pft.Transaction.CLEARED,
                splits={checking: '101', savings: '-101'})
        storage.save_txn(txn1)
        txn2 = pft.Transaction(txn_type='BP', txn_date=date(2017, 1, 28), payee='Subway', description='inv #42', status=pft.Transaction.CLEARED,
                splits={checking: '46.23', savings:'-46.23'})
        storage.save_txn(txn2)
        txn3 = pft.Transaction(txn_type='BP', txn_date=date(2017, 1, 28), payee='Subway', description='inv #42', status=pft.Transaction.CLEARED,
                splits={savings2: '-6.53', savings: '6.53'})
        storage.save_txn(txn3)
        ledger = storage.get_account_ledger(account=checking)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(len(txns), 2)
        self.assertEqual(txns[0].splits[checking], D('101'))
        self.assertEqual(txns[1].splits[checking], D('46.23'))

    def test_delete_txn_from_db(self):
        storage = pft.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        savings = get_test_account(name='Savings')
        storage.save_account(savings)
        txn = pft.Transaction(txn_type='BP', txn_date=date(2017, 1, 25), payee='Waffle House',
                splits={checking: '101', savings: '-101'})
        storage.save_txn(txn)
        txn2 = pft.Transaction(txn_date=date(2017, 1, 28), payee='Subway',
                splits={checking: '46.23', savings: '-46.23'})
        storage.save_txn(txn2)
        storage.delete_txn(txn.id)
        c = storage._db_connection.cursor()
        c.execute('SELECT txn_date FROM transactions')
        txn_records = c.fetchall()
        self.assertEqual(len(txn_records), 1)
        self.assertEqual(txn_records[0][0], '2017-01-28')
        txn_splits_records = c.execute('SELECT txn_id FROM txn_splits').fetchall()
        self.assertEqual(len(txn_splits_records), 2)
        self.assertEqual([r[0] for r in txn_splits_records], [txn2.id, txn2.id])

    def test_save_budget(self):
        storage = pft.SQLiteStorage(':memory:')
        housing = get_test_account(type_=pft.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=pft.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        account_budget_info = {
                housing: {'amount': D(15), 'carryover': D(0), 'notes': 'hello'},
                food: {'amount': D(25), 'carryover': D(10)}
            }
        b = pft.Budget(year=2018, account_budget_info=account_budget_info)
        storage.save_budget(b)
        cursor = storage._db_connection.cursor()
        records = cursor.execute('SELECT * FROM budgets WHERE start_date = "2018-01-01"').fetchall()
        self.assertEqual(len(records), 1)
        self.assertEqual(b.id, 1)
        records = cursor.execute('SELECT * FROM budget_values').fetchall()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0][1], 1)
        self.assertEqual(records[0][2], 1)
        self.assertEqual(records[0][3], '15')
        self.assertEqual(records[0][4], '0')
        self.assertEqual(records[0][5], 'hello')
        self.assertEqual(records[1][1], 1)
        self.assertEqual(records[1][2], 2)
        self.assertEqual(records[1][3], '25')
        self.assertEqual(records[1][4], '10')
        #test that old budget values are deleted
        b = pft.Budget(year=2018, account_budget_info={
                housing: {'amount': D(35), 'carryover': D(0)},
                food: {'amount': D(45), 'carryover': D(0)},
            }, id_=b.id)
        storage.save_budget(b)
        records = cursor.execute('SELECT * FROM budgets').fetchall()
        self.assertEqual(len(records), 1)
        records = cursor.execute('SELECT amount FROM budget_values ORDER BY amount').fetchall()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0][0], '35')

    def test_save_budget_empty_category_info(self):
        storage = pft.SQLiteStorage(':memory:')
        housing = get_test_account(type_=pft.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=pft.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        account_budget_info = {
                housing: {'amount': D(15), 'carryover': D(0)},
                food: {},
            }
        b = pft.Budget(year=2018, account_budget_info=account_budget_info)
        storage.save_budget(b)
        cursor = storage._db_connection.cursor()
        records = cursor.execute('SELECT * FROM budgets').fetchall()
        self.assertEqual(len(records), 1)
        records = cursor.execute('SELECT amount FROM budget_values ORDER BY amount').fetchall()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][0], '15')

    def test_save_budget_file(self):
        #test that save actually gets committed
        storage = pft.SQLiteStorage(self.file_name)
        housing = get_test_account(type_=pft.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=pft.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        b = pft.Budget(year=2018, account_budget_info={
            housing: {'amount': D(15), 'carryover': D(0)},
            food: {'amount': D(25), 'carryover': D(0)},
        })
        storage.save_budget(b)
        storage = pft.SQLiteStorage(self.file_name)
        cursor = storage._db_connection.cursor()
        records = cursor.execute('SELECT * FROM budgets WHERE start_date = "2018-01-01"').fetchall()
        self.assertEqual(len(records), 1)

    def test_get_budget(self):
        storage = pft.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        savings = get_test_account(name='Savings')
        storage.save_account(savings)
        housing = get_test_account(type_=pft.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=pft.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        transportation = get_test_account(type_=pft.AccountType.EXPENSE, name='Transportation')
        storage.save_account(transportation)
        txn1 = pft.Transaction(txn_date=date(2017, 1, 25),
                splits={checking: '-101', housing: '101'})
        txn2 = pft.Transaction(txn_date=date(2017, 2, 28),
                splits={checking: '-46.23', food: '46.23'})
        txn3 = pft.Transaction(txn_date=date(2017, 3, 28),
                splits={savings: '-56.23', food: '56.23'})
        txn4 = pft.Transaction(txn_date=date(2017, 4, 28),
                splits={checking: '-15', savings: 15})
        txn5 = pft.Transaction(txn_date=date(2017, 5, 28),
                splits={checking: 15, food: '-15'})
        for t in [txn1, txn2, txn3, txn4, txn5]:
            storage.save_txn(t)
        cursor = storage._db_connection.cursor()
        cursor.execute('INSERT INTO budgets (start_date, end_date) VALUES (?, ?)', ('2018-01-01', '2018-12-31'))
        budget_id = cursor.lastrowid
        cursor.execute('INSERT INTO budget_values (budget_id, account_id, amount, notes) VALUES (?, ?, ?, ?)', (budget_id, housing.id, '135', 'hello'))
        cursor.execute('INSERT INTO budget_values (budget_id, account_id, amount, carryover) VALUES (?, ?, ?, ?)', (budget_id, food.id, '70', '15'))
        budget = storage.get_budget(budget_id)
        self.assertEqual(budget.id, budget_id)
        self.assertEqual(budget.start_date, date(2018, 1, 1))
        self.assertEqual(budget.end_date, date(2018, 12, 31))

        report_display = budget.get_report_display()['expense']
        self.assertEqual(report_display[housing]['amount'], '135')
        self.assertEqual(report_display[housing]['carryover'], '')
        self.assertEqual(report_display[housing]['income'], '')
        self.assertEqual(report_display[housing]['spent'], '101')
        self.assertEqual(report_display[housing]['notes'], 'hello')

        self.assertEqual(report_display[food]['amount'], '70')
        self.assertEqual(report_display[food]['carryover'], '15')
        self.assertEqual(report_display[food]['income'], '15')
        self.assertEqual(report_display[food]['spent'], '102.46')

        self.assertEqual(report_display[transportation]['amount'], '')
        self.assertEqual(report_display[transportation]['spent'], '')

    def test_get_budget_reports(self):
        storage = pft.SQLiteStorage(':memory:')
        housing = get_test_account(type_=pft.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=pft.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        cursor = storage._db_connection.cursor()
        cursor.execute('INSERT INTO budgets (start_date, end_date) VALUES (?, ?)', ('2018-01-01', '2018-12-31'))
        budget_id = cursor.lastrowid
        cursor.execute('INSERT INTO budget_values (budget_id, account_id, amount) VALUES (?, ?, ?)', (budget_id, housing.id, '35'))
        cursor.execute('INSERT INTO budget_values (budget_id, account_id, amount) VALUES (?, ?, ?)', (budget_id, food.id, '70'))
        budgets = storage.get_budgets()
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets[0].start_date, date(2018, 1, 1))
        self.assertEqual(budgets[0].end_date, date(2018, 12, 31))
        expense_account = list(budgets[0].get_report_display()['expense'].keys())[0]
        self.assertEqual(expense_account.name, 'Housing')

    def test_save_scheduled_txn(self):
        checking = get_test_account(id_=1)
        savings = get_test_account(id_=2, name='Savings')
        valid_splits={
             checking: -101,
             savings: 101,
        }
        storage = pft.SQLiteStorage(':memory:')
        storage.save_account(checking)
        storage.save_account(savings)
        st = pft.ScheduledTransaction(
                name='weekly 1',
                frequency=pft.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
                txn_type='a',
                payee='Wendys',
                description='something',
            )
        storage.save_scheduled_transaction(st)
        st_records = storage._db_connection.execute('SELECT * FROM scheduled_transactions').fetchall()
        self.assertEqual(len(st_records), 1)
        self.assertEqual(st_records[0],
                (1, 'weekly 1', pft.ScheduledTransactionFrequency.WEEKLY.value, '2019-01-02', 'a', 'Wendys', 'something'))


def fake_method():
    pass


class TestQtGUI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication([])

    def test_pft_qt_gui(self):
        pft_qt_gui = pft.PFT_GUI_QT(':memory:')

    def test_account(self):
        storage = pft.SQLiteStorage(':memory:')
        a = get_test_account()
        storage.save_account(a)
        accounts_display = pft.AccountsDisplay(storage, reload_accounts=fake_method)
        widget = accounts_display.get_widget()
        accounts_display.add_account_widgets['entries']['user_id'].setText('400')
        accounts_display.add_account_widgets['entries']['name'].setText('Savings')
        accounts_display.add_account_widgets['entries']['parent'].setCurrentIndex(1)
        QtTest.QTest.mouseClick(accounts_display.add_account_widgets['buttons']['add_new'], QtCore.Qt.LeftButton)
        accounts = storage.get_accounts()
        self.assertEqual(len(accounts), 2)
        self.assertEqual(accounts[1].type.name, 'ASSET')
        self.assertEqual(accounts[1].user_id, '400')
        self.assertEqual(accounts[1].name, 'Savings')
        self.assertEqual(accounts[1].parent.name, 'Checking')

    def test_account_edit(self):
        storage = pft.SQLiteStorage(':memory:')
        checking = pft.Account(type_=pft.AccountType.ASSET, name='Checking')
        storage.save_account(checking)
        savings = pft.Account(type_=pft.AccountType.ASSET, name='Savings')
        storage.save_account(savings)
        accounts_display = pft.AccountsDisplay(storage, reload_accounts=fake_method)
        widget = accounts_display.get_widget()
        QtTest.QTest.mouseClick(accounts_display.accounts_widgets[savings.id]['labels']['name'], QtCore.Qt.LeftButton)
        accounts_display.accounts_widgets[savings.id]['entries']['name'].setText('New Savings')
        accounts_display.accounts_widgets[savings.id]['entries']['parent'].setCurrentIndex(1)
        QtTest.QTest.mouseClick(accounts_display.accounts_widgets[savings.id]['buttons']['save_edit'], QtCore.Qt.LeftButton)
        self.assertEqual(len(storage.get_accounts()), 2)
        self.assertEqual(storage.get_accounts()[1].name, 'New Savings')
        self.assertEqual(storage.get_accounts()[1].parent.name, 'Checking')

    def test_expense_account_edit(self):
        storage = pft.SQLiteStorage(':memory:')
        checking = pft.Account(type_=pft.AccountType.ASSET, name='Checking')
        storage.save_account(checking)
        food = pft.Account(type_=pft.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        accounts_display = pft.AccountsDisplay(storage, reload_accounts=fake_method)
        widget = accounts_display.get_widget()
        QtTest.QTest.mouseClick(accounts_display.accounts_widgets[food.id]['labels']['name'], QtCore.Qt.LeftButton)
        accounts_display.accounts_widgets[food.id]['entries']['name'].setText('New Food')
        QtTest.QTest.mouseClick(accounts_display.accounts_widgets[food.id]['buttons']['save_edit'], QtCore.Qt.LeftButton)
        self.assertEqual(len(storage.get_accounts()), 2)
        self.assertEqual(storage.get_accounts()[1].name, 'New Food')

    @patch('pft.set_widget_error_state')
    def test_account_exception(self, mock_method):
        storage = pft.SQLiteStorage(':memory:')
        accounts_display = pft.AccountsDisplay(storage, reload_accounts=fake_method)
        widget = accounts_display.get_widget()
        QtTest.QTest.mouseClick(accounts_display.add_account_widgets['buttons']['add_new'], QtCore.Qt.LeftButton)
        mock_method.assert_called_once_with(accounts_display.add_account_widgets['entries']['name'])

    def test_ledger_add(self):
        storage = pft.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        savings = get_test_account(name='Savings')
        storage.save_account(savings)
        housing = get_test_account(type_=pft.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        txn = pft.Transaction(splits={checking: D(5), savings: D(-5)}, txn_date=date.today())
        txn2 = pft.Transaction(splits={checking: D(5), savings: D(-5)}, txn_date=date(2017, 1, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        ledger_display = pft.LedgerDisplay(storage, show_ledger=fake_method)
        ledger_display.get_widget()
        self.assertEqual(ledger_display.add_txn_widgets['accounts_display']._categories_combo.count(), 4)
        ledger_display.add_txn_widgets['entries']['date'].setText('2017-01-05')
        ledger_display.add_txn_widgets['entries']['withdrawal'].setText('18')
        ledger_display.add_txn_widgets['accounts_display']._categories_combo.setCurrentIndex(1)
        QtTest.QTest.mouseClick(ledger_display.add_txn_widgets['buttons']['add_new'], QtCore.Qt.LeftButton)
        #make sure new txn was saved
        ledger = storage.get_account_ledger(account=checking)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(len(txns), 3)
        self.assertEqual(txns[1].splits[checking], D('-18'))
        #check new txn display
        self.assertEqual(ledger_display.add_txn_widgets['entries']['withdrawal'].text(), '')
        self.assertEqual(len(ledger_display.ledger.get_sorted_txns_with_balance()), 3)
        self.assertEqual(ledger_display.txns_display.txn_display_data[txns[1].id]['row'], 1)

    def test_ledger_add_not_first_account(self):
        #test that correct accounts are set for the new txn (not just first account in the list)
        storage = pft.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        savings = get_test_account(name='Savings')
        storage.save_account(savings)
        housing = get_test_account(type_=pft.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        ledger_display = pft.LedgerDisplay(storage, show_ledger=fake_method, current_account=savings)
        ledger_display.get_widget()
        #add new txn
        ledger_display.add_txn_widgets['entries']['date'].setText('2017-01-05')
        ledger_display.add_txn_widgets['entries']['withdrawal'].setText('18')
        ledger_display.add_txn_widgets['accounts_display']._categories_combo.setCurrentIndex(1)
        QtTest.QTest.mouseClick(ledger_display.add_txn_widgets['buttons']['add_new'], QtCore.Qt.LeftButton)
        #make sure new txn was saved correctly
        ledger = storage.get_account_ledger(account=savings)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].splits,
                {
                    savings: D('-18'),
                    housing: D(18)
                }
            )

    def test_ledger_add_multiple(self):
        storage = pft.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        housing = get_test_account(type_=pft.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        rent = get_test_account(type_=pft.AccountType.EXPENSE, name='Rent')
        storage.save_account(rent)
        ledger_display = pft.LedgerDisplay(storage, show_ledger=fake_method)
        ledger_display.get_widget()
        txn_accounts_display_splits = {rent: 3, housing: 7}
        ledger_display.add_txn_widgets['entries']['date'].setText('2017-01-05')
        ledger_display.add_txn_widgets['entries']['withdrawal'].setText('10')
        pft.get_new_txn_splits = MagicMock(return_value=txn_accounts_display_splits)
        QtTest.QTest.mouseClick(ledger_display.add_txn_widgets['accounts_display'].split_button, QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(ledger_display.add_txn_widgets['buttons']['add_new'], QtCore.Qt.LeftButton)
        #make sure new txn was saved
        ledger = storage.get_account_ledger(account=checking)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].splits[checking], D('-10'))

    def test_ledger_choose_account(self):
        storage = pft.SQLiteStorage(':memory:')
        checking = pft.Account(type_=pft.AccountType.ASSET, name='Checking')
        savings = pft.Account(type_=pft.AccountType.ASSET, name='Savings')
        storage.save_account(checking)
        storage.save_account(savings)
        txn = pft.Transaction(splits={checking: D(5), savings: D(-5)}, txn_date=date.today())
        txn2 = pft.Transaction(splits={savings: D(5), checking: D(-5)}, txn_date=date(2017, 1, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        ledger_display = pft.LedgerDisplay(storage, show_ledger=fake_method, current_account=savings)
        ledger_display.get_widget()
        self.assertEqual(ledger_display._current_account, savings)
        self.assertEqual(ledger_display.action_combo.currentIndex(), 1)
        self.assertEqual(ledger_display.action_combo.currentText(), 'Savings')

    def test_ledger_switch_account(self):
        show_ledger_mock = Mock()
        storage = pft.SQLiteStorage(':memory:')
        checking = pft.Account(type_=pft.AccountType.ASSET, name='Checking')
        savings = pft.Account(type_=pft.AccountType.ASSET, name='Savings')
        storage.save_account(checking)
        storage.save_account(savings)
        txn = pft.Transaction(splits={checking: D(5), savings: D(-5)}, txn_date=date.today())
        txn2 = pft.Transaction(splits={checking: D(5), savings: D(-5)}, txn_date=date(2017, 1, 2))
        txn3 = pft.Transaction(splits={savings: D(5), checking: D(-5)}, txn_date=date(2018, 1, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        storage.save_txn(txn3)
        ledger_display = pft.LedgerDisplay(storage, show_ledger=show_ledger_mock)
        ledger_display.get_widget()
        self.assertEqual(ledger_display._current_account, checking)
        self.assertEqual(ledger_display.action_combo.currentIndex(), 0)
        self.assertEqual(ledger_display.action_combo.currentText(), 'Checking')
        ledger_display.action_combo.setCurrentIndex(1)
        show_ledger_mock.assert_called_once_with(savings)

    def test_ledger_txn_edit(self):
        storage = pft.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        savings = get_test_account(name='Savings')
        storage.save_account(savings)
        txn = pft.Transaction(splits={checking: D(5), savings: D(-5)}, txn_date=date(2017, 1, 3))
        txn2 = pft.Transaction(splits={checking: D(17), savings: D(-17)}, txn_date=date(2017, 5, 2))
        txn3 = pft.Transaction(splits={checking: D(25), savings: D(-25)}, txn_date=date(2017, 10, 18))
        txn4 = pft.Transaction(splits={checking: D(10), savings: D(-10)}, txn_date=date(2018, 6, 6))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        storage.save_txn(txn3)
        storage.save_txn(txn4)
        ledger_display = pft.LedgerDisplay(storage, show_ledger=fake_method)
        ledger_display.get_widget()
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn.id]['widgets']['labels']['balance'].text(), '5')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['labels']['balance'].text(), '22')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn2.id]['row'], 1)
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn3.id]['widgets']['labels']['balance'].text(), '47')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn4.id]['widgets']['labels']['balance'].text(), '57')
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['labels']['date'], QtCore.Qt.LeftButton)
        ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['entries']['date'].setText('2017-12-31')
        ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['entries']['deposit'].setText('20')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn2.id]['accounts_display'].get_categories(), savings)
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['buttons']['save_edit'], QtCore.Qt.LeftButton)
        #make sure edit was saved
        ledger = storage.get_account_ledger(account=checking)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(len(txns), 4)
        self.assertEqual(txns[2].txn_date, date(2017, 12, 31))
        self.assertEqual(txns[2].splits[checking], D(20))
        #check display with edits
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn.id]['widgets']['labels']['balance'].text(), '5')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn.id]['row'], 0)
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn3.id]['widgets']['labels']['balance'].text(), '30')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn3.id]['row'], 1)
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['labels']['balance'].text(), '50')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn2.id]['row'], 2)
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn4.id]['widgets']['labels']['balance'].text(), '60')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn4.id]['row'], 3)

    def test_ledger_txn_edit_expense_account(self):
        storage = pft.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        housing = get_test_account(type_=pft.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        restaurants = get_test_account(type_=pft.AccountType.EXPENSE, name='Restaurants')
        storage.save_account(restaurants)
        txn = pft.Transaction(splits={checking: D(5), housing: D(-5)}, txn_date=date(2017, 1, 3))
        txn2 = pft.Transaction(splits={checking: D(17), housing: D(-17)}, txn_date=date(2017, 5, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        ledger_display = pft.LedgerDisplay(storage, show_ledger=fake_method)
        ledger_display.get_widget()
        #activate editing
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['labels']['date'], QtCore.Qt.LeftButton)
        #change expense account
        ledger_display.txns_display.txn_display_data[txn2.id]['accounts_display']._categories_combo.setCurrentIndex(2)
        #save the change
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['buttons']['save_edit'], QtCore.Qt.LeftButton)
        #make sure new category was saved
        ledger = storage.get_account_ledger(account=checking)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(txns[1].splits[restaurants], D(-17))

    def test_ledger_txn_edit_multiple_splits(self):
        storage = pft.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        housing = get_test_account(type_=pft.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        restaurants = get_test_account(type_=pft.AccountType.EXPENSE, name='Restaurants')
        storage.save_account(restaurants)
        food = get_test_account(type_=pft.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        initial_splits = {checking: D(-25), housing: D(20), restaurants: D(5)}
        txn_account_display_splits = {housing: D(15), restaurants: D(10)}
        final_splits = {checking: D(-25), housing: D(15), restaurants: D(10)}
        txn = pft.Transaction(splits=initial_splits, txn_date=date(2017, 1, 3))
        storage.save_txn(txn)
        ledger_display = pft.LedgerDisplay(storage, show_ledger=fake_method)
        ledger_display.get_widget()
        #activate editing
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn.id]['widgets']['labels']['date'], QtCore.Qt.LeftButton)
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn.id]['accounts_display']._categories_combo.currentText(), 'multiple')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn.id]['accounts_display']._categories_combo.currentData(), initial_splits)
        pft.get_new_txn_splits = MagicMock(return_value=txn_account_display_splits)
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn.id]['accounts_display'].split_button, QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn.id]['widgets']['buttons']['save_edit'], QtCore.Qt.LeftButton)
        updated_txn = storage.get_txn(txn.id)
        self.assertEqual(updated_txn.splits, final_splits)

    def test_ledger_txn_delete(self):
        storage = pft.SQLiteStorage(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        storage.save_account(checking)
        storage.save_account(savings)
        txn = pft.Transaction(splits={checking: D(5), savings: D(-5)}, txn_date=date.today())
        txn2 = pft.Transaction(splits={checking: D(23), savings: D(-23)}, txn_date=date(2017, 1, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        ledger_display = pft.LedgerDisplay(storage, show_ledger=fake_method)
        ledger_display.get_widget()
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn.id]['widgets']['labels']['date'], QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn.id]['widgets']['buttons']['delete'], QtCore.Qt.LeftButton)
        #make sure txn was deleted
        ledger = storage.get_account_ledger(account=checking)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].splits[checking], D(23))

    def test_budget(self):
        storage = pft.SQLiteStorage(':memory:')
        housing = get_test_account(type_=pft.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=pft.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        wages = get_test_account(type_=pft.AccountType.INCOME, name='Wages')
        storage.save_account(wages)
        b = pft.Budget(year=2018, account_budget_info={
            housing: {'amount': D(15), 'carryover': D(0)},
            food: {'amount': D(25), 'carryover': D(0)},
            wages: {'amount': D(100)},
        })
        storage.save_budget(b)
        budget = storage.get_budgets()[0]
        self.assertEqual(budget.get_budget_data()[housing]['amount'], D(15))
        budget_display = pft.BudgetDisplay(budget=budget, storage=storage, reload_budget=fake_method)
        widget = budget_display.get_widget()
        QtTest.QTest.mouseClick(budget_display._edit_button, QtCore.Qt.LeftButton)
        budget_display.data[housing.id]['budget_entry'].setText('30')
        QtTest.QTest.mouseClick(budget_display._save_button, QtCore.Qt.LeftButton) #now it's the save button
        budgets = storage.get_budgets()
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets[0].get_budget_data()[housing]['amount'], D(30))


class TestLoadTestData(unittest.TestCase):

    def test_load(self):
        storage = pft.SQLiteStorage(':memory:')
        load_test_data._load_data(storage, many_txns=False)
        accounts = storage.get_accounts()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-gui', dest='no_gui', action='store_true')
    args = parser.parse_args()
    if args.no_gui:
        suite = unittest.TestSuite()
        suite.addTest(unittest.makeSuite(TestAccount, 'test'))
        suite.addTest(unittest.makeSuite(TestTransaction, 'test'))
        suite.addTest(unittest.makeSuite(TestLedger, 'test'))
        suite.addTest(unittest.makeSuite(TestBudget, 'test'))
        suite.addTest(unittest.makeSuite(TestSQLiteStorage, 'test'))
        suite.addTest(unittest.makeSuite(TestLoadTestData, 'test'))
        runner = unittest.TextTestRunner()
        runner.run(suite)
    else:
        from PySide2 import QtWidgets, QtTest, QtCore
        unittest.main()

