from datetime import date
from decimal import Decimal as D
import os
import sqlite3
import tempfile
from tkinter.test.support import AbstractTkTest
from tkinter import END
import unittest

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
    )


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
        t.update_values(
                txn_type='1234',
                amount=D('45'),
            )
        self.assertEqual(t.txn_type, '1234')
        self.assertEqual(t.amount, D('45'))
        self.assertEqual(t.payee, 'Wendys')

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
        t.update_values(payee='')
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
            t.update_values(amount='ab')
        with self.assertRaises(InvalidTransactionError):
            t.update_values(txn_date='ab')
        c = Category('Cat')
        c2 = Category('Dog')
        with self.assertRaises(InvalidTransactionError):
            t.update_values(categories=[(c, D('55')), (c2, D('56'))])


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
        self.assertEqual(ledger._txns, [])
        a = Account(name='Checking', starting_balance=D('100'))
        txn = Transaction(account=a, amount=D('101'), txn_date=date.today())
        ledger.add_transaction(txn)
        self.assertEqual(len(ledger._txns), 1)

    def test_get_ledger_records(self):
        a = Account(name='Checking', starting_balance=D('100'))
        ledger = Ledger(starting_balance=a.starting_balance)
        ledger.add_transaction(Transaction(account=a, amount=D('32.45'), txn_date=date(2017, 8, 5)))
        ledger.add_transaction(Transaction(account=a, amount=D('-12'), txn_date=date(2017, 6, 5)))
        ledger.add_transaction(Transaction(account=a, amount=D('1'), txn_date=date(2017, 7, 30)))
        ledger.add_transaction(Transaction(account=a, amount=D('10'), txn_date=date(2017, 4, 25)))
        ledger_records = ledger.get_records()
        self.assertEqual(ledger_records[0]['txn'].txn_date, date(2017, 4, 25))
        self.assertEqual(ledger_records[0]['balance'], D('110'))
        self.assertEqual(ledger_records[1]['txn'].txn_date, date(2017, 6, 5))
        self.assertEqual(ledger_records[1]['balance'], D('98'))
        self.assertEqual(ledger_records[2]['txn'].txn_date, date(2017, 7, 30))
        self.assertEqual(ledger_records[2]['balance'], D('99'))
        self.assertEqual(ledger_records[3]['txn'].txn_date, date(2017, 8, 5))
        self.assertEqual(ledger_records[3]['balance'], D('131.45'))

    def test_clear_txns(self):
        a = Account(name='Checking', starting_balance=D('100'))
        ledger = Ledger(starting_balance=D('100.12'))
        ledger.add_transaction(Transaction(account=a, amount=D('12.34'), txn_date=date(2017, 8, 5)))
        ledger.clear_txns()
        self.assertEqual(ledger.get_records(), [])


class TestBudget(unittest.TestCase):

    def test_init(self):
        with self.assertRaises(BudgetError):
            Budget()
        with self.assertRaises(BudgetError):
            Budget(year=2018)
        c = Category(name='Housing', id_=1)
        c2 = Category(name='Food', id_=2)
        category_rows = {
                c: {'budget': D(15), 'carryover': D(5), 'income': D(5), 'spent': D(10)},
                c2: {'budget': D(35), 'carryover': D(10), 'income': D(0), 'spent': D(0)},
            }
        b = Budget(year=2018, category_rows=category_rows)
        self.assertEqual(b.year, 2018)
        rows = b.display_category_rows
        self.assertEqual(rows[c]['budget'], D(15))
        self.assertEqual(rows[c]['carryover'], D(5))
        self.assertEqual(rows[c]['income'], D(5))
        self.assertEqual(rows[c]['total_budget'], D(25))
        self.assertEqual(rows[c]['spent'], D(10))
        self.assertEqual(rows[c]['remaining'], D(15))
        self.assertEqual(rows[c]['percent_available'], D(60))
        self.assertEqual(rows[c2],
                {
                    'budget': D(35),
                    'income': D(0),
                    'carryover': D(10),
                    'total_budget': D(45),
                    'spent': D(0),
                    'remaining': D(45),
                    'percent_available': D(100),
                }
            )

    def test_percent_rounding(self):
        self.assertEqual(Budget.round_percent_available(D('1.1')), D(1))
        self.assertEqual(Budget.round_percent_available(D('1.8')), D(2))
        self.assertEqual(Budget.round_percent_available(D('1.5')), D(2))
        self.assertEqual(Budget.round_percent_available(D('2.5')), D(3))


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
        records = ledger.get_records()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]['txn'].amount, D('101'))
        self.assertEqual(records[1]['txn'].amount, D('46.23'))

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
                c: {'budget': D(15), 'income': D(0), 'carryover': D(0), 'spent': D(0)},
                c2: {'budget': D(25), 'income': D(0), 'carryover': D(10), 'spent': D(0)}
            }
        b = Budget(year=2018, category_rows=category_rows)
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
        b = Budget(year=2018, category_rows={
            c: {'budget': D(35), 'income': D(0), 'carryover': D(0), 'spent': D(0)},
                c2: {'budget': D(45), 'income': D(0), 'carryover': D(0), 'spent': D(0)},
            }, id_=b.id)
        storage.save_budget(b)
        records = cursor.execute('SELECT * FROM budgets').fetchall()
        self.assertEqual(len(records), 1)
        records = cursor.execute('SELECT amount FROM budget_values ORDER BY amount').fetchall()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0][0], '35')

    def test_save_budget_file(self):
        #test that save actually gets committed
        storage = SQLiteStorage(self.file_name)
        c = Category(name='Housing')
        storage.save_category(c)
        c2 = Category(name='Food')
        storage.save_category(c2)
        b = Budget(year=2018, category_rows={
            c: {'budget': D(15), 'income': D(0), 'carryover': D(0), 'spent': D(0)},
            c2: {'budget': D(25), 'income': D(0), 'carryover': D(0), 'spent': D(0)},
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
        categories = budget.display_category_rows.keys()
        housing = [c for c in categories if c.id == c_id][0]
        food = [c for c in categories if c.id == c2_id][0]
        transportation = [c for c in categories if c.id == c3_id][0]
        category_names = [c.name for c in categories]
        self.assertEqual(sorted(category_names), ['Food', 'Housing', 'Transportation'])

        category_rows = budget.display_category_rows
        self.assertEqual(category_rows[housing]['budget'], D(135))
        self.assertEqual(category_rows[housing]['income'], D(0))
        self.assertEqual(category_rows[housing]['carryover'], D(0))
        self.assertEqual(category_rows[housing]['spent'], D(101))

        self.assertEqual(category_rows[food]['budget'], D(70))
        self.assertEqual(category_rows[food]['income'], D('15'))
        self.assertEqual(category_rows[food]['carryover'], D(15))
        self.assertEqual(category_rows[food]['spent'], D('102.46'))

        self.assertEqual(category_rows[transportation]['budget'], D(0))
        self.assertEqual(category_rows[transportation]['spent'], D(0))
        self.assertEqual(str(category_rows[transportation]['spent']), '0')

    def test_get_budgets(self):
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
        cat = list(budgets[0].display_category_rows.keys())[0]
        self.assertEqual(cat.name, 'Housing')


class TestGUI(AbstractTkTest, unittest.TestCase):

    def test_add_account(self):
        storage = SQLiteStorage(':memory:')
        def load_accounts(): pass
        def display_ledger(): pass
        adw = AccountsDisplayWidget(master=self.root, storage=storage, load_accounts=load_accounts, display_ledger=display_ledger)
        adw.name_entry.insert(0, 'Checking')
        adw.starting_balance_entry.insert(0, '100')
        adw.save_button.invoke()
        #make sure there's an account now
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
        txn = Transaction(account=account, amount=D('5'), txn_date=date.today(), description='description',
                categories=[category])
        storage.save_txn(txn)
        ledger = Ledger(starting_balance=account.starting_balance)
        ledger_widget = LedgerWidget(ledger, master=self.root, storage=storage, account=account, delete_txn=lambda x: x, reload_function=lambda x: x)
        self.assertEqual(ledger_widget.data[txn.id]['labels']['categories'].cget('text'), '1: 5')
        self.assertEqual(ledger_widget.data[txn.id]['labels']['balance'].cget('text'), '105')
        #edit txn - check amount entry is 5
        ledger_widget.data[txn.id]['buttons'][0].invoke()
        self.assertEqual(ledger_widget.data[txn.id]['entries']['amount'].get(), '5')
        self.assertEqual(ledger_widget.data[txn.id]['entries']['categories'].get(), '1: 5')
        #edit txn - change amount to 25, add payee
        ledger_widget.data[txn.id]['entries']['amount'].insert(0, '2')
        ledger_widget.data[txn.id]['entries']['payee'].insert(0, 'Someone')
        ledger_widget.data[txn.id]['entries']['categories'].delete(0, END)
        ledger_widget.data[txn.id]['entries']['categories'].insert(0, str(category2.id))
        ledger_widget.data[txn.id]['buttons'][0].invoke()
        #make sure db record amount is updated to 25
        txns = storage._db_connection.execute('SELECT amount, payee FROM transactions').fetchall()
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0][0], '25')
        self.assertEqual(txns[0][1], 'Someone')
        txn_categories = storage._db_connection.execute('SELECT category_id, amount FROM txn_categories WHERE txn_id = ?', (txn.id,)).fetchall()
        self.assertEqual(len(txn_categories), 1)
        self.assertEqual(txn_categories[0][0], category2.id)
        self.assertEqual(txn_categories[0][1], '25')

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
        c = Category(name='Housing', id_=1)
        c2 = Category(name='Food', id_=2)
        b = Budget(year=2018, category_rows={
            c: {'budget': D(15), 'income': D(0), 'carryover': D(0), 'spent': D(10)},
            c2: {'budget': D(25), 'income': D(0), 'carryover': D(0), 'spent': D(50)},
        })
        bd = BudgetDisplayWidget(master=self.root, budget=b, save_budget=lambda x: x, reload_budget=lambda x: x)


if __name__ == '__main__':
    unittest.main()

