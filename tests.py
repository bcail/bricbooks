from datetime import date
from decimal import Decimal as D
import os
import sqlite3
import tempfile
import tkinter
import unittest
from unittest.mock import patch, Mock
from PySide2 import QtWidgets, QtTest, QtCore

from pft import (
        get_date,
        Account,
        InvalidAccountError,
        Transaction,
        InvalidTransactionError,
        Ledger,
        InvalidLedgerError,
        Category,
        Budget,
        BudgetError,
        SQLiteStorage,
        SQLiteStorageError,
        txn_categories_from_string,
        AccountsDisplay,
        LedgerTxnsDisplay,
        LedgerDisplay,
        CategoriesDisplay,
        BudgetDisplay,
        PFT_GUI_QT,
    )
import load_test_data


class TestUtils(unittest.TestCase):

    def test_get_date(self):
        self.assertEqual(get_date(date(2018, 1, 1)), date(2018, 1, 1))
        self.assertEqual(get_date('2018-01-01'), date(2018, 1, 1))
        with self.assertRaises(RuntimeError):
            get_date(10)


class TestAccount(unittest.TestCase):

    def test_init(self):
        a = Account(name='Checking', starting_balance=D('100'))
        self.assertEqual(a.name, 'Checking')
        self.assertEqual(a.starting_balance, D('100'))

    def test_starting_balance(self):
        with self.assertRaises(InvalidAccountError):
            Account(name='Checking', starting_balance=123.1)

    def test_eq(self):
        a = Account(name='Checking', starting_balance=D(100))
        a2 = Account(name='Savings', starting_balance=D(100))
        self.assertNotEqual(a, a2)
        self.assertEqual(a, a)
        a3 = Account(name='Checking', starting_balance=D(100))
        self.assertEqual(a, a3)


class TestCategory(unittest.TestCase):

    def test_init(self):
        c = Category('Restaurants', id_=1)
        self.assertEqual(c.name, 'Restaurants')
        self.assertEqual(str(c), 'Restaurants')
        c = Category('Restaurants')
        self.assertEqual(str(c), 'Restaurants')

    def test_eq(self):
        c = Category('Restaurants')
        c2 = Category('Housing')
        self.assertNotEqual(c, c2) #different name
        c3 = Category('Restaurants', id_=2)
        self.assertNotEqual(c, c3) #different id_
        c4 = Category('Restaurants')
        self.assertEqual(c, c4) #same id (None), same name
        c5 = Category('Restaurants', parent=c2)
        self.assertNotEqual(c, c5)

    def test_parent(self):
        parent = Category('Restaurants')
        child = Category('McDonalds', parent=parent)
        self.assertEqual(child.parent, parent)

    def test_user_id(self):
        c = Category('Restaurants', user_id='400')
        self.assertEqual(c.user_id, '400')
        self.assertEqual(str(c), '400 - Restaurants')


class TestTransaction(unittest.TestCase):

    def test_account_required(self):
        with self.assertRaises(InvalidTransactionError) as cm:
            Transaction()
        self.assertEqual(str(cm.exception), 'transaction must belong to an account')

    def test_invalid_txn_amount(self):
        a = Account(name='Checking', starting_balance=D('100'))
        with self.assertRaises(InvalidTransactionError) as cm:
            Transaction(account=a, amount=101.1)
        self.assertEqual(str(cm.exception), 'invalid type for amount')
        with self.assertRaises(InvalidTransactionError) as cm:
            Transaction(account=a, amount='123.456')
        self.assertEqual(str(cm.exception), 'no fractions of cents in a transaction')
        with self.assertRaises(InvalidTransactionError) as cm:
            Transaction(account=a, amount=D('123.456'))
        self.assertEqual(str(cm.exception), 'no fractions of cents in a transaction')

    def test_txn_amount(self):
        a = Account(name='Checking', starting_balance=D('100'))
        t = Transaction(account=a, amount='123', txn_date=date.today())
        self.assertEqual(t.amount, D('123'))
        t = Transaction(account=a, amount=12, txn_date=date.today())
        self.assertEqual(t.amount, D('12'))
        t = Transaction(account=a, amount='10.', txn_date=date.today())
        self.assertEqual(t.amount, D('10'))

    def test_invalid_txn_date(self):
        a = Account(name='Checking', starting_balance=D('100'))
        with self.assertRaises(InvalidTransactionError) as cm:
            Transaction(account=a, amount=D('101'))
        self.assertEqual(str(cm.exception), 'transaction must have a txn_date')
        with self.assertRaises(InvalidTransactionError) as cm:
            Transaction(account=a, amount=D('101'), txn_date=10)
        self.assertEqual(str(cm.exception), 'invalid txn_date')

    def test_txn_date(self):
        a = Account(name='Checking', starting_balance=D('100'))
        t = Transaction(account=a, amount='123', txn_date=date.today())
        self.assertEqual(t.txn_date, date.today())
        t = Transaction(account=a, amount='123', txn_date='2018-03-18')
        self.assertEqual(t.txn_date, date(2018, 3, 18))

    def test_init(self):
        a = Account(name='Checking', starting_balance=D('100'))
        t = Transaction(
                account=a,
                amount=D('101'),
                txn_date=date.today(),
                txn_type='1234',
                payee='McDonalds',
                description='2 big macs',
            )
        self.assertEqual(t.account, a)
        self.assertEqual(t.amount, D('101'))
        self.assertEqual(t.txn_date, date.today())
        self.assertEqual(t.txn_type, '1234')
        self.assertEqual(t.payee, 'McDonalds')
        self.assertEqual(t.description, '2 big macs')
        self.assertEqual(t.status, None)
        #test passing status in as argument
        t = Transaction(
                account=a,
                amount=D('101'),
                txn_date=date.today(),
                status=Transaction.CLEARED,
            )
        self.assertEqual(t.status, Transaction.CLEARED)

    def test_txn_from_user_strings(self):
        #construct txn from user strings, as much as possible (except account & categories)
        a = Account(name='Checking', starting_balance=D('100'))
        c = Category('Cat', id_=1)
        t = Transaction.from_user_strings(
                account=a,
                txn_type='1234',
                credit='101',
                debit='',
                txn_date='2017-10-15',
                description='something',
                payee='McDonalds',
                status='C',
                categories=[(c, D('101'))],
            )
        self.assertEqual(t.amount, D('101'))

    def test_get_display_strings(self):
        a = Account(name='Checking', starting_balance=D('100'))
        c = Category('Cat', id_=1)
        t = Transaction(
                account=a,
                txn_type='1234',
                amount=D('101'),
                txn_date=date.today(),
                description='something',
                payee='McDonalds',
                status='C',
                categories=[(c, D('101'))],
            )
        self.assertDictEqual(t.get_display_strings(),
                {
                    'txn_type': '1234',
                    'debit': '',
                    'credit': '101',
                    'description': 'something',
                    'txn_date': str(date.today()),
                    'payee': 'McDonalds',
                    'status': 'C',
                    'categories': 'Cat',
                }
            )

    def test_get_display_strings_sparse(self):
        a = Account(name='Checking', starting_balance=D('100'))
        t = Transaction(
                account=a,
                amount=D('-101'),
                txn_date=date.today(),
            )
        self.assertDictEqual(t.get_display_strings(),
                {
                    'txn_type': '',
                    'debit': '101',
                    'credit': '',
                    'description': '',
                    'txn_date': str(date.today()),
                    'payee': '',
                    'status': '',
                    'categories': '',
                }
            )

    def test_txn_categories_display(self):
        a = Account(name='Checking', starting_balance=D('100'))
        c = Category('Cat', id_=1)
        c2 = Category('Dog', id_=2)
        c3 = Category('Horse', id_=3)
        t = Transaction(
                account=a,
                amount=D('-101'),
                txn_date=date.today(),
                categories=[(c, D('-45')), (c2, D('-59')), (c3, D('3'))],
            )
        self.assertEqual(t._categories_display(), 'multiple')
        t = Transaction(
                account=a,
                amount=D(100),
                txn_date=date.today(),
                categories=[c]
            )
        self.assertEqual(t._categories_display(), 'Cat')

    def test_no_category(self):
        #uncategorized transaction
        a = Account(name='Checking', starting_balance=D('100'))
        t = Transaction(
                account=a,
                amount=D('101'),
                txn_date=date.today(),
            )
        self.assertEqual(t.categories, [])

    def test_one_category(self):
        #normal categorized transaction
        a = Account(name='Checking', starting_balance=D('100'))
        c = Category('Cat')
        t = Transaction(
                account=a,
                amount=D('101'),
                txn_date=date.today(),
                categories=[(c, D('101'))],
            )
        self.assertEqual(t.categories[0][0], c)
        self.assertEqual(t.categories[0][1], D('101'))
        #test passing in just a category, with no amount: assume it's for the whole amount
        t = Transaction(
                account=a,
                amount=D(101),
                txn_date=date.today(),
                categories=[c],
            )
        self.assertEqual(t.categories[0][0], c)
        self.assertEqual(t.categories[0][1], D(101))
        #test passing category not in a list
        t = Transaction(
                account=a,
                amount=D(101),
                txn_date=date.today(),
                categories=c,
            )
        self.assertEqual(t.categories[0][0], c)
        self.assertEqual(t.categories[0][1], D(101))

    def test_split_categories(self):
        a = Account(name='Checking', starting_balance=D('100'))
        c = Category('Cat')
        c2 = Category('Dog')
        t = Transaction(
                account=a,
                amount=D('101'),
                txn_date=date.today(),
                categories=[(c, D('45')), (c2, D('56'))],
            )
        self.assertEqual(t.categories[0][0], c)
        self.assertEqual(t.categories[0][1], D('45'))
        self.assertEqual(t.categories[1][0], c2)
        self.assertEqual(t.categories[1][1], D('56'))

    def test_negative_split_categories(self):
        a = Account(name='Checking', starting_balance=D('100'))
        c = Category('Cat')
        c2 = Category('Dog')
        t = Transaction(
                account=a,
                amount=D('-101'),
                txn_date=date.today(),
                categories=[(c, D('45')), (c2, D('56'))],
            )
        self.assertEqual(t.categories[0][0], c)
        self.assertEqual(t.categories[0][1], D('45'))
        self.assertEqual(t.categories[1][0], c2)
        self.assertEqual(t.categories[1][1], D('56'))

    def test_mixed_split_categories(self):
        a = Account(name='Checking', starting_balance=D('100'))
        c = Category('Cat')
        c2 = Category('Dog')
        c3 = Category('Horse')
        t = Transaction(
                account=a,
                amount=D('-101'),
                txn_date=date.today(),
                categories=[(c, D('45')), (c2, D('59')), (c3, D('-3'))],
            )
        self.assertEqual(t.categories[0][0], c)
        self.assertEqual(t.categories[0][1], D('45'))
        self.assertEqual(t.categories[1][0], c2)
        self.assertEqual(t.categories[1][1], D('59'))
        self.assertEqual(t.categories[2][0], c3)
        self.assertEqual(t.categories[2][1], D('-3'))

    def test_invalid_category_amounts(self):
        a = Account(name='Checking', starting_balance=D('100'))
        c = Category('Cat')
        c2 = Category('Dog')
        with self.assertRaises(InvalidTransactionError) as cm:
            Transaction(
                account=a,
                amount=D('101'),
                txn_date=date.today(),
                categories=[(c, D('55')), (c2, D('56'))],
            )
        self.assertEqual(str(cm.exception), 'split categories add up to more than txn amount')
        with self.assertRaises(InvalidTransactionError) as cm:
            Transaction(
                account=a,
                amount=D('-101'),
                txn_date=date.today(),
                categories=[(c, D('55')), (c2, D('53'))],
            )
        self.assertEqual(str(cm.exception), 'split categories add up to more than txn amount')

    def test_update_values(self):
        a = Account(name='Checking', starting_balance=D('100'))
        t = Transaction(
                account=a,
                amount=D('101'),
                txn_date=date.today(),
                txn_type='BP',
                payee='Wendys',
                description='salad',
            )
        t.update_from_user_strings(
                txn_type='1234',
                txn_date='2017-10-15',
                credit='45',
            )
        self.assertEqual(t.txn_type, '1234')
        self.assertEqual(t.amount, D('45'))
        self.assertEqual(t.payee, 'Wendys')
        self.assertEqual(t.txn_date, date(2017, 10, 15))

    def test_update_values_categories(self):
        a = Account(name='Checking', starting_balance=D('100'))
        c = Category('Cat')
        c2 = Category('Dog')
        t = Transaction(
                account=a,
                amount=D('101'),
                txn_date=date.today(),
            )
        t.update_from_user_strings(
                categories=[[c, '50'], [c2, '51']]
            )
        self.assertEqual(t.categories, [(c, D(50)), (c2, D(51))])

    def test_update_values_make_it_empty(self):
        a = Account(name='Checking', starting_balance=D('100'))
        t = Transaction(
                account=a,
                amount=D('101'),
                txn_date=date.today(),
                txn_type='1234',
                payee='Arbys',
                description='roast beef',
            )
        t.update_from_user_strings(credit='101', payee='')
        self.assertEqual(t.payee, '')

    def test_update_values_errors(self):
        a = Account(name='Checking', starting_balance=D('100'))
        t = Transaction(
                account=a,
                amount=D('101'),
                txn_date=date.today(),
                txn_type='1234',
                payee='Cracker Barrel',
                description='meal',
            )
        with self.assertRaises(InvalidTransactionError):
            t.update_from_user_strings(credit='ab')
        with self.assertRaises(InvalidTransactionError):
            t.update_from_user_strings(txn_date='ab')
        c = Category('Cat')
        c2 = Category('Dog')
        with self.assertRaises(InvalidTransactionError):
            t.update_from_user_strings(categories=[(c, D('55')), (c2, D('56'))])

    def test_update_values_debit_credit(self):
        a = Account(name='Checking', starting_balance=D('100'))
        t = Transaction(
                account=a,
                amount='101',
                txn_date=date.today(),
            )
        t.update_from_user_strings(debit='50')
        self.assertEqual(t.amount, D('-50'))
        t.update_from_user_strings(credit='25')
        self.assertEqual(t.amount, D('25'))


class TestLedger(unittest.TestCase):

    def test_init(self):
        with self.assertRaises(InvalidLedgerError) as cm:
            Ledger()
        self.assertEqual(str(cm.exception), 'ledger must have a starting balance')
        with self.assertRaises(InvalidLedgerError) as cm:
            Ledger(starting_balance=1)
        self.assertEqual(str(cm.exception), 'starting_balance must be a Decimal')
        ledger = Ledger(starting_balance=D('101.25'))
        self.assertEqual(ledger._starting_balance, D('101.25'))
        ledger = Ledger(starting_balance=D('0'))
        self.assertEqual(ledger._starting_balance, D('0'))

    def test_add_transaction(self):
        ledger = Ledger(starting_balance=D('1'))
        self.assertEqual(ledger._txns, {})
        a = Account(name='Checking', starting_balance=D('100'))
        txn = Transaction(id_=1, account=a, amount=D('101'), txn_date=date.today())
        ledger.add_transaction(txn)
        self.assertEqual(ledger._txns, {1: txn})

    def test_get_ledger_txns(self):
        a = Account(name='Checking', starting_balance=D('100'))
        ledger = Ledger(starting_balance=a.starting_balance)
        ledger.add_transaction(Transaction(id_=1, account=a, amount=D('32.45'), txn_date=date(2017, 8, 5)))
        ledger.add_transaction(Transaction(id_=2, account=a, amount=D('-12'), txn_date=date(2017, 6, 5)))
        ledger.add_transaction(Transaction(id_=3, account=a, amount=D('1'), txn_date=date(2017, 7, 30)))
        ledger.add_transaction(Transaction(id_=4, account=a, amount=D('10'), txn_date=date(2017, 4, 25)))
        ledger_records = ledger.get_sorted_txns_with_balance()
        self.assertEqual(ledger_records[0].txn_date, date(2017, 4, 25))
        self.assertEqual(ledger_records[0].balance, D('110'))
        self.assertEqual(ledger_records[1].txn_date, date(2017, 6, 5))
        self.assertEqual(ledger_records[1].balance, D('98'))
        self.assertEqual(ledger_records[2].txn_date, date(2017, 7, 30))
        self.assertEqual(ledger_records[2].balance, D('99'))
        self.assertEqual(ledger_records[3].txn_date, date(2017, 8, 5))
        self.assertEqual(ledger_records[3].balance, D('131.45'))

    def test_get_txn(self):
        a = Account(name='Checking', starting_balance=D('100'))
        ledger = Ledger(starting_balance=a.starting_balance)
        ledger.add_transaction(Transaction(id_=1, account=a, amount=D('32.45'), txn_date=date(2017, 8, 5)))
        ledger.add_transaction(Transaction(id_=2, account=a, amount=D('-12'), txn_date=date(2017, 6, 5)))
        txn = ledger.get_txn(id_=2)
        self.assertEqual(txn.amount, D('-12'))

    def test_clear_txns(self):
        a = Account(name='Checking', starting_balance=D('100'))
        ledger = Ledger(starting_balance=D('100.12'))
        ledger.add_transaction(Transaction(id_=1, account=a, amount=D('12.34'), txn_date=date(2017, 8, 5)))
        ledger.clear_txns()
        self.assertEqual(ledger.get_sorted_txns_with_balance(), [])


class TestBudget(unittest.TestCase):

    def test_init_dates(self):
        with self.assertRaises(BudgetError) as cm:
            Budget()
        self.assertEqual(str(cm.exception), 'must pass in dates')
        b = Budget(year=2018, category_budget_info={})
        self.assertEqual(b.start_date, date(2018, 1, 1))
        self.assertEqual(b.end_date, date(2018, 12, 31))
        b = Budget(year='2018', category_budget_info={})
        self.assertEqual(b.start_date, date(2018, 1, 1))
        b = Budget(start_date=date(2018, 1, 15), end_date=date(2019, 1, 14), category_budget_info={})
        self.assertEqual(b.start_date, date(2018, 1, 15))
        self.assertEqual(b.end_date, date(2019, 1, 14))

    def test_init(self):
        c = Category(name='Housing', id_=1)
        c2 = Category(name='Food', id_=2)
        c3 = Category(name='Transportation', id_=3)
        category_rows = {
                c: {'amount': D(15), 'carryover': D(5), 'notes': 'some important info'},
                c2: {'amount': '35', 'carryover': ''},
                c3: {},
            }
        b = Budget(year=2018, category_budget_info=category_rows)
        self.assertEqual(b.get_budget_data(),
                {c: {'amount': D(15), 'carryover': D(5), 'notes': 'some important info'}, c2: {'amount': D(35)}, c3: {}})

    def test_percent_rounding(self):
        self.assertEqual(Budget.round_percent_available(D('1.1')), D(1))
        self.assertEqual(Budget.round_percent_available(D('1.8')), D(2))
        self.assertEqual(Budget.round_percent_available(D('1.5')), D(2))
        self.assertEqual(Budget.round_percent_available(D('2.5')), D(3))

    def test_get_report_display(self):
        c = Category(name='Housing', id_=1)
        c2 = Category(name='Food', id_=2)
        c3 = Category(name='Transportation', id_=3)
        c4 = Category(name='Something', id_=4)
        c5 = Category(name='Wages', is_expense=False, id_=5)
        category_rows = {
                c: {'amount': D(15), 'carryover': D(5)},
                c2: {},
                c3: {'amount': D(10)},
                c4: {'amount': D(0)},
                c5: {'amount': D(100)},
            }
        budget = Budget(year=2018, category_budget_info=category_rows)
        with self.assertRaises(BudgetError):
            budget.get_report_display()
        income_spending_info = {c: {'income': D(5), 'spent': D(10)}, c2: {}, c5: {'income': D(80)}}
        budget = Budget(year=2018, category_budget_info=category_rows, income_spending_info=income_spending_info)
        budget_report = budget.get_report_display()
        c_info = budget_report['expense'][c]
        self.assertEqual(c_info['amount'], '15')
        self.assertEqual(c_info['carryover'], '5')
        self.assertEqual(c_info['income'], '5')
        self.assertEqual(c_info['total_budget'], '25')
        self.assertEqual(c_info['spent'], '10')
        self.assertEqual(c_info['remaining'], '15')
        self.assertEqual(c_info['percent_available'], '60%')
        c2_info = budget_report['expense'][c2]
        self.assertEqual(c2_info,
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
        c3_info = budget_report['expense'][c3]
        self.assertEqual(c3_info,
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
        c5_info = budget_report['income'][c5]
        self.assertEqual(c5_info,
                {
                    'amount': '100',
                    'income': '80',
                    'percent': '80%',
                    'remaining': '20',
                }
            )


TABLES = [('accounts',), ('budgets',), ('budget_values',), ('categories',), ('transactions',), ('txn_categories',)]


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
        storage = SQLiteStorage(':memory:')
        tables = storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, TABLES)

    def test_init_no_file(self):
        storage = SQLiteStorage(self.file_name)
        tables = storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, TABLES)

    def test_init_empty_file(self):
        with open(self.file_name, 'wb') as f:
            pass
        storage = SQLiteStorage(self.file_name)
        tables = storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, TABLES)

    def test_init_db_already_setup(self):
        #set up file
        init_storage = SQLiteStorage(self.file_name)
        tables = init_storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, TABLES)
        #and now open it again and make sure everything's fine
        storage = SQLiteStorage(self.file_name)
        tables = init_storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, TABLES)

    def test_save_account(self):
        storage = SQLiteStorage(':memory:')
        account = Account(name='Checking', starting_balance=D(100))
        storage.save_account(account)
        #make sure we save the id to the account object
        self.assertEqual(account.id, 1)
        c = storage._db_connection.cursor()
        c.execute('SELECT * FROM accounts')
        db_info = c.fetchone()
        self.assertEqual(db_info,
                (account.id, 'Checking', '100'))
        account = Account(id_=1, name='Savings', starting_balance=D(200))
        storage.save_account(account)
        c.execute('SELECT * FROM accounts')
        db_info = c.fetchall()
        self.assertEqual(db_info,
                [(1, 'Savings', '200')])

    def test_get_account(self):
        storage = SQLiteStorage(':memory:')
        c = storage._db_connection.cursor()
        c.execute('INSERT INTO accounts(name, starting_balance) VALUES (?, ?)', ('Checking', str(D(100))))
        account_id = c.lastrowid
        account = storage.get_account(account_id)
        self.assertEqual(account.id, account_id)
        self.assertEqual(account.name, 'Checking')
        self.assertEqual(account.starting_balance, D(100))

    def test_get_accounts(self):
        storage = SQLiteStorage(':memory:')
        c = storage._db_connection.cursor()
        c.execute('INSERT INTO accounts(name, starting_balance) VALUES (?, ?)', ('Checking', str(D(100))))
        c.execute('INSERT INTO accounts(name, starting_balance) VALUES (?, ?)', ('Savings', str(D(1000))))
        accounts = storage.get_accounts()
        self.assertEqual(len(accounts), 2)
        self.assertEqual(accounts[0].name, 'Checking')
        self.assertEqual(accounts[1].name, 'Savings')

    def test_save_category(self):
        storage = SQLiteStorage(':memory:')
        parent = Category(name='Restaurants', is_expense=True, user_id='400')
        child = Category(name='McDonalds', is_expense=True, parent=parent)
        storage.save_category(parent)
        storage.save_category(child)
        self.assertEqual(parent.id, 1)
        self.assertEqual(child.id, 2)
        records = storage._db_connection.execute('SELECT * FROM categories').fetchall()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0][0], 1)
        self.assertEqual(records[0][1], 'Restaurants')
        self.assertEqual(records[0][2], 1)
        self.assertEqual(records[0][3], None)
        self.assertEqual(records[0][4], '400')
        self.assertEqual(records[1][0], 2)
        self.assertEqual(records[1][1], 'McDonalds')
        self.assertEqual(records[1][2], 1)
        self.assertEqual(records[1][3], 1)
        self.assertEqual(records[1][4], None)

    def test_update_category(self):
        storage = SQLiteStorage(':memory:')
        c = Category(name='Housing', is_expense=True)
        storage.save_category(c)
        c.is_expense = False
        storage.save_category(c)
        records = storage._db_connection.execute('SELECT * FROM categories').fetchall()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][0], 1)
        self.assertEqual(records[0][1], 'Housing')
        self.assertEqual(records[0][2], 0)

    def test_get_categories(self):
        storage = SQLiteStorage(':memory:')
        c = Category(name='Housing')
        storage.save_category(c)
        c2 = Category(name='Wages', is_expense=False, user_id='400')
        storage.save_category(c2)
        c3 = Category(name='Base Salary', is_expense=False, parent=c2)
        storage.save_category(c3)
        categories = storage.get_categories()
        self.assertEqual(len(categories), 3)
        self.assertEqual(categories[0], c)
        self.assertEqual(categories[1], c3)
        self.assertEqual(categories[2], c2)
        self.assertTrue(categories[0].is_expense)
        self.assertFalse(categories[1].is_expense)
        self.assertFalse(categories[2].is_expense)
        self.assertTrue(categories[0].parent is None)
        self.assertEqual(categories[1].parent, c2)
        self.assertTrue(categories[0].user_id is None)
        self.assertEqual(categories[2].user_id, '400')

    def test_get_parent_categories(self):
        storage = SQLiteStorage(':memory:')
        c = Category(name='Housing')
        storage.save_category(c)
        c2 = Category(name='Wages')
        storage.save_category(c2)
        c3 = Category(name='Base Salary', parent=c2)
        storage.save_category(c3)
        categories = storage.get_parent_categories()
        self.assertEqual(len(categories), 2)
        self.assertEqual(categories[0].name, 'Housing')
        self.assertEqual(categories[1].name, 'Wages')

    def test_get_child_categories(self):
        storage = SQLiteStorage(':memory:')
        c = Category(name='Housing')
        storage.save_category(c)
        c2 = Category(name='Wages')
        storage.save_category(c2)
        c3 = Category(name='Base Salary', parent=c2)
        storage.save_category(c3)
        categories = storage.get_child_categories(parent=c2)
        self.assertEqual(len(categories), 1)
        self.assertEqual(categories[0].name, 'Base Salary')

    def test_delete_category(self):
        storage = SQLiteStorage(':memory:')
        c = Category(name='Housing')
        storage.save_category(c)
        storage.delete_category(c.id)
        records = storage._db_connection.execute('SELECT * FROM categories').fetchall()
        self.assertEqual(records, [])

    def test_delete_category_with_txn(self):
        storage = SQLiteStorage(':memory:')
        a = Account(name='Checking', starting_balance=D('100'))
        storage.save_account(a)
        c = Category(name='Housing')
        storage.save_category(c)
        t = Transaction(
                account=a,
                amount=D('-101'),
                txn_date=date.today(),
                categories=[c],
            )
        storage.save_txn(t)
        with self.assertRaises(SQLiteStorageError) as cm:
            storage.delete_category(c.id)
        self.assertEqual(str(cm.exception), 'category has transactions')

    def test_txn_from_db(self):
        storage = SQLiteStorage(':memory:')
        c = storage._db_connection.cursor()
        c.execute('INSERT INTO accounts(name, starting_balance) VALUES (?, ?)', ('Checking', '100'))
        account_id = c.lastrowid
        c.execute('INSERT INTO transactions(account_id, txn_type, txn_date, payee, amount, description, status) values (?, ?, ?, ?, ?, ?, ?)',
                (account_id, '1234', '2017-01-25', 'Burger King', '101.00', 'inv #1', Transaction.CLEARED))
        txn_id = c.lastrowid
        c.execute('INSERT INTO categories(name) VALUES (?)', ('Cat',))
        cat_id = c.lastrowid
        c.execute('INSERT INTO txn_categories(txn_id, category_id, amount) VALUES (?, ?, ?)', (txn_id, cat_id, str(D('50'))))
        c.execute('SELECT * FROM transactions')
        db_info = c.fetchone()
        txn = storage._txn_from_db_record(db_info=db_info)
        self.assertEqual(txn.id, 1)
        self.assertEqual(txn.account.name, 'Checking')
        self.assertEqual(txn.txn_type, '1234')
        self.assertEqual(txn.txn_date, date(2017, 1, 25))
        self.assertEqual(txn.payee, 'Burger King')
        self.assertEqual(txn.amount, D('101.00'))
        self.assertEqual(txn.description, 'inv #1')
        self.assertEqual(txn.status, 'C')
        self.assertEqual(txn.categories[0][0].name, 'Cat')
        self.assertEqual(txn.categories[0][1], D('50'))

    def test_sparse_txn_from_db(self):
        storage = SQLiteStorage(':memory:')
        c = storage._db_connection.cursor()
        c.execute('INSERT INTO accounts(name, starting_balance) values (?, ?)', ('Checking', '100'))
        account_id = c.lastrowid
        c.execute('INSERT INTO transactions(account_id, txn_date, amount) values (?, ?, ?)',
                (account_id, '2017-01-25', '101.00'))
        c.execute('SELECT * FROM transactions')
        db_info = c.fetchone()
        txn = storage._txn_from_db_record(db_info=db_info)
        self.assertEqual(txn.id, 1)
        self.assertEqual(txn.txn_date, date(2017, 1, 25))
        self.assertEqual(txn.amount, D('101.00'))
        self.assertEqual(txn.categories, [])

    def test_txn_to_db(self):
        storage = SQLiteStorage(':memory:')
        c = Category('Cat')
        storage.save_category(c)
        c2 = Category('Dog')
        storage.save_category(c2)
        c3 = Category('Horse')
        storage.save_category(c3)
        a = Account(name='Checking', starting_balance=D('100'))
        storage.save_account(a)
        t = Transaction(
                account=a,
                amount=D('-101'),
                txn_date=date.today(),
                txn_type='',
                payee='Chick-fil-A',
                description='chicken sandwich',
                status=Transaction.CLEARED,
                categories=[(c, D('-45')), (c2, D('-59')), (c3, D('3'))],
            )
        storage.save_txn(t)
        #make sure we save the id to the txn object
        self.assertEqual(t.id, 1)
        c = storage._db_connection.cursor()
        c.execute('SELECT * FROM transactions')
        db_info = c.fetchone()
        self.assertEqual(db_info,
                (1, a.id, '', date.today().strftime('%Y-%m-%d'), 'Chick-fil-A', '-101', 'chicken sandwich', Transaction.CLEARED))
        c.execute('SELECT * FROM txn_categories')
        txn_category_records = c.fetchall()
        self.assertEqual(txn_category_records, [(1, 1, 1, '-45'),
                                                (2, 1, 2, '-59'),
                                                (3, 1, 3, '3')])

    def test_sparse_txn_to_db(self):
        storage = SQLiteStorage(':memory:')
        a = Account(name='Checking', starting_balance=D('100'))
        t = Transaction(
                account=a,
                txn_date=date.today(),
                amount=D('101'),
            )
        storage.save_txn(t)
        c = storage._db_connection.cursor()
        c.execute('SELECT * FROM transactions')
        db_info = c.fetchone()
        self.assertEqual(db_info,
                (1, 1, None, date.today().strftime('%Y-%m-%d'), None, '101', None, None))

    def test_round_trip(self):
        storage = SQLiteStorage(':memory:')
        a = Account(name='Checking', starting_balance=D('100'))
        storage.save_account(a)
        c = Category('Cat')
        storage.save_category(c)
        c2 = Category('Dog')
        storage.save_category(c2)
        #create txn & save it
        t = Transaction(
                account=a,
                txn_date=date.today(),
                amount=D('-101'),
                categories=[(c, D('-45')), (c2, D('-56'))],
            )
        storage.save_txn(t)
        #read it back from the db
        cursor = storage._db_connection.cursor()
        cursor.execute('SELECT * FROM transactions')
        db_info = cursor.fetchone()
        txn = storage._txn_from_db_record(db_info=db_info)
        #update it & save it to db again
        self.assertEqual(txn.txn_type, None)
        self.assertEqual(txn.payee, None)
        txn.txn_type = '123'
        txn.payee = 'Five Guys'
        txn.categories = [(c, D('-101'))]
        storage.save_txn(txn)
        #verify db record
        cursor.execute('SELECT * FROM transactions')
        db_records = cursor.fetchall()
        self.assertEqual(len(db_records), 1)
        new_txn = storage._txn_from_db_record(db_info=db_records[0])
        self.assertEqual(new_txn.txn_type, '123')
        self.assertEqual(new_txn.payee, 'Five Guys')
        self.assertEqual(new_txn.categories[0][0].name, 'Cat')
        self.assertEqual(new_txn.categories[0][1], D('-101'))

    def test_load_txns_into_ledger(self):
        storage = SQLiteStorage(':memory:')
        c = storage._db_connection.cursor()
        c.execute('INSERT INTO accounts(name, starting_balance) values (?, ?)', ('Checking', '100'))
        account_id = c.lastrowid
        c.execute('INSERT INTO accounts(name, starting_balance) values (?, ?)', ('Savings', '1000'))
        savings_account_id = c.lastrowid
        c.execute('INSERT INTO transactions(account_id, txn_type, txn_date, payee, amount, description, status) values (?, ?, ?, ?, ?, ?, ?)',
                (account_id, 'BP', '2017-01-25', 'Pizza Hut', '101.00', 'inv #1', Transaction.CLEARED))
        txn_id = c.lastrowid
        c.execute('INSERT INTO transactions(account_id, txn_type, txn_date, payee, amount, description, status) values (?, ?, ?, ?, ?, ?, ?)',
                (account_id, 'BP', '2017-01-28', 'Subway', '46.23', 'inv #42', Transaction.CLEARED))
        txn2_id = c.lastrowid
        c.execute('INSERT INTO transactions(account_id, txn_type, txn_date, payee, amount, description, status) values (?, ?, ?, ?, ?, ?, ?)',
                (savings_account_id, 'BP', '2017-01-28', 'Subway', '6.53', 'inv #42', Transaction.CLEARED))
        savings_txn_id = c.lastrowid
        c.execute('INSERT INTO categories(name) VALUES (?)', ('Cat',))
        cat_id = c.lastrowid
        c.execute('INSERT INTO categories(name) VALUES (?)', ('Dog',))
        cat2_id = c.lastrowid
        c.execute('INSERT INTO txn_categories(txn_id, category_id, amount) VALUES (?, ?, ?)', (txn_id, cat_id, str(D('101'))))
        c.execute('INSERT INTO txn_categories(txn_id, category_id, amount) VALUES (?, ?, ?)', (txn2_id, cat2_id, str(D('46.23'))))
        ledger = Ledger(starting_balance=D('0'))
        storage.load_txns_into_ledger(account_id, ledger)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(len(txns), 2)
        self.assertEqual(txns[0].amount, D('101'))
        self.assertEqual(txns[1].amount, D('46.23'))

    def test_delete_txn_from_db(self):
        storage = SQLiteStorage(':memory:')
        c = storage._db_connection.cursor()
        c.execute('INSERT INTO transactions(txn_type, txn_date, payee, amount, description, status) values (?, ?, ?, ?, ?, ?)',
                ('BP', '2017-01-25', 'Waffle House', '101.00', 'inv #1', Transaction.CLEARED))
        txn_id = c.lastrowid
        c.execute('INSERT INTO transactions(txn_type, txn_date, payee, amount, description, status) values (?, ?, ?, ?, ?, ?)',
                ('BP', '2017-01-28', 'Subway', '46.23', 'inv #42', Transaction.CLEARED))
        txn2_id = c.lastrowid
        storage.delete_txn(txn_id)
        c.execute('SELECT * FROM transactions')
        records = c.fetchall()
        self.assertEqual(len(records), 1)

    def test_save_budget(self):
        storage = SQLiteStorage(':memory:')
        c = Category(name='Housing')
        storage.save_category(c)
        c2 = Category(name='Food')
        storage.save_category(c2)
        category_rows = {
                c: {'amount': D(15), 'carryover': D(0), 'notes': 'hello'},
                c2: {'amount': D(25), 'carryover': D(10)}
            }
        b = Budget(year=2018, category_budget_info=category_rows)
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
        b = Budget(year=2018, category_budget_info={
                c: {'amount': D(35), 'carryover': D(0)},
                c2: {'amount': D(45), 'carryover': D(0)},
            }, id_=b.id)
        storage.save_budget(b)
        records = cursor.execute('SELECT * FROM budgets').fetchall()
        self.assertEqual(len(records), 1)
        records = cursor.execute('SELECT amount FROM budget_values ORDER BY amount').fetchall()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0][0], '35')

    def test_save_budget_empty_category_info(self):
        storage = SQLiteStorage(':memory:')
        c = Category(name='Housing')
        storage.save_category(c)
        c2 = Category(name='Food')
        storage.save_category(c2)
        category_rows = {
                c: {'amount': D(15), 'carryover': D(0)},
                c2: {},
            }
        b = Budget(year=2018, category_budget_info=category_rows)
        storage.save_budget(b)
        cursor = storage._db_connection.cursor()
        records = cursor.execute('SELECT * FROM budgets').fetchall()
        self.assertEqual(len(records), 1)
        records = cursor.execute('SELECT amount FROM budget_values ORDER BY amount').fetchall()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][0], '15')

    def test_save_budget_file(self):
        #test that save actually gets committed
        storage = SQLiteStorage(self.file_name)
        c = Category(name='Housing')
        storage.save_category(c)
        c2 = Category(name='Food')
        storage.save_category(c2)
        b = Budget(year=2018, category_budget_info={
            c: {'amount': D(15), 'carryover': D(0)},
            c2: {'amount': D(25), 'carryover': D(0)},
        })
        storage.save_budget(b)
        storage = SQLiteStorage(self.file_name)
        cursor = storage._db_connection.cursor()
        records = cursor.execute('SELECT * FROM budgets WHERE start_date = "2018-01-01"').fetchall()
        self.assertEqual(len(records), 1)

    def test_get_budget(self):
        storage = SQLiteStorage(':memory:')
        cursor = storage._db_connection.cursor()
        cursor.execute('INSERT INTO categories (name, is_expense) VALUES (?, ?)', ('Housing', 1))
        c_id = cursor.lastrowid
        cursor.execute('INSERT INTO categories (name, is_expense) VALUES (?, ?)', ('Food', 1))
        c2_id = cursor.lastrowid
        cursor.execute('INSERT INTO categories (name, is_expense) VALUES (?, ?)', ('Transportation', 1))
        c3_id = cursor.lastrowid
        cursor.execute('INSERT INTO accounts(name, starting_balance) values (?, ?)', ('Checking', '1000'))
        account_id = cursor.lastrowid
        cursor.execute('INSERT INTO accounts(name, starting_balance) values (?, ?)', ('Saving', '1000'))
        account2_id = cursor.lastrowid
        cursor.execute('INSERT INTO transactions(account_id, txn_date, amount) values (?, ?, ?)',
                (account_id, '2017-01-25', '-101', ))
        txn_id = cursor.lastrowid
        cursor.execute('INSERT INTO transactions(account_id, txn_date, amount) values (?, ?, ?)',
                (account_id, '2017-02-28', '-46.23'))
        txn2_id = cursor.lastrowid
        cursor.execute('INSERT INTO transactions(account_id, txn_date, amount) values (?, ?, ?)',
                (account2_id, '2017-03-28', '-56.23'))
        txn3_id = cursor.lastrowid
        cursor.execute('INSERT INTO transactions(account_id, txn_date, amount) values (?, ?, ?)',
                (account_id, '2017-04-28', '-15'))
        txn4_id = cursor.lastrowid
        cursor.execute('INSERT INTO transactions(account_id, txn_date, amount) values (?, ?, ?)',
                (account_id, '2017-05-28', '15'))
        txn5_id = cursor.lastrowid
        cursor.execute('INSERT INTO txn_categories(txn_id, category_id, amount) VALUES (?, ?, ?)', (txn_id, c_id, str(D('-101'))))
        cursor.execute('INSERT INTO txn_categories(txn_id, category_id, amount) VALUES (?, ?, ?)', (txn2_id, c2_id, str(D('-46.23'))))
        cursor.execute('INSERT INTO txn_categories(txn_id, category_id, amount) VALUES (?, ?, ?)', (txn3_id, c2_id, str(D('-56.23'))))
        cursor.execute('INSERT INTO txn_categories(txn_id, category_id, amount) VALUES (?, ?, ?)', (txn5_id, c2_id, str(D('15'))))
        cursor.execute('INSERT INTO budgets (start_date, end_date) VALUES (?, ?)', ('2018-01-01', '2018-12-31'))
        budget_id = cursor.lastrowid
        cursor.execute('INSERT INTO budget_values (budget_id, category_id, amount, notes) VALUES (?, ?, ?, ?)', (budget_id, c_id, '135', 'hello'))
        cursor.execute('INSERT INTO budget_values (budget_id, category_id, amount, carryover) VALUES (?, ?, ?, ?)', (budget_id, c2_id, '70', '15'))
        budget = storage.get_budget(budget_id)
        self.assertEqual(budget.id, budget_id)
        self.assertEqual(budget.start_date, date(2018, 1, 1))
        self.assertEqual(budget.end_date, date(2018, 12, 31))
        housing = storage.get_category(c_id)
        food = storage.get_category(c2_id)
        transportation = storage.get_category(c3_id)

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
        storage = SQLiteStorage(':memory:')
        cursor = storage._db_connection.cursor()
        cursor.execute('INSERT INTO categories (name, is_expense) VALUES (?, ?)', ('Housing', 1))
        c_id = cursor.lastrowid
        cursor.execute('INSERT INTO categories (name, is_expense) VALUES (?, ?)', ('Food', 1))
        c2_id = cursor.lastrowid
        cursor.execute('INSERT INTO budgets (start_date, end_date) VALUES (?, ?)', ('2018-01-01', '2018-12-31'))
        budget_id = cursor.lastrowid
        cursor.execute('INSERT INTO budget_values (budget_id, category_id, amount) VALUES (?, ?, ?)', (budget_id, c_id, '35'))
        cursor.execute('INSERT INTO budget_values (budget_id, category_id, amount) VALUES (?, ?, ?)', (budget_id, c2_id, '70'))
        budgets = storage.get_budgets()
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets[0].start_date, date(2018, 1, 1))
        self.assertEqual(budgets[0].end_date, date(2018, 12, 31))
        cat = list(budgets[0].get_report_display()['expense'].keys())[0]
        self.assertEqual(cat.name, 'Housing')


def fake_method():
    pass


class TestGUIUtils(unittest.TestCase):

    def test_categories_from_string(self):
        #takes string from user, parses it, and loads the category objects for passing to Transaction object
        storage = SQLiteStorage(':memory:')
        c = Category('Cat')
        c2 = Category('Dog')
        c3 = Category('Horse')
        storage.save_category(c)
        storage.save_category(c2)
        storage.save_category(c3)
        categories_string = '%s: -45, %s: -59, %s: 3' % (c.id, c2.id, c3.id)
        categories = txn_categories_from_string(storage, categories_string)
        self.assertEqual(categories, [(c, D('-45')), (c2, D('-59')), (c3, D('3'))])
        categories_string = str(c.id)
        categories = txn_categories_from_string(storage, categories_string)
        self.assertEqual(categories, [c])
        categories_string = ''
        categories = txn_categories_from_string(storage, categories_string)
        self.assertEqual(categories, [])


class TestQtGUI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication([])

    def test_pft_qt_gui(self):
        pft_qt_gui = PFT_GUI_QT(':memory:')

    def test_account(self):
        storage = SQLiteStorage(':memory:')
        a = Account(name='Checking', starting_balance=D(100))
        storage.save_account(a)
        accounts_display = AccountsDisplay(storage, reload_accounts=fake_method)
        widget = accounts_display.get_widget()
        accounts_display.add_account_widgets['entries']['name'].setText('Savings')
        accounts_display.add_account_widgets['entries']['starting_balance'].setText('500')
        QtTest.QTest.mouseClick(accounts_display.add_account_widgets['buttons']['add_new'], QtCore.Qt.LeftButton)
        accounts = storage.get_accounts()
        self.assertEqual(len(accounts), 2)

    def test_account_edit(self):
        storage = SQLiteStorage(':memory:')
        a = Account(name='Checking', starting_balance=D(100))
        storage.save_account(a)
        accounts_display = AccountsDisplay(storage, reload_accounts=fake_method)
        widget = accounts_display.get_widget()
        QtTest.QTest.mouseClick(accounts_display.accounts_widgets[a.id]['labels']['name'], QtCore.Qt.LeftButton)
        accounts_display.accounts_widgets[a.id]['entries']['name'].setText('Saving')
        QtTest.QTest.mouseClick(accounts_display.accounts_widgets[a.id]['buttons']['save_edit'], QtCore.Qt.LeftButton)
        self.assertEqual(len(storage.get_accounts()), 1)
        self.assertEqual(storage.get_accounts()[0].name, 'Saving')

    @patch('pft.set_widget_error_state')
    def test_account_exception(self, mock_method):
        storage = SQLiteStorage(':memory:')
        accounts_display = AccountsDisplay(storage, reload_accounts=fake_method)
        widget = accounts_display.get_widget()
        QtTest.QTest.mouseClick(accounts_display.add_account_widgets['buttons']['add_new'], QtCore.Qt.LeftButton)
        mock_method.assert_called_once_with(accounts_display.add_account_widgets['entries']['name'])

    def test_ledger_add(self):
        storage = SQLiteStorage(':memory:')
        account = Account(name='Checking', starting_balance=D(100))
        storage.save_account(account)
        txn = Transaction(account=account, amount=D(5), txn_date=date.today())
        txn2 = Transaction(account=account, amount=D(5), txn_date=date(2017, 1, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        ledger_display = LedgerDisplay(storage, show_ledger=fake_method)
        ledger_display.get_widget()
        ledger_display.add_txn_widgets['entries']['date'].setText('2017-01-05')
        ledger_display.add_txn_widgets['entries']['debit'].setText('18')
        QtTest.QTest.mouseClick(ledger_display.add_txn_widgets['buttons']['add_new'], QtCore.Qt.LeftButton)
        #make sure new txn was saved
        ledger = Ledger(starting_balance=account.starting_balance)
        storage.load_txns_into_ledger(account.id, ledger)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(len(txns), 3)
        self.assertEqual(txns[1].amount, D('-18'))
        #check new txn display
        self.assertEqual(ledger_display.add_txn_widgets['entries']['debit'].text(), '')
        self.assertEqual(len(ledger_display.ledger.get_sorted_txns_with_balance()), 3)
        self.assertEqual(ledger_display.txns_display.txn_display_data[txns[1].id]['row'], 1)

    def test_ledger_choose_account(self):
        storage = SQLiteStorage(':memory:')
        account = Account(name='Checking', starting_balance=D(100))
        account2 = Account(name='Savings', starting_balance=D(100))
        storage.save_account(account)
        storage.save_account(account2)
        txn = Transaction(account=account, amount=D(5), txn_date=date.today())
        txn2 = Transaction(account=account2, amount=D(5), txn_date=date(2017, 1, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        ledger_display = LedgerDisplay(storage, show_ledger=fake_method, current_account=account2)
        ledger_display.get_widget()
        self.assertEqual(ledger_display._current_account, account2)
        self.assertEqual(ledger_display.action_combo.currentIndex(), 1)
        self.assertEqual(ledger_display.action_combo.currentText(), 'Savings')

    def test_ledger_switch_account(self):
        show_ledger_mock = Mock()
        storage = SQLiteStorage(':memory:')
        account = Account(name='Checking', starting_balance=D(100))
        account2 = Account(name='Savings', starting_balance=D(100))
        storage.save_account(account)
        storage.save_account(account2)
        txn = Transaction(account=account, amount=D(5), txn_date=date.today())
        txn2 = Transaction(account=account, amount=D(5), txn_date=date(2017, 1, 2))
        txn3 = Transaction(account=account2, amount=D(5), txn_date=date(2018, 1, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        storage.save_txn(txn3)
        ledger_display = LedgerDisplay(storage, show_ledger=show_ledger_mock)
        ledger_display.get_widget()
        self.assertEqual(ledger_display._current_account, account)
        self.assertEqual(ledger_display.action_combo.currentIndex(), 0)
        self.assertEqual(ledger_display.action_combo.currentText(), 'Checking')
        ledger_display.action_combo.setCurrentIndex(1)
        show_ledger_mock.assert_called_once_with(account2)

    def test_ledger_txn_edit(self):
        storage = SQLiteStorage(':memory:')
        account = Account(name='Checking', starting_balance=D(100))
        storage.save_account(account)
        txn = Transaction(account=account, amount=D(5), txn_date=date(2017, 1, 3))
        txn2 = Transaction(account=account, amount=D(17), txn_date=date(2017, 5, 2))
        txn3 = Transaction(account=account, amount=D(25), txn_date=date(2017, 10, 18))
        txn4 = Transaction(account=account, amount=D(10), txn_date=date(2018, 6, 6))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        storage.save_txn(txn3)
        storage.save_txn(txn4)
        ledger_display = LedgerDisplay(storage, show_ledger=fake_method)
        ledger_display.get_widget()
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn.id]['widgets']['labels']['balance'].text(), '105')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['labels']['balance'].text(), '122')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn2.id]['row'], 1)
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn3.id]['widgets']['labels']['balance'].text(), '147')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn4.id]['widgets']['labels']['balance'].text(), '157')
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['labels']['date'], QtCore.Qt.LeftButton)
        ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['entries']['date'].setText('2017-12-31')
        ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['entries']['credit'].setText('20')
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['buttons']['save_edit'], QtCore.Qt.LeftButton)
        #make sure edit was saved
        ledger = Ledger(starting_balance=account.starting_balance)
        storage.load_txns_into_ledger(account.id, ledger)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(len(txns), 4)
        self.assertEqual(txns[2].txn_date, date(2017, 12, 31))
        self.assertEqual(txns[2].amount, D(20))
        #check display with edits
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn.id]['widgets']['labels']['balance'].text(), '105')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn.id]['row'], 0)
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn3.id]['widgets']['labels']['balance'].text(), '130')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn3.id]['row'], 1)
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['labels']['balance'].text(), '150')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn2.id]['row'], 2)
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn4.id]['widgets']['labels']['balance'].text(), '160')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn4.id]['row'], 3)

    def test_ledger_txn_edit_category(self):
        storage = SQLiteStorage(':memory:')
        account = Account(name='Checking', starting_balance=D(100))
        storage.save_account(account)
        cat = Category(name='Housing')
        cat2 = Category(name='Restaurants')
        storage.save_category(cat)
        storage.save_category(cat2)
        txn = Transaction(account=account, amount=D(5), txn_date=date(2017, 1, 3))
        txn2 = Transaction(account=account, amount=D(17), txn_date=date(2017, 5, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        ledger_display = LedgerDisplay(storage, show_ledger=fake_method)
        ledger_display.get_widget()
        #activate editing
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['labels']['date'], QtCore.Qt.LeftButton)
        #select a category
        ledger_display.txns_display.txn_display_data[txn2.id]['categories_display']._categories_combo.setCurrentIndex(2)
        #save the change
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['buttons']['save_edit'], QtCore.Qt.LeftButton)
        #make sure new category was saved
        ledger = Ledger(starting_balance=account.starting_balance)
        storage.load_txns_into_ledger(account.id, ledger)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(txns[1].categories[0][0].name, 'Restaurants')

    def test_ledger_txn_delete(self):
        storage = SQLiteStorage(':memory:')
        account = Account(name='Checking', starting_balance=D(100))
        storage.save_account(account)
        txn = Transaction(account=account, amount=D(5), txn_date=date.today())
        txn2 = Transaction(account=account, amount=D(23), txn_date=date(2017, 1, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        ledger_display = LedgerDisplay(storage, show_ledger=fake_method)
        ledger_display.get_widget()
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn.id]['widgets']['labels']['date'], QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn.id]['widgets']['buttons']['delete'], QtCore.Qt.LeftButton)
        #make sure txn was deleted
        ledger = Ledger(starting_balance=account.starting_balance)
        storage.load_txns_into_ledger(account.id, ledger)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].amount, D(23))

    def test_categories_add(self):
        storage = SQLiteStorage(':memory:')
        self.assertEqual(storage.get_categories(), [])
        categories_display = CategoriesDisplay(storage, reload_categories=fake_method)
        categories_display.get_widget()
        QtTest.QTest.keyClicks(categories_display.name_entry, 'Housing')
        QtTest.QTest.mouseClick(categories_display.add_button, QtCore.Qt.LeftButton)
        self.assertEqual(storage.get_categories()[0].name, 'Housing')

    def test_categories_add_user_id(self):
        storage = SQLiteStorage(':memory:')
        self.assertEqual(storage.get_categories(), [])
        categories_display = CategoriesDisplay(storage, reload_categories=fake_method)
        categories_display.get_widget()
        categories_display.user_id_entry.setText('400')
        categories_display.name_entry.setText('Housing')
        QtTest.QTest.mouseClick(categories_display.add_button, QtCore.Qt.LeftButton)
        cat = storage.get_categories()[0]
        self.assertEqual(cat.name, 'Housing')
        self.assertEqual(cat.user_id, '400')

    def test_categories_edit(self):
        storage = SQLiteStorage(':memory:')
        cat = Category(name='Housing')
        storage.save_category(cat)
        categories_display = CategoriesDisplay(storage, reload_categories=fake_method)
        categories_display.get_widget()
        QtTest.QTest.mouseClick(categories_display.data[cat.id]['labels']['name'], QtCore.Qt.LeftButton)
        self.assertEqual(categories_display.data[cat.id]['entries']['name'].text(), 'Housing')
        categories_display.data[cat.id]['entries']['user_id'].setText('400')
        categories_display.data[cat.id]['entries']['name'].setText('Food')
        QtTest.QTest.mouseClick(categories_display.data[cat.id]['buttons']['save_edit'], QtCore.Qt.LeftButton)
        cat = storage.get_categories()[0]
        self.assertEqual(cat.name, 'Food')
        self.assertEqual(cat.user_id, '400')

    def test_categories_delete(self):
        storage = SQLiteStorage(':memory:')
        cat = Category(name='Housing')
        storage.save_category(cat)
        categories_display = CategoriesDisplay(storage, reload_categories=fake_method)
        categories_display.get_widget()
        QtTest.QTest.mouseClick(categories_display.data[cat.id]['labels']['name'], QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(categories_display.data[cat.id]['buttons']['delete'], QtCore.Qt.LeftButton)
        self.assertEqual(storage.get_categories(), [])

    def test_budget(self):
        storage = SQLiteStorage(':memory:')
        c = Category(name='Housing')
        storage.save_category(c)
        c2 = Category(name='Food')
        storage.save_category(c2)
        c3 = Category(name='Wages', is_expense=False)
        storage.save_category(c3)
        b = Budget(year=2018, category_budget_info={
            c: {'amount': D(15), 'carryover': D(0)},
            c2: {'amount': D(25), 'carryover': D(0)},
            c3: {'amount': D(100)},
        })
        storage.save_budget(b)
        budget = storage.get_budgets()[0]
        self.assertEqual(budget.get_budget_data()[c]['amount'], D(15))
        budget_display = BudgetDisplay(budget=budget, storage=storage, reload_budget=fake_method)
        budget_display.get_widget()
        QtTest.QTest.mouseClick(budget_display._edit_button, QtCore.Qt.LeftButton)
        budget_display.data[c.id]['budget_entry'].setText('30')
        QtTest.QTest.mouseClick(budget_display._save_button, QtCore.Qt.LeftButton) #now it's the save button
        budgets = storage.get_budgets()
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets[0].get_budget_data()[c]['amount'], D(30))


class TestLoadTestData(unittest.TestCase):

    def test_load(self):
        storage = SQLiteStorage(':memory:')
        load_test_data._load_data(storage, many_txns=False)


if __name__ == '__main__':
    unittest.main()

