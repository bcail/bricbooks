'''
Architecture:
    Inner Layer - Account, Category, Transaction, Ledger classes. They know nothing about the storage or UI.
    Next Layer - SQLiteStorage (or another storage class). Knows about inner layer objects, but not the UI.
    Outer Layer - Tkinter widgets (or console UI, ...). Knows about storage layer and inner objects.
    No objects should use private/hidden members of other objects.
'''
from datetime import date
from decimal import Decimal, InvalidOperation
import os
import sqlite3
import tkinter as tk
from tkinter import ttk


DATA_FILENAME = 'python_finance_tracking.sqlite3'
TITLE = 'Python Finance Tracking'


class InvalidAccountError(RuntimeError):
    pass

class InvalidTransactionError(RuntimeError):
    pass

class InvalidLedgerError(RuntimeError):
    pass


class Account:

    def __init__(self, id=None, name=None, starting_balance=None):
        self.id = id
        self.name = name
        self.starting_balance = self._check_starting_balance(starting_balance)

    def _check_starting_balance(self, starting_balance):
        if isinstance(starting_balance, Decimal):
            return starting_balance
        elif isinstance(starting_balance, (int, str)):
            try:
                return Decimal(starting_balance)
            except InvalidOperation:
                raise InvalidAccountError(f'invalid starting balance {starting_balance}')
        else:
            raise InvalidAccountError(f'invalid type {type(starting_balance)} for starting_balance')
        return starting_balance


class Category:

    def __init__(self, name, id_=None):
        self.name = name
        self.id = id_

    def __eq__(self, other_category):
        return self.id == other_category.id


class Transaction:

    CLEARED = 'C'
    RECONCILED = 'R'

    def __init__(self, account=None, amount=None, txn_date=None, txn_type=None, categories=None, payee=None, description=None, status=None, id_=None):
        self.account = self._check_account(account)
        self.amount = self._check_amount(amount)
        self.txn_date = self._check_txn_date(txn_date)
        self.txn_type = txn_type
        self.categories = self._check_categories(categories)
        self.payee = payee
        self.description = description
        self.status = status
        self.id = id_

    def _check_account(self, account):
        if not account:
            raise InvalidTransactionError('transaction must belong to an account')
        return account

    def _check_amount(self, amount):
        if not amount:
            raise InvalidTransactionError('transaction must have an amount')
        if isinstance(amount, Decimal):
            decimal_amount = amount
        elif isinstance(amount, (int, str)):
            try:
                decimal_amount = Decimal(amount)
            except InvalidOperation:
                raise InvalidTransactionError(f'invalid amount {amount}')
        else:
            raise InvalidTransactionError('invalid type for amount')

        #check for fractions of cents
        amt_str = str(decimal_amount)
        if '.' in amt_str:
            _, decimals = amt_str.split('.')
            if len(decimals) > 2:
                raise InvalidTransactionError('no fractions of cents in a transaction')
        return decimal_amount

    def _check_txn_date(self, txn_date):
        if not txn_date:
            raise InvalidTransactionError('transaction must have a txn_date')
        if isinstance(txn_date, date):
            return txn_date
        elif isinstance(txn_date, str):
            try:
                year, month, day = txn_date.split('-')
                return date(int(year), int(month), int(day))
            except ValueError:
                raise InvalidTransactionError('invalid txn_date')
        else:
            raise InvalidTransactionError('invalid type for txn_date')

    def _check_categories(self, input_categories):
        if not input_categories:
            input_categories = []
        _category_total = Decimal('0')
        categories = []
        for c in input_categories:
            if isinstance(c, tuple):
                _category_total += c[1]
                categories.append(c)
            elif isinstance(c, Category):
                _category_total += self.amount
                categories.append( (c, self.amount) )
        if abs(_category_total) > abs(self.amount):
            raise InvalidTransactionError('split categories add up to more than txn amount')
        return categories

    def update_values(self, amount=None, txn_date=None, txn_type=None, categories=None, payee=None, description=None, status=None):
        if amount is not None:
            self.amount = self._check_amount(amount)
        if txn_date is not None:
            self.txn_date = self._check_txn_date(txn_date)
        if txn_type is not None:
            self.txn_type = txn_type
        if categories is not None:
            self.categories = self._check_categories(categories)
        if payee is not None:
            self.payee = payee
        if description is not None:
            self.description = description
        if status is not None:
            self.status = status


class Ledger:

    def __init__(self, starting_balance=None):
        if starting_balance is None:
            raise InvalidLedgerError('ledger must have a starting balance')
        if not isinstance(starting_balance, Decimal):
            raise InvalidLedgerError('starting_balance must be a Decimal')
        self._txns = []
        self._starting_balance = starting_balance

    def add_transaction(self, txn):
        self._txns.append(txn)

    def get_records(self):
        balance = self._starting_balance
        records = []
        for t in self._txns:
            balance = balance + t.amount
            records.append({'balance': balance, 'txn': t})
        sorted_records = sorted(records, key=lambda x: x['txn'].txn_date)
        return sorted_records

    def clear_txns(self):
        self._txns = []


### Storage ###

class SQLiteStorage:

    def __init__(self, conn_name):
        #conn_name is either ':memory:' or the name of the data file
        if conn_name == ':memory:':
            self._db_connection = sqlite3.connect(conn_name)
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(current_dir, conn_name)
            self._db_connection = sqlite3.connect(file_path)
        tables = self._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        if not tables:
            self._setup_db()

    def _setup_db(self):
        '''
        Initialize empty DB.
        '''
        self._db_connection.execute('CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT, starting_balance TEXT)')
        self._db_connection.execute('CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT)')
        self._db_connection.execute('CREATE TABLE transactions (id INTEGER PRIMARY KEY, account_id INTEGER, txn_type TEXT, txn_date TEXT, payee TEXT, amount TEXT, description TEXT, status TEXT)')
        self._db_connection.execute('CREATE TABLE txn_categories (id INTEGER PRIMARY KEY, txn_id INTEGER, category_id INTEGER, amount TEXT)')

    def get_account(self, account_id):
        account_info = self._db_connection.execute('SELECT id, name, starting_balance FROM accounts WHERE id = ?', (account_id,)).fetchone()
        return Account(id=account_info[0], name=account_info[1], starting_balance=Decimal(account_info[2]))

    def save_account(self, account):
        c = self._db_connection.cursor()
        c.execute('INSERT INTO accounts(name, starting_balance) VALUES(?, ?)', (account.name, str(account.starting_balance)))
        account.id = c.lastrowid
        self._db_connection.commit()

    def get_accounts(self):
        db_records = self._db_connection.execute('SELECT id FROM accounts ORDER BY id').fetchall()
        accounts = []
        for r in db_records:
            accounts.append(self.get_account(r[0]))
        return accounts

    def get_category(self, category_id):
        db_record = self._db_connection.execute('SELECT id, name FROM categories WHERE id = ?', (category_id,)).fetchone()
        return Category(name=db_record[1], id_=db_record[0])

    def save_category(self, category):
        c = self._db_connection.cursor()
        if category.id:
            c.execute('UPDATE categories SET name = ? WHERE id = ?', (category.name, category.id))
        else:
            c.execute('INSERT INTO categories(name) VALUES(?)', (category.name,))
            category.id = c.lastrowid
        self._db_connection.commit()

    def _txn_from_db_record(self, db_info=None):
        if not db_info:
            raise InvalidTransactionError('no db_info to construct transaction')
        id_, account_id, txn_type, txn_date, payee, amount, description, status = db_info
        year, month, day = txn_date.split('-')
        txn_date = date(int(year), int(month), int(day))
        amount = Decimal(amount)
        account = self.get_account(account_id)
        c = self._db_connection.cursor()
        categories = []
        category_records = c.execute('SELECT category_id, amount FROM txn_categories WHERE txn_id = ?', (id_,))
        if category_records:
            for cat_record in category_records:
                cat_id = cat_record[0]
                category = self.get_category(cat_id)
                categories.append((category, Decimal(cat_record[1])))
        return Transaction(account=account, amount=amount, txn_date=txn_date, txn_type=txn_type, categories=categories, payee=payee, description=description, status=status, id_=id_)

    def save_txn(self, txn):
        c = self._db_connection.cursor()
        if not txn.account.id:
            self.save_account(txn.account)
        if txn.id:
            c.execute('UPDATE transactions SET account_id = ?, txn_type = ?, txn_date = ?, payee = ?, amount = ?, description = ?, status = ? WHERE id = ?',
                (txn.account.id, txn.txn_type, txn.txn_date.strftime('%Y-%m-%d'), txn.payee, str(txn.amount), txn.description, txn.status, txn.id))
        else:
            c.execute('INSERT INTO transactions(account_id, txn_type, txn_date, payee, amount, description, status) VALUES(?, ?, ?, ?, ?, ?, ?)',
                (txn.account.id, txn.txn_type, txn.txn_date.strftime('%Y-%m-%d'), txn.payee, str(txn.amount), txn.description, txn.status))
            txn.id = c.lastrowid
        #always delete any previous categories
        c.execute('DELETE FROM txn_categories WHERE txn_id = ?', (txn.id,))
        if txn.categories:
            for category in txn.categories:
                c.execute('INSERT INTO txn_categories(txn_id, category_id, amount) VALUES(?, ?, ?)', (txn.id, category[0].id, str(category[1])))
        self._db_connection.commit()

    def delete_txn(self, txn_id):
        self._db_connection.execute('DELETE FROM transactions WHERE id = ?', (txn_id,))
        self._db_connection.commit()

    def load_txns_into_ledger(self, account_id, ledger):
        db_txn_records = self._db_connection.execute('SELECT * FROM transactions WHERE account_id = ?', (account_id,)).fetchall()
        for db_txn in db_txn_records:
            txn = self._txn_from_db_record(db_info=db_txn)
            ledger.add_transaction(txn)


### GUI ###

TXN_TYPE_WIDTH = 10
DATE_WIDTH = 12
PAYEE_WIDTH = 25
AMOUNT_WIDTH = 12
DESCRIPTION_WIDTH = 45
STATUS_WIDTH = 7
BALANCE_WIDTH = 12
CATEGORIES_WIDTH = 12
ACTIONS_WIDTH = 20


def txn_categories_from_string(storage, categories_str):
    categories_list = categories_str.split(', ')
    categories = []
    for category_info in categories_list:
        if ':' in category_info:
            cat_id, amount = category_info.split(': ')
            categories.append( (storage.get_category(cat_id), Decimal(amount)) )
        else:
            cat_id = category_info
            categories.append(storage.get_category(cat_id))
    return categories


def txn_categories_display(txn):
    return ', '.join([f'{c[0].id}: {c[1]}' for c in txn.categories])


class LedgerTxnWidget(ttk.Frame):

    def __init__(self, txn, balance, master=None, storage=None, reload_function=None):
        super().__init__(master=master, padding=(0, 0, 0, 0))
        self.txn = txn
        self.balance = balance
        self.storage = storage
        self.reload_function = reload_function
        self._display_txn()

    def _display_txn(self):
        self.txn_type_label = ttk.Label(self, width=TXN_TYPE_WIDTH, borderwidth=1, relief="solid")
        self.txn_type_label['text'] = self.txn.txn_type or ''
        self.date_label = ttk.Label(self, width=DATE_WIDTH, borderwidth=1, relief="solid")
        self.date_label['text'] = str(self.txn.txn_date)
        self.payee_label = ttk.Label(self, width=PAYEE_WIDTH, borderwidth=1, relief="solid")
        self.payee_label['text'] = self.txn.payee or ''
        self.amount_label = ttk.Label(self, width=AMOUNT_WIDTH, borderwidth=1, relief="solid")
        self.amount_label['text'] = str(self.txn.amount)
        self.description_label = ttk.Label(self, width=DESCRIPTION_WIDTH, borderwidth=1, relief="solid")
        self.description_label['text'] = self.txn.description
        self.status_label = ttk.Label(self, width=STATUS_WIDTH, borderwidth=1, relief="solid")
        self.status_label['text'] = self.txn.status
        self.balance_label = ttk.Label(self, width=BALANCE_WIDTH, text=str(self.balance), borderwidth=1, relief="solid")
        self.categories_label = ttk.Label(self, width=CATEGORIES_WIDTH, borderwidth=1, relief='solid')
        self.categories_label['text'] = txn_categories_display(self.txn)
        self.edit_button = ttk.Button(self, text='Edit', width=8)
        self.edit_button['command'] = self._edit
        self.delete_button = ttk.Button(self, text='Delete', width=9)
        self.delete_button['command'] = self._delete
        self.txn_type_label.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)
        self.date_label.grid(row=0, column=1, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)
        self.payee_label.grid(row=0, column=2, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)
        self.amount_label.grid(row=0, column=3, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)
        self.description_label.grid(row=0, column=4, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)
        self.status_label.grid(row=0, column=5, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)
        self.balance_label.grid(row=0, column=6, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)
        self.categories_label.grid(row=0, column=7, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)
        self.edit_button.grid(row=0, column=8, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)
        self.delete_button.grid(row=0, column=9, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=3)
        self.grid_columnconfigure(2, weight=3)
        self.grid_columnconfigure(3, weight=3)
        self.grid_columnconfigure(4, weight=3)
        self.grid_columnconfigure(5, weight=3)
        self.grid_columnconfigure(6, weight=3)
        self.grid_columnconfigure(7, weight=3)
        self.grid_columnconfigure(8, weight=1)
        self.grid_columnconfigure(9, weight=1)

    def _edit(self):
        #destroy the labels that have the current data & the edit button
        self.txn_type_label.destroy()
        self.date_label.destroy()
        self.payee_label.destroy()
        self.amount_label.destroy()
        self.description_label.destroy()
        self.status_label.destroy()
        self.balance_label.destroy()
        self.edit_button.destroy()
        self.delete_button.destroy()
        #create entries with the current data in them
        self.txn_type_var = tk.StringVar()
        if self.txn.txn_type:
            self.txn_type_var.set(self.txn.txn_type)
        self.txn_type_entry = ttk.Entry(self, width=TXN_TYPE_WIDTH, textvariable=self.txn_type_var)
        self.date_var = tk.StringVar()
        self.date_var.set(str(self.txn.txn_date))
        self.date_entry = ttk.Entry(self, width=DATE_WIDTH, textvariable=self.date_var)
        self.payee_var = tk.StringVar()
        if self.txn.payee:
            self.payee_var.set(self.txn.payee)
        self.payee_entry = ttk.Entry(self, width=PAYEE_WIDTH, textvariable=self.payee_var)
        self.amount_var = tk.StringVar()
        self.amount_var.set(str(self.txn.amount))
        self.amount_entry = ttk.Entry(self, width=AMOUNT_WIDTH, textvariable=self.amount_var)
        self.description_var = tk.StringVar()
        if self.txn.description:
            self.description_var.set(self.txn.description)
        self.description_entry = ttk.Entry(self, width=DESCRIPTION_WIDTH, textvariable=self.description_var)
        self.status_var = tk.StringVar()
        if self.txn.status:
            self.status_var.set(self.txn.status)
        self.status_entry = ttk.Entry(self, width=STATUS_WIDTH, textvariable=self.status_var)
        self.edit_save_button = ttk.Button(self, text='Save Edit', command=self._edit_save)
        self.blank_label = ttk.Label(self, width=ACTIONS_WIDTH, text='')
        self.txn_type_entry.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.date_entry.grid(row=0, column=1, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.payee_entry.grid(row=0, column=2, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.amount_entry.grid(row=0, column=3, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.description_entry.grid(row=0, column=4, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.status_entry.grid(row=0, column=5, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.edit_save_button.grid(row=0, column=6, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.blank_label.grid(row=0, column=7, sticky=(tk.N, tk.S, tk.E, tk.W))

    def _destroy_entries(self):
        self.txn_type_entry.destroy()
        self.date_entry.destroy()
        self.payee_entry.destroy()
        self.amount_entry.destroy()
        self.description_entry.destroy()
        self.status_entry.destroy()
        self.edit_save_button.destroy()
        self.blank_label.destroy()

    def _edit_save(self):
        txn_type = self.txn_type_var.get()
        txn_date = self.date_var.get()
        payee = self.payee_var.get()
        amount = self.amount_var.get()
        description = self.description_var.get()
        status = self.status_var.get()
        self.txn.update_values(
                txn_type=txn_type,
                txn_date=txn_date,
                amount=amount,
                description=description,
                status=status,
            )
        self.storage.save_txn(self.txn)
        self._destroy_entries()
        self._display_txn()

    def _delete(self):
        self.storage.delete_txn(self.txn.id)
        self.reload_function()


class LedgerWidget(ttk.Frame):

    def __init__(self, ledger, master, storage, account_id):
        super().__init__(master=master, padding=(0, 0, 0, 0))
        self.grid_columnconfigure(0, weight=1)
        self.ledger = ledger
        self.storage = storage
        self.account_id = account_id
        self.txn_widgets = []
        self.load_ledger()

    def _clear(self):
        for txn_widget in self.txn_widgets:
            txn_widget.destroy()
        self.ledger.clear_txns()

    def load_ledger(self):
        self._clear()
        self.txn_widgets = []
        self.storage.load_txns_into_ledger(self.account_id, self.ledger)
        row = 0
        for record in self.ledger.get_records():
            txn_widget = LedgerTxnWidget(record['txn'], record['balance'], master=self, storage=self.storage, reload_function=self.load_ledger)
            txn_widget.grid(row=row, column=0, sticky=(tk.W, tk.E))
            self.txn_widgets.append(txn_widget)
            row += 1


class AddTransactionWidget(ttk.Frame):

    def __init__(self, master, account, storage, reload_ledger):
        super().__init__(master=master, padding=(0, 0, 0, 0))
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=3)
        self.grid_columnconfigure(2, weight=3)
        self.grid_columnconfigure(3, weight=3)
        self.grid_columnconfigure(4, weight=3)
        self.grid_columnconfigure(5, weight=3)
        self.grid_columnconfigure(6, weight=1)
        self.grid_columnconfigure(7, weight=1)
        self.account = account
        self.storage = storage
        self.reload_ledger = reload_ledger
        self.txn_type_entry = ttk.Entry(self, width=TXN_TYPE_WIDTH)
        self.date_entry = ttk.Entry(self, width=DATE_WIDTH)
        self.payee_entry = ttk.Entry(self, width=PAYEE_WIDTH)
        self.amount_entry = ttk.Entry(self, width=AMOUNT_WIDTH)
        self.description_entry = ttk.Entry(self, width=DESCRIPTION_WIDTH)
        self.status_entry = ttk.Entry(self, width=STATUS_WIDTH)
        self.save_button = ttk.Button(self, text='Save', command=self._save, width=BALANCE_WIDTH)
        self.spacer_label = ttk.Label(self, text='', width=ACTIONS_WIDTH)
        self.txn_type_entry.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)
        self.date_entry.grid(row=0, column=1, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)
        self.payee_entry.grid(row=0, column=2, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)
        self.amount_entry.grid(row=0, column=3, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)
        self.description_entry.grid(row=0, column=4, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)
        self.status_entry.grid(row=0, column=5, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)
        self.save_button.grid(row=0, column=6, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)
        self.spacer_label.grid(row=0, column=7, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5)

    def _clear_entries(self):
        self.txn_type_entry.delete(0, 'end')
        self.date_entry.delete(0, 'end')
        self.payee_entry.delete(0, 'end')
        self.amount_entry.delete(0, 'end')
        self.description_entry.delete(0, 'end')
        self.status_entry.delete(0, 'end')

    def _save(self):
        txn_type = self.txn_type_entry.get()
        date_val = self.date_entry.get()
        year, month, day = date_val.split('-')
        txn_date = date(int(year), int(month), int(day))
        payee = self.payee_entry.get()
        amount = Decimal(self.amount_entry.get())
        description = self.description_entry.get()
        status = self.status_entry.get()
        txn = Transaction(account=self.account, txn_type=txn_type, amount=amount, txn_date=txn_date, payee=payee, description=description, status=status)
        self.storage.save_txn(txn)
        self._clear_entries()
        self.reload_ledger()


class HeadingsWidget(ttk.Frame):

    def __init__(self, master):
        super().__init__(master=master, padding=(0, 0, 0, 0))
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=3)
        self.grid_columnconfigure(2, weight=3)
        self.grid_columnconfigure(3, weight=3)
        self.grid_columnconfigure(4, weight=3)
        self.grid_columnconfigure(5, weight=3)
        self.grid_columnconfigure(6, weight=3)
        self.grid_columnconfigure(7, weight=3)
        self.grid_columnconfigure(8, weight=1)
        self._create_headings()

    def _create_headings(self):
        txn_type_heading = ttk.Label(self, text='Txn Type', width=TXN_TYPE_WIDTH)
        date_heading = ttk.Label(self, text='Date', width=DATE_WIDTH)
        payee_heading = ttk.Label(self, text='Payee', width=PAYEE_WIDTH)
        amount_heading = ttk.Label(self, text='Amount', width=AMOUNT_WIDTH)
        description_heading = ttk.Label(self, text='Description', width=DESCRIPTION_WIDTH)
        status_heading = ttk.Label(self, text='Status', width=STATUS_WIDTH)
        balance_heading = ttk.Label(self, text='Balance', width=BALANCE_WIDTH)
        categories_heading = ttk.Label(self, text='Categories', width=CATEGORIES_WIDTH)
        actions_heading = ttk.Label(self, text='Actions', width=ACTIONS_WIDTH+1)
        txn_type_heading.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        date_heading.grid(row=0, column=1, sticky=(tk.N, tk.S, tk.E, tk.W))
        payee_heading.grid(row=0, column=2, sticky=(tk.N, tk.S, tk.E, tk.W))
        amount_heading.grid(row=0, column=3, sticky=(tk.N, tk.S, tk.E, tk.W))
        description_heading.grid(row=0, column=4, sticky=(tk.N, tk.S, tk.E, tk.W))
        status_heading.grid(row=0, column=5, sticky=(tk.N, tk.S, tk.E, tk.W))
        balance_heading.grid(row=0, column=6, sticky=(tk.N, tk.S, tk.E, tk.W))
        categories_heading.grid(row=0, column=7, sticky=(tk.N, tk.S, tk.E, tk.W))
        actions_heading.grid(row=0, column=8, sticky=(tk.N, tk.S, tk.E, tk.W))


class AddAccountWidget(ttk.Frame):

    def __init__(self, master, storage, load_accounts, display_ledger):
        super().__init__(master=master, padding=(0, 0, 0, 0))
        self._storage = storage
        self._load_accounts = load_accounts
        self._display_ledger = display_ledger
        heading = ttk.Label(self, text='Add New Account')
        name_label = ttk.Label(self, text='Name')
        self.name_entry = ttk.Entry(self)
        starting_balance_label = ttk.Label(self, text='Starting Balance')
        self.starting_balance_entry = ttk.Entry(self)
        self.save_button = ttk.Button(self, text='Save New Account', command=self._add)
        heading.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        name_label.grid(row=1, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.name_entry.grid(row=1, column=1, sticky=(tk.N, tk.S, tk.E, tk.W))
        starting_balance_label.grid(row=1, column=2, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.starting_balance_entry.grid(row=1, column=3, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.save_button.grid(row=1, column=4, sticky=(tk.N, tk.S, tk.E, tk.W))

    def _add(self):
        a = Account(name=self.name_entry.get(), starting_balance=Decimal(self.starting_balance_entry.get()))
        self._storage.save_account(a)
        self.destroy()
        self._load_accounts()
        self._display_ledger()


class PFT_GUI:

    def __init__(self, root=None):
        self.storage = SQLiteStorage(DATA_FILENAME)

        #root Tk application
        if root:
            self.root = root
        else:
            self.root = tk.Tk()
        self.root.title(TITLE)
        #make sure root container is set to resize properly
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self._load_accounts()
        if self.accounts:
            self._show_ledger()
        else:
            self._show_add_account()

        self.root.mainloop()

    def _load_accounts(self):
        self.accounts = self.storage.get_accounts()

    def _show_add_account(self):
        add_account_frame = AddAccountWidget(master=self.root, storage=self.storage, load_accounts=self._load_accounts, display_ledger=self._show_ledger)
        add_account_frame.grid(sticky=(tk.N, tk.W, tk.S, tk.E))

    def _show_ledger(self):
        #this frame contains everything the user sees
        content_frame = ttk.Frame(master=self.root)
        #two rows in content_frame: headings in row 0, ledger & scrolls in row 1
        #two columns in the content_frame: ledger in column 0, and scrollbar in column 1
        #set row 0 and column 0 to resize - don't want the vertical scrollbar to resize horizontally
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_rowconfigure(1, weight=1)

        #https://stackoverflow.com/questions/1873575/how-could-i-get-a-frame-with-a-scrollbar-in-tkinter
        headings = HeadingsWidget(master=content_frame)
        vertical_scrollbar = ttk.Scrollbar(master=content_frame, orient=tk.VERTICAL)

        canvas = tk.Canvas(master=content_frame, yscrollcommand=vertical_scrollbar.set, highlightthickness=0, borderwidth=0)

        vertical_scrollbar.configure(command=canvas.yview)

        ledger = Ledger(starting_balance=self.accounts[0].starting_balance)
        self.ledger_widget = LedgerWidget(ledger, master=canvas, storage=self.storage, account_id=self.accounts[0].id)

        self.ledger_widget.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))

        #this line has to go after the ledger_widget.grid, for the scrollbar to work
        #   (although it doesn't resize if it there's extra space in the window)
        ledger_window_id = canvas.create_window(0, 0, anchor=tk.NW, window=self.ledger_widget)

        headings.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))
        vertical_scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S))
        canvas.grid(row=1, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

        #update_idletasks has to go before configuring the scrollregion
        self.root.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

        #https://stackoverflow.com/questions/16188420/python-tkinter-scrollbar-for-frame
        def _configure_canvas(event):
            if self.ledger_widget.winfo_reqwidth() != canvas.winfo_width():
                # update the inner frame's width to fill the canvas
                canvas.itemconfigure(ledger_window_id, width=canvas.winfo_width())
        canvas.bind('<Configure>', _configure_canvas)

        def _configure_ledger_widget(event):
            size = (self.ledger_widget.winfo_reqwidth(), self.ledger_widget.winfo_reqheight())
            canvas.config(scrollregion="0 0 %s %s" % size)
        self.ledger_widget.bind('<Configure>', _configure_ledger_widget)

        content_frame.grid(sticky=(tk.N, tk.W, tk.S, tk.E))

        add_txn_widget = AddTransactionWidget(master=self.root, account=self.accounts[0], storage=self.storage, reload_ledger=self.ledger_widget.load_ledger)
        add_txn_widget.grid(row=2, column=0, columnspan=2, sticky=(tk.N, tk.W, tk.S, tk.E))


if __name__ == '__main__':
    PFT_GUI()

