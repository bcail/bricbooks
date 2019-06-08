'''
Architecture:
    Inner Layer - Account, Category, Transaction, Ledger classes. They know nothing about the storage or UI.
    Next Layer - SQLiteStorage (or another storage class). Knows about inner layer objects, but not the UI.
    Outer Layer - Tkinter widgets (or console UI, ...). Knows about storage layer and inner objects.
    No objects should use private/hidden members of other objects.
'''
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from functools import partial
import os
import sqlite3
import subprocess
import sys


TITLE = 'Python Finance Tracking'
PYSIDE2_VERSION = '5.12.2'

class AccountType(Enum):
    ASSET = 0
    LIABILITY = 1
    EQUITY = 2
    INCOME = 3
    EXPENSE = 4


def _do_qt_install():
    print('installing Qt for Python (PySide2)')
    cmd = [sys.executable, '-m', 'pip', 'install', 'PySide2==%s' % PYSIDE2_VERSION]
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(result.stdout.decode('utf8'))
    except subprocess.CalledProcessError as e:
        print('Error installing Qt for Python')
        if e.stdout:
            print(e.stdout.decode('utf8'))
        if e.stderr:
            print(e.stderr.decode('utf8'))
        sys.exit(1)


def install_qt_for_python():
    install = input("couldn't import Qt for Python module - OK to download & install it (Y/n)?")
    if install.lower() != 'n':
        _do_qt_install()
        print('Please restart %s now.' % TITLE)
        sys.exit(0)


try:
    from PySide2 import QtWidgets
except ImportError:
    pass


class InvalidAccountError(RuntimeError):
    pass

class InvalidAccountNameError(InvalidAccountError):
    pass

class InvalidAccountStartingBalanceError(InvalidAccountError):
    pass

class InvalidTransactionError(RuntimeError):
    pass

class InvalidLedgerError(RuntimeError):
    pass

class BudgetError(RuntimeError):
    pass

class SQLiteStorageError(RuntimeError):
    pass


def get_date(val):
    if isinstance(val, str):
        year, month, day = val.split('-')
        return date(int(year), int(month), int(day))
    if isinstance(val, date):
        return val
    raise RuntimeError('invalid date')


class Account:

    def __init__(self, id_=None, type_=None, name=None, starting_balance=None):
        self.id = id_
        if not type_:
            raise InvalidAccountError('Account must have a type')
        if not name:
            raise InvalidAccountNameError('Account must have a name')
        self.type = self._check_type(type_)
        self.name = name
        self.starting_balance = self._check_starting_balance(starting_balance)

    def __str__(self):
        return self.name

    def __eq__(self, other_account):
        if self.id:
            return self.id == other_account.id
        else:
            return self.name == other_account.name

    def _check_type(self, type_):
        if not isinstance(type_, AccountType):
            raise InvalidAccountError('Invalid account type "%s"' % type_)
        return type_

    def _check_starting_balance(self, starting_balance):
        if isinstance(starting_balance, Decimal):
            return starting_balance
        elif isinstance(starting_balance, (int, str)):
            try:
                return Decimal(starting_balance)
            except InvalidOperation:
                raise InvalidAccountStartingBalanceError('Invalid starting balance %s' % starting_balance)
        else:
            raise InvalidAccountStartingBalanceError('Invalid type %s for starting_balance' % type(starting_balance))
        return starting_balance


class Category:

    def __init__(self, name, is_expense=True, id_=None, parent=None, user_id=None):
        self.name = name
        self.id = id_
        self.is_expense = is_expense
        self.parent = parent
        self.user_id = user_id

    def __str__(self):
        if self.user_id:
            return '%s - %s' % (self.user_id, self.name)
        else:
            return self.name

    def __repr__(self):
        return str(self)

    def __eq__(self, other_category):
        if not other_category:
            return False
        if self.id or other_category.id:
            return self.id == other_category.id
        if self.name == other_category.name:
            if self.parent == other_category.parent:
                return True
        return False

    def __hash__(self):
        return self.id


class Transaction:

    CLEARED = 'C'
    RECONCILED = 'R'

    @staticmethod
    def from_user_strings(account, credit, debit, txn_date, txn_type, categories, payee, description, status):
        if credit:
            amount = credit
        elif debit:
            amount = '-%s' % debit
        return Transaction(
                account=account,
                amount=amount,
                txn_date=txn_date,
                categories=categories,
                payee=payee,
                description=description,
                status=status
            )

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

    def __str__(self):
        return '%s: %s' % (self.id, self.amount)

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
        try:
            return get_date(txn_date)
        except Exception:
            raise InvalidTransactionError('invalid txn_date')

    def _check_categories(self, input_categories):
        if not input_categories:
            input_categories = []
        _category_total = Decimal('0')
        categories = []
        if isinstance(input_categories, Category):
            input_categories = [input_categories]
        for c in input_categories:
            if isinstance(c, tuple) or isinstance(c, list):
                category_amt = Decimal(c[1])
                _category_total += category_amt
                categories.append( (c[0], category_amt) )
            elif isinstance(c, Category):
                _category_total += self.amount
                categories.append( (c, self.amount) )
            else:
                raise InvalidTransactionError('unhandled txn_categories')
        if abs(_category_total) > abs(self.amount):
            raise InvalidTransactionError('split categories add up to more than txn amount')
        return categories

    def _categories_display(self):
        if len(self.categories) == 1:
            return str(self.categories[0][0])
        elif not self.categories:
            return ''
        return 'multiple'

    def get_display_strings(self):
        if self.amount < Decimal(0):
            debit = str(self.amount * Decimal('-1'))
            credit = ''
        else:
            debit = ''
            credit = str(self.amount)
        return {
                'txn_type': self.txn_type or '',
                'debit': debit,
                'credit': credit,
                'description': self.description or '',
                'txn_date': str(self.txn_date),
                'payee': self.payee or '',
                'status': self.status or '',
                'categories': self._categories_display(),
            }

    def update_from_user_strings(self, debit=None, credit=None, txn_date=None, txn_type=None, categories=None, payee=None, description=None, status=None):
        if debit:
            self.amount = self._check_amount('-%s' % debit)
        elif credit:
            self.amount = self._check_amount(credit)
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
        self._txns = {}
        self._starting_balance = starting_balance

    def add_transaction(self, txn):
        if not txn.id:
            raise Exception('txn must have an id')
        self._txns[txn.id] = txn

    def get_sorted_txns_with_balance(self):
        sorted_txns = sorted(self._txns.values(), key=lambda t: t.txn_date)
        balance = self._starting_balance
        sorted_records = []
        for t in sorted_txns:
            balance = balance + t.amount
            t.balance = balance
            sorted_records.append(t)
        return sorted_records

    def get_txn(self, id_):
        return self._txns[id_]

    def remove_txn(self, id_):
        del self._txns[id_]

    def clear_txns(self):
        self._txns = {}

    def get_payees(self):
        payees = set()
        for txn in self._txns.values():
            if txn.payee:
                payees.add(txn.payee)
        return sorted(list(payees))


class Budget:
    '''Budget information that's entered by the user - no defaults or calculated values, but
    empty strings are dropped (so we can pass empty string from user form), and strings are converted
    Decimal values. Note: all categories are passed in - if there's no budget info, it just has an empty {}.
    '''

    @staticmethod
    def round_percent_available(percent):
        return percent.quantize(Decimal('1.'), rounding=ROUND_HALF_UP)

    def __init__(self, year=None, start_date=None, end_date=None, category_budget_info=None, id_=None, income_spending_info=None):
        if start_date and end_date:
            self.start_date = get_date(start_date)
            self.end_date = get_date(end_date)
        elif year:
            self.start_date = date(int(year), 1, 1)
            self.end_date = date(int(year), 12, 31)
        else:
            raise BudgetError('must pass in dates')
        self._budget_data = {}
        for category, info in category_budget_info.items():
            keep_info = {}
            for key, value in info.items():
                if value == '':
                    pass
                elif key == 'notes':
                    keep_info[key] = value
                elif isinstance(value, str):
                    keep_info[key] = Decimal(value)
                else:
                    keep_info[key] = value
            self._budget_data[category] = keep_info
        self.id = id_
        self._income_spending_info = income_spending_info

    def __str__(self):
        return '%s %s-%s' % (self.id, self.start_date, self.end_date)

    def get_budget_data(self):
        return self._budget_data

    def get_report_display(self, income_spending_info=None):
        if self._income_spending_info is None:
            raise BudgetError('must pass in income_spending_info to get the report display')
        report = {'expense': {}, 'income': {}}
        for category, budget_info in self._budget_data.items():
            report_info = {}
            report_info.update(budget_info)
            report_info.update(self._income_spending_info.get(category, {}))
            if 'amount' in report_info:
                carryover = report_info.get('carryover', Decimal(0))
                income = report_info.get('income', Decimal(0))
                if category.is_expense:
                    report_info['total_budget'] = report_info['amount'] + carryover + income
                    spent = report_info.get('spent', Decimal(0))
                    report_info['remaining'] = report_info['total_budget'] - spent
                    try:
                        percent_available = (report_info['remaining'] / report_info['total_budget']) * Decimal(100)
                        report_info['percent_available'] = '{}%'.format(Budget.round_percent_available(percent_available))
                    except InvalidOperation:
                        report_info['percent_available'] = ''
                else:
                    report_info['remaining'] = report_info['amount'] - income
                    percent = (income / report_info['amount']) * Decimal(100)
                    report_info['percent'] = '{}%'.format(Budget.round_percent_available(percent))
            else:
                report_info['amount'] = ''
                report_info['total_budget'] = ''
                report_info['remaining'] = ''
                if category.is_expense:
                    report_info['percent_available'] = ''
                else:
                    report_info['percent'] = ''
            if category.is_expense:
                if 'carryover' not in report_info:
                    report_info['carryover'] = ''
                if 'spent' not in report_info:
                    report_info['spent'] = ''
            if 'income' not in report_info:
                report_info['income'] = ''
            if category.is_expense:
                report['expense'][category] = report_info
            else:
                report['income'][category] = report_info
            for key in report_info.keys():
                if report_info[key] == Decimal(0):
                    report_info[key] = ''
                else:
                    report_info[key] = str(report_info[key])
        return report


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
        conn.execute('CREATE TABLE accounts (id INTEGER PRIMARY KEY, type INTEGER, name TEXT, starting_balance TEXT)')
        conn.execute('CREATE TABLE budgets (id INTEGER PRIMARY KEY, name TEXT, start_date TEXT, end_date TEXT)')
        conn.execute('CREATE TABLE budget_values (id INTEGER PRIMARY KEY, budget_id INTEGER, category_id INTEGER, amount TEXT, carryover TEXT, notes TEXT)')
        conn.execute('CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT, is_expense INTEGER, parent_id INTEGER, user_id TEXT)')
        conn.execute('CREATE TABLE transactions (id INTEGER PRIMARY KEY, account_id INTEGER, txn_type TEXT, txn_date TEXT, payee TEXT, amount TEXT, description TEXT, status TEXT)')
        conn.execute('CREATE TABLE txn_categories (id INTEGER PRIMARY KEY, txn_id INTEGER, category_id INTEGER, amount TEXT)')

    def get_account(self, account_id):
        account_info = self._db_connection.execute('SELECT id, type, name, starting_balance FROM accounts WHERE id = ?', (account_id,)).fetchone()
        return Account(
                id_=account_info[0],
                type_=AccountType(account_info[1]),
                name=account_info[2],
                starting_balance=Decimal(account_info[3])
            )

    def save_account(self, account):
        c = self._db_connection.cursor()
        if account.id:
            c.execute('UPDATE accounts SET type = ?, name = ?, starting_balance = ?  WHERE id = ?',
                    (account.type.value, account.name, str(account.starting_balance), account.id))
        else:
            c.execute('INSERT INTO accounts(type, name, starting_balance) VALUES(?, ?, ?)', (account.type.value, account.name, str(account.starting_balance)))
            account.id = c.lastrowid
        self._db_connection.commit()

    def get_accounts(self):
        db_records = self._db_connection.execute('SELECT id FROM accounts ORDER BY id').fetchall()
        accounts = []
        for r in db_records:
            accounts.append(self.get_account(r[0]))
        return accounts

    def get_category(self, category_id):
        db_record = self._db_connection.execute('SELECT id, name, is_expense, parent_id, user_id FROM categories WHERE id = ?', (category_id,)).fetchone()
        if not db_record:
            raise Exception('No category with id: %s' % category_id)
        if db_record[3]:
            parent = self.get_category(db_record[3])
        else:
            parent = None
        return Category(name=db_record[1], is_expense=bool(db_record[2]), id_=db_record[0], parent=parent, user_id=db_record[4])

    def get_categories(self):
        categories = []
        category_records = self._db_connection.execute('SELECT id FROM categories ORDER BY user_id, id').fetchall()
        for cat_record in category_records:
            cat_id = cat_record[0]
            category = self.get_category(cat_id)
            categories.append(category)
        return categories

    def get_parent_categories(self):
        categories = []
        category_records = self._db_connection.execute('SELECT id FROM categories WHERE parent_id IS NULL ORDER BY user_id, id').fetchall()
        for cat_record in category_records:
            cat_id = cat_record[0]
            category = self.get_category(cat_id)
            categories.append(category)
        return categories

    def get_child_categories(self, parent):
        categories = []
        category_records = self._db_connection.execute('SELECT id FROM categories WHERE parent_id = ? ORDER BY user_id, id', (parent.id,)).fetchall()
        for cat_record in category_records:
            cat_id = cat_record[0]
            category = self.get_category(cat_id)
            categories.append(category)
        return categories

    def save_category(self, category):
        c = self._db_connection.cursor()
        if category.is_expense:
            expense_val = 1
        else:
            expense_val = 0
        if category.parent:
            parent_val = category.parent.id
        else:
            parent_val = None
        if category.id:
            c.execute('UPDATE categories SET name = ?, is_expense = ?, parent_id = ?, user_id = ? WHERE id = ?',
                    (category.name, category.is_expense, parent_val, category.user_id, category.id))
        else:
            c.execute('INSERT INTO categories(name, is_expense, parent_id, user_id) VALUES(?, ?, ?, ?)',
                    (category.name, expense_val, parent_val, category.user_id))
            category.id = c.lastrowid
        self._db_connection.commit()

    def delete_category(self, category_id):
        if self._get_txn_ids_for_category(category_id):
            raise SQLiteStorageError('category has transactions')
        self._db_connection.execute('DELETE FROM categories WHERE id = ?', (category_id,))
        self._db_connection.commit()

    def _get_txn_ids_for_category(self, category_id):
        return self._db_connection.execute('SELECT txn_id FROM txn_categories WHERE category_id = ?', (category_id,)).fetchall()

    def _txn_from_db_record(self, db_info=None):
        if not db_info:
            raise InvalidTransactionError('no db_info to construct transaction')
        id_, account_id, txn_type, txn_date, payee, amount, description, status = db_info
        txn_date = get_date(txn_date)
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
            c.execute('INSERT INTO budgets(start_date, end_date) VALUES(?, ?)', (budget.start_date, budget.end_date))
            budget.id = c.lastrowid
        for cat, info in budget.get_budget_data().items():
            if info:
                if not cat.id:
                    self.save_category(cat)
                carryover = str(info.get('carryover', ''))
                notes = info.get('notes', '')
                values = (budget.id, cat.id, str(info['amount']), carryover, notes)
                c.execute('INSERT INTO budget_values(budget_id, category_id, amount, carryover, notes) VALUES (?, ?, ?, ?, ?)', values)
        self._db_connection.commit()

    def get_budget(self, budget_id):
        c = self._db_connection.cursor()
        records = c.execute('SELECT start_date, end_date FROM budgets WHERE id = ?', (budget_id,)).fetchall()
        start_date = get_date(records[0][0])
        end_date = get_date(records[0][1])
        all_category_budget_info = {}
        all_income_spending_info = {}
        category_records = self._db_connection.execute('SELECT id FROM categories ORDER BY id').fetchall()
        if not category_records:
            raise Exception('found no categories in DB')
        for cat_record in category_records:
            cat_id = cat_record[0]
            category = self.get_category(cat_id)
            all_category_budget_info[category] = {}
            all_income_spending_info[category] = {}
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
            all_income_spending_info[category]['spent'] = spent
            all_income_spending_info[category]['income'] = income
            budget_records = c.execute('SELECT amount, carryover, notes FROM budget_values WHERE budget_id = ? AND category_id = ?', (budget_id, cat_id)).fetchall()
            if budget_records:
                r = budget_records[0]
                all_category_budget_info[category]['amount'] = Decimal(r[0])
                if r[1]:
                    all_category_budget_info[category]['carryover'] = Decimal(r[1])
                else:
                    all_category_budget_info[category]['carryover'] = Decimal(0)
                if r[2]:
                    all_category_budget_info[category]['notes'] = r[2]
            else:
                all_category_budget_info[category]['budget'] = Decimal(0)
                all_category_budget_info[category]['carryover'] = Decimal(0)
        return Budget(id_=budget_id, start_date=start_date, end_date=end_date, category_budget_info=all_category_budget_info,
                income_spending_info=all_income_spending_info)

    def get_budgets(self):
        budgets = []
        c = self._db_connection.cursor()
        budget_records = c.execute('SELECT id FROM budgets').fetchall()
        for budget_record in budget_records:
            budget_id = int(budget_records[0][0])
            budgets.append(self.get_budget(budget_id))
        return budgets


### GUI ###

TXN_TYPE_WIDTH = 7
DATE_WIDTH = 10
PAYEE_WIDTH = 25
DESCRIPTION_WIDTH = 40
STATUS_WIDTH = 6
CATEGORIES_WIDTH = 15
AMOUNT_WIDTH = 10
BALANCE_WIDTH = 12
ACTIONS_WIDTH = 16


ERROR_STYLE = '''QLineEdit {
    border: 2px solid red;
}'''


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


def set_widget_error_state(widget):
    widget.setStyleSheet(ERROR_STYLE)


class AccountsDisplay:

    def __init__(self, storage, reload_accounts):
        self.storage = storage
        self._reload = reload_accounts

    def get_widget(self):
        main_widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        type_label = QtWidgets.QLabel('Type')
        name_label = QtWidgets.QLabel('Name')
        starting_balance_label = QtWidgets.QLabel('Starting Balance')
        layout.addWidget(type_label, 0, 0)
        layout.addWidget(name_label, 0, 1)
        layout.addWidget(starting_balance_label, 0, 2)
        self.accounts_widgets = {}
        accounts = self.storage.get_accounts()
        row = 1
        for acc in accounts:

            def _edit(event, acc_id):
                orig_name = self.accounts_widgets[acc_id]['labels']['name'].text()
                orig_starting_balance = self.accounts_widgets[acc_id]['labels']['starting_balance'].text()
                for label in self.accounts_widgets[acc_id]['labels'].values():
                    layout.removeWidget(label)
                    label.deleteLater()
                name_entry = QtWidgets.QLineEdit()
                name_entry.setText(orig_name)
                starting_balance_entry = QtWidgets.QLineEdit()
                starting_balance_entry.setText(orig_starting_balance)
                row = self.accounts_widgets[acc_id]['row']
                layout.addWidget(name_entry, row, 0)
                layout.addWidget(starting_balance_entry, row, 1)

                def _save(acc_id):
                    name = self.accounts_widgets[acc_id]['entries']['name'].text()
                    starting_balance = self.accounts_widgets[acc_id]['entries']['starting_balance'].text()
                    try:
                        self.storage.save_account(Account(name=name, starting_balance=starting_balance, id_=acc_id))
                        self._reload()
                    except InvalidAccountNameError:
                        set_widget_error_state(self.accounts_widgets[acc_id]['entries']['name'])
                    except InvalidAccountStartingBalanceError:
                        set_widget_error_state(self.accounts_widgets[acc_id]['entries']['starting_balance'])

                save_button = QtWidgets.QPushButton('Save Edit')
                save_button.clicked.connect(partial(_save, acc_id=acc_id))
                layout.addWidget(save_button, row, 2)
                self.accounts_widgets[acc_id]['entries'] = {
                        'name': name_entry,
                        'starting_balance': starting_balance_entry,
                    }
                self.accounts_widgets[acc_id]['buttons'] = {
                        'save_edit': save_button,
                    }

            edit_function = partial(_edit, acc_id=acc.id)
            type_label = QtWidgets.QLabel(str(acc.type))
            type_label.mousePressEvent = edit_function
            name_label = QtWidgets.QLabel(acc.name)
            name_label.mousePressEvent = edit_function
            starting_balance_label = QtWidgets.QLabel(str(acc.starting_balance))
            starting_balance_label.mousePressEvent = edit_function
            layout.addWidget(type_label, row, 0)
            layout.addWidget(name_label, row, 1)
            layout.addWidget(starting_balance_label, row, 2)
            self.accounts_widgets[acc.id] = {
                    'row': row,
                    'labels': {'name': name_label, 'starting_balance': starting_balance_label},
                }
            row += 1

        add_account_name = QtWidgets.QLineEdit()
        layout.addWidget(add_account_name, row, 0)
        add_account_starting_balance = QtWidgets.QLineEdit()
        layout.addWidget(add_account_starting_balance, row, 1)
        button = QtWidgets.QPushButton('Add New')
        button.clicked.connect(self._save_new_account)
        layout.addWidget(button, row, 2)
        self.add_account_widgets = {
                'entries': {'name': add_account_name, 'starting_balance': add_account_starting_balance},
                'buttons': {'add_new': button},
            }
        layout.addWidget(QtWidgets.QLabel(''), row+1, 0)
        layout.setRowStretch(row+1, 1)
        main_widget.setLayout(layout)
        return main_widget

    def _save_new_account(self):
        name = self.add_account_widgets['entries']['name'].text()
        starting_balance = self.add_account_widgets['entries']['starting_balance'].text()
        try:
            account = Account(name=name, starting_balance=starting_balance)
            self.storage.save_account(account)
            self._reload()
        except InvalidAccountStartingBalanceError:
            set_widget_error_state(self.add_account_widgets['entries']['starting_balance'])
        except InvalidAccountNameError:
            set_widget_error_state(self.add_account_widgets['entries']['name'])


def set_ledger_column_widths(layout):
    layout.setColumnStretch(0, 1)
    layout.setColumnStretch(1, 1)
    layout.setColumnStretch(2, 4)
    layout.setColumnStretch(3, 5)
    layout.setColumnStretch(4, 5)
    layout.setColumnStretch(5, 1)
    layout.setColumnStretch(6, 3)
    layout.setColumnStretch(7, 3)
    layout.setColumnStretch(8, 3)


class SplitTransactionEditor:

    def __init__(self, all_categories, initial_txn_categories):
        self._all_categories = all_categories
        self._initial_txn_categories = initial_txn_categories
        self._final_txn_categories = []
        self._entries = {}

    def _get_txn_categories(self, split_editor):
        for value in self._entries.values():
            #value is amount_entry, category
            text = value[0].text()
            if text:
                self._final_txn_categories.append([value[1], text])
        split_editor.accept()

    def _show_split_editor(self):
        split_editor = QtWidgets.QDialog()
        layout = QtWidgets.QGridLayout()
        row = 0
        for cat in self._all_categories:
            layout.addWidget(QtWidgets.QLabel(cat.name), row, 0)
            amount_entry = QtWidgets.QLineEdit()
            for txn_cat in self._initial_txn_categories:
                if cat == txn_cat[0]:
                    amount_entry.setText(str(txn_cat[1]))
            self._entries[cat.id] = (amount_entry, cat)
            layout.addWidget(amount_entry, row, 1)
            row += 1
        ok_button = QtWidgets.QPushButton('Done')
        ok_button.clicked.connect(partial(self._get_txn_categories, split_editor=split_editor))
        cancel_button = QtWidgets.QPushButton('Cancel')
        cancel_button.clicked.connect(split_editor.reject)
        layout.addWidget(ok_button, row, 0)
        layout.addWidget(cancel_button, row, 1)
        split_editor.setLayout(layout)
        split_editor.exec_()

    def get_categories_for_split_transaction(self):
        self._show_split_editor()
        return self._final_txn_categories


class LedgerTxnsDisplay:

    def __init__(self, ledger, storage):
        self.ledger = ledger
        self.storage = storage
        self.txn_display_data = {}

    def get_widget(self):
        self.txns_layout = QtWidgets.QGridLayout()
        set_ledger_column_widths(self.txns_layout)
        self._redisplay_txns()
        txns_widget = QtWidgets.QWidget()
        txns_widget.setLayout(self.txns_layout)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(txns_widget)
        return scroll

    def display_new_txn(self, txn):
        self.ledger.add_transaction(txn)
        self._redisplay_txns()

    def _redisplay_txns(self):
        '''draw/redraw txns on the screen as needed'''
        for index, txn in enumerate(self.ledger.get_sorted_txns_with_balance()):
            if (txn.id not in self.txn_display_data) or (self.txn_display_data[txn.id]['row'] != index):
                self._display_txn(txn, row=index, layout=self.txns_layout)
            else:
                try:
                    if self.txn_display_data[txn.id]['widgets']['labels']['balance'].text() != txn.balance:
                        self._display_txn(txn, row=index, layout=self.txns_layout)
                except KeyError:
                    pass

    def _remove_edit_widgets(self, txn_widgets, layout):
        for widget in txn_widgets['entries'].values():
            layout.removeWidget(widget)
            widget.deleteLater()
        for widget in txn_widgets['buttons'].values():
            layout.removeWidget(widget)
            widget.deleteLater()

    def _delete(self, txn_id, layout, txn_widgets):
        #delete from storage, remove it from ledger, delete the edit widgets, delete the display info
        #   & then redisplay any txns necessary
        self.storage.delete_txn(txn_id)
        self.ledger.remove_txn(txn_id)
        self._remove_edit_widgets(txn_widgets, layout)
        del self.txn_display_data[txn_id]
        self._redisplay_txns()

    def _save_edit(self, txn_id, layout):
        #get data from widgets, update the txn, save it, delete the edit widgets, delete the display info
        #   & then redisplay any txns necessary
        entries = self.txn_display_data[txn_id]['widgets']['entries']
        txn_type = entries['type'].text()
        txn_date = entries['date'].text()
        payee = entries['payee'].text()
        debit = entries['debit'].text()
        credit = entries['credit'].text()
        description = entries['description'].text()
        status = entries['status'].text()
        categories = self.txn_display_data[txn_id]['categories_display'].get_categories()
        txn = self.ledger.get_txn(txn_id)
        txn.update_from_user_strings(
                txn_type=txn_type,
                txn_date=txn_date,
                payee=payee,
                debit=debit,
                credit=credit,
                description=description,
                status=status,
                categories=categories,
            )
        self.storage.save_txn(txn)
        self._remove_edit_widgets(self.txn_display_data[txn_id]['widgets'], layout)
        del self.txn_display_data[txn_id]
        self._redisplay_txns()

    def _edit(self, event, txn_id, layout):
        #create edit entries using initial values from labels, delete labels,
        #   add edit entries to layout, add save/delete buttons, and set txn_display_data
        row = self.txn_display_data[txn_id]['row']
        txn = self.txn_display_data[txn_id]['txn']
        widgets = self.txn_display_data[txn_id]['widgets']
        type_entry = QtWidgets.QLineEdit()
        type_entry.setText(widgets['labels']['type'].text())
        date_entry = QtWidgets.QLineEdit()
        date_entry.setText(widgets['labels']['date'].text())
        payee_entry = QtWidgets.QLineEdit()
        payee_entry.setText(widgets['labels']['payee'].text())
        description_entry = QtWidgets.QLineEdit()
        description_entry.setText(widgets['labels']['description'].text())
        txn_categories_display = TxnCategoriesDisplay(self.storage, txn=txn)
        status_entry = QtWidgets.QLineEdit()
        status_entry.setText(widgets['labels']['status'].text())
        credit_entry = QtWidgets.QLineEdit()
        credit_entry.setText(widgets['labels']['credit'].text())
        debit_entry = QtWidgets.QLineEdit()
        debit_entry.setText(widgets['labels']['debit'].text())
        for widget in self.txn_display_data[txn_id]['widgets']['labels'].values():
            layout.removeWidget(widget)
            widget.deleteLater()
        self.txn_display_data[txn_id]['widgets']['labels'] = {}
        layout.addWidget(type_entry, row, 0)
        layout.addWidget(date_entry, row, 1)
        layout.addWidget(payee_entry, row, 2)
        layout.addWidget(description_entry, row, 3)
        layout.addWidget(txn_categories_display.get_widget(), row, 4)
        layout.addWidget(status_entry, row, 5)
        layout.addWidget(debit_entry, row, 6)
        layout.addWidget(credit_entry, row, 7)
        save_edit_button = QtWidgets.QPushButton('Save Edit')
        save_edit_button.clicked.connect(partial(self._save_edit, txn_id=txn_id, layout=layout))
        delete_button = QtWidgets.QPushButton('Delete')
        delete_button.clicked.connect(partial(self._delete, txn_id=txn_id, layout=layout, txn_widgets=self.txn_display_data[txn_id]['widgets']))
        buttons_layout = QtWidgets.QGridLayout()
        buttons_layout.addWidget(save_edit_button, 0, 0)
        buttons_layout.addWidget(delete_button, 0, 1)
        buttons_widget = QtWidgets.QWidget()
        buttons_widget.setLayout(buttons_layout)
        layout.addWidget(buttons_widget, row, 8)
        self.txn_display_data[txn_id]['widgets']['entries'] = {
                'type': type_entry,
                'date': date_entry,
                'payee': payee_entry,
                'description': description_entry,
                'categories': txn_categories_display.get_widget(),
                'status': status_entry,
                'credit': credit_entry,
                'debit': debit_entry,
            }
        self.txn_display_data[txn_id]['widgets']['buttons'] = {
                'save_edit': save_edit_button,
                'delete': delete_button,
            }
        self.txn_display_data[txn_id]['categories_display'] = txn_categories_display

    def _display_txn(self, txn, row, layout):
        #clear labels if this txn was already displayed, create new labels, add them to layout, and set txn_display_data
        if txn.id in self.txn_display_data:
            for widget in self.txn_display_data[txn.id]['widgets']['labels'].values():
                layout.removeWidget(widget)
                widget.deleteLater()
        tds = txn.get_display_strings()
        edit_function = partial(self._edit, txn_id=txn.id, layout=layout)
        type_label = QtWidgets.QLabel(tds['txn_type'])
        type_label.mousePressEvent = edit_function
        date_label = QtWidgets.QLabel(tds['txn_date'])
        date_label.mousePressEvent = edit_function
        payee_label = QtWidgets.QLabel(tds['payee'])
        payee_label.mousePressEvent = edit_function
        description_label = QtWidgets.QLabel(tds['description'])
        description_label.mousePressEvent = edit_function
        categories_label = QtWidgets.QLabel(tds['categories'])
        categories_label.mousePressEvent = edit_function
        status_label = QtWidgets.QLabel(tds['status'])
        status_label.mousePressEvent = edit_function
        credit_label = QtWidgets.QLabel(tds['credit'])
        credit_label.mousePressEvent = edit_function
        debit_label = QtWidgets.QLabel(tds['debit'])
        debit_label.mousePressEvent = edit_function
        balance_label = QtWidgets.QLabel(str(txn.balance))
        balance_label.mousePressEvent = edit_function
        layout.addWidget(type_label, row, 0)
        layout.addWidget(date_label, row, 1)
        layout.addWidget(payee_label, row, 2)
        layout.addWidget(description_label, row, 3)
        layout.addWidget(categories_label, row, 4)
        layout.addWidget(status_label, row, 5)
        layout.addWidget(debit_label, row, 6)
        layout.addWidget(credit_label, row, 7)
        layout.addWidget(balance_label, row, 8)
        self.txn_display_data[txn.id] = {
                'widgets': {
                    'labels': {
                        'type': type_label,
                        'date': date_label,
                        'payee': payee_label,
                        'description': description_label,
                        'categories': categories_label,
                        'status': status_label,
                        'credit': credit_label,
                        'debit': debit_label,
                        'balance': balance_label
                    }
                },
                'row': row,
                'txn': txn,
            }


class TxnCategoriesDisplay:

    def __init__(self, storage, txn=None):
        self._storage = storage
        self._txn = txn
        layout = QtWidgets.QGridLayout()
        self._categories_combo = QtWidgets.QComboBox()
        self._categories_combo.addItem('---------', None)
        current_index = 0
        index = 0
        for index, category in enumerate(self._storage.get_categories()):
            #find correct category in the list if txn has a category
            if txn and txn.categories and len(txn.categories) == 1:
                if category == txn.categories[0][0]:
                    current_index = index + 1
            self._categories_combo.addItem(category.name, category)
        self._multiple_entry_index = index + 2
        current_categories = []
        if txn and txn.categories and len(txn.categories) > 1:
            current_categories = txn.categories
            current_index = self._multiple_entry_index
        self._categories_combo.addItem('multiple', current_categories)
        self._categories_combo.setCurrentIndex(current_index)
        layout.addWidget(self._categories_combo, 0, 0)
        split_button = QtWidgets.QPushButton('Split')
        txn_id = None
        if txn:
            txn_id = txn.id
        split_button.clicked.connect(self._split_transactions)
        layout.addWidget(split_button)
        self._widget = QtWidgets.QWidget()
        self._widget.setLayout(layout)

    def _split_transactions(self):
        initial_txn_categories = []
        if self._txn:
            initial_txn_categories = self._txn.categories
        editor = SplitTransactionEditor(self.storage.get_categories(), initial_txn_categories)
        txn_categories = editor.get_categories_for_split_transaction()
        self._categories_combo.setCurrentIndex(self._multiple_entry_index)
        self._categories_combo.setItemData(self._multiple_entry_index, txn_categories)

    def get_categories(self):
        return self._categories_combo.currentData()

    def get_widget(self):
        return self._widget


class LedgerDisplay:

    def __init__(self, storage, show_ledger, current_account=None):
        self.storage = storage
        self._show_ledger = show_ledger
        if not current_account:
            current_account = storage.get_accounts()[0]
        self._current_account = current_account

    def get_widget(self):
        self.widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        set_ledger_column_widths(layout)
        new_row = self._show_headings(layout, row=0)
        self.ledger = Ledger(starting_balance=self._current_account.starting_balance)
        self.storage.load_txns_into_ledger(self._current_account.id, self.ledger)
        self.txns_display = LedgerTxnsDisplay(self.ledger, self.storage)
        layout.addWidget(self.txns_display.get_widget(), new_row, 0, 1, 9)
        self.add_txn_widgets = {'entries': {}, 'buttons': {}}
        self._show_add_txn(layout, self.add_txn_widgets, payees=self.ledger.get_payees(), row=new_row+1)
        self.widget.setLayout(layout)
        return self.widget

    def _update_account(self, index):
        self._show_ledger(self.storage.get_accounts()[index])

    def _show_headings(self, layout, row):
        self.action_combo = QtWidgets.QComboBox()
        current_index = 0
        for index, a in enumerate(self.storage.get_accounts()):
            if a.id == self._current_account.id:
                current_index = index
            self.action_combo.addItem(a.name)
        self.action_combo.setCurrentIndex(current_index)
        self.action_combo.currentIndexChanged.connect(self._update_account)
        layout.addWidget(self.action_combo, row, 0)
        row += 1
        layout.addWidget(QtWidgets.QLabel('Txn Type'), row, 0)
        layout.addWidget(QtWidgets.QLabel('Date'), row, 1)
        layout.addWidget(QtWidgets.QLabel('Payee'), row, 2)
        layout.addWidget(QtWidgets.QLabel('Description'), row, 3)
        layout.addWidget(QtWidgets.QLabel('Categories'), row, 4)
        layout.addWidget(QtWidgets.QLabel('Status'), row, 5)
        layout.addWidget(QtWidgets.QLabel('Debit (-)'), row, 6)
        layout.addWidget(QtWidgets.QLabel('Credit (+)'), row, 7)
        layout.addWidget(QtWidgets.QLabel('Balance'), row, 8)
        return row + 1

    def _show_add_txn(self, layout, add_txn_widgets, payees, row):
        entry_names = ['type', 'date']
        for column_index, entry_name in enumerate(entry_names):
            entry = QtWidgets.QLineEdit()
            add_txn_widgets['entries'][entry_name] = entry
            layout.addWidget(entry, row, column_index)
        payee_entry = QtWidgets.QComboBox()
        payee_entry.setEditable(True)
        payee_entry.addItem('')
        for payee in payees:
            payee_entry.addItem(payee)
        add_txn_widgets['payee'] = payee_entry
        layout.addWidget(payee_entry, row, 2)
        description_entry = QtWidgets.QLineEdit()
        add_txn_widgets['entries']['description'] = description_entry
        layout.addWidget(description_entry, row, 3)
        txn_categories_display = TxnCategoriesDisplay(self.storage)
        layout.addWidget(txn_categories_display.get_widget(), row, 4)
        add_txn_widgets['categories_display'] = txn_categories_display
        entry_names = ['status', 'debit', 'credit']
        column_index = 5
        for entry_name in entry_names:
            entry = QtWidgets.QLineEdit()
            add_txn_widgets['entries'][entry_name] = entry
            layout.addWidget(entry, row, column_index)
            column_index += 1
        add_new_button = QtWidgets.QPushButton('Add New')
        add_new_button.clicked.connect(self._save_new_txn)
        add_txn_widgets['buttons']['add_new'] = add_new_button
        layout.addWidget(add_new_button, row, 8)

    def _save_new_txn(self):
        txn_type = self.add_txn_widgets['entries']['type'].text()
        txn_date = self.add_txn_widgets['entries']['date'].text()
        payee = self.add_txn_widgets['payee'].currentText()
        description = self.add_txn_widgets['entries']['description'].text()
        categories = self.add_txn_widgets['categories_display'].get_categories()
        status = self.add_txn_widgets['entries']['status'].text()
        credit = self.add_txn_widgets['entries']['credit'].text()
        debit = self.add_txn_widgets['entries']['debit'].text()
        txn = Transaction.from_user_strings(
                account=self.storage.get_accounts()[0],
                txn_type=txn_type,
                credit=credit,
                debit=debit,
                txn_date=txn_date,
                payee=payee,
                description=description,
                status=status,
                categories=categories
            )
        self.storage.save_txn(txn)
        self.txns_display.display_new_txn(txn)
        self._clear_add_txn_widgets()

    def _clear_add_txn_widgets(self):
        for widget in self.add_txn_widgets['entries'].values():
            widget.setText('')
        self.add_txn_widgets['payee'].setCurrentText('')


class CategoriesDisplay:

    def __init__(self, storage, reload_categories):
        self._storage = storage
        self._reload = reload_categories

    def _delete(self, cat_id):
        self._storage.delete_category(cat_id)
        self._reload()

    def _save_edit(self, cat_id):
        user_id = self.data[cat_id]['entries']['user_id'].text() or None
        parent = self.data[cat_id]['parent_combo'].currentData()
        c = Category(id_=cat_id, name=self.data[cat_id]['entries']['name'].text(), user_id=user_id, parent=parent)
        self._storage.save_category(c)
        self._reload()

    def _edit(self, event, cat_id, layout):
        user_id_entry = QtWidgets.QLineEdit()
        user_id_entry.setText(self.data[cat_id]['labels']['user_id'].text())
        current_cat_name = self.data[cat_id]['labels']['name'].text()
        name_entry = QtWidgets.QLineEdit()
        name_entry.setText(current_cat_name)

        parent_combo = QtWidgets.QComboBox()
        current_index = 0
        edit_category = self.data[cat_id]['cat']
        parent_combo.addItem('-------', None)
        for index, cat in enumerate(self._storage.get_categories()):
            if edit_category.parent:
                if edit_category.parent.id == cat.id:
                    current_index = index + 1
            if cat.name != current_cat_name:
                parent_combo.addItem(cat.name, cat)
        parent_combo.setCurrentIndex(current_index)

        layout.addWidget(user_id_entry, self.data[cat_id]['row'], 1)
        layout.addWidget(name_entry, self.data[cat_id]['row'], 2)
        layout.addWidget(parent_combo, self.data[cat_id]['row'], 3)
        save_edit_button = QtWidgets.QPushButton('Save Edit')
        save_edit_button.clicked.connect(partial(self._save_edit, cat_id=cat_id))
        layout.addWidget(save_edit_button, self.data[cat_id]['row'], 4)
        delete_button = QtWidgets.QPushButton('Delete')
        delete_button.clicked.connect(partial(self._delete, cat_id=cat_id))
        layout.addWidget(delete_button, self.data[cat_id]['row'], 5)
        self.data[cat_id]['entries'] = {'user_id': user_id_entry, 'name': name_entry}
        self.data[cat_id]['parent_combo'] = parent_combo
        self.data[cat_id]['buttons'] = {'save_edit': save_edit_button, 'delete': delete_button}

    def get_widget(self):
        self.main_widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 5)
        layout.setColumnStretch(2, 15)
        layout.setColumnStretch(3, 15)
        layout.addWidget(QtWidgets.QLabel('User ID'), 0, 0)
        layout.addWidget(QtWidgets.QLabel('Name'), 0, 1)
        layout.addWidget(QtWidgets.QLabel('Parent Category'), 0, 2)
        row = 1
        self.data = {}
        categories = self._storage.get_categories()
        for cat in categories:
            row_data = {'row': row, 'cat': cat}
            edit_function = partial(self._edit, cat_id=cat.id, layout=layout)
            id_label = QtWidgets.QLabel(str(cat.id))
            if cat.user_id:
                user_id_label = QtWidgets.QLabel(cat.user_id)
            else:
                user_id_label = QtWidgets.QLabel()
            name_label = QtWidgets.QLabel(cat.name)
            if cat.parent:
                parent_name = cat.parent.name
            else:
                parent_name = ''
            parent_label = QtWidgets.QLabel(parent_name)
            layout.addWidget(user_id_label, row, 0)
            layout.addWidget(name_label, row, 1)
            layout.addWidget(parent_label, row, 2)
            id_label.mousePressEvent = edit_function
            name_label.mousePressEvent = edit_function
            row_data['labels'] = {'user_id': user_id_label, 'name': name_label}
            self.data[cat.id] = row_data
            row += 1
        self.user_id_entry = QtWidgets.QLineEdit()
        layout.addWidget(self.user_id_entry, row, 0)
        self.name_entry = QtWidgets.QLineEdit()
        layout.addWidget(self.name_entry, row, 1)
        self.add_parent_combo = QtWidgets.QComboBox()
        self.add_parent_combo.addItem('-------', None)
        for index, cat in enumerate(self._storage.get_categories()):
            self.add_parent_combo.addItem(cat.name, cat)
        layout.addWidget(self.add_parent_combo, row, 2)
        self.add_button = QtWidgets.QPushButton('Add New')
        self.add_button.clicked.connect(self._add)
        layout.addWidget(self.add_button, row, 3)
        layout.addWidget(QtWidgets.QLabel(''), row+1, 0)
        layout.setRowStretch(row+1, 1)
        self.main_widget.setLayout(layout)
        return self.main_widget

    def _add(self):
        user_id = self.user_id_entry.text() or None
        c = Category(name=self.name_entry.text(), user_id=user_id, parent=self.add_parent_combo.currentData())
        self._storage.save_category(c)
        self._reload()


class BudgetDisplay:

    def __init__(self, budget, storage, reload_budget):
        self.budget = budget
        self.storage = storage
        self.reload_budget = reload_budget

    def get_widget(self):
        self.main_widget = QtWidgets.QWidget()
        self.layout = QtWidgets.QGridLayout()
        self.layout.addWidget(QtWidgets.QLabel('Category'), 0, 0)
        self.layout.addWidget(QtWidgets.QLabel('Amount'), 0, 1)
        self.layout.addWidget(QtWidgets.QLabel('Income'), 0, 2)
        self.layout.addWidget(QtWidgets.QLabel('Carryover'), 0, 3)
        self.layout.addWidget(QtWidgets.QLabel('Total Budget'), 0, 4)
        self.layout.addWidget(QtWidgets.QLabel('Spent'), 0, 5)
        self.layout.addWidget(QtWidgets.QLabel('Remaining'), 0, 6)
        self.layout.addWidget(QtWidgets.QLabel('Percent Available'), 0, 7)
        row_index = 1
        self.data = {}
        budget_report = self.budget.get_report_display()
        for cat, info in budget_report['income'].items():
            self.layout.addWidget(QtWidgets.QLabel(cat.name), row_index, 0)
            budget_label = QtWidgets.QLabel(info['amount'])
            self.layout.addWidget(budget_label, row_index, 1)
            self.layout.addWidget(QtWidgets.QLabel(info['income']), row_index, 2)
            carryover_label = QtWidgets.QLabel(info['carryover'])
            self.layout.addWidget(carryover_label, row_index, 3)
            self.layout.addWidget(QtWidgets.QLabel(info['spent']), row_index, 5)
            self.layout.addWidget(QtWidgets.QLabel(info['remaining']), row_index, 6)
            self.layout.addWidget(QtWidgets.QLabel(info['percent']), row_index, 7)
            row_data = {'budget_label': budget_label}
            row_data['carryover_label'] = carryover_label
            row_data['row_index'] = row_index
            row_data['category'] = cat
            self.data[cat.id] = row_data
            row_index += 1
        for cat, info in budget_report['expense'].items():
            self.layout.addWidget(QtWidgets.QLabel(cat.name), row_index, 0)
            budget_label = QtWidgets.QLabel(info['amount'])
            self.layout.addWidget(budget_label, row_index, 1)
            self.layout.addWidget(QtWidgets.QLabel(info['income']), row_index, 2)
            carryover_label = QtWidgets.QLabel(info['carryover'])
            self.layout.addWidget(carryover_label, row_index, 3)
            self.layout.addWidget(QtWidgets.QLabel(info['total_budget']), row_index, 4)
            self.layout.addWidget(QtWidgets.QLabel(info['spent']), row_index, 5)
            self.layout.addWidget(QtWidgets.QLabel(info['remaining']), row_index, 6)
            self.layout.addWidget(QtWidgets.QLabel(info['percent_available']), row_index, 7)
            row_data = {'budget_label': budget_label}
            row_data['carryover_label'] = carryover_label
            row_data['row_index'] = row_index
            row_data['category'] = cat
            self.data[cat.id] = row_data
            row_index += 1
        self.button_row_index = row_index
        self._edit_button = QtWidgets.QPushButton('Edit')
        self._edit_button.clicked.connect(self._edit)
        self.layout.addWidget(self._edit_button, self.button_row_index, 0)
        self.layout.addWidget(QtWidgets.QLabel(''), row_index+1, 0)
        self.layout.setRowStretch(row_index+1, 1)
        self.main_widget.setLayout(self.layout)
        return self.main_widget

    def _save(self):
        category_rows = {}
        for cat_id, info in self.data.items():
            cat = info['category']
            category_rows[cat] = {
                    'amount': info['budget_entry'].text(),
                    'carryover': info['carryover_entry'].text()
                }
        b = Budget(id_=self.budget.id, start_date=self.budget.start_date, end_date=self.budget.end_date, category_budget_info=category_rows)
        self.storage.save_budget(b)
        self.reload_budget()

    def _edit(self):
        for cat_id, info in self.data.items():
            budget_val = info['budget_label'].text()
            carryover_val = info['carryover_label'].text()
            self.layout.removeWidget(info['budget_label'])
            info['budget_label'].deleteLater()
            self.layout.removeWidget(info['carryover_label'])
            info['carryover_label'].deleteLater()
            budget_entry = QtWidgets.QLineEdit()
            budget_entry.setText(budget_val)
            self.layout.addWidget(budget_entry, info['row_index'], 1)
            info['budget_entry'] = budget_entry
            carryover_entry = QtWidgets.QLineEdit()
            carryover_entry.setText(carryover_val)
            self.layout.addWidget(carryover_entry, info['row_index'], 3)
            info['carryover_entry'] = carryover_entry
        self.layout.removeWidget(self._edit_button)
        self._edit_button.deleteLater()
        self._save_button = QtWidgets.QPushButton('Save')
        self._save_button.clicked.connect(self._save)
        self.layout.addWidget(self._save_button, self.button_row_index, 0)


class PFT_GUI_QT:

    def __init__(self, file_name=None):
        title = 'Python Finance Tracking'
        self.parent_window = QtWidgets.QWidget()
        self.parent_window.setWindowTitle(title)
        self.parent_layout = QtWidgets.QGridLayout()
        self.parent_window.setLayout(self.parent_layout)

        self.content_area = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QGridLayout()
        self.content_area.setLayout(self.content_layout)
        self.parent_layout.addWidget(self.content_area, 1, 0, 1, 6)
        self.parent_window.showMaximized()

        self.main_widget = None
        self._show_action_buttons(self.parent_layout, file_loaded=False)
        if file_name:
            self._load_db(file_name)

    def _load_db(self, file_name):
        try:
            self.storage = SQLiteStorage(file_name)
        except sqlite3.DatabaseError as e:
            if 'file is not a database' in str(e):
                msgbox = QtWidgets.QMessageBox()
                msgbox.setText('File %s is not a database' % file_name)
                msgbox.exec_()
                return
            raise
        accounts = self.storage.get_accounts()
        if accounts:
            self._show_ledger()
        else:
            self._show_accounts()

    def _new_file(self):
        file_name = QtWidgets.QFileDialog.getSaveFileName()[0]
        if file_name:
            self._load_db(file_name)

    def _open_file(self):
        file_name = QtWidgets.QFileDialog.getOpenFileName()[0]
        if file_name:
            self._load_db(file_name)

    def _update_action_buttons(self, display):
        self.accounts_button.setEnabled(True)
        self.ledger_button.setEnabled(True)
        self.categories_button.setEnabled(True)
        self.budget_button.setEnabled(True)
        if display == 'accounts':
            self.accounts_button.setEnabled(False)
        elif display == 'categories':
            self.categories_button.setEnabled(False)
        elif display == 'budget':
            self.budget_button.setEnabled(False)
        else:
            self.ledger_button.setEnabled(False)

    def _show_action_buttons(self, layout, file_loaded=True):
        self.new_button = QtWidgets.QPushButton('New')
        self.new_button.clicked.connect(self._new_file)
        layout.addWidget(self.new_button, 0, 0)
        self.open_button = QtWidgets.QPushButton('Open')
        self.open_button.clicked.connect(self._open_file)
        layout.addWidget(self.open_button, 0, 1)
        self.accounts_button = QtWidgets.QPushButton('Accounts')
        self.accounts_button.clicked.connect(self._show_accounts)
        layout.addWidget(self.accounts_button, 0, 2)
        self.ledger_button = QtWidgets.QPushButton('Ledger')
        self.ledger_button.clicked.connect(self._show_ledger)
        layout.addWidget(self.ledger_button, 0, 3)
        self.categories_button = QtWidgets.QPushButton('Categories')
        self.categories_button.clicked.connect(self._show_categories)
        layout.addWidget(self.categories_button, 0, 4)
        self.budget_button = QtWidgets.QPushButton('Budget')
        self.budget_button.clicked.connect(self._show_budget)
        layout.addWidget(self.budget_button, 0, 5)
        if not file_loaded:
            self.accounts_button.setEnabled(False)
            self.ledger_button.setEnabled(False)
            self.categories_button.setEnabled(False)
            self.budget_button.setEnabled(False)

    def _show_accounts(self):
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self._update_action_buttons('accounts')
        self.accounts_display = AccountsDisplay(self.storage, reload_accounts=self._show_accounts)
        self.main_widget = self.accounts_display.get_widget()
        self.content_layout.addWidget(self.main_widget, 0, 0)

    def _show_ledger(self, current_account=None):
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self._update_action_buttons('ledger')
        self.ledger_display = LedgerDisplay(self.storage, show_ledger=self._show_ledger, current_account=current_account)
        self.main_widget = self.ledger_display.get_widget()
        self.content_layout.addWidget(self.main_widget, 0, 0)

    def _show_categories(self):
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self._update_action_buttons(display='categories')
        self.categories_display = CategoriesDisplay(self.storage, reload_categories=self._show_categories)
        self.main_widget = self.categories_display.get_widget()
        self.content_layout.addWidget(self.main_widget, 0, 0)

    def _show_budget(self):
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self._update_action_buttons(display='budget')
        budgets = self.storage.get_budgets()
        self.budget_display = BudgetDisplay(budgets[0], self.storage, self._show_budget)
        self.main_widget = self.budget_display.get_widget()
        self.content_layout.addWidget(self.main_widget, 0, 0)


def parse_args():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--install_qt', dest='install_qt', action='store_true')
    parser.add_argument('-f', '--file_name', dest='file_name')
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    args = parse_args()
    if args.install_qt:
        _do_qt_install()
        sys.exit(0)

    try:
        from PySide2 import QtWidgets
    except ImportError:
        install_qt_for_python()

    app = QtWidgets.QApplication([])
    if args.file_name:
        gui = PFT_GUI_QT(args.file_name)
    else:
        gui = PFT_GUI_QT()
    app.exec_()

