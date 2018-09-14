'''
Architecture:
    Inner Layer - Account, Category, Transaction, Ledger classes. They know nothing about the storage or UI.
    Next Layer - SQLiteStorage (or another storage class). Knows about inner layer objects, but not the UI.
    Outer Layer - Tkinter widgets (or console UI, ...). Knows about storage layer and inner objects.
    No objects should use private/hidden members of other objects.
'''
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
import sqlite3
try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    raise SystemExit("error importing tkinter - please make sure it's installed")


DATA_FILENAME = 'python_finance_tracking.sqlite3'
TITLE = 'Python Finance Tracking'


class InvalidAccountError(RuntimeError):
    pass

class InvalidTransactionError(RuntimeError):
    pass

class InvalidLedgerError(RuntimeError):
    pass

class BudgetError(RuntimeError):
    pass


class Account:

    def __init__(self, id=None, name=None, starting_balance=None):
        self.id = id
        self.name = name
        self.starting_balance = self._check_starting_balance(starting_balance)

    def __str__(self):
        return self.name

    def _check_starting_balance(self, starting_balance):
        if isinstance(starting_balance, Decimal):
            return starting_balance
        elif isinstance(starting_balance, (int, str)):
            try:
                return Decimal(starting_balance)
            except InvalidOperation:
                raise InvalidAccountError('invalid starting balance %s' % starting_balance)
        else:
            raise InvalidAccountError('invalid type %s for starting_balance' % type(starting_balance))
        return starting_balance


class Category:

    def __init__(self, name, id_=None):
        self.name = name
        self.id = id_

    def __str__(self):
        return '%s: %s' % (self.id, self.name)

    def __repr__(self):
        return str(self)

    def __eq__(self, other_category):
        return self.id == other_category.id

    def __hash__(self):
        return self.id


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
                raise InvalidTransactionError('invalid amount %s' % amount)
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
        sorted_txns = sorted(self._txns, key=lambda t: t.txn_date)
        sorted_records = []
        balance = self._starting_balance
        for t in sorted_txns:
            balance = balance + t.amount
            sorted_records.append({'txn': t, 'balance': balance})
        return sorted_records

    def clear_txns(self):
        self._txns = []


class Budget:

    @staticmethod
    def round_percent_available(percent):
        return percent.quantize(Decimal('1.'), rounding=ROUND_HALF_UP)

    def __init__(self, year=None, category_rows=None, id_=None):
        if not year:
            raise BudgetError('must pass in year to Budget')
        self.year = year
        if not category_rows:
            raise BudgetError('must pass in category info to Budget')
        self._category_rows = category_rows
        self.id = id_

    def __str__(self):
        return '%s %s' % (self.id, self.year)

    @property
    def save_category_rows(self):
        return self._category_rows

    @property
    def display_category_rows(self):
        for cat, info in self._category_rows.items():
            total_budget = info['budget'] + info['carryover'] + info['income']
            info['total_budget'] = total_budget
            remaining = total_budget - info['spent']
            info['remaining'] = remaining
            if total_budget:
                percent_available = (remaining / total_budget) * Decimal(100)
                info['percent_available'] = Budget.round_percent_available(percent_available)
            else:
                info['percent_available'] = Decimal(0)
        return self._category_rows


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
        conn = self._db_connection
        conn.execute('CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT, starting_balance TEXT)')
        conn.execute('CREATE TABLE budgets (id INTEGER PRIMARY KEY, name TEXT, year TEXT)')
        conn.execute('CREATE TABLE budget_values (id INTEGER PRIMARY KEY, budget_id INTEGER, category_id INTEGER, amount TEXT, carryover TEXT)')
        conn.execute('CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT)')
        conn.execute('CREATE TABLE transactions (id INTEGER PRIMARY KEY, account_id INTEGER, txn_type TEXT, txn_date TEXT, payee TEXT, amount TEXT, description TEXT, status TEXT)')
        conn.execute('CREATE TABLE txn_categories (id INTEGER PRIMARY KEY, txn_id INTEGER, category_id INTEGER, amount TEXT)')

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
        if not db_record:
            raise Exception('No category with id: %s' % category_id)
        return Category(name=db_record[1], id_=db_record[0])

    def get_categories(self):
        categories = []
        category_records = self._db_connection.execute('SELECT id FROM categories ORDER BY id').fetchall()
        for cat_record in category_records:
            cat_id = cat_record[0]
            category = self.get_category(cat_id)
            categories.append(category)
        return categories

    def save_category(self, category):
        c = self._db_connection.cursor()
        if category.id:
            c.execute('UPDATE categories SET name = ? WHERE id = ?', (category.name, category.id))
        else:
            c.execute('INSERT INTO categories(name) VALUES(?)', (category.name,))
            category.id = c.lastrowid
        self._db_connection.commit()

    def delete_category(self, category_id):
        self._db_connection.execute('DELETE FROM categories WHERE id = ?', (category_id,))
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

    def save_budget(self, budget):
        c = self._db_connection.cursor()
        if budget.id:
            #delete existing values, and then we'll add the current ones
            c.execute('DELETE FROM budget_values WHERE budget_id = ?', (budget.id,))
        else:
            c.execute('INSERT INTO budgets(year) VALUES(?)', (budget.year,))
            budget.id = c.lastrowid
        for cat, info in budget.save_category_rows.items():
            if not cat.id:
                self.save_category(cat)
            carryover = str(info.get('carryover', ''))
            values = (budget.id, cat.id, str(info['budget']), carryover)
            c.execute('INSERT INTO budget_values(budget_id, category_id, amount, carryover) VALUES (?, ?, ?, ?)', values)
        self._db_connection.commit()

    def get_budget(self, budget_id):
        c = self._db_connection.cursor()
        records = c.execute('SELECT year FROM budgets WHERE id = ?', (budget_id,)).fetchall()
        year = int(records[0][0])
        category_rows = {}
        category_records = self._db_connection.execute('SELECT id FROM categories ORDER BY id').fetchall()
        for cat_record in category_records:
            cat_id = cat_record[0]
            category = self.get_category(cat_id)
            category_rows[category] = {}
            #get spent & income values for each category
            spent = Decimal(0)
            income = Decimal(0)
            txn_category_records = self._db_connection.execute('SELECT amount FROM txn_categories WHERE category_id = ?', (cat_id,)).fetchall()
            for record in txn_category_records:
                amt = Decimal(record[0])
                if amt > Decimal(0):
                    income += amt
                else:
                    spent += amt
            #spent value should be positive, even though it's negative values in the DB
            if spent:
                spent = spent * Decimal(-1)
            category_rows[category]['spent'] = spent
            category_rows[category]['income'] = income
            budget_records = c.execute('SELECT amount, carryover FROM budget_values WHERE budget_id = ? AND category_id = ?', (budget_id, cat_id)).fetchall()
            if budget_records:
                r = budget_records[0]
                category_rows[category]['budget'] = Decimal(r[0])
                if r[1]:
                    category_rows[category]['carryover'] = Decimal(r[1])
                else:
                    category_rows[category]['carryover'] = Decimal(0)
            else:
                category_rows[category]['budget'] = Decimal(0)
                category_rows[category]['carryover'] = Decimal(0)
        return Budget(id_=budget_id, year=year, category_rows=category_rows)

    def get_budgets(self):
        budgets = []
        c = self._db_connection.cursor()
        budget_records = c.execute('SELECT id FROM budgets').fetchall()
        for budget_record in budget_records:
            budget_id = int(budget_records[0][0])
            budgets.append(self.get_budget(budget_id))
        return budgets


### GUI ###

TXN_TYPE_WIDTH = 10
DATE_WIDTH = 12
PAYEE_WIDTH = 25
AMOUNT_WIDTH = 12
DESCRIPTION_WIDTH = 45
STATUS_WIDTH = 7
BALANCE_WIDTH = 12
CATEGORIES_WIDTH = 12
ACTIONS_WIDTH = 16


def txn_categories_from_string(storage, categories_str):
    categories_list = categories_str.split(', ')
    categories = []
    for category_info in categories_list:
        if ':' in category_info:
            cat_id, amount = category_info.split(': ')
            categories.append( (storage.get_category(cat_id), Decimal(amount)) )
        elif category_info:
            cat_id = int(category_info)
            categories.append(storage.get_category(cat_id))
    return categories


def txn_categories_display(txn):
    return ', '.join(['%s: %s' % (c[0].id, c[1]) for c in txn.categories])


class LedgerWidget(ttk.Frame):

    def __init__(self, ledger, master, storage, account, delete_txn, reload_function):
        super().__init__(master=master, padding=(0, 0, 0, 0))
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=3)
        self.grid_columnconfigure(2, weight=3)
        self.grid_columnconfigure(3, weight=3)
        self.grid_columnconfigure(4, weight=3)
        self.grid_columnconfigure(5, weight=3)
        self.grid_columnconfigure(6, weight=3)
        self.grid_columnconfigure(7, weight=3)
        self.grid_columnconfigure(8, weight=1)
        self.grid_columnconfigure(9, weight=1)
        self.ledger = ledger
        self.storage = storage
        self.account = account
        self._reload = reload_function
        self._delete_txn = delete_txn
        self.data = {}
        self.load_ledger()

    def load_ledger(self):
        self.storage.load_txns_into_ledger(self.account.id, self.ledger)
        row = 0
        for record in self.ledger.get_records():
            self._display_txn(record['txn'], record['balance'], row)
            row += 1

    def _display_txn(self, txn, balance, row):

        def _edit(txn_id=txn.id):

            def _edit_save(txn_id=txn_id):
                entries = self.data[txn_id]['entries']
                txn_type = entries['txn_type'].get()
                txn_date = entries['date'].get()
                payee = entries['payee'].get()
                amount = entries['amount'].get()
                description = entries['description'].get()
                status = entries['status'].get()
                categories_str = entries['categories'].get()
                categories = txn_categories_from_string(self.storage, categories_str)
                txn = self.data[txn_id]['txn']
                txn.update_values(
                        txn_type=txn_type,
                        txn_date=txn_date,
                        payee=payee,
                        amount=amount,
                        description=description,
                        status=status,
                        categories=categories,
                    )
                self.storage.save_txn(txn)
                self._reload(self.account)

            for label in self.data[txn_id]['labels'].values():
                label.destroy()
            self.data[txn_id]['labels'] = {}
            for btn in self.data[txn_id]['buttons']:
                btn.destroy()
            self.data[txn_id]['buttons'] = []

            txn_type_entry = ttk.Entry(self, width=TXN_TYPE_WIDTH)
            if txn.txn_type:
                txn_type_entry.insert(0, txn.txn_type)
            date_entry = ttk.Entry(self, width=DATE_WIDTH)
            date_entry.insert(0, str(txn.txn_date))
            payee_entry = ttk.Entry(self, width=PAYEE_WIDTH)
            if txn.payee:
                payee_entry.insert(0, txn.payee)
            amount_entry = ttk.Entry(self, width=AMOUNT_WIDTH)
            amount_entry.insert(0, str(txn.amount))
            description_entry = ttk.Entry(self, width=DESCRIPTION_WIDTH)
            if txn.description:
                description_entry.insert(0, txn.description)
            status_entry = ttk.Entry(self, width=STATUS_WIDTH)
            if txn.status:
                status_entry.insert(0, txn.status)
            categories_entry = ttk.Entry(self)
            categories_entry.insert(0, txn_categories_display(txn))
            edit_save_button = ttk.Button(self, text='Save Edit', command=_edit_save)
            txn_type_entry.grid(row=row, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
            date_entry.grid(row=row, column=1, sticky=(tk.N, tk.S, tk.E, tk.W))
            payee_entry.grid(row=row, column=2, sticky=(tk.N, tk.S, tk.E, tk.W))
            amount_entry.grid(row=row, column=3, sticky=(tk.N, tk.S, tk.E, tk.W))
            description_entry.grid(row=row, column=4, sticky=(tk.N, tk.S, tk.E, tk.W))
            status_entry.grid(row=row, column=5, sticky=(tk.N, tk.S, tk.E, tk.W))
            categories_entry.grid(row=row, column=6, sticky=(tk.N, tk.S, tk.E, tk.W))
            edit_save_button.grid(row=row, column=7, sticky=(tk.N, tk.S, tk.E, tk.W))

            self.data[txn_id]['entries'] = {
                    'txn_type': txn_type_entry,
                    'date': date_entry,
                    'payee': payee_entry,
                    'amount': amount_entry,
                    'description': description_entry,
                    'status': status_entry,
                    'categories': categories_entry,
                }
            self.data[txn_id]['buttons'] = [edit_save_button]

        def _delete(txn_id=txn.id):
            self._delete_txn(txn_id)
            self._reload()

        row_data = {'txn': txn}
        txn_type_label = ttk.Label(self, width=TXN_TYPE_WIDTH, borderwidth=1, relief="solid")
        txn_type_label['text'] = txn.txn_type or ''
        date_label = ttk.Label(self, width=DATE_WIDTH, borderwidth=1, relief="solid")
        date_label['text'] = str(txn.txn_date)
        payee_label = ttk.Label(self, width=PAYEE_WIDTH, borderwidth=1, relief="solid")
        payee_label['text'] = txn.payee or ''
        amount_label = ttk.Label(self, width=AMOUNT_WIDTH, borderwidth=1, relief="solid")
        amount_label['text'] = str(txn.amount)
        description_label = ttk.Label(self, width=DESCRIPTION_WIDTH, borderwidth=1, relief="solid")
        description_label['text'] = txn.description
        status_label = ttk.Label(self, width=STATUS_WIDTH, borderwidth=1, relief="solid")
        status_label['text'] = txn.status
        balance_label = ttk.Label(self, width=BALANCE_WIDTH, text=str(balance), borderwidth=1, relief="solid")
        categories_label = ttk.Label(self, width=CATEGORIES_WIDTH, borderwidth=1, relief='solid')
        categories_label['text'] = txn_categories_display(txn)
        edit_button = ttk.Button(self, text='Edit', width=6)
        edit_button['command'] = _edit
        delete_button = ttk.Button(self, text='Delete', width=8)
        delete_button['command'] = _delete
        txn_type_label.grid(row=row, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        date_label.grid(row=row, column=1, sticky=(tk.N, tk.S, tk.E, tk.W))
        payee_label.grid(row=row, column=2, sticky=(tk.N, tk.S, tk.E, tk.W))
        amount_label.grid(row=row, column=3, sticky=(tk.N, tk.S, tk.E, tk.W))
        description_label.grid(row=row, column=4, sticky=(tk.N, tk.S, tk.E, tk.W))
        status_label.grid(row=row, column=5, sticky=(tk.N, tk.S, tk.E, tk.W))
        balance_label.grid(row=row, column=6, sticky=(tk.N, tk.S, tk.E, tk.W))
        categories_label.grid(row=row, column=7, sticky=(tk.N, tk.S, tk.E, tk.W))
        edit_button.grid(row=row, column=8, sticky=(tk.N, tk.S, tk.E, tk.W))
        delete_button.grid(row=row, column=9, sticky=(tk.N, tk.S, tk.E, tk.W))
        row_data['labels'] = {
                'txn_type': txn_type_label,
                'date': date_label,
                'payee': payee_label,
                'amount': amount_label,
                'description': description_label,
                'status': status_label,
                'balance': balance_label,
                'categories': categories_label
            }
        row_data['buttons'] = [edit_button, delete_button]
        self.data[txn.id] = row_data


class ActionsWidget(ttk.Frame):

    def __init__(self, master, show_accounts, show_ledger, show_categories, show_budget):
        super().__init__(master=master)
        accounts_button = ttk.Button(master=self, text='Accounts', command=show_accounts)
        accounts_button.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S))
        ledger_button = ttk.Button(master=self, text='Ledger', command=show_ledger)
        ledger_button.grid(row=0, column=1, sticky=(tk.N, tk.W, tk.S))
        budget_button = ttk.Button(master=self, text='Categories', command=show_categories)
        budget_button.grid(row=0, column=2, sticky=(tk.N, tk.W, tk.S))
        budget_button = ttk.Button(master=self, text='Budget', command=show_budget)
        budget_button.grid(row=0, column=3, sticky=(tk.N, tk.W, tk.S))


class AccountsDisplayWidget(ttk.Frame):

    def __init__(self, master, accounts, storage, show_accounts):
        super().__init__(master=master)
        self._storage = storage
        self._show_accounts = show_accounts
        ttk.Label(self, text='Name').grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        ttk.Label(self, text='Starting Balance').grid(row=0, column=1, sticky=(tk.N, tk.S, tk.E, tk.W))
        row = 1
        for account in accounts:
            ttk.Label(self, text=account.name).grid(row=row, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
            ttk.Label(self, text=str(account.starting_balance)).grid(row=row, column=1, sticky=(tk.N, tk.S, tk.E, tk.W))
            row += 1
        self.add_account_name_entry = ttk.Entry(self)
        self.add_account_name_entry.grid(row=row, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))
        self.add_account_starting_balance_entry = ttk.Entry(self)
        self.add_account_starting_balance_entry.grid(row=row, column=1, sticky=(tk.N, tk.W, tk.S, tk.E))
        self.add_account_button = ttk.Button(self, text='Add New', command=self._add)
        self.add_account_button.grid(row=row, column=2, sticky=(tk.N, tk.W, tk.S, tk.E))

    def _add(self):
        a = Account(name=self.add_account_name_entry.get(), starting_balance=Decimal(self.add_account_starting_balance_entry.get()))
        self._storage.save_account(a)
        self._show_accounts()


class LedgerDisplayWidget(ttk.Frame):

    def __init__(self, master, accounts, current_account, show_ledger, storage):
        super().__init__(master=master)
        self.show_ledger = show_ledger
        self.accounts = accounts
        self.current_account = current_account
        self.storage = storage
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=3)
        self.grid_columnconfigure(2, weight=3)
        self.grid_columnconfigure(3, weight=3)
        self.grid_columnconfigure(4, weight=3)
        self.grid_columnconfigure(5, weight=3)
        self.grid_columnconfigure(6, weight=3)
        self.grid_columnconfigure(7, weight=3)
        self.grid_columnconfigure(8, weight=1)

        #headings
        self.action_var = tk.StringVar(self) #has to have the "self.", or else the account name doesn't show in the combobox
        self.action_combo = ttk.Combobox(self, textvariable=self.action_var)
        self.action_combo['values'] = [a.name for a in self.accounts]
        self.action_combo.bind('<<ComboboxSelected>>', self._update_account)
        self.action_combo.grid(row=0, column=0, columnspan=3, sticky=(tk.W))
        self.action_combo.set(self.current_account.name)
        headings_row = 1
        ttk.Label(self, text='Txn Type', width=TXN_TYPE_WIDTH).grid(row=headings_row, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        ttk.Label(self, text='Date', width=DATE_WIDTH).grid(row=headings_row, column=1, sticky=(tk.N, tk.S, tk.E, tk.W))
        ttk.Label(self, text='Payee', width=PAYEE_WIDTH).grid(row=headings_row, column=2, sticky=(tk.N, tk.S, tk.E, tk.W))
        ttk.Label(self, text='Amount', width=AMOUNT_WIDTH).grid(row=headings_row, column=3, sticky=(tk.N, tk.S, tk.E, tk.W))
        ttk.Label(self, text='Description', width=DESCRIPTION_WIDTH).grid(row=headings_row, column=4, sticky=(tk.N, tk.S, tk.E, tk.W))
        ttk.Label(self, text='Status', width=STATUS_WIDTH).grid(row=headings_row, column=5, sticky=(tk.N, tk.S, tk.E, tk.W))
        ttk.Label(self, text='Balance', width=BALANCE_WIDTH).grid(row=headings_row, column=6, sticky=(tk.N, tk.S, tk.E, tk.W))
        ttk.Label(self, text='Categories', width=CATEGORIES_WIDTH).grid(row=headings_row, column=7, sticky=(tk.N, tk.S, tk.E, tk.W))
        ttk.Label(self, text='Actions', width=ACTIONS_WIDTH+1).grid(row=headings_row, column=8, sticky=(tk.N, tk.S, tk.E, tk.W))

        #https://stackoverflow.com/questions/1873575/how-could-i-get-a-frame-with-a-scrollbar-in-tkinter
        vertical_scrollbar = ttk.Scrollbar(master=self, orient=tk.VERTICAL)

        canvas = tk.Canvas(master=self, yscrollcommand=vertical_scrollbar.set, highlightthickness=0, borderwidth=0)

        vertical_scrollbar.configure(command=canvas.yview)

        ledger = Ledger(starting_balance=current_account.starting_balance)
        self.ledger_widget = LedgerWidget(ledger, master=canvas, storage=storage, account=current_account, delete_txn=storage.delete_txn, reload_function=show_ledger)

        self.ledger_widget.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W)) #necessary? this is on the canvas...

        #this line has to go after the ledger_widget.grid, for the scrollbar to work
        #   (although it doesn't resize if it there's extra space in the window)
        ledger_window_id = canvas.create_window(0, 0, anchor=tk.NW, window=self.ledger_widget)

        canvas.grid(row=2, column=0, columnspan=9, sticky=(tk.N, tk.W, tk.S, tk.E))
        vertical_scrollbar.grid(row=2, column=9, sticky=(tk.N, tk.S))

        #update_idletasks has to go before configuring the scrollregion
        self.update_idletasks()
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

        txn_type_entry = ttk.Entry(self, width=TXN_TYPE_WIDTH)
        date_entry = ttk.Entry(self, width=DATE_WIDTH)
        payee_entry = ttk.Entry(self, width=PAYEE_WIDTH)
        amount_entry = ttk.Entry(self, width=AMOUNT_WIDTH)
        description_entry = ttk.Entry(self, width=DESCRIPTION_WIDTH)
        status_entry = ttk.Entry(self, width=STATUS_WIDTH)
        categories_entry = ttk.Entry(self, width=CATEGORIES_WIDTH)
        save_button = ttk.Button(self, text='Save', command=self._save_new_txn, width=BALANCE_WIDTH)
        add_txn_row = 3
        txn_type_entry.grid(row=add_txn_row, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        date_entry.grid(row=add_txn_row, column=1, sticky=(tk.N, tk.S, tk.E, tk.W))
        payee_entry.grid(row=add_txn_row, column=2, sticky=(tk.N, tk.S, tk.E, tk.W))
        amount_entry.grid(row=add_txn_row, column=3, sticky=(tk.N, tk.S, tk.E, tk.W))
        description_entry.grid(row=add_txn_row, column=4, sticky=(tk.N, tk.S, tk.E, tk.W))
        status_entry.grid(row=add_txn_row, column=5, sticky=(tk.N, tk.S, tk.E, tk.W))
        categories_entry.grid(row=add_txn_row, column=6, sticky=(tk.N, tk.S, tk.E, tk.W))
        save_button.grid(row=add_txn_row, column=7, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.add_txn_data = {}
        self.add_txn_data['entries'] = {
                'txn_type': txn_type_entry,
                'date': date_entry,
                'payee': payee_entry,
                'amount': amount_entry,
                'description': description_entry,
                'status': status_entry,
                'categories': categories_entry
            }

    def _clear_add_txn_entries(self):
        for entry in self.add_txn_data['entries'].values():
            entry.delete(0, tk.END)

    def _save_new_txn(self):
        txn_type = self.add_txn_data['entries']['txn_type'].get()
        date_val = self.add_txn_data['entries']['date'].get()
        year, month, day = date_val.split('-')
        txn_date = date(int(year), int(month), int(day))
        payee = self.add_txn_data['entries']['payee'].get()
        amount = Decimal(self.add_txn_data['entries']['amount'].get())
        description = self.add_txn_data['entries']['description'].get()
        status = self.add_txn_data['entries']['status'].get()
        categories_str = self.add_txn_data['entries']['categories'].get()
        categories = txn_categories_from_string(self.storage, categories_str)
        txn = Transaction(account=self.current_account, txn_type=txn_type, amount=amount, txn_date=txn_date, payee=payee, description=description, status=status, categories=categories)
        self.storage.save_txn(txn)
        self._clear_add_txn_entries()
        self.show_ledger()

    def _update_account(self, event):
        current_account_index = self.action_combo.current()
        self.show_ledger(current_account=self.accounts[current_account_index])


class CategoriesDisplayWidget(ttk.Frame):

    def __init__(self, master, categories, storage, reload_categories, delete_category):
        super().__init__(master=master)
        self._storage = storage
        self._reload = reload_categories
        self._delete_category = delete_category
        ttk.Label(self, text='ID').grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))
        ttk.Label(self, text='Name').grid(row=0, column=1, sticky=(tk.N, tk.W, tk.S, tk.E))
        row = 1
        data = {}
        for cat in categories:
            row_data = {'row': row}
            ttk.Label(self, text=cat.id).grid(row=row, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))
            name_label = ttk.Label(self, text=cat.name)
            name_label.grid(row=row, column=1, sticky=(tk.N, tk.W, tk.S, tk.E))
            row_data['name_label'] = name_label
            def _edit(cat_id=cat.id):
                def _save(cat_id=cat_id):
                    c = Category(id_=cat_id, name=data[cat_id]['name_entry'].get())
                    self._storage.save_category(c)
                    self._reload()
                data[cat_id]['name_label'].destroy()
                name_entry = ttk.Entry(self)
                name_entry.grid(row=data[cat_id]['row'], column=1, sticky=(tk.N, tk.W, tk.S, tk.E))
                data[cat_id]['name_entry'] = name_entry
                data[cat_id]['edit_button']['text'] = 'Save'
                data[cat_id]['edit_button']['command'] = _save
            def _delete(cat_id=cat.id):
                self._delete_category(cat_id)
                self._reload()
            edit_button = ttk.Button(self, text='Edit', command=_edit)
            edit_button.grid(row=row, column=2, sticky=(tk.N, tk.W, tk.S, tk.E))
            row_data['edit_button'] = edit_button
            ttk.Button(self, text='Delete', command=_delete).grid(row=row, column=3, sticky=(tk.N, tk.W, tk.S, tk.E))
            data[cat.id] = row_data
            row += 1
        self.name_entry = ttk.Entry(self)
        self.name_entry.grid(row=row, column=1, sticky=(tk.N, tk.W, tk.S, tk.E))
        ttk.Button(self, text='Add New', command=self._add).grid(row=row, column=2, sticky=(tk.N, tk.W, tk.S, tk.E))

    def _add(self):
        c = Category(name=self.name_entry.get())
        self._storage.save_category(c)
        self._reload()


class BudgetDisplayWidget(ttk.Frame):

    def __init__(self, master, budget, save_budget, reload_budget):
        super().__init__(master=master)
        self._budget = budget
        self._save_budget = save_budget
        self._reload_budget = reload_budget
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=1)
        self.grid_columnconfigure(3, weight=1)
        self.grid_columnconfigure(4, weight=1)
        self.grid_columnconfigure(5, weight=1)
        self.grid_columnconfigure(6, weight=1)
        self.grid_columnconfigure(7, weight=1)
        ttk.Label(self, text='Category').grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))
        ttk.Label(self, text='Amount').grid(row=0, column=1, sticky=(tk.N, tk.W, tk.S, tk.E))
        ttk.Label(self, text='Income').grid(row=0, column=2, sticky=(tk.N, tk.W, tk.S, tk.E))
        ttk.Label(self, text='Carryover').grid(row=0, column=3, sticky=(tk.N, tk.W, tk.S, tk.E))
        ttk.Label(self, text='Total Budget').grid(row=0, column=4, sticky=(tk.N, tk.W, tk.S, tk.E))
        ttk.Label(self, text='Spent').grid(row=0, column=5, sticky=(tk.N, tk.W, tk.S, tk.E))
        ttk.Label(self, text='Remaining').grid(row=0, column=6, sticky=(tk.N, tk.W, tk.S, tk.E))
        ttk.Label(self, text='Percent Available').grid(row=0, column=7, sticky=(tk.N, tk.W, tk.S, tk.E))
        row_index = 1
        self.data = {}
        for cat, info in budget.display_category_rows.items():
            ttk.Label(self, text=cat.name).grid(row=row_index, column=0)
            budget_label = ttk.Label(self, text=str(info['budget']))
            budget_label.grid(row=row_index, column=1)
            ttk.Label(self, text=str(info['income'])).grid(row=row_index, column=2)
            carryover_label = ttk.Label(self, text=str(info['carryover']))
            carryover_label.grid(row=row_index, column=3)
            ttk.Label(self, text=str(info['total_budget'])).grid(row=row_index, column=4)
            ttk.Label(self, text=str(info['spent'])).grid(row=row_index, column=5)
            ttk.Label(self, text=str(info['remaining'])).grid(row=row_index, column=6)
            percent_available = str(info['percent_available']) + '%'
            ttk.Label(self, text=percent_available).grid(row=row_index, column=7)
            row_data = {'budget_label': budget_label}
            row_data['carryover_label'] = carryover_label
            row_data['row_index'] = row_index
            row_data['category'] = cat
            self.data[cat.id] = row_data
            row_index += 1
        self._edit_button = ttk.Button(self, text='Edit', command=self._edit)
        self._edit_button.grid(row=row_index, column=0)

    def _save(self):
        category_rows = {}
        for cat_id, data in self.data.items():
            cat = data['category']
            category_rows[cat] = {
                    'budget': data['budget_entry'].get(),
                    'carryover': data['carryover_entry'].get()
                }
        b = Budget(id_=self._budget.id, year=self._budget.year, category_rows=category_rows)
        self._save_budget(b)
        self._reload_budget()

    def _edit(self):
        for cat_id, data in self.data.items():
            budget_val = data['budget_label']['text']
            carryover_val = data['carryover_label']['text']
            data['budget_label'].destroy()
            data['carryover_label'].destroy()
            budget_entry = ttk.Entry(self)
            budget_entry.insert(0, budget_val)
            budget_entry.grid(row=data['row_index'], column=1)
            data['budget_entry'] = budget_entry
            carryover_entry = ttk.Entry(self)
            carryover_entry.insert(0, carryover_val)
            carryover_entry.grid(row=data['row_index'], column=3)
            data['carryover_entry'] = carryover_entry
        self._edit_button['text'] = 'Save'
        self._edit_button['command'] = self._save


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
        #this frame will contain everything the user sees
        self.content_frame = None

        self._load_accounts()
        if self.accounts:
            self._show_ledger()
        else:
            self._show_accounts()

        self.root.mainloop()

    def _load_accounts(self):
        self.accounts = self.storage.get_accounts()

    def _load_budgets(self):
        return self.storage.get_budgets()

    def _show_actions(self):
        actions_widget = ActionsWidget(master=self.content_frame, show_accounts=self._show_accounts,
                show_ledger=self._show_ledger, show_categories=self._show_categories, show_budget=self._show_budget)
        actions_widget.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

    def _show_accounts(self):
        if self.content_frame:
            self.content_frame.destroy()
        self.content_frame = ttk.Frame(master=self.root)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(1, weight=1)
        self._show_actions()
        accounts = self.storage.get_accounts()
        adw = AccountsDisplayWidget(master=self.content_frame, accounts=accounts, storage=self.storage, show_accounts=self._show_accounts)
        adw.grid(sticky=(tk.N, tk.W, tk.S, tk.E))
        self.content_frame.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

    def _show_ledger(self, current_account=None):
        if not current_account:
            current_account = self.accounts[0]

        if self.content_frame:
            self.content_frame.destroy()
        self.content_frame = ttk.Frame(master=self.root)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(1, weight=1)
        self._show_actions()
        ldw = LedgerDisplayWidget(master=self.content_frame, accounts=self.accounts, current_account=current_account, show_ledger=self._show_ledger, storage=self.storage)
        ldw.grid(row=1, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))
        self.content_frame.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

    def _show_categories(self):
        if self.content_frame:
            self.content_frame.destroy()
        self.content_frame = ttk.Frame(master=self.root)
        self._show_actions()
        categories = self.storage.get_categories()
        cdw = CategoriesDisplayWidget(master=self.content_frame, categories=categories, storage=self.storage,
                reload_categories=self._show_categories, delete_category=self.storage.delete_category)
        cdw.grid(row=1, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))
        self.content_frame.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

    def _show_budget(self):
        budgets = self._load_budgets()
        if self.content_frame:
            self.content_frame.destroy()
        self.content_frame = ttk.Frame(master=self.root)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(1, weight=1)
        self._show_actions()
        bdw = BudgetDisplayWidget(master=self.content_frame, budget=budgets[0], save_budget=self.storage.save_budget, reload_budget=self._show_budget)
        bdw.grid(row=1, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))
        self.content_frame.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))


if __name__ == '__main__':
    PFT_GUI()

