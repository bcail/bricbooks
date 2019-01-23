from datetime import date
from decimal import Decimal as D
import os
import sqlite3
import tempfile
import tkinter
import unittest
from unittest.mock import patch
from PySide2 import QtWidgets, QtTest, QtCore

from pft import (
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
        txn_categories_from_string,
        txn_categories_display,
        AccountsDisplayWidget,
        LedgerWidget,
        CategoriesDisplayWidget,
        BudgetDisplayWidget,
        PFT_GUI,
    )
import pft_qt as pft_qt


class AbstractTkTest:
    '''Copy this from cpython source code (tkinter.test.support), because Ubuntu/Mint don't seem to package that support code.'''

    @classmethod
    def setUpClass(cls):
        cls._old_support_default_root = tkinter._support_default_root
        destroy_default_root()
        tkinter.NoDefaultRoot()
        cls.root = tkinter.Tk()
        cls.wantobjects = cls.root.wantobjects()
        # De-maximize main window.
        # Some window managers can maximize new windows.
        cls.root.wm_state('normal')
        try:
            cls.root.wm_attributes('-zoomed', False)
        except tkinter.TclError:
            pass

    @classmethod
    def tearDownClass(cls):
        cls.root.update_idletasks()
        cls.root.destroy()
        del cls.root
        tkinter._default_root = None
        tkinter._support_default_root = cls._old_support_default_root

    def setUp(self):
        self.root.deiconify()

    def tearDown(self):
        for w in self.root.winfo_children():
            w.destroy()
        self.root.withdraw()

def destroy_default_root():
    if getattr(tkinter, '_default_root', None):
        tkinter._default_root.update_idletasks()
        tkinter._default_root.destroy()
        tkinter._default_root = None


class TestAccount(unittest.TestCase):

    def test_init(self):
        a = Account(name='Checking', starting_balance=D('100'))
        self.assertEqual(a.name, 'Checking')
        self.assertEqual(a.starting_balance, D('100'))

    def test_starting_balance(self):
        with self.assertRaises(InvalidAccountError):
            Account(name='Checking', starting_balance=123.1)


class TestCategory(unittest.TestCase):

    def test_init(self):
        c = Category('Restaurants')
        self.assertEqual(c.name, 'Restaurants')


class TestTransaction(unittest.TestCase):

    def test_invalid_txn_amount(self):
        with self.assertRaises(InvalidTransactionError) as cm:
            Transaction()
        self.assertEqual(str(cm.exception), 'transaction must belong to an account')
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
        self.assertEqual(str(cm.exception), 'invalid type for txn_date')

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
                    'categories': '1: 101',
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
                categories=[(c, D('-45')), (c2, D('-56'))],
            )
        self.assertEqual(t.categories[0][0], c)
        self.assertEqual(t.categories[0][1], D('-45'))
        self.assertEqual(t.categories[1][0], c2)
        self.assertEqual(t.categories[1][1], D('-56'))

    def test_mixed_split_categories(self):
        a = Account(name='Checking', starting_balance=D('100'))
        c = Category('Cat')
        c2 = Category('Dog')
        c3 = Category('Horse')
        t = Transaction(
                account=a,
                amount=D('-101'),
                txn_date=date.today(),
                categories=[(c, D('-45')), (c2, D('-59')), (c3, D('3'))],
            )
        self.assertEqual(t.categories[0][0], c)
        self.assertEqual(t.categories[0][1], D('-45'))
        self.assertEqual(t.categories[1][0], c2)
        self.assertEqual(t.categories[1][1], D('-59'))
        self.assertEqual(t.categories[2][0], c3)
        self.assertEqual(t.categories[2][1], D('3'))

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
        ledger_records = ledger.get_sorted_txns()
        self.assertEqual(ledger_records[0].txn_date, date(2017, 4, 25))
        self.assertEqual(ledger_records[1].txn_date, date(2017, 6, 5))
        self.assertEqual(ledger_records[2].txn_date, date(2017, 7, 30))
        self.assertEqual(ledger_records[3].txn_date, date(2017, 8, 5))

    def test_get_txn(self):
        a = Account(name='Checking', starting_balance=D('100'))
        ledger = Ledger(starting_balance=a.starting_balance)
        ledger.add_transaction(Transaction(id_=1, account=a, amount=D('32.45'), txn_date=date(2017, 8, 5)))
        ledger.add_transaction(Transaction(id_=2, account=a, amount=D('-12'), txn_date=date(2017, 6, 5)))
        txn = ledger.get_txn(id=2)
        self.assertEqual(txn.amount, D('-12'))

    def test_clear_txns(self):
        a = Account(name='Checking', starting_balance=D('100'))
        ledger = Ledger(starting_balance=D('100.12'))
        ledger.add_transaction(Transaction(id_=1, account=a, amount=D('12.34'), txn_date=date(2017, 8, 5)))
        ledger.clear_txns()
        self.assertEqual(ledger.get_sorted_txns(), [])


class TestBudget(unittest.TestCase):

    def test_init(self):
        with self.assertRaises(BudgetError):
            Budget()
        c = Category(name='Housing', id_=1)
        c2 = Category(name='Food', id_=2)
        c3 = Category(name='Transportation', id_=3)
        category_rows = {
                c: {'amount': D(15), 'carryover': D(5)},
                c2: {'amount': '35', 'carryover': ''},
                c3: {},
            }
        b = Budget(year=2018, category_budget_info=category_rows)
        self.assertEqual(b.year, 2018)
        self.assertEqual(b.get_budget_data(),
                {c: {'amount': D(15), 'carryover': D(5)}, c2: {'amount': D(35)}, c3: {}})

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
        category_rows = {
                c: {'amount': D(15), 'carryover': D(5)},
                c2: {},
                c3: {'amount': D(10)},
                c4: {'amount': D(0)},
            }
        budget = Budget(year=2018, category_budget_info=category_rows)
        with self.assertRaises(BudgetError):
            budget.get_report_display()
        income_spending_info = {c: {'income': D(5), 'spent': D(10)}, c2: {}}
        budget = Budget(year=2018, category_budget_info=category_rows, income_spending_info=income_spending_info)
        budget_report = budget.get_report_display()
        c_info = budget_report[c]
        self.assertEqual(c_info['amount'], '15')
        self.assertEqual(c_info['carryover'], '5')
        self.assertEqual(c_info['income'], '5')
        self.assertEqual(c_info['total_budget'], '25')
        self.assertEqual(c_info['spent'], '10')
        self.assertEqual(c_info['remaining'], '15')
        self.assertEqual(c_info['percent_available'], '60%')
        c2_info = budget_report[c2]
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
        c3_info = budget_report[c3]
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
        account = Account(id=1, name='Savings', starting_balance=D(200))
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
        c = Category(name='Housing')
        storage.save_category(c)
        self.assertEqual(c.id, 1)
        records = storage._db_connection.execute('SELECT * FROM categories').fetchall()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][0], 1)
        self.assertEqual(records[0][1], 'Housing')

    def test_get_categories(self):
        storage = SQLiteStorage(':memory:')
        c = Category(name='Housing')
        storage.save_category(c)
        c2 = Category(name='Food')
        storage.save_category(c2)
        categories = storage.get_categories()
        self.assertEqual(categories[0], c)
        self.assertEqual(categories[1], c2)
        self.assertEqual(len(categories), 2)

    def test_delete_category(self):
        storage = SQLiteStorage(':memory:')
        c = Category(name='Housing')
        storage.save_category(c)
        storage.delete_category(c.id)
        records = storage._db_connection.execute('SELECT * FROM categories').fetchall()
        self.assertEqual(records, [])

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
        txns = ledger.get_sorted_txns()
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
                c: {'amount': D(15), 'carryover': D(0)},
                c2: {'amount': D(25), 'carryover': D(10)}
            }
        b = Budget(year=2018, category_budget_info=category_rows)
        storage.save_budget(b)
        cursor = storage._db_connection.cursor()
        records = cursor.execute('SELECT * FROM budgets WHERE year = 2018').fetchall()
        self.assertEqual(len(records), 1)
        self.assertEqual(b.id, 1)
        records = cursor.execute('SELECT * FROM budget_values').fetchall()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0][1], 1)
        self.assertEqual(records[0][2], 1)
        self.assertEqual(records[0][3], '15')
        self.assertEqual(records[0][4], '0')
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
        records = cursor.execute('SELECT * FROM budgets WHERE year = 2018').fetchall()
        self.assertEqual(len(records), 1)

    def test_get_budget(self):
        storage = SQLiteStorage(':memory:')
        cursor = storage._db_connection.cursor()
        cursor.execute('INSERT INTO categories (name) VALUES (?)', ('Housing',))
        c_id = cursor.lastrowid
        cursor.execute('INSERT INTO categories (name) VALUES (?)', ('Food',))
        c2_id = cursor.lastrowid
        cursor.execute('INSERT INTO categories (name) VALUES (?)', ('Transportation',))
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
        cursor.execute('INSERT INTO budgets (year) VALUES (?)', ('2018',))
        budget_id = cursor.lastrowid
        cursor.execute('INSERT INTO budget_values (budget_id, category_id, amount) VALUES (?, ?, ?)', (budget_id, c_id, '135'))
        cursor.execute('INSERT INTO budget_values (budget_id, category_id, amount, carryover) VALUES (?, ?, ?, ?)', (budget_id, c2_id, '70', '15'))
        budget = storage.get_budget(budget_id)
        self.assertEqual(budget.id, budget_id)
        self.assertEqual(budget.year, 2018)
        housing = storage.get_category(c_id)
        food = storage.get_category(c2_id)
        transportation = storage.get_category(c3_id)

        report_display = budget.get_report_display()
        self.assertEqual(report_display[housing]['amount'], '135')
        self.assertEqual(report_display[housing]['carryover'], '')
        self.assertEqual(report_display[housing]['income'], '')
        self.assertEqual(report_display[housing]['spent'], '101')

        self.assertEqual(report_display[food]['amount'], '70')
        self.assertEqual(report_display[food]['carryover'], '15')
        self.assertEqual(report_display[food]['income'], '15')
        self.assertEqual(report_display[food]['spent'], '102.46')

        self.assertEqual(report_display[transportation]['amount'], '')
        self.assertEqual(report_display[transportation]['spent'], '')

    def test_get_budget_reports(self):
        storage = SQLiteStorage(':memory:')
        cursor = storage._db_connection.cursor()
        cursor.execute('INSERT INTO categories (name) VALUES (?)', ('Housing',))
        c_id = cursor.lastrowid
        cursor.execute('INSERT INTO categories (name) VALUES (?)', ('Food',))
        c2_id = cursor.lastrowid
        cursor.execute('INSERT INTO budgets (year) VALUES (?)', ('2018',))
        budget_id = cursor.lastrowid
        cursor.execute('INSERT INTO budget_values (budget_id, category_id, amount) VALUES (?, ?, ?)', (budget_id, c_id, '35'))
        cursor.execute('INSERT INTO budget_values (budget_id, category_id, amount) VALUES (?, ?, ?)', (budget_id, c2_id, '70'))
        budgets = storage.get_budgets()
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets[0].year, 2018)
        cat = list(budgets[0].get_report_display().keys())[0]
        self.assertEqual(cat.name, 'Housing')


def fake_method():
    pass


class TestGUI(AbstractTkTest, unittest.TestCase):

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

    def test_accounts_display_widget(self):
        storage = SQLiteStorage(':memory:')
        acc = Account(name='Savings', starting_balance=D(5000))
        storage.save_account(acc)
        adw = AccountsDisplayWidget(master=self.root, accounts=[acc], storage=storage, show_accounts=fake_method)
        adw.add_account_name_entry.insert(0, 'Checking')
        adw.add_account_starting_balance_entry.insert(0, '100')
        adw.add_account_button.invoke()
        #make sure there's another account now
        accounts = storage._db_connection.execute('SELECT name FROM accounts').fetchall()
        self.assertEqual(len(accounts), 2)
        self.assertEqual(accounts[0][0], 'Savings')
        self.assertEqual(accounts[1][0], 'Checking')

    def test_accounts_display_widget_edit(self):
        storage = SQLiteStorage(':memory:')
        acc = Account(name='Savings', starting_balance=D(5000))
        storage.save_account(acc)
        adw = AccountsDisplayWidget(master=self.root, accounts=[acc], storage=storage, show_accounts=fake_method)
        adw.data[acc.id]['edit_button'].invoke()
        self.assertEqual(adw.data[acc.id]['entries']['name'].get(), 'Savings')
        adw.data[acc.id]['entries']['name'].delete(0, tkinter.END)
        adw.data[acc.id]['entries']['name'].insert(0, 'Checking')
        adw.data[acc.id]['save_button'].invoke()
        accounts = storage._db_connection.execute('SELECT name FROM accounts').fetchall()
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0][0], 'Checking')

    def test_ledger_widget(self):
        storage = SQLiteStorage(':memory:')
        account = Account(name='Checking', starting_balance=D('100'))
        storage.save_account(account)
        category = Category(name='Housing')
        category2 = Category(name='Food')
        storage.save_category(category)
        storage.save_category(category2)
        txn = Transaction(account=account, amount=D(5), txn_date=date.today(), description='description',
                categories=[category])
        storage.save_txn(txn)
        txn2 = Transaction(account=account, amount=D(15), txn_date=date(2017, 1, 1))
        storage.save_txn(txn2)
        ledger = Ledger(starting_balance=account.starting_balance)
        ledger_widget = LedgerWidget(ledger, master=self.root, storage=storage, account=account)
        self.assertEqual(ledger_widget.display_data[txn.id]['labels']['categories'].cget('text'), '1: 5')
        self.assertEqual(ledger_widget.display_data[txn.id]['labels']['balance'].cget('text'), '120')
        self.assertEqual(ledger_widget.display_data[txn.id]['row'], 1)
        self.assertEqual(ledger_widget.display_data[txn2.id]['labels']['balance'].cget('text'), '115')
        self.assertEqual(ledger_widget.display_data[txn2.id]['row'], 0)
        #edit txn - check credit entry is 5
        ledger_widget.display_data[txn.id]['labels']['txn_type'].event_generate('<Button-1>', x=0, y=0)
        self.assertEqual(ledger_widget.display_data[txn.id]['entries']['credit'].get(), '5')
        self.assertEqual(ledger_widget.display_data[txn.id]['entries']['categories'].get(), '1: 5')
        #edit txn - change amount to 25, add payee
        ledger_widget.display_data[txn.id]['entries']['credit'].insert(0, '2')
        ledger_widget.display_data[txn.id]['entries']['payee'].insert(0, 'Someone')
        ledger_widget.display_data[txn.id]['entries']['categories'].delete(0, tkinter.END)
        ledger_widget.display_data[txn.id]['entries']['categories'].insert(0, str(category2.id))
        ledger_widget.display_data[txn.id]['buttons'][0].invoke()
        #make sure db record amount is updated to 25
        txns = storage._db_connection.execute('SELECT amount, payee FROM transactions WHERE id = ?', (txn.id,)).fetchall()
        self.assertEqual(txns[0][0], '25')
        self.assertEqual(txns[0][1], 'Someone')
        txn_categories = storage._db_connection.execute('SELECT category_id, amount FROM txn_categories WHERE txn_id = ?', (txn.id,)).fetchall()
        self.assertEqual(len(txn_categories), 1)
        self.assertEqual(txn_categories[0][0], category2.id)
        self.assertEqual(txn_categories[0][1], '25')

    def test_ledger_widget_empty_add(self):
        storage = SQLiteStorage(':memory:')
        account = Account(name='Checking', starting_balance=D('100'))
        storage.save_account(account)
        ledger = Ledger(starting_balance=account.starting_balance)
        ledger_widget = LedgerWidget(ledger, master=self.root, storage=storage, account=account)
        new_txn = Transaction(account=account, amount=D('17'), txn_date=date(2017, 5, 1))
        storage.save_txn(new_txn)
        ledger_widget.display_new_txn(new_txn)

    def test_ledger_widget_add(self):
        storage = SQLiteStorage(':memory:')
        account = Account(name='Checking', starting_balance=D('100'))
        storage.save_account(account)
        txn = Transaction(account=account, amount=D('5'), txn_date=date.today())
        txn2 = Transaction(account=account, amount=D('5'), txn_date=date(2017, 1, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        ledger = Ledger(starting_balance=account.starting_balance)
        ledger_widget = LedgerWidget(ledger, master=self.root, storage=storage, account=account)
        new_txn = Transaction(account=account, amount=D('17'), txn_date=date(2017, 5, 1))
        storage.save_txn(new_txn)
        ledger_widget.display_new_txn(new_txn)
        self.assertEqual(len(ledger_widget.display_data.keys()), 3)
        self.assertEqual(ledger_widget.display_data[new_txn.id]['labels']['credit'].cget('text'), '17')
        self.assertEqual(ledger_widget.display_data[new_txn.id]['row'], 1)
        self.assertEqual(ledger_widget.display_data[txn.id]['row'], 2)
        self.assertEqual(ledger_widget.display_data[txn2.id]['row'], 0)

    def test_ledger_widget_reorder(self):
        storage = SQLiteStorage(':memory:')
        account = Account(name='Checking', starting_balance=D('100'))
        storage.save_account(account)
        txn = Transaction(account=account, amount=D('5'), txn_date=date(2017, 1, 1))
        txn2 = Transaction(account=account, amount=D('5'), txn_date=date(2017, 1, 2))
        txn3 = Transaction(account=account, amount=D('5'), txn_date=date(2017, 1, 3))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        storage.save_txn(txn3)
        ledger = Ledger(starting_balance=account.starting_balance)
        ledger_widget = LedgerWidget(ledger, master=self.root, storage=storage, account=account)
        self.assertEqual(ledger_widget.display_data[txn.id]['row'], 0)
        self.assertEqual(ledger_widget.display_data[txn3.id]['row'], 2)
        #change date of first txn, moving it to the end
        ledger_widget.display_data[txn.id]['labels']['txn_type'].event_generate('<Button-1>', x=0, y=0)
        ledger_widget.display_data[txn.id]['entries']['date'].delete(0, tkinter.END)
        ledger_widget.display_data[txn.id]['entries']['date'].insert(0, '2017-01-20')
        ledger_widget.display_data[txn.id]['buttons'][0].invoke()
        self.assertEqual(ledger_widget.display_data[txn.id]['row'], 2)
        self.assertEqual(ledger_widget.display_data[txn3.id]['row'], 1)

    def test_ledger_widget_delete(self):
        storage = SQLiteStorage(':memory:')
        account = Account(name='Checking', starting_balance=D('100'))
        storage.save_account(account)
        txn = Transaction(account=account, amount=D('5'), txn_date=date(2017, 1, 1))
        txn2 = Transaction(account=account, amount=D('5'), txn_date=date(2017, 1, 2))
        txn3 = Transaction(account=account, amount=D('5'), txn_date=date(2017, 1, 3))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        storage.save_txn(txn3)
        ledger = Ledger(starting_balance=account.starting_balance)
        ledger_widget = LedgerWidget(ledger, master=self.root, storage=storage, account=account)
        ledger_widget.display_data[txn.id]['labels']['txn_type'].event_generate('<Button-1>', x=0, y=0)
        ledger_widget.display_data[txn.id]['buttons'][1].invoke()
        self.assertTrue(txn.id not in ledger_widget.display_data)
        self.assertEqual(ledger_widget.display_data[txn2.id]['row'], 0)

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
        self.assertEqual(txn_categories_display(t), '%s: -45, %s: -59, %s: 3' % (c.id, c2.id, c3.id))

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

    def test_categories_display_widget(self):
        storage = SQLiteStorage(':memory:')
        c = Category(name='Housing')
        storage.save_category(c)
        c2 = Category(name='Food')
        storage.save_category(c2)
        CategoriesDisplayWidget(master=self.root, categories=[c, c2], storage=storage,
                reload_categories=lambda x: x, delete_category=lambda x: x)

    def test_budget_display_widget(self):
        storage = SQLiteStorage(':memory:')
        c = Category(name='Housing')
        storage.save_category(c)
        c2 = Category(name='Food')
        storage.save_category(c2)
        b = Budget(year=2018, category_budget_info={
            c: {'amount': D(15), 'carryover': D(0),},
            c2: {'amount': D(25), 'carryover': D(0)},
        })
        storage.save_budget(b)
        budget = storage.get_budgets()[0]
        self.assertEqual(budget.get_budget_data()[c]['amount'], D(15))
        dw = BudgetDisplayWidget(master=self.root, budget=budget, storage=storage, reload_budget=fake_method)
        dw._edit_button.invoke()
        dw.data[c.id]['budget_entry'].delete(0, tkinter.END)
        dw.data[c.id]['budget_entry'].insert(0, '30')
        dw._edit_button.invoke()
        budget = storage.get_budgets()[0]
        self.assertEqual(budget.get_budget_data()[c]['amount'], D(30))

    def test_pft_gui_empty_file_create_account_show_ledger(self):
        pft_gui = PFT_GUI(self.file_name)
        pft_gui.adw.add_account_name_entry.insert(0, 'Checking')
        pft_gui.adw.add_account_starting_balance_entry.insert(0, '1000')
        pft_gui.adw.add_account_button.invoke()
        pft_gui._show_ledger()


class TestQtGUI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication([])

    def test_pft_qt_gui(self):
        pft_qt_gui = pft_qt.PFT_GUI_QT(':memory:')

    def test_account(self):
        storage = SQLiteStorage(':memory:')
        a = Account(name='Checking', starting_balance=D(100))
        storage.save_account(a)
        dw = pft_qt.AccountsDisplayWidget(storage, reload_accounts=fake_method)
        dw.add_account_widgets['entries']['name'].setText('Savings')
        dw.add_account_widgets['entries']['starting_balance'].setText('500')
        QtTest.QTest.mouseClick(dw.add_account_widgets['buttons']['add_new'], QtCore.Qt.LeftButton)
        accounts = storage.get_accounts()
        self.assertEqual(len(accounts), 2)

    def test_account_edit(self):
        storage = SQLiteStorage(':memory:')
        a = Account(name='Checking', starting_balance=D(100))
        storage.save_account(a)
        dw = pft_qt.AccountsDisplayWidget(storage, reload_accounts=fake_method)
        QtTest.QTest.mouseClick(dw.accounts_widgets[a.id]['buttons']['edit'], QtCore.Qt.LeftButton)
        dw.accounts_widgets[a.id]['entries']['name'].setText('Saving')
        QtTest.QTest.mouseClick(dw.accounts_widgets[a.id]['buttons']['save'], QtCore.Qt.LeftButton)
        self.assertEqual(len(storage.get_accounts()), 1)
        self.assertEqual(storage.get_accounts()[0].name, 'Saving')

    @patch('pft_qt.set_widget_error_state')
    def test_account_exception(self, mock_method):
        storage = SQLiteStorage(':memory:')
        dw = pft_qt.AccountsDisplayWidget(storage, reload_accounts=fake_method)
        QtTest.QTest.mouseClick(dw.add_account_widgets['buttons']['add_new'], QtCore.Qt.LeftButton)
        mock_method.assert_called_once()

    def test_ledger(self):
        storage = SQLiteStorage(':memory:')
        account = Account(name='Checking', starting_balance=D(100))
        storage.save_account(account)
        txn = Transaction(account=account, amount=D(5), txn_date=date.today())
        txn2 = Transaction(account=account, amount=D(5), txn_date=date(2017, 1, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        dw = pft_qt.LedgerDisplayWidget(storage)
        dw.add_txn_widgets['entries']['date'].setText('2017-01-05')
        dw.add_txn_widgets['entries']['debit'].setText('18')
        QtTest.QTest.mouseClick(dw.add_txn_widgets['buttons']['add_new'], QtCore.Qt.LeftButton)
        #make sure new txn was saved
        ledger = Ledger(starting_balance=account.starting_balance)
        storage.load_txns_into_ledger(account.id, ledger)
        txns = ledger.get_sorted_txns()
        self.assertEqual(len(txns), 3)
        self.assertEqual(txns[1].amount, D('-18'))
        #check new txn display
        self.assertEqual(dw.add_txn_widgets['entries']['debit'].text(), '')
        self.assertEqual(len(dw.ledger.get_sorted_txns()), 3)
        self.assertEqual(dw.txns_display.txn_display_data[txns[1].id]['row'], 1)

    def test_ledger_txn_edit(self):
        storage = SQLiteStorage(':memory:')
        account = Account(name='Checking', starting_balance=D(100))
        storage.save_account(account)
        txn = Transaction(account=account, amount=D(5), txn_date=date.today())
        txn2 = Transaction(account=account, amount=D(5), txn_date=date(2017, 1, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        dw = pft_qt.LedgerDisplayWidget(storage)
        QtTest.QTest.mouseClick(dw.txns_display.txn_display_data[txn.id]['widgets']['labels']['date'], QtCore.Qt.LeftButton)
        dw.txns_display.txn_display_data[txn.id]['widgets']['entries']['credit'].setText('20')
        QtTest.QTest.mouseClick(dw.txns_display.txn_display_data[txn.id]['widgets']['buttons']['save_edit'], QtCore.Qt.LeftButton)
        #make sure edit was saved
        ledger = Ledger(starting_balance=account.starting_balance)
        storage.load_txns_into_ledger(account.id, ledger)
        txns = ledger.get_sorted_txns()
        self.assertEqual(len(txns), 2)
        self.assertEqual(txns[1].txn_date, date.today())
        self.assertEqual(txns[1].amount, D(20))

    def test_categories(self):
        storage = SQLiteStorage(':memory:')
        self.assertEqual(storage.get_categories(), [])
        dw = pft_qt.CategoriesDisplayWidget(storage, reload_categories=fake_method)
        QtTest.QTest.keyClicks(dw.name_entry, 'Housing')
        QtTest.QTest.mouseClick(dw.add_button, QtCore.Qt.LeftButton)
        self.assertEqual(storage.get_categories()[0].name, 'Housing')

    def test_budget(self):
        storage = SQLiteStorage(':memory:')
        c = Category(name='Housing')
        storage.save_category(c)
        c2 = Category(name='Food')
        storage.save_category(c2)
        b = Budget(year=2018, category_budget_info={
            c: {'amount': D(15), 'carryover': D(0)},
            c2: {'amount': D(25), 'carryover': D(0)},
        })
        storage.save_budget(b)
        budget = storage.get_budgets()[0]
        self.assertEqual(budget.get_budget_data()[c]['amount'], D(15))
        dw = pft_qt.BudgetDisplayWidget(budget=budget, storage=storage, reload_budget=fake_method)
        QtTest.QTest.mouseClick(dw._edit_button, QtCore.Qt.LeftButton)
        dw.data[c.id]['budget_entry'].setText('30')
        QtTest.QTest.mouseClick(dw._save_button, QtCore.Qt.LeftButton) #now it's the save button
        budgets = storage.get_budgets()
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets[0].get_budget_data()[c]['amount'], D(30))


if __name__ == '__main__':
    unittest.main()

