from datetime import date
from decimal import Decimal as D
import os
import sqlite3
import tempfile
from tkinter.test.support import AbstractTkTest
import unittest

from pft import (
        Account,
        InvalidAccountError,
        Transaction,
        InvalidTransactionError,
        Ledger,
        InvalidLedgerError,
        Category,
        SQLiteStorage,
        txn_categories_from_string,
        txn_categories_display,
        AddAccountWidget,
        LedgerTxnWidget,
        AddTransactionWidget,
        PFT_GUI,
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
        t = Transaction(
                account=a,
                amount=D(101),
                txn_date=date.today(),
                categories=[c],
            )
        self.assertEqual(t.categories[0][0], c)

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
        ledger = Ledger(starting_balance=D('765.12'))
        ledger.add_transaction(Transaction(account=a, amount=D('32.45'), txn_date=date(2017, 4, 5)))
        ledger.add_transaction(Transaction(account=a, amount=D('-12'), txn_date=date(2017, 6, 5)))
        ledger_records = ledger.get_records()
        self.assertEqual(ledger_records[0]['txn'].amount, D('32.45'))
        self.assertEqual(ledger_records[0]['balance'], D('797.57'))
        self.assertEqual(ledger_records[1]['txn'].amount, D('-12'))
        self.assertEqual(ledger_records[1]['balance'], D('785.57'))

    def test_sorted_ledger_records(self):
        a = Account(name='Checking', starting_balance=D('100'))
        ledger = Ledger(starting_balance=D('100.12'))
        ledger.add_transaction(Transaction(account=a, amount=D('32.45'), txn_date=date(2017, 8, 5)))
        ledger.add_transaction(Transaction(account=a, amount=D('-12'), txn_date=date(2017, 6, 5)))
        ledger.add_transaction(Transaction(account=a, amount=D('1'), txn_date=date(2017, 7, 30)))
        ledger.add_transaction(Transaction(account=a, amount=D('10'), txn_date=date(2017, 4, 25)))
        ledger_records = ledger.get_records()
        self.assertEqual(ledger_records[0]['txn'].txn_date, date(2017, 4, 25))
        self.assertEqual(ledger_records[1]['txn'].txn_date, date(2017, 6, 5))
        self.assertEqual(ledger_records[2]['txn'].txn_date, date(2017, 7, 30))
        self.assertEqual(ledger_records[3]['txn'].txn_date, date(2017, 8, 5))

    def test_clear_txns(self):
        a = Account(name='Checking', starting_balance=D('100'))
        ledger = Ledger(starting_balance=D('100.12'))
        ledger.add_transaction(Transaction(account=a, amount=D('12.34'), txn_date=date(2017, 8, 5)))
        ledger.clear_txns()
        self.assertEqual(ledger.get_records(), [])


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
        self.assertEqual(tables, [('accounts',), ('categories',), ('transactions',), ('txn_categories',)])

    def test_init_no_file(self):
        storage = SQLiteStorage(self.file_name)
        tables = storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, [('accounts',), ('categories',), ('transactions',), ('txn_categories',)])

    def test_init_empty_file(self):
        with open(self.file_name, 'wb') as f:
            pass
        storage = SQLiteStorage(self.file_name)
        tables = storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, [('accounts',), ('categories',), ('transactions',), ('txn_categories',)])

    def test_init_db_already_setup(self):
        #set up file
        init_storage = SQLiteStorage(self.file_name)
        tables = init_storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, [('accounts',), ('categories',), ('transactions',), ('txn_categories',)])
        #and now open it again and make sure everything's fine
        storage = SQLiteStorage(self.file_name)
        tables = init_storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, [('accounts',), ('categories',), ('transactions',), ('txn_categories',)])

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


class TestGUI(AbstractTkTest, unittest.TestCase):

    def test_add_account(self):
        storage = SQLiteStorage(':memory:')
        def load_accounts(): pass
        def display_ledger(): pass
        aa = AddAccountWidget(master=self.root, storage=storage, load_accounts=load_accounts, display_ledger=display_ledger)
        aa.name_entry.insert(0, 'Checking')
        aa.starting_balance_entry.insert(0, '100')
        aa.save_button.invoke()
        #make sure there's an account now
        accounts = storage._db_connection.execute('SELECT name FROM accounts').fetchall()
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0][0], 'Checking')

    def test_ledger_txn_widget(self):
        a = Account(name='Checking', starting_balance=D('100'))
        txn = Transaction(account=a, amount=D('5'), txn_date=date.today())
        ltw = LedgerTxnWidget(txn, D(105), master=self.root)
        self.assertEqual(ltw.balance_label.cget('text'), '105')

    def test_add_transaction(self):
        storage = SQLiteStorage(':memory:')
        account = Account(name='Checking', starting_balance=D(0))
        def reload_ledger(): pass
        atw = AddTransactionWidget(master=self.root, account=account, storage=storage, reload_ledger=reload_ledger)
        atw.date_entry.insert(0, '2018-01-13')
        atw.amount_entry.insert(0, '100')
        atw.save_button.invoke()
        #make sure there's a transaction now
        txns = storage._db_connection.execute('SELECT amount FROM transactions').fetchall()
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0][0], '100')

    def test_categories_display(self):
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
        self.assertEqual(txn_categories_display(t), f'{c.id}: -45, {c2.id}: -59, {c3.id}: 3')

    def test_categories_from_string(self):
        #takes string from user, parses it, and loads the category objects for passing to Transaction object
        storage = SQLiteStorage(':memory:')
        c = Category('Cat')
        c2 = Category('Dog')
        c3 = Category('Horse')
        storage.save_category(c)
        storage.save_category(c2)
        storage.save_category(c3)
        categories_string = f'{c.id}: -45, {c2.id}: -59, {c3.id}: 3'
        categories = txn_categories_from_string(storage, categories_string)
        self.assertEqual(categories, [(c, D('-45')), (c2, D('-59')), (c3, D('3'))])
        categories_string = f'{c.id}'
        categories = txn_categories_from_string(storage, categories_string)
        self.assertEqual(categories, [c])
        categories_string = ''
        categories = txn_categories_from_string(storage, categories_string)
        self.assertEqual(categories, [])


if __name__ == '__main__':
    unittest.main()

