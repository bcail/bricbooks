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

class InvalidTransactionError(RuntimeError):
    pass

class InvalidLedgerError(RuntimeError):
    pass

class InvalidScheduledTransactionError(RuntimeError):
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

    def __init__(self, id_=None, type_=None, user_id=None, name=None, parent=None):
        self.id = id_
        if not type_:
            raise InvalidAccountError('Account must have a type')
        if not name:
            raise InvalidAccountNameError('Account must have a name')
        self.type = self._check_type(type_)
        self.user_id = user_id or None
        self.name = name
        self.parent = parent

    def __str__(self):
        if self.user_id:
            return '%s - %s' % (self.user_id, self.name)
        else:
            return self.name

    def __repr__(self):
        return '%s - %s' % (self.type, self.name)

    def __eq__(self, other_account):
        if not other_account:
            return False
        if self.id and other_account.id:
            return self.id == other_account.id
        else:
            raise InvalidAccountError("Can't compare accounts without an id")

    def __hash__(self):
        return self.id

    def _check_type(self, type_):
        if not isinstance(type_, AccountType):
            raise InvalidAccountError('Invalid account type "%s"' % type_)
        return type_

def check_txn_splits(input_splits):
    if not input_splits or len(input_splits.items()) < 2:
        raise InvalidTransactionError('transaction must have at least 2 splits')
    splits = {}
    total = Decimal(0)
    for account, amount in input_splits.items():
        if not account:
            raise InvalidTransactionError('must have a valid account in splits')
        if isinstance(amount, Decimal):
            decimal_amount = amount
        elif isinstance(amount, (int, str)):
            decimal_amount = Decimal(amount)
        else:
            raise InvalidTransactionError('invalid split amount: %s' % amount)
        #check for fractions of cents
        amt_str = str(decimal_amount)
        if '.' in amt_str:
            _, decimals = amt_str.split('.')
            if len(decimals) > 2:
                raise InvalidTransactionError('no fractions of cents in a transaction')
        total += decimal_amount
        splits[account] = decimal_amount
    if total != Decimal(0):
        raise InvalidTransactionError("splits don't balance")
    return splits


class Transaction:

    CLEARED = 'C'
    RECONCILED = 'R'

    @staticmethod
    def splits_from_user_info(account, deposit, withdrawal, input_categories):
        splits = {}
        categories = {}
        try:
            amount = Decimal(deposit or withdrawal)
        except InvalidOperation:
            raise InvalidTransactionError('invalid deposit/withdrawal')
        if isinstance(input_categories, Account):
            categories[input_categories] = amount
        elif isinstance(input_categories, dict):
            categories = input_categories
        else:
            raise InvalidTransactionError('invalid input categories: %s' % input_categories)
        if deposit:
            splits[account] = deposit
            for key, value in categories.items():
                splits[key] = '-%s' % value
        elif withdrawal:
            splits[account] = '-%s' % withdrawal
            splits.update(categories)
        return splits

    @staticmethod
    def from_user_info(account, deposit, withdrawal, txn_date, txn_type, categories, payee, description, status):
        splits = Transaction.splits_from_user_info(account, deposit, withdrawal, categories)
        return Transaction(
                splits=splits,
                txn_date=txn_date,
                txn_type=txn_type,
                payee=payee,
                description=description,
                status=status
            )

    def __init__(self, txn_date=None, txn_type=None, splits=None, payee=None, description=None, status=None, id_=None):
        self.splits = check_txn_splits(splits)
        self.txn_date = self._check_txn_date(txn_date)
        self.txn_type = txn_type
        self.payee = payee
        self.description = description
        self.status = self._handle_status(status)
        self.id = id_

    def __str__(self):
        return '%s: %s' % (self.id, self.txn_date)

    def _check_account(self, account):
        if not account:
            raise InvalidTransactionError('transaction must belong to an account')
        return account

    def _check_txn_date(self, txn_date):
        if not txn_date:
            raise InvalidTransactionError('transaction must have a txn_date')
        try:
            return get_date(txn_date)
        except Exception:
            raise InvalidTransactionError('invalid txn_date "%s"' % txn_date)

    def _handle_status(self, status):
        if status:
            if status.upper() == self.CLEARED:
                return self.CLEARED
            elif status.upper() == self.RECONCILED:
                return self.RECONCILED
            else:
                raise InvalidTransactionError('invalid status "%s"' % status)
        else:
            return None

    def _categories_display(self, main_account):
        if len(self.splits.keys()) == 2:
            for account in self.splits.keys():
                if account != main_account:
                    return str(account)
        return 'multiple'

    def get_display_strings_for_ledger(self, account):
        amount = self.splits[account]
        if amount < Decimal(0):
            #make negative amount display as positive
            withdrawal = str(amount * Decimal('-1'))
            deposit = ''
        else:
            withdrawal = ''
            deposit = str(amount)
        return {
                'txn_type': self.txn_type or '',
                'withdrawal': withdrawal,
                'deposit': deposit,
                'description': self.description or '',
                'txn_date': str(self.txn_date),
                'payee': self.payee or '',
                'status': self.status or '',
                'categories': self._categories_display(main_account=account),
            }

    def update_from_user_info(self, account=None, deposit=None, withdrawal=None, txn_date=None, txn_type=None, categories=None, payee=None, description=None, status=None):
        if deposit or withdrawal:
            splits = Transaction.splits_from_user_info(account, deposit, withdrawal, categories)
            self.splits = check_txn_splits(splits)
        if txn_date is not None:
            self.txn_date = self._check_txn_date(txn_date)
        if txn_type is not None:
            self.txn_type = txn_type
        if payee is not None:
            self.payee = payee
        if description is not None:
            self.description = description
        if status is not None:
            self.status = status


class Ledger:

    def __init__(self, account=None):
        if account is None:
            raise InvalidLedgerError('ledger must have an account')
        self.account = account
        self._txns = {}

    def __str__(self):
        return '%s ledger' % self.account.name

    def add_transaction(self, txn):
        if not txn.id:
            raise Exception('txn must have an id')
        self._txns[txn.id] = txn

    def _sort_txns(self, txns):
        return sorted(txns, key=lambda t: t.txn_date)

    def _add_balance_to_txns(self, txns):
        #txns must be sorted already
        txns_with_balance = []
        balance = Decimal(0)
        for t in txns:
            balance = balance + t.splits[self.account]
            t.balance = balance
            txns_with_balance.append(t)
        return txns_with_balance

    def get_sorted_txns_with_balance(self):
        sorted_txns = self._sort_txns(self._txns.values())
        return self._add_balance_to_txns(sorted_txns)

    def search(self, search_term):
        results = []
        search_term = search_term.lower()
        for t in self._txns.values():
            if t.payee and search_term in t.payee.lower():
                results.append(t)
            elif t.description and search_term in t.description.lower():
                results.append(t)
        return self._sort_txns(results)

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


class ScheduledTransactionFrequency(Enum):
    WEEKLY = 1
    MONTHLY = 2
    QUARTERLY = 3
    ANNUALLY = 4


class ScheduledTransaction:

    def __init__(self, name, frequency, next_due_date, splits, txn_type=None, payee=None, description=None):
        self.name = name
        if not isinstance(frequency, ScheduledTransactionFrequency):
            raise InvalidScheduledTransactionError('invalid frequency "%s"' % frequency)
        self.frequency = frequency
        self.next_due_date = self._check_date(next_due_date)
        self.splits = check_txn_splits(splits)
        self.txn_type = txn_type
        self.payee = payee
        self.description = description

    def _check_date(self, dt):
        try:
            return get_date(dt)
        except Exception:
            raise InvalidScheduledTransactionError('invalid date "%s"' % dt)


class Budget:
    '''Budget information that's entered by the user - no defaults or calculated values, but
    empty strings are dropped (so we can pass empty string from user form), and strings are converted
    Decimal values. Note: all accounts are passed in - if there's no budget info, it just has an empty {}.
    '''

    @staticmethod
    def round_percent_available(percent):
        return percent.quantize(Decimal('1.'), rounding=ROUND_HALF_UP)

    def __init__(self, year=None, start_date=None, end_date=None, account_budget_info=None, id_=None, income_spending_info=None):
        if start_date and end_date:
            self.start_date = get_date(start_date)
            self.end_date = get_date(end_date)
        elif year:
            self.start_date = date(int(year), 1, 1)
            self.end_date = date(int(year), 12, 31)
        else:
            raise BudgetError('must pass in dates')
        self._budget_data = {}
        for account, info in account_budget_info.items():
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
            self._budget_data[account] = keep_info
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
        for account, budget_info in self._budget_data.items():
            report_info = {}
            report_info.update(budget_info)
            report_info.update(self._income_spending_info.get(account, {}))
            if 'amount' in report_info:
                carryover = report_info.get('carryover', Decimal(0))
                income = report_info.get('income', Decimal(0))
                if account.type == AccountType.EXPENSE:
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
                if account.type == AccountType.EXPENSE:
                    report_info['percent_available'] = ''
                else:
                    report_info['percent'] = ''
            if account.type == AccountType.EXPENSE:
                if 'carryover' not in report_info:
                    report_info['carryover'] = ''
                if 'spent' not in report_info:
                    report_info['spent'] = ''
            if 'income' not in report_info:
                report_info['income'] = ''
            if account.type == AccountType.EXPENSE:
                report['expense'][account] = report_info
            else:
                report['income'][account] = report_info
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
        conn.execute('CREATE TABLE accounts (id INTEGER PRIMARY KEY, type INTEGER, user_id TEXT, name TEXT, parent_id INTEGER)')
        conn.execute('CREATE TABLE budgets (id INTEGER PRIMARY KEY, name TEXT, start_date TEXT, end_date TEXT)')
        conn.execute('CREATE TABLE budget_values (id INTEGER PRIMARY KEY, budget_id INTEGER, account_id INTEGER, amount TEXT, carryover TEXT, notes TEXT)')
        conn.execute('CREATE TABLE scheduled_transactions (id INTEGER PRIMARY KEY, name TEXT, frequency INTEGER, next_due_date TEXT, txn_type TEXT, payee TEXT, description TEXT)')
        conn.execute('CREATE TABLE scheduled_txn_splits (id INTEGER PRIMARY KEY, scheduled_txn_id INTEGER, account_id INTEGER, amount TEXT)')
        conn.execute('CREATE TABLE transactions (id INTEGER PRIMARY KEY, txn_type TEXT, txn_date TEXT, payee TEXT, description TEXT, status TEXT)')
        conn.execute('CREATE TABLE txn_splits (id INTEGER PRIMARY KEY, txn_id INTEGER, account_id INTEGER, amount TEXT)')

    def get_account(self, account_id):
        account_info = self._db_connection.execute('SELECT id, type, user_id, name, parent_id FROM accounts WHERE id = ?', (account_id,)).fetchone()
        if not account_info:
            raise Exception('no account with id "%s"' % account_id)
        parent = None
        if account_info[4]:
            parent = self.get_account(account_info[4])
        return Account(
                id_=account_info[0],
                type_=AccountType(account_info[1]),
                user_id=account_info[2],
                name=account_info[3],
                parent=parent,
            )

    def save_account(self, account):
        c = self._db_connection.cursor()
        parent_id = None
        if account.parent:
            if not account.parent.id:
                self.save_account(account.parent)
            parent_id = account.parent.id
        if account.id:
            c.execute('UPDATE accounts SET type = ?, user_id = ?, name = ?, parent_id = ? WHERE id = ?',
                    (account.type.value, account.user_id, account.name, parent_id, account.id))
        else:
            c.execute('INSERT INTO accounts(type, user_id, name, parent_id) VALUES(?, ?, ?, ?)', (account.type.value, account.user_id, account.name, parent_id))
            account.id = c.lastrowid
        self._db_connection.commit()

    def _get_accounts_by_type(self, type_):
        db_records = self._db_connection.execute('SELECT id FROM accounts WHERE type = ? ORDER BY id', (type_.value,)).fetchall()
        accounts = []
        for r in db_records:
            accounts.append(self.get_account(r[0]))
        return accounts

    def get_accounts(self, type_=None):
        if type_:
            return self._get_accounts_by_type(type_)
        else:
            accounts = []
            for type_ in [AccountType.ASSET, AccountType.LIABILITY, AccountType.INCOME, AccountType.EXPENSE, AccountType.EQUITY]:
                accounts.extend(self._get_accounts_by_type(type_))
            return accounts

    def _txn_from_db_record(self, db_info=None):
        if not db_info:
            raise InvalidTransactionError('no db_info to construct transaction')
        id_, txn_type, txn_date, payee, description, status = db_info
        txn_date = get_date(txn_date)
        cursor = self._db_connection.cursor()
        splits = {}
        split_records = cursor.execute('SELECT account_id, amount FROM txn_splits WHERE txn_id = ?', (id_,))
        if split_records:
            for split_record in split_records:
                account_id = split_record[0]
                account = self.get_account(account_id)
                splits[account] = split_record[1]
        return Transaction(splits=splits, txn_date=txn_date, txn_type=txn_type, payee=payee, description=description, status=status, id_=id_)

    def get_txn(self, txn_id):
        cursor = self._db_connection.cursor()
        cursor.execute('SELECT * FROM transactions WHERE id = ?', (txn_id,))
        db_info = cursor.fetchone()
        return self._txn_from_db_record(db_info=db_info)

    def save_txn(self, txn):
        c = self._db_connection.cursor()
        if txn.id:
            c.execute('UPDATE transactions SET txn_type = ?, txn_date = ?, payee = ?, description = ?, status = ? WHERE id = ?',
                (txn.txn_type, txn.txn_date.strftime('%Y-%m-%d'), txn.payee, txn.description, txn.status, txn.id))
        else:
            c.execute('INSERT INTO transactions(txn_type, txn_date, payee, description, status) VALUES(?, ?, ?, ?, ?)',
                (txn.txn_type, txn.txn_date.strftime('%Y-%m-%d'), txn.payee, txn.description, txn.status))
            txn.id = c.lastrowid
        #always delete any previous splits
        c.execute('DELETE FROM txn_splits WHERE txn_id = ?', (txn.id,))
        for account, amount in txn.splits.items():
            if not account.id:
                self.save_account(account)
            c.execute('INSERT INTO txn_splits(txn_id, account_id, amount) VALUES(?, ?, ?)', (txn.id, account.id, str(amount)))
        self._db_connection.commit()

    def delete_txn(self, txn_id):
        self._db_connection.execute('DELETE FROM txn_splits WHERE txn_id = ?', (txn_id,))
        self._db_connection.execute('DELETE FROM transactions WHERE id = ?', (txn_id,))
        self._db_connection.commit()

    def get_account_ledger(self, account):
        ledger = Ledger(account=account)
        db_txn_id_records = self._db_connection.execute('SELECT txn_id FROM txn_splits WHERE account_id = ?', (account.id,)).fetchall()
        txn_ids = set([r[0] for r in db_txn_id_records])
        for txn_id in txn_ids:
            txn = self.get_txn(txn_id)
            ledger.add_transaction(txn)
        return ledger

    def save_budget(self, budget):
        c = self._db_connection.cursor()
        if budget.id:
            #delete existing values, and then we'll add the current ones
            c.execute('DELETE FROM budget_values WHERE budget_id = ?', (budget.id,))
        else:
            c.execute('INSERT INTO budgets(start_date, end_date) VALUES(?, ?)', (budget.start_date, budget.end_date))
            budget.id = c.lastrowid
        for account, info in budget.get_budget_data().items():
            if info:
                if not account.id:
                    self.save_account(account)
                carryover = str(info.get('carryover', ''))
                notes = info.get('notes', '')
                values = (budget.id, account.id, str(info['amount']), carryover, notes)
                c.execute('INSERT INTO budget_values(budget_id, account_id, amount, carryover, notes) VALUES (?, ?, ?, ?, ?)', values)
        self._db_connection.commit()

    def get_budget(self, budget_id):
        c = self._db_connection.cursor()
        records = c.execute('SELECT start_date, end_date FROM budgets WHERE id = ?', (budget_id,)).fetchall()
        start_date = get_date(records[0][0])
        end_date = get_date(records[0][1])
        all_expense_budget_info = {}
        all_income_spending_info = {}
        income_and_expense_accounts = self.get_accounts(type_=AccountType.EXPENSE)
        income_and_expense_accounts.extend(self.get_accounts(type_=AccountType.INCOME))
        if not income_and_expense_accounts:
            raise Exception('found no income/expense accounts in DB')
        for account in income_and_expense_accounts:
            all_expense_budget_info[account] = {}
            all_income_spending_info[account] = {}
            #get spent & income values for each expense account
            spent = Decimal(0)
            income = Decimal(0)
            txn_splits_records = self._db_connection.execute('SELECT amount FROM txn_splits WHERE account_id = ?', (account.id,)).fetchall()
            for record in txn_splits_records:
                amt = Decimal(record[0])
                if account.type == AccountType.EXPENSE:
                    if amt < Decimal(0):
                        income += amt * Decimal(-1)
                    else:
                        spent += amt
            all_income_spending_info[account]['spent'] = spent
            all_income_spending_info[account]['income'] = income
            budget_records = c.execute('SELECT amount, carryover, notes FROM budget_values WHERE budget_id = ? AND account_id = ?', (budget_id, account.id)).fetchall()
            if budget_records:
                r = budget_records[0]
                all_expense_budget_info[account]['amount'] = Decimal(r[0])
                if r[1]:
                    all_expense_budget_info[account]['carryover'] = Decimal(r[1])
                else:
                    all_expense_budget_info[account]['carryover'] = Decimal(0)
                if r[2]:
                    all_expense_budget_info[account]['notes'] = r[2]
            else:
                all_expense_budget_info[account]['budget'] = Decimal(0)
                all_expense_budget_info[account]['carryover'] = Decimal(0)
        return Budget(id_=budget_id, start_date=start_date, end_date=end_date, account_budget_info=all_expense_budget_info,
                income_spending_info=all_income_spending_info)

    def get_budgets(self):
        budgets = []
        c = self._db_connection.cursor()
        budget_records = c.execute('SELECT id FROM budgets').fetchall()
        for budget_record in budget_records:
            budget_id = int(budget_records[0][0])
            budgets.append(self.get_budget(budget_id))
        return budgets

    def save_scheduled_transaction(self, scheduled_txn):
        c = self._db_connection.cursor()
        c.execute('INSERT INTO scheduled_transactions(name, frequency, next_due_date, txn_type, payee, description) VALUES (?, ?, ?, ?, ?, ?)',
            (scheduled_txn.name, scheduled_txn.frequency.value, scheduled_txn.next_due_date.strftime('%Y-%m-%d'), scheduled_txn.txn_type, scheduled_txn.payee, scheduled_txn.description))
        scheduled_txn.id = c.lastrowid
        for account, amount in scheduled_txn.splits.items():
            c.execute('INSERT INTO scheduled_txn_splits(scheduled_txn_id, account_id, amount) VALUES (?, ?, ?)', (scheduled_txn.id, account.id, str(amount)))
        self._db_connection.commit()

    def get_scheduled_transaction(self, id_):
        c = self._db_connection.cursor()
        splits = {}
        split_records = c.execute('SELECT account_id, amount FROM scheduled_txn_splits WHERE scheduled_txn_id = ?', (id_,))
        if split_records:
            for split_record in split_records:
                account_id = split_record[0]
                account = self.get_account(account_id)
                splits[account] = split_record[1]
        rows = c.execute('SELECT name,frequency,next_due_date,txn_type,payee,description FROM scheduled_transactions WHERE id = ?', (id_,)).fetchall()
        st = ScheduledTransaction(
                name=rows[0][0],
                frequency=ScheduledTransactionFrequency(rows[0][1]),
                next_due_date=rows[0][2],
                splits=splits,
                txn_type=rows[0][3],
                payee=rows[0][4],
                description=rows[0][5],
            )
        return st


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


GUI_FIELDS = {
        'type': {'column_number': 0, 'add_edit_column_number': 0, 'column_stretch': 1},
        'date': {'column_number': 1, 'add_edit_column_number': 1, 'column_stretch': 2},
        'payee': {'column_number': 2, 'add_edit_column_number': 2, 'column_stretch': 2},
        'description': {'column_number': 3, 'add_edit_column_number': 3, 'column_stretch': 2},
        'status': {'column_number': 4, 'add_edit_column_number': 4, 'column_stretch': 1},
        'withdrawal': {'column_number': 5, 'add_edit_column_number': 5, 'column_stretch': 2},
        'deposit': {'column_number': 6, 'add_edit_column_number': 6, 'column_stretch': 2},
        'balance': {'column_number': 7, 'add_edit_column_number': -1, 'column_stretch': 2},
        'categories': {'column_number': 8, 'add_edit_column_number': 7, 'column_stretch': 3},
        'buttons': {'column_number': -1, 'add_edit_column_number': 8, 'column_stretch': 2},
    }


ERROR_STYLE = '''QLineEdit {
    border: 2px solid red;
}'''


def set_widget_error_state(widget):
    widget.setStyleSheet(ERROR_STYLE)


ACCOUNTS_GUI_FIELDS = {
        'type': {'column_number': 0, 'column_stretch': 2},
        'user_id': {'column_number': 1, 'column_stretch': 1},
        'name': {'column_number': 2, 'column_stretch': 3},
        'parent': {'column_number': 3, 'column_stretch': 3},
        'buttons': {'column_number': 4, 'column_stretch': 3},
    }


class AccountsDisplay:

    def __init__(self, storage, reload_accounts):
        self.storage = storage
        self._reload = reload_accounts

    def _save_edit(self, acc_id):
        type_ = self.accounts_widgets[acc_id]['entries']['type'].currentData()
        user_id = self.accounts_widgets[acc_id]['entries']['user_id'].text()
        name = self.accounts_widgets[acc_id]['entries']['name'].text()
        parent = self.accounts_widgets[acc_id]['entries']['parent'].currentData()
        try:
            self.storage.save_account(Account(type_=type_, user_id=user_id, name=name, id_=acc_id, parent=parent))
            self._reload()
        except InvalidAccountNameError:
            set_widget_error_state(self.accounts_widgets[acc_id]['entries']['name'])

    def _edit(self, event, layout, acc_id):
        account = self.storage.get_account(acc_id)
        orig_user_id = self.accounts_widgets[acc_id]['labels']['user_id'].text()
        orig_name = self.accounts_widgets[acc_id]['labels']['name'].text()
        for label in self.accounts_widgets[acc_id]['labels'].values():
            layout.removeWidget(label)
            label.deleteLater()
        type_entry = QtWidgets.QComboBox()
        for index, account_type in enumerate(AccountType):
            type_entry.addItem(account_type.name, account_type)
            if account_type == account.type:
                type_entry.setCurrentIndex(index)
        user_id_entry = QtWidgets.QLineEdit()
        user_id_entry.setText(orig_user_id)
        name_entry = QtWidgets.QLineEdit()
        name_entry.setText(orig_name)
        parent_combo = QtWidgets.QComboBox()
        parent_combo.addItem('-----------', None)
        current_index = 0
        for acc_index, acc in enumerate(self.storage.get_accounts()):
            if account != acc:
                parent_combo.addItem(acc.name, acc)
            if account.parent == acc:
                current_index = acc_index + 1 #because index 0 is the blank '--------' value
        parent_combo.setCurrentIndex(current_index)
        row = self.accounts_widgets[acc_id]['row']
        layout.addWidget(type_entry, row, ACCOUNTS_GUI_FIELDS['type']['column_number'])
        layout.addWidget(user_id_entry, row, ACCOUNTS_GUI_FIELDS['user_id']['column_number'])
        layout.addWidget(name_entry, row, ACCOUNTS_GUI_FIELDS['name']['column_number'])
        layout.addWidget(parent_combo, row, ACCOUNTS_GUI_FIELDS['parent']['column_number'])

        save_button = QtWidgets.QPushButton('Save Edit')
        save_button.clicked.connect(partial(self._save_edit, acc_id=acc_id))
        layout.addWidget(save_button, row, ACCOUNTS_GUI_FIELDS['buttons']['column_number'])
        self.accounts_widgets[acc_id]['entries'] = {
                'type': type_entry,
                'user_id': user_id_entry,
                'name': name_entry,
                'parent': parent_combo,
            }
        self.accounts_widgets[acc_id]['buttons'] = {
                'save_edit': save_button,
            }

    def get_widget(self):
        main_widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        for field_info in ACCOUNTS_GUI_FIELDS.values():
            layout.setColumnStretch(field_info['column_number'], field_info['column_stretch'])
        row = 0
        layout.addWidget(QtWidgets.QLabel('Type'), row, ACCOUNTS_GUI_FIELDS['type']['column_number'])
        layout.addWidget(QtWidgets.QLabel('User ID'), row, ACCOUNTS_GUI_FIELDS['user_id']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Name'), row, ACCOUNTS_GUI_FIELDS['name']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Parent Account'), row, ACCOUNTS_GUI_FIELDS['parent']['column_number'])
        self.accounts_widgets = {}
        accounts = self.storage.get_accounts()
        row = 1
        accounts_widget = self._get_accounts_widget(self.accounts_widgets, accounts)
        layout.addWidget(accounts_widget, row, 0, 1, 5)
        row = 2
        self.add_account_widgets = {}
        self._show_add_account(layout, row, self.add_account_widgets, accounts)
        row = 3
        layout.addWidget(QtWidgets.QLabel(''), row, 0)
        layout.setRowStretch(row, 1)
        main_widget.setLayout(layout)
        return main_widget

    def _get_accounts_widget(self, accounts_widgets, accounts):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        for field_info in ACCOUNTS_GUI_FIELDS.values():
            layout.setColumnStretch(field_info['column_number'], field_info['column_stretch'])
        row = 0
        for acc in accounts:
            edit_function = partial(self._edit, layout=layout, acc_id=acc.id)
            type_label = QtWidgets.QLabel(acc.type.name)
            type_label.mousePressEvent = edit_function
            user_id_label = QtWidgets.QLabel(acc.user_id or '')
            user_id_label.mousePressEvent = edit_function
            name_label = QtWidgets.QLabel(acc.name)
            name_label.mousePressEvent = edit_function
            parent = acc.parent or ''
            parent_label = QtWidgets.QLabel(str(parent))
            parent_label.mousePressEvent = edit_function
            empty_label = QtWidgets.QLabel('')
            empty_label.mousePressEvent = edit_function
            layout.addWidget(type_label, row, ACCOUNTS_GUI_FIELDS['type']['column_number'])
            layout.addWidget(user_id_label, row, ACCOUNTS_GUI_FIELDS['user_id']['column_number'])
            layout.addWidget(name_label, row, ACCOUNTS_GUI_FIELDS['name']['column_number'])
            layout.addWidget(parent_label, row, ACCOUNTS_GUI_FIELDS['parent']['column_number'])
            layout.addWidget(empty_label, row, ACCOUNTS_GUI_FIELDS['buttons']['column_number'])
            accounts_widgets[acc.id] = {
                    'row': row,
                    'labels': {
                        'type_label': type_label,
                        'user_id': user_id_label,
                        'name': name_label,
                        'parent': parent_label,
                        'empty': empty_label,
                    },
                }
            row += 1
        widget.setLayout(layout)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        return scroll

    def _show_add_account(self, layout, row, add_account_widgets, all_accounts):
        add_account_type = QtWidgets.QComboBox()
        for account_type in AccountType:
            add_account_type.addItem(account_type.name, account_type)
        layout.addWidget(add_account_type, row, ACCOUNTS_GUI_FIELDS['type']['column_number'])
        add_account_user_id = QtWidgets.QLineEdit()
        layout.addWidget(add_account_user_id, row, ACCOUNTS_GUI_FIELDS['user_id']['column_number'])
        add_account_name = QtWidgets.QLineEdit()
        layout.addWidget(add_account_name, row, ACCOUNTS_GUI_FIELDS['name']['column_number'])
        parent_combo = QtWidgets.QComboBox()
        parent_combo.addItem('---------', None)
        for account in all_accounts:
            parent_combo.addItem(account.name, account)
        layout.addWidget(parent_combo, row, ACCOUNTS_GUI_FIELDS['parent']['column_number'])
        button = QtWidgets.QPushButton('Add New')
        button.clicked.connect(self._save_new_account)
        layout.addWidget(button, row, ACCOUNTS_GUI_FIELDS['buttons']['column_number'])
        add_account_widgets['entries'] = {
                'type': add_account_type,
                'user_id': add_account_user_id,
                'name': add_account_name,
                'parent': parent_combo,
            }
        add_account_widgets['buttons'] = {'add_new': button}

    def _save_new_account(self):
        type_ = self.add_account_widgets['entries']['type'].currentData()
        user_id = self.add_account_widgets['entries']['user_id'].text()
        name = self.add_account_widgets['entries']['name'].text()
        parent = self.add_account_widgets['entries']['parent'].currentData()
        try:
            account = Account(type_=type_, user_id=user_id, name=name, parent=parent)
            self.storage.save_account(account)
            self._reload()
        except InvalidAccountNameError:
            set_widget_error_state(self.add_account_widgets['entries']['name'])


def set_ledger_column_widths(layout):
    for field_info in GUI_FIELDS.values():
        if field_info['column_number'] >= 0:
            layout.setColumnStretch(field_info['column_number'], field_info['column_stretch'])


class SplitTransactionEditor:

    def __init__(self, all_accounts, initial_txn_splits):
        self._all_accounts = all_accounts
        self._initial_txn_splits = initial_txn_splits
        self._final_txn_splits = {}
        self._entries = {}

    def _get_txn_splits(self, split_editor):
        for value in self._entries.values():
            #value is amount_entry, account
            text = value[0].text()
            if text:
                self._final_txn_splits[value[1]] = text
        split_editor.accept()

    def _show_split_editor(self):
        split_editor = QtWidgets.QDialog()
        layout = QtWidgets.QGridLayout()
        row = 0
        for account in self._all_accounts:
            layout.addWidget(QtWidgets.QLabel(account.name), row, 0)
            amount_entry = QtWidgets.QLineEdit()
            for acc, amt in self._initial_txn_splits.items():
                if acc == account:
                    amount_entry.setText(str(amt))
            self._entries[account.id] = (amount_entry, account)
            layout.addWidget(amount_entry, row, 1)
            row += 1
        ok_button = QtWidgets.QPushButton('Done')
        ok_button.clicked.connect(partial(self._get_txn_splits, split_editor=split_editor))
        cancel_button = QtWidgets.QPushButton('Cancel')
        cancel_button.clicked.connect(split_editor.reject)
        layout.addWidget(ok_button, row, 0)
        layout.addWidget(cancel_button, row, 1)
        split_editor.setLayout(layout)
        split_editor.exec_()

    def get_txn_splits(self):
        self._show_split_editor()
        return self._final_txn_splits


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
        index = 0 #initialize in case there are no txns in the ledger
        for index, txn in enumerate(self.ledger.get_sorted_txns_with_balance()):
            if (txn.id not in self.txn_display_data) or (self.txn_display_data[txn.id]['row'] != index):
                self._display_txn(txn, row=index, layout=self.txns_layout)
            else:
                try:
                    if self.txn_display_data[txn.id]['widgets']['labels']['balance'].text() != txn.balance:
                        self._display_txn(txn, row=index, layout=self.txns_layout)
                except KeyError:
                    pass
        self.txns_layout.addWidget(QtWidgets.QLabel(''), index+1, 0)
        self.txns_layout.setRowStretch(index+1, 1)

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
        withdrawal = entries['withdrawal'].text()
        deposit = entries['deposit'].text()
        description = entries['description'].text()
        status = entries['status'].text()
        categories = self.txn_display_data[txn_id]['accounts_display'].get_categories()
        txn = self.ledger.get_txn(txn_id)
        txn.update_from_user_info(
                account=self.ledger.account,
                txn_type=txn_type,
                txn_date=txn_date,
                payee=payee,
                withdrawal=withdrawal,
                deposit=deposit,
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
        txn_accounts_display = TxnAccountsDisplay(self.storage, main_account=self.ledger.account, txn=txn)
        status_entry = QtWidgets.QLineEdit()
        status_entry.setText(widgets['labels']['status'].text())
        deposit_entry = QtWidgets.QLineEdit()
        deposit_entry.setText(widgets['labels']['deposit'].text())
        withdrawal_entry = QtWidgets.QLineEdit()
        withdrawal_entry.setText(widgets['labels']['withdrawal'].text())
        for widget in self.txn_display_data[txn_id]['widgets']['labels'].values():
            layout.removeWidget(widget)
            widget.deleteLater()
        self.txn_display_data[txn_id]['widgets']['labels'] = {}
        layout.addWidget(type_entry, row, GUI_FIELDS['type']['add_edit_column_number'])
        layout.addWidget(date_entry, row, GUI_FIELDS['date']['add_edit_column_number'])
        layout.addWidget(payee_entry, row, GUI_FIELDS['payee']['add_edit_column_number'])
        layout.addWidget(description_entry, row, GUI_FIELDS['description']['add_edit_column_number'])
        layout.addWidget(txn_accounts_display.get_widget(), row, GUI_FIELDS['categories']['add_edit_column_number'])
        layout.addWidget(status_entry, row, GUI_FIELDS['status']['add_edit_column_number'])
        layout.addWidget(withdrawal_entry, row, GUI_FIELDS['withdrawal']['add_edit_column_number'])
        layout.addWidget(deposit_entry, row, GUI_FIELDS['deposit']['add_edit_column_number'])
        save_edit_button = QtWidgets.QPushButton('Save Edit')
        save_edit_button.clicked.connect(partial(self._save_edit, txn_id=txn_id, layout=layout))
        delete_button = QtWidgets.QPushButton('Delete')
        delete_button.clicked.connect(partial(self._delete, txn_id=txn_id, layout=layout, txn_widgets=self.txn_display_data[txn_id]['widgets']))
        buttons_layout = QtWidgets.QGridLayout()
        buttons_layout.addWidget(save_edit_button, 0, 0)
        buttons_layout.addWidget(delete_button, 1, 0)
        buttons_widget = QtWidgets.QWidget()
        buttons_widget.setLayout(buttons_layout)
        layout.addWidget(buttons_widget, row, GUI_FIELDS['buttons']['add_edit_column_number'])
        self.txn_display_data[txn_id]['widgets']['entries'] = {
                'type': type_entry,
                'date': date_entry,
                'payee': payee_entry,
                'description': description_entry,
                'categories': txn_accounts_display.get_widget(),
                'status': status_entry,
                'deposit': deposit_entry,
                'withdrawal': withdrawal_entry,
            }
        self.txn_display_data[txn_id]['widgets']['buttons'] = {
                'save_edit': save_edit_button,
                'delete': delete_button,
            }
        self.txn_display_data[txn_id]['accounts_display'] = txn_accounts_display

    def _display_txn(self, txn, row, layout):
        #clear labels if this txn was already displayed, create new labels, add them to layout, and set txn_display_data
        if txn.id in self.txn_display_data:
            for widget in self.txn_display_data[txn.id]['widgets']['labels'].values():
                layout.removeWidget(widget)
                widget.deleteLater()
        tds = txn.get_display_strings_for_ledger(self.ledger.account)
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
        deposit_label = QtWidgets.QLabel(tds['deposit'])
        deposit_label.mousePressEvent = edit_function
        withdrawal_label = QtWidgets.QLabel(tds['withdrawal'])
        withdrawal_label.mousePressEvent = edit_function
        balance_label = QtWidgets.QLabel(str(txn.balance))
        balance_label.mousePressEvent = edit_function
        layout.addWidget(type_label, row, GUI_FIELDS['type']['column_number'])
        layout.addWidget(date_label, row, GUI_FIELDS['date']['column_number'])
        layout.addWidget(payee_label, row, GUI_FIELDS['payee']['column_number'])
        layout.addWidget(description_label, row, GUI_FIELDS['description']['column_number'])
        layout.addWidget(categories_label, row, GUI_FIELDS['categories']['column_number'])
        layout.addWidget(status_label, row, GUI_FIELDS['status']['column_number'])
        layout.addWidget(withdrawal_label, row, GUI_FIELDS['withdrawal']['column_number'])
        layout.addWidget(deposit_label, row, GUI_FIELDS['deposit']['column_number'])
        layout.addWidget(balance_label, row, GUI_FIELDS['balance']['column_number'])
        self.txn_display_data[txn.id] = {
                'widgets': {
                    'labels': {
                        'type': type_label,
                        'date': date_label,
                        'payee': payee_label,
                        'description': description_label,
                        'categories': categories_label,
                        'status': status_label,
                        'deposit': deposit_label,
                        'withdrawal': withdrawal_label,
                        'balance': balance_label
                    }
                },
                'row': row,
                'txn': txn,
            }


def get_new_txn_splits(accounts, initial_txn_splits):
    editor = SplitTransactionEditor(accounts, initial_txn_splits)
    return editor.get_txn_splits()


class TxnAccountsDisplay:

    def __init__(self, storage, main_account=None, txn=None):
        self._storage = storage
        self._main_account = main_account
        self._txn = txn
        layout = QtWidgets.QGridLayout()
        self._categories_combo = QtWidgets.QComboBox()
        self._categories_combo.addItem('---------', None)
        current_index = 0
        index = 0
        accounts = []
        for type_ in [AccountType.EXPENSE, AccountType.INCOME, AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY]:
            accounts.extend(self._storage.get_accounts(type_=type_))
        for account in accounts:
            if account != self._main_account:
                #find correct account in the list if txn has just two splits
                if txn and len(txn.splits.keys()) == 2:
                    if account in txn.splits:
                        current_index = index + 1
                self._categories_combo.addItem(account.name, account)
                index += 1
        self._multiple_entry_index = index + 1
        current_categories = []
        if txn and len(txn.splits.keys()) > 2:
            current_categories = txn.splits
            current_index = self._multiple_entry_index
        self._categories_combo.addItem('multiple', current_categories)
        self._categories_combo.setCurrentIndex(current_index)
        layout.addWidget(self._categories_combo, 0, 0)
        self.split_button = QtWidgets.QPushButton('Split')
        txn_id = None
        if txn:
            txn_id = txn.id
        self.split_button.clicked.connect(self._split_transactions)
        layout.addWidget(self.split_button)
        self._widget = QtWidgets.QWidget()
        self._widget.setLayout(layout)

    def _split_transactions(self):
        initial_txn_splits = {}
        if self._txn:
            initial_txn_splits = self._txn.splits
        accounts = self._storage.get_accounts()
        txn_splits = get_new_txn_splits(accounts, initial_txn_splits)
        self._categories_combo.setCurrentIndex(self._multiple_entry_index)
        self._categories_combo.setItemData(self._multiple_entry_index, txn_splits)

    def get_categories(self):
        splits = self._categories_combo.currentData()
        #remove main account split (if present), because that comes from withdrawal/deposit fields
        if isinstance(splits, dict):
            splits.pop(self._main_account, None)
        return splits

    def get_widget(self):
        return self._widget


class LedgerDisplay:

    def __init__(self, storage, show_ledger, current_account=None):
        self.storage = storage
        self._show_ledger = show_ledger
        if not current_account:
            current_account = storage.get_accounts(type_=AccountType.ASSET)[0]
        self._current_account = current_account

    def get_widget(self):
        self.widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        set_ledger_column_widths(layout)
        new_row = self._show_headings(layout, row=0)
        self.ledger = self.storage.get_account_ledger(account=self._current_account)
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
        accounts = self.storage.get_accounts(type_=AccountType.ASSET)
        accounts.extend(self.storage.get_accounts(type_=AccountType.LIABILITY))
        for index, a in enumerate(accounts):
            if a.id == self._current_account.id:
                current_index = index
            self.action_combo.addItem(a.name)
        self.action_combo.setCurrentIndex(current_index)
        self.action_combo.currentIndexChanged.connect(self._update_account)
        layout.addWidget(self.action_combo, row, 0)
        row += 1
        layout.addWidget(QtWidgets.QLabel('Type'), row, GUI_FIELDS['type']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Date'), row, GUI_FIELDS['date']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Payee'), row, GUI_FIELDS['payee']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Description'), row, GUI_FIELDS['description']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Categories'), row, GUI_FIELDS['categories']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Status'), row, GUI_FIELDS['status']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Withdrawal (-)'), row, GUI_FIELDS['withdrawal']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Deposit (+)'), row, GUI_FIELDS['deposit']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Balance'), row, GUI_FIELDS['balance']['column_number'])
        return row + 1

    def _show_add_txn(self, layout, add_txn_widgets, payees, row):
        entry_names = ['type', 'date']
        for entry_name in entry_names:
            entry = QtWidgets.QLineEdit()
            add_txn_widgets['entries'][entry_name] = entry
            layout.addWidget(entry, row, GUI_FIELDS[entry_name]['add_edit_column_number'])
        payee_entry = QtWidgets.QComboBox()
        payee_entry.setEditable(True)
        payee_entry.addItem('')
        for payee in payees:
            payee_entry.addItem(payee)
        add_txn_widgets['payee'] = payee_entry
        layout.addWidget(payee_entry, row, GUI_FIELDS['payee']['add_edit_column_number'])
        description_entry = QtWidgets.QLineEdit()
        add_txn_widgets['entries']['description'] = description_entry
        layout.addWidget(description_entry, row, GUI_FIELDS['description']['add_edit_column_number'])
        txn_accounts_display = TxnAccountsDisplay(self.storage, main_account=self._current_account)
        layout.addWidget(txn_accounts_display.get_widget(), row, GUI_FIELDS['categories']['add_edit_column_number'])
        add_txn_widgets['accounts_display'] = txn_accounts_display
        entry_names = ['status', 'withdrawal', 'deposit']
        column_index = 5
        for entry_name in entry_names:
            entry = QtWidgets.QLineEdit()
            add_txn_widgets['entries'][entry_name] = entry
            layout.addWidget(entry, row, GUI_FIELDS[entry_name]['add_edit_column_number'])
            column_index += 1
        add_new_button = QtWidgets.QPushButton('Add New')
        add_new_button.clicked.connect(self._save_new_txn)
        add_txn_widgets['buttons']['add_new'] = add_new_button
        layout.addWidget(add_new_button, row, GUI_FIELDS['buttons']['add_edit_column_number'])

    def _save_new_txn(self):
        txn_type = self.add_txn_widgets['entries']['type'].text()
        txn_date = self.add_txn_widgets['entries']['date'].text()
        payee = self.add_txn_widgets['payee'].currentText()
        description = self.add_txn_widgets['entries']['description'].text()
        categories = self.add_txn_widgets['accounts_display'].get_categories()
        status = self.add_txn_widgets['entries']['status'].text()
        deposit = self.add_txn_widgets['entries']['deposit'].text()
        withdrawal = self.add_txn_widgets['entries']['withdrawal'].text()
        txn = Transaction.from_user_info(
                account=self._current_account,
                txn_type=txn_type,
                deposit=deposit,
                withdrawal=withdrawal,
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


class BudgetDisplay:

    def __init__(self, budget, storage, reload_budget):
        self.budget = budget
        self.storage = storage
        self.reload_budget = reload_budget

    def get_widget(self):
        self.main_widget = QtWidgets.QWidget()
        self.layout = QtWidgets.QGridLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
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
        for account, info in budget_report['income'].items():
            self.layout.addWidget(QtWidgets.QLabel(account.name), row_index, 0)
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
            row_data['account'] = account
            self.data[account.id] = row_data
            row_index += 1
        for account, info in budget_report['expense'].items():
            self.layout.addWidget(QtWidgets.QLabel(account.name), row_index, 0)
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
            row_data['account'] = account
            self.data[account.id] = row_data
            row_index += 1
        self.button_row_index = row_index
        self._edit_button = QtWidgets.QPushButton('Edit')
        self._edit_button.clicked.connect(self._edit)
        self.layout.addWidget(self._edit_button, self.button_row_index, 0)
        self.layout.addWidget(QtWidgets.QLabel(''), row_index+1, 0)
        self.layout.setRowStretch(row_index+1, 1)
        self.main_widget.setLayout(self.layout)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.main_widget)
        return scroll

    def _save(self):
        account_budget_info = {}
        for acc_id, info in self.data.items():
            account = info['account']
            account_budget_info[account] = {
                    'amount': info['budget_entry'].text(),
                    'carryover': info['carryover_entry'].text()
                }
        b = Budget(id_=self.budget.id, start_date=self.budget.start_date, end_date=self.budget.end_date, account_budget_info=account_budget_info)
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
        self.parent_window = QtWidgets.QWidget()
        self.parent_window.setWindowTitle(TITLE)
        self.parent_layout = QtWidgets.QGridLayout()
        self.parent_layout.setContentsMargins(4, 4, 4, 4)
        self.parent_window.setLayout(self.parent_layout)

        self.content_area = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QGridLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
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
        self.budget_button.setEnabled(True)
        if display == 'accounts':
            self.accounts_button.setEnabled(False)
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
        self.budget_button = QtWidgets.QPushButton('Budget')
        self.budget_button.clicked.connect(self._show_budget)
        layout.addWidget(self.budget_button, 0, 4)
        if not file_loaded:
            self.accounts_button.setEnabled(False)
            self.ledger_button.setEnabled(False)
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

    def _show_budget(self):
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self._update_action_buttons(display='budget')
        budgets = self.storage.get_budgets()
        self.budget_display = BudgetDisplay(budgets[0], self.storage, self._show_budget)
        self.main_widget = self.budget_display.get_widget()
        self.content_layout.addWidget(self.main_widget, 0, 0)


def _list_accounts(storage):
    for a in storage.get_accounts():
        print('%s - %s' % (a.id, a.name))


def _get_account(storage):
    acc_id = input('enter account ID: ')
    return storage.get_account(acc_id)


def run_cli(file_name):
    banner = 'Command-line PFT'
    storage = SQLiteStorage(file_name)
    local = {
        'storage': storage,
        'list_accounts': partial(_list_accounts, storage=storage),
        'get_account': partial(_get_account, storage=storage),
    }
    import code
    code.interact(banner=banner, local=local)


def parse_args():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--install_qt', dest='install_qt', action='store_true')
    parser.add_argument('-f', '--file_name', dest='file_name')
    parser.add_argument('--cli', dest='cli', action='store_true')
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    args = parse_args()
    if args.install_qt:
        _do_qt_install()
        sys.exit(0)

    if args.cli:
        run_cli(args.file_name)
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

