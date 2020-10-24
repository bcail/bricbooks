'''
Architecture:
    Inner Layer - Account, Category, Transaction, Ledger, ... classes. They know nothing about the storage or UI.
    Middle Layer - SQLiteStorage (or another storage class). Knows about inner layer objects, but not the UI.
    Outer Layer - UI (Qt, console). Knows about storage layer and inner objects.
    No objects should use private/hidden members of other objects.
'''
from collections import namedtuple
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from functools import partial
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
try:
    import readline
except ImportError:
    readline = None


TITLE = 'bricbooks'
PYSIDE2_VERSION = '5.14.0'
CUR_DIR = Path(__file__).parent.resolve()


class AccountType(Enum):
    ASSET = 0
    LIABILITY = 1
    EQUITY = 2
    INCOME = 3
    EXPENSE = 4


def _do_qt_install():
    cmd = [sys.executable, '-m', 'pip', 'install', 'PySide2==%s' % PYSIDE2_VERSION]
    print('installing Qt for Python (PySide2): %s' % ' '.join(cmd))
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
    else:
        print('Exiting.')
        sys.exit(0)


try:
    from PySide2 import QtWidgets
except ImportError:
    pass


class InvalidAccountError(RuntimeError):
    pass

class InvalidAccountNameError(InvalidAccountError):
    pass

class InvalidPayeeError(RuntimeError):
    pass

class InvalidDecimalAmount(RuntimeError):
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
        try:
            year, month, day = val.split('-')
            return date(int(year), int(month), int(day))
        except ValueError:
            month, day, year = val.split('/')
            return date(int(year), int(month), int(day))
    if isinstance(val, date):
        return val
    raise RuntimeError('invalid date %s' % val)


def get_files(directory):
    d = Path(directory)
    return d.glob('*.sqlite3')


def increment_month(date_obj):
    if date_obj.month == 12:
        return date(date_obj.year + 1, 1, date_obj.day)
    if date_obj.month == 1 and date_obj.day > 28:
        return date(date_obj.year, 2, 28)
    if date_obj.day == 31 and date_obj.month in [3, 5, 8, 10]:
        return date(date_obj.year, date_obj.month+1, 30)
    return date(date_obj.year, date_obj.month+1, date_obj.day)


def increment_quarter(date_obj):
    if date_obj.day == 31 and date_obj.month in [1, 3, 8]:
        day = 30
    elif date_obj.day > 28 and date_obj.month == 11:
        day = 28
    else:
        day = date_obj.day
    if date_obj.month == 10:
        month = 1
    elif date_obj.month == 11:
        month = 2
    elif date_obj.month == 12:
        month = 3
    else:
        month = date_obj.month + 3
    if date_obj.month in [10, 11, 12]:
        year = date_obj.year + 1
    else:
        year = date_obj.year
    return date(year, month, day)


def increment_year(date_obj):
    return date(date_obj.year+1, date_obj.month, date_obj.day)


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
        if isinstance(type_, AccountType):
            return type_
        else:
            try:
                return AccountType(int(type_))
            except ValueError:
                raise InvalidAccountError('Invalid account type "%s"' % type_)


class Payee:

    def __init__(self, name, notes=None, id_=None):
        if not name:
            raise Exception('must pass in a payee name')
        self.name = name
        self.notes = notes
        self.id = id_

    def __eq__(self, other_payee):
        if not other_payee:
            return False
        if self.id and other_payee.id:
            return self.id == other_payee.id
        else:
            raise InvalidPayeeError("Can't compare payees without an id")

    def __hash__(self):
        return self.id


def get_decimal_amount(value):
    decimal_value = None
    if isinstance(value, Decimal):
        decimal_value = value
    elif isinstance(value, (int, str)):
        try:
            decimal_value = Decimal(value)
        except InvalidOperation:
            raise InvalidDecimalAmount('bad decimal value: %s' % value)
    else:
        raise InvalidDecimalAmount('bad decimal value: %s' % value)
    decimal_value_str = str(decimal_value)
    if '.' in decimal_value_str:
        _, decimals = decimal_value_str.split('.')
        if len(decimals) > 2:
            raise InvalidDecimalAmount('no fractions of cents allowed: %s' % value)
    return decimal_value


def check_txn_splits(input_splits):
    if not input_splits or len(input_splits.items()) < 2:
        raise InvalidTransactionError('transaction must have at least 2 splits')
    splits = {}
    total = Decimal(0)
    for account, amount in input_splits.items():
        if not account:
            raise InvalidTransactionError('must have a valid account in splits')
        try:
            decimal_amount = get_decimal_amount(amount)
        except InvalidDecimalAmount as e:
            raise InvalidTransactionError('invalid split: %s' % e)
        #check for fractions of cents
        amt_str = str(decimal_amount)
        total += decimal_amount
        splits[account] = decimal_amount
    if total != Decimal(0):
        raise InvalidTransactionError("splits don't balance")
    return splits


class Transaction:

    CLEARED = 'C'
    RECONCILED = 'R'

    @staticmethod
    def handle_status(status):
        if status:
            if status.upper() == Transaction.CLEARED:
                return Transaction.CLEARED
            elif status.upper() == Transaction.RECONCILED:
                return Transaction.RECONCILED
            else:
                raise InvalidTransactionError('invalid status "%s"' % status)
        else:
            return None

    @staticmethod
    def splits_from_user_info(account, deposit, withdrawal, input_categories):
        splits = {}
        categories = {}
        try:
            amount = get_decimal_amount(deposit or withdrawal)
        except InvalidDecimalAmount as e:
            raise InvalidTransactionError('invalid deposit/withdrawal: %s' % e)
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
    def from_user_info(account, deposit, withdrawal, txn_date, txn_type, categories, payee, description, status, id_=None):
        splits = Transaction.splits_from_user_info(account, deposit, withdrawal, categories)
        return Transaction(
                splits=splits,
                txn_date=txn_date,
                txn_type=txn_type,
                payee=payee,
                description=description,
                status=status,
                id_=id_
            )

    def __init__(self, txn_date=None, txn_type=None, splits=None, payee=None, description=None, status=None, id_=None):
        self.splits = check_txn_splits(splits)
        self.txn_date = self._check_txn_date(txn_date)
        self.txn_type = txn_type
        if payee:
            if isinstance(payee, str):
                self.payee = Payee(name=payee)
            elif isinstance(payee, Payee):
                self.payee = payee
            else:
                raise InvalidTransactionError('invalid payee: %s' % payee)
        else:
            self.payee = None
        self.description = description
        self.status = Transaction.handle_status(status)
        self.id = id_

    def __str__(self):
        return '%s: %s' % (self.id, self.txn_date)

    def __repr__(self):
        return self.__str__()

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


def _categories_display(splits, main_account):
    if len(splits.keys()) == 2:
        for account in splits.keys():
            if account != main_account:
                return str(account)
    return 'multiple'


def get_display_strings_for_ledger(account, txn):
    '''txn can be either Transaction or ScheduledTransaction'''
    amount = txn.splits[account]
    if amount < Decimal(0):
        #make negative amount display as positive
        withdrawal = str(amount * Decimal('-1'))
        deposit = ''
    else:
        withdrawal = ''
        deposit = str(amount)
    if txn.payee:
        payee = txn.payee.name
    else:
        payee = ''
    display_strings = {
            'txn_type': txn.txn_type or '',
            'withdrawal': withdrawal,
            'deposit': deposit,
            'description': txn.description or '',
            'payee': payee,
            'categories': _categories_display(splits=txn.splits, main_account=account),
        }
    if isinstance(txn, ScheduledTransaction):
        display_strings['name'] = txn.name
        display_strings['next_due_date'] = str(txn.next_due_date)
        display_strings['frequency'] = str(txn.frequency)
        display_strings['txn_date'] = str(date.today())
    else:
        display_strings['status'] = txn.status or ''
        display_strings['txn_date'] = str(txn.txn_date)
    return display_strings


LedgerBalances = namedtuple('LedgerBalances', ['current', 'current_cleared'])


class Ledger:

    def __init__(self, account=None):
        if account is None:
            raise InvalidLedgerError('ledger must have an account')
        self.account = account
        self._txns = {}
        self._scheduled_txns = {}

    def __str__(self):
        return '%s ledger' % self.account.name

    def add_transaction(self, txn):
        if not txn.id:
            raise Exception('txn must have an id')
        self._txns[txn.id] = txn

    def add_scheduled_transaction(self, scheduled_txn):
        self._scheduled_txns[scheduled_txn.id] = scheduled_txn

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
            if t.payee and search_term in t.payee.name.lower():
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

    def get_current_balances(self):
        sorted_txns = self.get_sorted_txns_with_balance()
        current = Decimal(0)
        current_cleared = Decimal(0)
        today = date.today()
        for t in sorted_txns:
            if t.txn_date <= today:
                current = t.balance
                if t.status == Transaction.CLEARED:
                    current_cleared = current_cleared + t.splits[self.account]
        return LedgerBalances(current=current, current_cleared=current_cleared)

    def get_payees(self):
        payees = set()
        for txn in self._txns.values():
            if txn.payee:
                payees.add(txn.payee)
        return sorted(list(payees), key=lambda p: p.name)

    def get_scheduled_transactions_due(self):
        all_scheduled_txns = list(self._scheduled_txns.values())
        return [t for t in all_scheduled_txns if t.is_due()]


class ScheduledTransactionFrequency(Enum):
    WEEKLY = 1
    MONTHLY = 2
    QUARTERLY = 3
    ANNUALLY = 4


class ScheduledTransaction:

    @staticmethod
    def from_user_info(name, frequency, next_due_date, account, deposit, withdrawal, txn_date, txn_type, categories, payee, description, id_=None):
        splits = Transaction.splits_from_user_info(account, deposit, withdrawal, categories)
        return ScheduledTransaction(
                name=name,
                frequency=frequency,
                next_due_date=next_due_date,
                splits=splits,
                txn_type=txn_type,
                payee=payee,
                description=description,
                id_=id_
            )

    def __init__(self, name, frequency, next_due_date, splits, txn_type=None, payee=None, description=None, status=None, id_=None):
        self.name = name
        if isinstance(frequency, ScheduledTransactionFrequency):
            self.frequency = frequency
        else:
            try:
                self.frequency = ScheduledTransactionFrequency(int(frequency))
            except ValueError:
                raise InvalidScheduledTransactionError('invalid frequency "%s"' % frequency)
        self.next_due_date = self._check_date(next_due_date)
        self.splits = check_txn_splits(splits)
        self.txn_type = txn_type
        self.payee = payee
        self.description = description
        self.status = Transaction.handle_status(status)
        self.id = id_

    def __str__(self):
        return '%s: %s (%s %s) (%s)' % (self.id, self.name, self.frequency, self.next_due_date, self.splits)

    def _check_date(self, dt):
        try:
            return get_date(dt)
        except Exception:
            raise InvalidScheduledTransactionError('invalid date "%s"' % dt)

    def is_due(self):
        if self.next_due_date <= date.today():
            return True
        return False

    def next_txn_entered(self):
        #update next_due_date since the txn has been entered
        if self.frequency == ScheduledTransactionFrequency.WEEKLY:
            self.next_due_date = self.next_due_date + timedelta(days=7)
        elif self.frequency == ScheduledTransactionFrequency.MONTHLY:
            self.next_due_date = increment_month(self.next_due_date)
        elif self.frequency == ScheduledTransactionFrequency.QUARTERLY:
            self.next_due_date = increment_quarter(self.next_due_date)
        elif self.frequency == ScheduledTransactionFrequency.ANNUALLY:
            self.next_due_date = increment_year(self.next_due_date)
        else:
            raise Exception('invalid frequency %s' % self.frequency)


class Budget:
    '''Budget information that's entered by the user - no defaults or calculated values, but
    empty strings are dropped (so we can pass empty string from user form), and strings are converted
    Decimal values. Note: all accounts are passed in - if there's no budget info, it just has an empty {}.
    '''

    @staticmethod
    def round_percent_available(percent):
        return percent.quantize(Decimal('1.'), rounding=ROUND_HALF_UP)

    def __init__(self, year=None, start_date=None, end_date=None, name=None, account_budget_info=None, id_=None, income_spending_info=None):
        if start_date and end_date:
            self.start_date = get_date(start_date)
            self.end_date = get_date(end_date)
        elif year:
            self.start_date = date(int(year), 1, 1)
            self.end_date = date(int(year), 12, 31)
        else:
            raise BudgetError('must pass in dates')
        self.name = name
        self._budget_data = {}
        if account_budget_info:
            for account, info in account_budget_info.items():
                keep_info = {}
                for key, value in info.items():
                    if key in ['amount', 'carryover']:
                        if isinstance(value, Decimal):
                            keep_info[key] = value
                        elif not value:
                            continue
                        else:
                            try:
                                keep_info[key] = get_decimal_amount(value)
                            except InvalidDecimalAmount as e:
                                raise BudgetError('invalid budget amount: %s' % e)
                    elif key == 'notes':
                        if value:
                            keep_info[key] = value
                    else:
                        raise BudgetError('invalid budget info: %s' % info)
                self._budget_data[account] = keep_info
        self.id = id_
        self._income_spending_info = income_spending_info

    def __str__(self):
        if self.name:
            return '%s: %s (%s - %s)' % (self.id, self.name, self.start_date, self.end_date)
        else:
            return '%s: %s - %s' % (self.id, self.start_date, self.end_date)

    def __eq__(self, other_budget):
        if not other_budget:
            return False
        if self.id and other_budget.id:
            return self.id == other_budget.id
        else:
            raise BudgetError("Can't compare budgets without an id")

    def get_budget_data(self):
        '''returns {account1: {'amount': xxx}, account2: {}, ...}'''
        return self._budget_data

    def get_report_display(self):
        '''adds income & spending data to budget data, & converts to strings, for a budget report to display
        { 'expense': {
                expense_account1: {'amount': '10', 'income': '5', 'carryover': '5', 'total_budget': '20', 'spent': '10', 'remaining': '10', 'percent_available': '50%', 'notes': 'note1'},
                expense_account2: {'amount': '5', 'total_budget': '5', 'remaining': '5', 'percent_available': '100%'},
                expense_account3: {},
            },
          'income': {
                income_account1: {'amount': '10', 'income': '7', 'remaining': '3', 'remaining_percent': '70%', 'notes': 'note2'},
                                    #may also want to have current status based on how much time remaining (70% through the year, only 60% income so far, ...)
                income_account2: {},
          } }
        '''
        if self._income_spending_info is None:
            raise BudgetError('must pass in income_spending_info to get the report display')
        report = {'expense': {}, 'income': {}}
        for account, budget_info in self._budget_data.items():
            report_info = {}
            report_info.update(budget_info)
            for key, value in self._income_spending_info.get(account, {}).items():
                if value:
                    report_info[key] = value
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
                        report_info['percent_available'] = 'error'
                else:
                    report_info['remaining'] = report_info['amount'] - income
                    percent = (income / report_info['amount']) * Decimal(100)
                    report_info['remaining_percent'] = '{}%'.format(Budget.round_percent_available(percent))
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
        if not conn_name:
            raise SQLiteStorageError('invalid SQLite connection name: %s' % conn_name)
        #conn_name is either ':memory:' or the name of the data file
        if conn_name == ':memory:':
            self._db_connection = sqlite3.connect(conn_name)
        else:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(current_dir, conn_name)
            self._db_connection = sqlite3.connect(file_path)
        self._db_connection.execute('PRAGMA foreign_keys = ON;')
        result = self._db_connection.execute('PRAGMA foreign_keys').fetchall()
        if result[0][0] != 1:
            print('WARNING: can\'t enable sqlite3 foreign_keys')
        tables = self._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        if not tables:
            self._setup_db()

    def _setup_db(self):
        '''
        Initialize empty DB.
        '''
        conn = self._db_connection
        conn.execute('CREATE TABLE accounts (id INTEGER PRIMARY KEY, type INTEGER NOT NULL, user_id TEXT, name TEXT UNIQUE NOT NULL, parent_id INTEGER, closed INTEGER,'\
                'FOREIGN KEY(parent_id) REFERENCES accounts(id))')
        conn.execute('CREATE TABLE budgets (id INTEGER PRIMARY KEY, name TEXT, start_date TEXT NOT NULL, end_date TEXT NOT NULL)')
        conn.execute('CREATE TABLE budget_values (id INTEGER PRIMARY KEY, budget_id INTEGER NOT NULL, account_id INTEGER NOT NULL, amount TEXT, carryover TEXT, notes TEXT,'\
                'FOREIGN KEY(budget_id) REFERENCES budgets(id), FOREIGN KEY(account_id) REFERENCES accounts(id))')
        conn.execute('CREATE TABLE payees (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, notes TEXT)')
        conn.execute('CREATE TABLE scheduled_transactions (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, frequency INTEGER NOT NULL, next_due_date TEXT NOT NULL, txn_type TEXT, payee_id INTEGER, description TEXT, status TEXT,'\
                'FOREIGN KEY(payee_id) REFERENCES payees(id))')
        conn.execute('CREATE TABLE scheduled_txn_splits (id INTEGER PRIMARY KEY, scheduled_txn_id INTEGER NOT NULL, account_id INTEGER NOT NULL, amount TEXT,'\
                'FOREIGN KEY(scheduled_txn_id) REFERENCES scheduled_transactions(id), FOREIGN KEY(account_id) REFERENCES accounts(id))')
        conn.execute('CREATE TABLE transactions (id INTEGER PRIMARY KEY, txn_type TEXT, txn_date TEXT, payee_id INTEGER, description TEXT, status TEXT,'\
                'FOREIGN KEY(payee_id) REFERENCES payees(id))')
        conn.execute('CREATE TABLE txn_splits (id INTEGER PRIMARY KEY, txn_id INTEGER NOT NULL, account_id INTEGER NOT NULL, amount TEXT, description TEXT,'\
                'FOREIGN KEY(txn_id) REFERENCES transactions(id), FOREIGN KEY(account_id) REFERENCES accounts(id))')
        conn.execute('CREATE TABLE misc (key TEXT UNIQUE NOT NULL, value TEXT)')
        conn.execute('INSERT INTO misc(key, value) VALUES(?, ?)', ('schema_version', '0'))

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
            parent_id = account.parent.id
        if account.id:
            c.execute('UPDATE accounts SET type = ?, user_id = ?, name = ?, parent_id = ? WHERE id = ?',
                    (account.type.value, account.user_id, account.name, parent_id, account.id))
            if c.rowcount < 1:
                raise Exception('no account with id %s to update' % account.id)
        else:
            c.execute('INSERT INTO accounts(type, user_id, name, parent_id) VALUES(?, ?, ?, ?)', (account.type.value, account.user_id, account.name, parent_id))
            account.id = c.lastrowid
        self._db_connection.commit()

    def get_payee(self, payee_id=None, name=None):
        '''return None if object can't be found for whatever reason'''
        if payee_id:
            info = self._db_connection.execute('SELECT id, name, notes FROM payees WHERE id = ?', (payee_id,)).fetchone()
            if not info:
                return None
        elif name:
            info = self._db_connection.execute('SELECT id, name, notes FROM payees WHERE name = ?', (name,)).fetchone()
            if not info:
                return None
        else:
            return None
        return Payee(
                id_=info[0],
                name=info[1],
                notes=info[2]
            )

    def get_payees(self):
        results = self._db_connection.execute('SELECT id, name, notes FROM payees').fetchall()
        payees = []
        for r in results:
            payees.append(Payee(id_=r[0], name=r[1], notes=r[2]))
        return payees

    def save_payee(self, payee):
        c = self._db_connection.cursor()
        if payee.id:
            c.execute('UPDATE payees SET name = ?, notes = ?', (payee.name, payee.notes))
            if c.rowcount < 1:
                raise Exception('no payee with id %s to update' % payee.id)
        else:
            c.execute('INSERT INTO payees(name, notes) VALUES(?, ?)', (payee.name, payee.notes))
            payee.id = c.lastrowid
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
        id_, txn_type, txn_date, payee_id, description, status = db_info
        txn_date = get_date(txn_date)
        payee = self.get_payee(payee_id)
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
        if txn.payee:
            if not txn.payee.id: #Payee may not have been saved in DB yet
                db_payee = self.get_payee(name=txn.payee.name)
                if db_payee:
                    txn.payee.id = db_payee.id
                else:
                    self.save_payee(txn.payee)
            payee = txn.payee.id
        else:
            payee = None
        if txn.id:
            c.execute('UPDATE transactions SET txn_type = ?, txn_date = ?, payee_id = ?, description = ?, status = ? WHERE id = ?',
                (txn.txn_type, txn.txn_date.strftime('%Y-%m-%d'), payee, txn.description, txn.status, txn.id))
            if c.rowcount < 1:
                raise Exception('no txn with id %s to update' % txn.id)
        else:
            c.execute('INSERT INTO transactions(txn_type, txn_date, payee_id, description, status) VALUES(?, ?, ?, ?, ?)',
                (txn.txn_type, txn.txn_date.strftime('%Y-%m-%d'), payee, txn.description, txn.status))
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

    def get_ledger(self, account):
        if not isinstance(account, Account):
            account = self.get_account(account)
        ledger = Ledger(account=account)
        db_txn_id_records = self._db_connection.execute('SELECT txn_id FROM txn_splits WHERE account_id = ?', (account.id,)).fetchall()
        txn_ids = set([r[0] for r in db_txn_id_records])
        for txn_id in txn_ids:
            txn = self.get_txn(txn_id)
            ledger.add_transaction(txn)
        db_scheduled_txn_id_records = self._db_connection.execute('SELECT scheduled_txn_id FROM scheduled_txn_splits WHERE account_id = ?', (account.id,)).fetchall()
        scheduled_txn_ids = set(r[0] for r in db_scheduled_txn_id_records)
        for scheduled_txn_id in scheduled_txn_ids:
            ledger.add_scheduled_transaction(self.get_scheduled_transaction(scheduled_txn_id))
        return ledger

    def save_budget(self, budget):
        c = self._db_connection.cursor()
        if budget.id:
            c.execute('UPDATE budgets SET name = ?, start_date = ?, end_date = ? WHERE id = ?',
                (budget.name, str(budget.start_date), str(budget.end_date), budget.id))
            #delete existing values, and then we'll add the current ones
            c.execute('DELETE FROM budget_values WHERE budget_id = ?', (budget.id,))
        else:
            c.execute('INSERT INTO budgets(start_date, end_date) VALUES(?, ?)', (budget.start_date, budget.end_date))
            budget.id = c.lastrowid
        budget_data = budget.get_budget_data()
        if budget_data:
            for account, info in budget_data.items():
                if info:
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
        account_budget_info = {}
        all_income_spending_info = {}
        income_and_expense_accounts = []
        income_and_expense_accounts.extend(self.get_accounts(type_=AccountType.EXPENSE))
        income_and_expense_accounts.extend(self.get_accounts(type_=AccountType.INCOME))
        for account in income_and_expense_accounts:
            account_budget_info[account] = {}
            all_income_spending_info[account] = {}
            #get spent & income values for each expense account
            spent = Decimal(0)
            income = Decimal(0)
            txn_splits_records = self._db_connection.execute('SELECT txn_splits.amount FROM txn_splits INNER JOIN transactions ON txn_splits.txn_id = transactions.id WHERE txn_splits.account_id = ? AND transactions.txn_date > ? AND transactions.txn_date < ?', (account.id, start_date, end_date)).fetchall()
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
                account_budget_info[account]['amount'] = r[0]
                account_budget_info[account]['carryover'] = r[1]
                account_budget_info[account]['notes'] = r[2]
            else:
                account_budget_info[account] = {}
        return Budget(id_=budget_id, start_date=start_date, end_date=end_date, account_budget_info=account_budget_info,
                income_spending_info=all_income_spending_info)

    def get_budgets(self):
        budgets = []
        c = self._db_connection.cursor()
        budget_records = c.execute('SELECT id FROM budgets ORDER BY start_date DESC').fetchall()
        for budget_record in budget_records:
            budget_id = int(budget_record[0])
            budgets.append(self.get_budget(budget_id))
        return budgets

    def save_scheduled_transaction(self, scheduled_txn):
        c = self._db_connection.cursor()
        if scheduled_txn.payee:
            if not scheduled_txn.payee.id: #Payee may not have been saved in DB yet
                db_payee = self.get_payee(name=scheduled_txn.payee.name)
                if db_payee:
                    scheduled_txn.payee.id = db_payee.id
                else:
                    self.save_payee(scheduled_txn.payee)
            payee = scheduled_txn.payee.id
        else:
            payee = None
        if scheduled_txn.id:
            c.execute('UPDATE scheduled_transactions SET name = ?, frequency = ?, next_due_date = ?, txn_type = ?, payee_id = ?, description = ?, status = ? WHERE id = ?',
                (scheduled_txn.name, scheduled_txn.frequency.value, scheduled_txn.next_due_date.strftime('%Y-%m-%d'), scheduled_txn.txn_type, payee, scheduled_txn.description, scheduled_txn.status, scheduled_txn.id))
            if c.rowcount < 1:
                raise Exception('no scheduled transaction with id %s to update' % scheduled_txn.id)
            c.execute('DELETE FROM scheduled_txn_splits WHERE scheduled_txn_id = ?', (scheduled_txn.id,))
            for account, amount in scheduled_txn.splits.items():
                c.execute('INSERT INTO scheduled_txn_splits(scheduled_txn_id, account_id, amount) VALUES (?, ?, ?)', (scheduled_txn.id, account.id, str(amount)))
        else:
            c.execute('INSERT INTO scheduled_transactions(name, frequency, next_due_date, txn_type, payee_id, description, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (scheduled_txn.name, scheduled_txn.frequency.value, scheduled_txn.next_due_date.strftime('%Y-%m-%d'), scheduled_txn.txn_type, payee, scheduled_txn.description, scheduled_txn.status))
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
        rows = c.execute('SELECT name,frequency,next_due_date,txn_type,payee_id,description,status FROM scheduled_transactions WHERE id = ?', (id_,)).fetchall()
        payee = self.get_payee(rows[0][4])
        st = ScheduledTransaction(
                name=rows[0][0],
                frequency=ScheduledTransactionFrequency(rows[0][1]),
                next_due_date=rows[0][2],
                splits=splits,
                txn_type=rows[0][3],
                payee=payee,
                description=rows[0][5],
                status=rows[0][6],
                id_=id_,
            )
        return st

    def get_scheduled_transactions(self):
        c = self._db_connection.cursor()
        scheduled_txns_records = c.execute('SELECT id FROM scheduled_transactions').fetchall()
        scheduled_txns = []
        for st_record in scheduled_txns_records:
            scheduled_txns.append(self.get_scheduled_transaction(st_record[0]))
        return scheduled_txns


### GUI ###

ACCOUNTS_GUI_FIELDS = {
        'type': {'column_number': 0, 'column_stretch': 2, 'label': 'Type'},
        'user_id': {'column_number': 1, 'column_stretch': 1, 'label': 'User ID'},
        'name': {'column_number': 2, 'column_stretch': 3, 'label': 'Name'},
        'parent': {'column_number': 3, 'column_stretch': 3, 'label': 'Parent'},
        'buttons': {'column_number': 4, 'column_stretch': 3},
    }


GUI_FIELDS = {
        'txn_type': {'column_number': 0, 'add_edit_column_number': 0, 'column_stretch': 1, 'label': 'Txn Type'},
        'txn_date': {'column_number': 1, 'add_edit_column_number': 1, 'column_stretch': 2, 'label': 'Date'},
        'payee': {'column_number': 2, 'add_edit_column_number': 2, 'column_stretch': 2, 'label': 'Payee'},
        'description': {'column_number': 3, 'add_edit_column_number': 3, 'column_stretch': 2, 'label': 'Description'},
        'status': {'column_number': 4, 'add_edit_column_number': 4, 'column_stretch': 1, 'label': 'Status'},
        'withdrawal': {'column_number': 5, 'add_edit_column_number': 5, 'column_stretch': 2, 'label': 'Withdrawal'},
        'deposit': {'column_number': 6, 'add_edit_column_number': 6, 'column_stretch': 2, 'label': 'Deposit'},
        'balance': {'column_number': 7, 'add_edit_column_number': -1, 'column_stretch': 2, 'label': 'Balance'},
        'categories': {'column_number': 8, 'add_edit_column_number': 7, 'column_stretch': 3, 'label': 'Categories'},
        'buttons': {'column_number': -1, 'add_edit_column_number': 8, 'column_stretch': 2, 'label': ''},
    }


ERROR_STYLE = '''QLineEdit {
    border: 2px solid red;
}'''


def set_widget_error_state(widget):
    widget.setStyleSheet(ERROR_STYLE)


class AccountForm:
    '''display widgets for Account data, and create a new
        Account when user finishes entering data'''

    def __init__(self, all_accounts, account=None, save_account=None):
        self._all_accounts = all_accounts
        self._account = account
        self._save_account = save_account
        self._widgets = {}

    def show_form(self):
        self._display = QtWidgets.QDialog()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self._show_widgets(layout, self._widgets)
        self._display.setLayout(layout)
        self._display.open()

    def _show_widgets(self, layout, widgets):
        row = 0
        for index, f in enumerate(['type', 'user_id', 'name', 'parent']):
            layout.addWidget(QtWidgets.QLabel(ACCOUNTS_GUI_FIELDS[f]['label']), row, index)
        row += 1
        account_type = QtWidgets.QComboBox()
        for index, type_ in enumerate(AccountType):
            account_type.addItem(type_.name, type_)
            if self._account and self._account.type == type_:
                account_type.setCurrentIndex(index)
        layout.addWidget(account_type, row, ACCOUNTS_GUI_FIELDS['type']['column_number'])
        user_id = QtWidgets.QLineEdit()
        if self._account:
            user_id.setText(self._account.user_id)
        layout.addWidget(user_id, row, ACCOUNTS_GUI_FIELDS['user_id']['column_number'])
        name = QtWidgets.QLineEdit()
        if self._account:
            name.setText(self._account.name)
        layout.addWidget(name, row, ACCOUNTS_GUI_FIELDS['name']['column_number'])
        parent_combo = QtWidgets.QComboBox()
        parent_combo.addItem('---------', None)
        for index, acc in enumerate(self._all_accounts):
            parent_combo.addItem(acc.name, acc)
            if self._account and self._account.parent == acc:
                parent_combo.setCurrentIndex(index+1)
        layout.addWidget(parent_combo, row, ACCOUNTS_GUI_FIELDS['parent']['column_number'])
        button = QtWidgets.QPushButton('Save')
        button.clicked.connect(self._save_new_account)
        layout.addWidget(button, row, ACCOUNTS_GUI_FIELDS['buttons']['column_number'])
        widgets['type'] = account_type
        widgets['user_id'] = user_id
        widgets['name'] = name
        widgets['parent'] = parent_combo
        widgets['save_btn'] = button

    def _save_new_account(self):
        type_ = self._widgets['type'].currentData()
        user_id = self._widgets['user_id'].text()
        name = self._widgets['name'].text()
        parent = self._widgets['parent'].currentData()
        if self._account:
            id_ = self._account.id
        else:
            id_ = None
        try:
            account = Account(id_=id_, type_=type_, user_id=user_id, name=name, parent=parent)
            self._display.accept()
            self._save_account(account)
        except InvalidAccountNameError:
            set_widget_error_state(self._widgets['name'])


class AccountsDisplay:

    def __init__(self, storage, reload_accounts):
        self.storage = storage
        self._reload = reload_accounts

    def get_widget(self):
        main_widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        for field_info in ACCOUNTS_GUI_FIELDS.values():
            layout.setColumnStretch(field_info['column_number'], field_info['column_stretch'])
        row = 0
        self.add_button = QtWidgets.QPushButton('New Account')
        self.add_button.clicked.connect(self._open_new_account_form)
        layout.addWidget(self.add_button, row, 0)
        row += 1
        layout.addWidget(QtWidgets.QLabel('Type'), row, ACCOUNTS_GUI_FIELDS['type']['column_number'])
        layout.addWidget(QtWidgets.QLabel('User ID'), row, ACCOUNTS_GUI_FIELDS['user_id']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Name'), row, ACCOUNTS_GUI_FIELDS['name']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Parent Account'), row, ACCOUNTS_GUI_FIELDS['parent']['column_number'])
        row += 1
        self.accounts_widgets = {}
        accounts = self.storage.get_accounts()
        accounts_widget = self._get_accounts_widget(self.accounts_widgets, accounts)
        layout.addWidget(accounts_widget, row, 0, 1, 5)
        row += 1
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

    def _open_new_account_form(self):
        self.add_account_display = AccountForm(self.storage.get_accounts(), save_account=self._save_account)
        self.add_account_display.show_form()

    def _save_account(self, account):
        self.storage.save_account(account)
        self._reload()

    def _edit(self, event, layout, acc_id):
        self.edit_account_display = AccountForm(self.storage.get_accounts(), account=self.storage.get_account(acc_id), save_account=self._save_account)
        self.edit_account_display.show_form()


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
        main_layout = QtWidgets.QGridLayout()
        main_widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        row = 0
        for account in self._all_accounts:
            layout.addWidget(QtWidgets.QLabel(str(account)), row, 0)
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
        main_widget.setLayout(layout)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(main_widget)
        main_layout.addWidget(scroll, 0, 0)
        split_editor.setLayout(main_layout)
        split_editor.exec_()

    def get_txn_splits(self):
        self._show_split_editor()
        return self._final_txn_splits


class LedgerTxnsDisplay:

    def __init__(self, ledger, storage, filter_text, post_update_function):
        self.ledger = ledger
        self.storage = storage
        self._filter_text = filter_text
        self._scheduled_txn_widgets = []
        self._post_update_function = post_update_function

    def get_widget(self):
        self.main_widget = QtWidgets.QScrollArea()
        self.main_widget.setWidgetResizable(True)
        self.txns_layout = QtWidgets.QGridLayout() #need handle to this for display_new_txn
        set_ledger_column_widths(self.txns_layout)
        self.txn_display_data = {}
        self._redisplay_txns()
        txns_widget = QtWidgets.QWidget()
        txns_widget.setLayout(self.txns_layout)
        self.main_widget.setWidget(txns_widget)
        return self.main_widget

    def display_new_txn(self, txn):
        self.ledger.add_transaction(txn)
        self._redisplay_txns()

    def _redisplay_txns(self):
        '''draw/redraw txns on the screen as needed'''
        index = 0 #initialize in case there are no txns in the ledger
        if self._filter_text:
            txns = self.ledger.search(self._filter_text)
        else:
            txns = self.ledger.get_sorted_txns_with_balance()
        for index, txn in enumerate(txns):
            if (txn.id not in self.txn_display_data) or (self.txn_display_data[txn.id]['row'] != index):
                self._display_txn(txn, row=index, layout=self.txns_layout)
            else:
                try:
                    if self.txn_display_data[txn.id]['widgets']['labels']['balance'].text() != txn.balance:
                        self._display_txn(txn, row=index, layout=self.txns_layout)
                except KeyError:
                    pass
        row = index + 1
        for w in self._scheduled_txn_widgets:
            self.txns_layout.removeWidget(w)
            w.deleteLater()
        self._scheduled_txn_widgets = []
        scheduled_txns_due = self.ledger.get_scheduled_transactions_due()
        if scheduled_txns_due:
            heading = QtWidgets.QLabel('Scheduled Transactions Due')
            self.txns_layout.addWidget(heading, row, 0, 1, 9)
            self._scheduled_txn_widgets.append(heading)
            row += 1
        for scheduled_txn in scheduled_txns_due:
            self._display_scheduled_txn(self.txns_layout, row, scheduled_txn)
            row += 1
        empty = QtWidgets.QLabel('')
        self._scheduled_txn_widgets.append(empty)
        self.txns_layout.addWidget(empty, row, 0)
        self.txns_layout.setRowStretch(row, 1)
        self._post_update_function()

    def _delete(self, txn, layout):
        #delete from storage, remove it from ledger, delete the display info
        #   & then redisplay any txns necessary
        self.storage.delete_txn(txn.id)
        self.ledger.remove_txn(txn.id)
        for widget in self.txn_display_data[txn.id]['widgets']['labels'].values():
            layout.removeWidget(widget)
            widget.deleteLater()
        del self.txn_display_data[txn.id]
        self._redisplay_txns()

    def _save_edit(self, txn, layout):
        self.storage.save_txn(txn)
        self.ledger.add_transaction(txn)
        for widget in self.txn_display_data[txn.id]['widgets']['labels'].values():
            layout.removeWidget(widget)
            widget.deleteLater()
        del self.txn_display_data[txn.id]
        self._redisplay_txns()

    def _edit(self, event, txn_id, layout):
        txn = self.ledger.get_txn(txn_id)
        self.edit_txn_display = TxnForm(
                payees=self.ledger.get_payees(),
                save_txn=partial(self._save_edit, layout=layout),
                storage=self.storage,
                current_account=self.ledger.account,
                txn=txn,
                delete_txn=partial(self._delete, layout=layout)
            )
        self.edit_txn_display.show_form()

    def _enter_scheduled_txn(self, new_txn, scheduled_txn, layout):
        scheduled_txn.next_txn_entered()
        self.storage.save_scheduled_transaction(scheduled_txn)
        self.storage.save_txn(new_txn)
        self.ledger.add_transaction(new_txn)
        self._redisplay_txns()

    def _skip_scheduled_txn(self, scheduled_txn):
        pass

    def _show_scheduled_txn_form(self, event, scheduled_txn, layout):
        save_txn = partial(self._enter_scheduled_txn, scheduled_txn=scheduled_txn, layout=layout)
        self.scheduled_txn_display = TxnForm(
                payees=self.ledger.get_payees(),
                save_txn=save_txn,
                storage=self.storage,
                current_account=self.ledger.account,
                txn=scheduled_txn,
                skip_txn=partial(self._skip_scheduled_txn, scheduled_txn=scheduled_txn)
            )
        self.scheduled_txn_display.show_form()

    def _display_txn(self, txn, row, layout):
        #clear labels if this txn was already displayed, create new labels, add them to layout, and set txn_display_data
        if txn.id in self.txn_display_data:
            for widget in self.txn_display_data[txn.id]['widgets']['labels'].values():
                layout.removeWidget(widget)
                widget.deleteLater()
        tds = get_display_strings_for_ledger(self.ledger.account, txn)
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
        try:
            balance = str(txn.balance)
        except AttributeError:
            balance = ''
        balance_label = QtWidgets.QLabel(balance)
        balance_label.mousePressEvent = edit_function
        layout.addWidget(type_label, row, GUI_FIELDS['txn_type']['column_number'])
        layout.addWidget(date_label, row, GUI_FIELDS['txn_date']['column_number'])
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

    def _display_scheduled_txn(self, layout, row, scheduled_txn):
        show_form = partial(self._show_scheduled_txn_form, scheduled_txn=scheduled_txn, layout=layout)
        tds = get_display_strings_for_ledger(txn=scheduled_txn, account=self.ledger.account)
        type_label = QtWidgets.QLabel(tds['txn_type'])
        type_label.mousePressEvent = show_form
        date_label = QtWidgets.QLabel(tds['txn_date'])
        date_label.mousePressEvent = show_form
        payee_label = QtWidgets.QLabel(tds['payee'])
        payee_label.mousePressEvent = show_form
        description_label = QtWidgets.QLabel(tds['description'])
        description_label.mousePressEvent = show_form
        withdrawal_label = QtWidgets.QLabel(tds['withdrawal'])
        withdrawal_label.mousePressEvent = show_form
        deposit_label = QtWidgets.QLabel(tds['deposit'])
        deposit_label.mousePressEvent = show_form
        categories_label = QtWidgets.QLabel(tds['categories'])
        categories_label.mousePressEvent = show_form
        layout.addWidget(type_label, row, 0)
        layout.addWidget(date_label, row, 1)
        layout.addWidget(payee_label, row, 2)
        layout.addWidget(description_label, row, 3)
        layout.addWidget(withdrawal_label, row, 5)
        layout.addWidget(deposit_label, row, 6)
        layout.addWidget(categories_label, row, 8)
        self._scheduled_txn_widgets.extend(
                [type_label, date_label, payee_label, description_label, withdrawal_label,
                    deposit_label, categories_label]
            )


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
                self._categories_combo.addItem(str(account), account)
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
        new_txn_splits = get_new_txn_splits(accounts, initial_txn_splits)
        if new_txn_splits and new_txn_splits != initial_txn_splits:
            self._categories_combo.setCurrentIndex(self._multiple_entry_index)
            self._categories_combo.setItemData(self._multiple_entry_index, new_txn_splits)

    def get_categories(self):
        splits = self._categories_combo.currentData()
        #remove main account split (if present), because that comes from withdrawal/deposit fields
        if isinstance(splits, dict):
            splits.pop(self._main_account, None)
        return splits

    def get_widget(self):
        return self._widget


class TxnForm:
    '''Display widgets for Transaction data, and create a new
    Transaction when user finishes entering data.
    Displays ScheduledTransaction actions if txn is a ScheduledTxn.'''

    def __init__(self, payees, save_txn, storage, current_account, txn=None, delete_txn=None, skip_txn=None):
        self._payees = payees
        self._save_txn = save_txn
        self._storage = storage
        self._current_account = current_account
        self._txn = txn
        self._delete_txn = delete_txn
        self._skip_txn = skip_txn
        self._widgets = {}

    def show_form(self):
        self._txn_display = QtWidgets.QDialog()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        set_ledger_column_widths(layout)
        self._show_widgets(layout, payees=self._payees, txn=self._txn, current_account=self._current_account)
        self._txn_display.setLayout(layout)
        self._txn_display.open()

    def _show_widgets(self, layout, payees, txn, current_account):
        tds = {}
        if txn:
            tds = get_display_strings_for_ledger(current_account, txn)
        labels = [None, None, None, None, None, None, None, None, None]
        widgets = [None, None, None, None, None, None, None, None, None]
        for name in ['txn_type', 'txn_date', 'description', 'withdrawal', 'deposit']:
            entry = QtWidgets.QLineEdit()
            if self._txn:
                entry.setText(tds[name])
            self._widgets[name] = entry
            widgets[GUI_FIELDS[name]['add_edit_column_number']] = entry
            labels[GUI_FIELDS[name]['add_edit_column_number']] = QtWidgets.QLabel(GUI_FIELDS[name]['label'])
        status_entry = QtWidgets.QComboBox()
        for index, status in enumerate(['', Transaction.CLEARED, Transaction.RECONCILED]):
            status_entry.addItem(status)
            try:
                if self._txn and self._txn.status == status:
                    status_entry.setCurrentIndex(index)
            except AttributeError: #ScheduledTxn doesn't have a status
                pass
        self._widgets['status'] = status_entry
        widgets[GUI_FIELDS['status']['add_edit_column_number']] = status_entry
        labels[GUI_FIELDS['status']['add_edit_column_number']] = QtWidgets.QLabel(GUI_FIELDS['status']['label'])
        payee_entry = QtWidgets.QComboBox()
        payee_entry.setEditable(True)
        payee_entry.addItem('')
        payee_index = 0
        for index, payee in enumerate(payees):
            payee_entry.addItem(payee.name, payee)
            if self._txn and payee.name == tds['payee']:
                payee_index = index + 1 #because of first empty item
        if self._txn:
            payee_entry.setCurrentIndex(payee_index)
        self._widgets['payee'] = payee_entry
        widgets[GUI_FIELDS['payee']['add_edit_column_number']] = payee_entry
        labels[GUI_FIELDS['payee']['add_edit_column_number']] = QtWidgets.QLabel(GUI_FIELDS['payee']['label'])
        txn_accounts_display = TxnAccountsDisplay(self._storage, main_account=self._current_account, txn=self._txn)
        widgets[GUI_FIELDS['categories']['add_edit_column_number']] = txn_accounts_display.get_widget()
        labels[GUI_FIELDS['categories']['add_edit_column_number']] = QtWidgets.QLabel(GUI_FIELDS['categories']['label'])
        self._widgets['accounts_display'] = txn_accounts_display
        if isinstance(self._txn, ScheduledTransaction):
            button = QtWidgets.QPushButton('Enter New Txn')
        elif self._txn:
            button = QtWidgets.QPushButton('Save Edit')
        else:
            button = QtWidgets.QPushButton('Add New')
        self._widgets['save_btn'] = button
        button.clicked.connect(self._save)
        widgets[GUI_FIELDS['buttons']['add_edit_column_number']] = button
        for index, label in enumerate(labels):
            if label:
                layout.addWidget(label, 0, index)
        for index, widget in enumerate(widgets):
            layout.addWidget(widget, 1, index)
        if self._txn:
            delete_button = QtWidgets.QPushButton('Delete Txn')
            delete_button.clicked.connect(self.delete)
            self._widgets['delete_btn'] = delete_button
            layout.addWidget(delete_button, 2, 0)

    def _save(self):
        txn_type = self._widgets['txn_type'].text()
        txn_date = self._widgets['txn_date'].text()
        payee = self._widgets['payee'].currentData()
        if not payee:
            payee = self._widgets['payee'].currentText()
        description = self._widgets['description'].text()
        categories = self._widgets['accounts_display'].get_categories()
        status = self._widgets['status'].currentText()
        deposit = self._widgets['deposit'].text()
        withdrawal = self._widgets['withdrawal'].text()
        kwargs = {
            'account': self._current_account,
            'txn_type': txn_type,
            'deposit': deposit,
            'withdrawal': withdrawal,
            'txn_date': txn_date,
            'payee': payee,
            'description': description,
            'status': status,
            'categories': categories,
        }
        if self._txn:
            kwargs['id_'] = self._txn.id
        txn = Transaction.from_user_info(**kwargs)
        self._txn_display.accept()
        self._save_txn(txn)

    def delete(self):
        self._txn_display.accept()
        self._delete_txn(self._txn)


class LedgerDisplay:

    def __init__(self, storage, current_account=None):
        self.storage = storage
        #choose an account if there is one
        if not current_account:
            accounts = self.storage.get_accounts(type_=AccountType.ASSET)
            if accounts:
                current_account = accounts[0]
        self._current_account = current_account
        self.txns_display_widget = None
        self.balances_widget = None

    def get_widget(self):
        self.widget, self.layout = self._setup_main()
        if self._current_account:
            self._display_ledger(self.layout, self._current_account)
        else:
            self.layout.addWidget(QtWidgets.QLabel(''), self._ledger_txns_row_index, 0, 1, 9)
            self.layout.setRowStretch(self._ledger_txns_row_index, 1)
        return self.widget

    def _setup_main(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        set_ledger_column_widths(layout)
        new_row = self._show_headings(layout, row=0)
        self._ledger_txns_row_index = new_row
        widget.setLayout(layout)
        return widget, layout

    def _display_ledger(self, layout, account, filter_text=''):
        self.ledger = self.storage.get_ledger(account=account)
        self.txns_display = LedgerTxnsDisplay(self.ledger, self.storage, filter_text,
                post_update_function=partial(self._display_balances_widget, layout=layout, ledger=self.ledger))
        if self.txns_display_widget:
            layout.removeWidget(self.txns_display_widget)
            self.txns_display_widget.deleteLater()
        self.txns_display_widget = self.txns_display.get_widget()
        layout.addWidget(self.txns_display_widget, self._ledger_txns_row_index, 0, 1, 9)

    def _display_balances_widget(self, layout, ledger):
        if self.balances_widget:
            layout.removeWidget(self.balances_widget)
            self.balances_widget.deleteLater()
        self.balances_widget = self._get_balances_widget(ledger=self.ledger)
        layout.addWidget(self.balances_widget, self._ledger_txns_row_index+1, 0, 1, 9)

    def _get_balances_widget(self, ledger):
        #this is a row below the list of txns
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        balances = ledger.get_current_balances()
        balance_text = f'Current Balance: {balances.current}'
        cleared_text = f'Cleared: {balances.current_cleared}'
        layout.addWidget(QtWidgets.QLabel(cleared_text), 0, 0)
        layout.addWidget(QtWidgets.QLabel(balance_text), 0, 1)
        widget.setLayout(layout)
        return widget

    def _update_account(self, index):
        self._current_account = self.storage.get_accounts()[index]
        self._display_ledger(layout=self.layout, account=self._current_account)

    def _filter_txns(self):
        self._display_ledger(layout=self.layout, account=self._current_account, filter_text=self._filter_box.text())

    def _show_all_txns(self):
        self._filter_box.setText('')
        self._display_ledger(layout=self.layout, account=self._current_account)

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
        self.add_button = QtWidgets.QPushButton('New Txn')
        self.add_button.clicked.connect(self._open_new_txn_form)
        layout.addWidget(self.add_button, row, 1)
        self._filter_box = QtWidgets.QLineEdit()
        layout.addWidget(self._filter_box, row, 3)
        self._filter_btn = QtWidgets.QPushButton('Filter')
        self._filter_btn.clicked.connect(self._filter_txns)
        layout.addWidget(self._filter_btn, row, 4)
        clear_btn = QtWidgets.QPushButton('Show all')
        clear_btn.clicked.connect(self._show_all_txns)
        layout.addWidget(clear_btn, row, 5)
        row += 1
        layout.addWidget(QtWidgets.QLabel('Type'), row, GUI_FIELDS['txn_type']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Date'), row, GUI_FIELDS['txn_date']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Payee'), row, GUI_FIELDS['payee']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Description'), row, GUI_FIELDS['description']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Categories'), row, GUI_FIELDS['categories']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Status'), row, GUI_FIELDS['status']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Withdrawal (-)'), row, GUI_FIELDS['withdrawal']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Deposit (+)'), row, GUI_FIELDS['deposit']['column_number'])
        layout.addWidget(QtWidgets.QLabel('Balance'), row, GUI_FIELDS['balance']['column_number'])
        return row + 1

    def _open_new_txn_form(self):
        self.add_txn_display = TxnForm(payees=self.ledger.get_payees(), save_txn=self._save_new_txn, storage=self.storage, current_account=self._current_account)
        self.add_txn_display.show_form()

    def _save_new_txn(self, txn):
        self.storage.save_txn(txn)
        self.txns_display.display_new_txn(txn)


class BudgetForm:
    '''Handle editing an existing budget or creating a new one'''

    def __init__(self, budget=None, accounts=None, save_budget=None):
        if budget and accounts:
            raise BudgetError('pass budget or accounts, not both')
        self._budget = budget
        self._widgets = {'budget_data': {}}
        self._save_budget = save_budget
        self._accounts = accounts
        if self._budget:
            self._budget_data = self._budget.get_budget_data()
        else:
            self._budget_data = {}
            for account in self._accounts:
                self._budget_data[account] = {}

    def show_form(self):
        self._display = QtWidgets.QDialog()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self._show_widgets(layout, self._widgets)
        self._display.setLayout(layout)
        self._display.open()

    def _show_widgets(self, layout, widgets):
        row = 0
        for index, label in enumerate(['Start Date', 'End Date']):
            layout.addWidget(QtWidgets.QLabel(label), row, index)
        row += 1
        start_date = QtWidgets.QLineEdit()
        end_date = QtWidgets.QLineEdit()
        if self._budget:
            start_date.setText(str(self._budget.start_date))
            end_date.setText(str(self._budget.end_date))
        layout.addWidget(start_date, row, 0)
        layout.addWidget(end_date, row, 1)
        widgets['start_date'] = start_date
        widgets['end_date'] = end_date
        row += 1
        layout.addWidget(QtWidgets.QLabel('Amount'), row, 1)
        layout.addWidget(QtWidgets.QLabel('Carryover'), row, 2)
        row += 1
        for account, info in self._budget_data.items():
            layout.addWidget(QtWidgets.QLabel(str(account)), row, 0)
            amount = QtWidgets.QLineEdit()
            carryover = QtWidgets.QLineEdit()
            amount.setText(str(info.get('amount', '')))
            carryover.setText(str(info.get('carryover', '')))
            widgets['budget_data'][account] = {
                    'amount': amount,
                    'carryover': carryover,
                }
            layout.addWidget(amount, row, 1)
            layout.addWidget(carryover, row, 2)
            row += 1
        save_button = QtWidgets.QPushButton('Save')
        save_button.clicked.connect(self._save)
        layout.addWidget(save_button, row, 0)

    def _save(self):
        start_date = self._widgets['start_date'].text()
        end_date = self._widgets['end_date'].text()
        account_budget_info = {}
        for account, widgets in self._widgets['budget_data'].items():
            account_budget_info[account] = {'amount': widgets['amount'].text(), 'carryover': widgets['carryover'].text()}
        if self._budget:
            b = Budget(start_date=start_date, end_date=end_date, id_=self._budget.id, account_budget_info=account_budget_info)
        else:
            b = Budget(start_date=start_date, end_date=end_date, account_budget_info=account_budget_info)
        self._display.accept()
        self._save_budget(b)


class BudgetDataDisplay:
    '''Just for displaying budget values and income/expense data.'''

    def __init__(self, budget, save_budget):
        self._budget = budget
        self._save_budget = save_budget

    def get_widget(self):
        self.main_widget = QtWidgets.QScrollArea()
        self.main_widget.setWidgetResizable(True)
        widget = QtWidgets.QWidget()
        self.layout = QtWidgets.QGridLayout()
        layout = self.layout
        widget.setLayout(layout)
        row = 0
        self.data = {}
        budget = self._budget
        budget_report = budget.get_report_display()
        for account, info in budget_report['income'].items():
            layout.addWidget(QtWidgets.QLabel(account.name), row, 0)
            budget_label = QtWidgets.QLabel(info.get('amount', ''))
            layout.addWidget(budget_label, row, 1)
            layout.addWidget(QtWidgets.QLabel(info.get('income', '')), row, 2)
            carryover_label = QtWidgets.QLabel(info.get('carryover', ''))
            layout.addWidget(carryover_label, row, 3)
            layout.addWidget(QtWidgets.QLabel(info.get('spent', '')), row, 5)
            layout.addWidget(QtWidgets.QLabel(info.get('remaining', '')), row, 6)
            layout.addWidget(QtWidgets.QLabel(info.get('percent', '')), row, 7)
            row_data = {'budget_label': budget_label}
            row_data['carryover_label'] = carryover_label
            row_data['row'] = row
            row_data['account'] = account
            self.data[account.id] = row_data
            row += 1
        for account, info in budget_report['expense'].items():
            layout.addWidget(QtWidgets.QLabel(account.name), row, 0)
            budget_label = QtWidgets.QLabel(info.get('amount', ''))
            layout.addWidget(budget_label, row, 1)
            layout.addWidget(QtWidgets.QLabel(info.get('income', '')), row, 2)
            carryover_label = QtWidgets.QLabel(info.get('carryover', ''))
            layout.addWidget(carryover_label, row, 3)
            layout.addWidget(QtWidgets.QLabel(info.get('total_budget', '')), row, 4)
            layout.addWidget(QtWidgets.QLabel(info.get('spent', '')), row, 5)
            layout.addWidget(QtWidgets.QLabel(info.get('remaining', '')), row, 6)
            layout.addWidget(QtWidgets.QLabel(info.get('percent_available', '')), row, 7)
            row_data = {'budget_label': budget_label}
            row_data['carryover_label'] = carryover_label
            row_data['row'] = row
            row_data['account'] = account
            self.data[account.id] = row_data
            row += 1
        layout.addWidget(QtWidgets.QLabel(''), row+1, 0)
        layout.setRowStretch(row+1, 1)
        self.main_widget.setWidget(widget)
        return self.main_widget


class BudgetDisplay:

    @staticmethod
    def budget_display_for_list(budget):
        if budget.name:
            return '%s (%s - %s)' % (budget.name, budget.start_date, budget.end_date)
        else:
            return '%s - %s' % (budget.start_date, budget.end_date)

    def __init__(self, storage, current_budget=None):
        self.storage = storage
        if not current_budget:
            budgets = self.storage.get_budgets()
            if budgets:
                current_budget = budgets[0]
        self._current_budget = current_budget
        self._budget_select_combo = None
        self._budget_data_display_widget = None

    def get_widget(self):
        self.widget, self.layout, self._row_index = self._setup_main()
        if self._current_budget:
            self._display_budget(self.layout, self._current_budget, self._row_index)
        else:
            self.layout.addWidget(QtWidgets.QLabel(''), self._row_index, 0, 1, 6)
            self.layout.setRowStretch(self._row_index, 1)
        return self.widget

    def _setup_main(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        row_index = self._show_headings(layout, row=0)
        widget.setLayout(layout)
        return widget, layout, row_index

    def _display_budget(self, layout, budget, row):
        self.budget_data_display = BudgetDataDisplay(budget, save_budget=self._save_budget_and_reload)
        if self._budget_data_display_widget:
            layout.removeWidget(self._budget_data_display_widget)
            self._budget_data_display_widget.deleteLater()
        self._budget_data_display_widget = self.budget_data_display.get_widget()
        layout.addWidget(self._budget_data_display_widget, row, 0, 1, 8)
        row += 1
        self._edit_button = QtWidgets.QPushButton('Edit')
        self._edit_button.clicked.connect(partial(self._open_form, budget=budget))
        layout.addWidget(self._edit_button, row, 0)

    def _update_budget(self, index=0):
        self._current_budget = self.storage.get_budgets()[index]
        self._budget_select_combo.setCurrentIndex(index)
        self._display_budget(layout=self.layout, budget=self._current_budget, row=self._row_index)

    def _show_headings(self, layout, row):
        self._budget_select_combo = QtWidgets.QComboBox()
        current_index = 0
        budgets = self.storage.get_budgets()
        for index, budget in enumerate(budgets):
            if budget == self._current_budget:
                current_index = index
            self._budget_select_combo.addItem(BudgetDisplay.budget_display_for_list(budget), budget)
        self._budget_select_combo.setCurrentIndex(current_index)
        self._budget_select_combo.currentIndexChanged.connect(self._update_budget)
        layout.addWidget(self._budget_select_combo, row, 0)
        self.add_button = QtWidgets.QPushButton('New Budget')
        self.add_button.clicked.connect(partial(self._open_form, budget=None))
        layout.addWidget(self.add_button, row, 1)
        row += 1
        layout.addWidget(QtWidgets.QLabel('Category'), row, 0)
        layout.addWidget(QtWidgets.QLabel('Amount'), row, 1)
        layout.addWidget(QtWidgets.QLabel('Income'), row, 2)
        layout.addWidget(QtWidgets.QLabel('Carryover'), row, 3)
        layout.addWidget(QtWidgets.QLabel('Total Budget'), row, 4)
        layout.addWidget(QtWidgets.QLabel('Spent'), row, 5)
        layout.addWidget(QtWidgets.QLabel('Remaining'), row, 6)
        layout.addWidget(QtWidgets.QLabel('Percent Available'), row, 7)
        return row + 1

    def _save_budget_and_reload(self, budget, new_budget=False):
        self.storage.save_budget(budget)
        #need to reload budget from storage here, so txn info is picked up
        self._current_budget = self.storage.get_budget(budget_id=budget.id)
        if new_budget:
            #need to add new budget to select combo and select it
            num_items = self._budget_select_combo.count()
            self._budget_select_combo.addItem(BudgetDisplay.budget_display_for_list(self._current_budget), self._current_budget)
            self._budget_select_combo.setCurrentIndex(num_items)
        self._display_budget(layout=self.layout, budget=self._current_budget, row=self._row_index)

    def _open_form(self, budget):
        if budget:
            self.budget_form = BudgetForm(budget=budget, save_budget=self._save_budget_and_reload)
        else:
            income_and_expense_accounts = self.storage.get_accounts(type_=AccountType.INCOME)
            income_and_expense_accounts.extend(self.storage.get_accounts(type_=AccountType.EXPENSE))
            self.budget_form = BudgetForm(accounts=income_and_expense_accounts, save_budget=partial(self._save_budget_and_reload, new_budget=True))
        self.budget_form.show_form()


def show_error(msg):
    msgbox = QtWidgets.QMessageBox()
    msgbox.setText(msg)
    msgbox.exec_()


class GUI_QT:

    def __init__(self, file_name=None):
        self.parent_window = QtWidgets.QWidget()
        self.parent_window.setWindowTitle(TITLE)
        self.parent_layout = QtWidgets.QGridLayout()
        self.parent_layout.setContentsMargins(4, 4, 4, 4)
        self.parent_window.setLayout(self.parent_layout)
        self.parent_window.showMaximized()
        self.content_area = None

        if file_name:
            self._load_db(file_name)
        else:
            self._show_splash()

    def _show_splash(self):
        #show screen for creating new db or opening existing one
        self.content_area = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QGridLayout()
        new_button = QtWidgets.QPushButton('New')
        new_button.clicked.connect(self._new_file)
        self.content_layout.addWidget(new_button, 0, 0)
        open_button = QtWidgets.QPushButton('Open')
        open_button.clicked.connect(self._open_file)
        self.content_layout.addWidget(open_button, 1, 0)
        files = get_files(CUR_DIR)
        for index, f in enumerate(files):
            button = QtWidgets.QPushButton(f.name)
            button.clicked.connect(partial(self._load_db, file_name=str(f)))
            self.content_layout.addWidget(button, index+2, 0)
        self.content_area.setLayout(self.content_layout)
        self.parent_layout.addWidget(self.content_area, 1, 0, 1, 2)

    def _load_db(self, file_name):
        try:
            self.storage = SQLiteStorage(file_name)
        except sqlite3.DatabaseError as e:
            if 'file is not a database' in str(e):
                show_error(msg='File %s is not a database' % file_name)
                return
            raise
        if self.content_area:
            self.parent_layout.removeWidget(self.content_area)
            self.content_area.deleteLater()
        self.content_area = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QGridLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_area.setLayout(self.content_layout)
        self.parent_layout.addWidget(self.content_area, 1, 0, 1, 6)
        self.main_widget = None
        self._show_action_buttons(self.parent_layout)
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

    def _show_action_buttons(self, layout):
        self.accounts_button = QtWidgets.QPushButton('Accounts')
        self.accounts_button.clicked.connect(self._show_accounts)
        layout.addWidget(self.accounts_button, 0, 0)
        self.ledger_button = QtWidgets.QPushButton('Ledger')
        self.ledger_button.clicked.connect(self._show_ledger)
        layout.addWidget(self.ledger_button, 0, 1)
        self.budget_button = QtWidgets.QPushButton('Budget')
        self.budget_button.clicked.connect(self._show_budget)
        layout.addWidget(self.budget_button, 0, 2)

    def _show_accounts(self):
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self.accounts_display = AccountsDisplay(self.storage, reload_accounts=self._show_accounts)
        self.main_widget = self.accounts_display.get_widget()
        self.content_layout.addWidget(self.main_widget, 0, 0)

    def _show_ledger(self):
        accounts = self.storage.get_accounts(type_=AccountType.ASSET)
        if not accounts:
            show_error('Enter an asset account first.')
            return
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self.ledger_display = LedgerDisplay(self.storage)
        self.main_widget = self.ledger_display.get_widget()
        self.content_layout.addWidget(self.main_widget, 0, 0)

    def _show_budget(self, current_budget=None):
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self.budget_display = BudgetDisplay(self.storage, current_budget=current_budget)
        self.main_widget = self.budget_display.get_widget()
        self.content_layout.addWidget(self.main_widget, 0, 0)


class CLI:

    ACCOUNT_LIST_HEADER = ' ID   | Type        | User ID | Name                           | Parent\n'\
        '==============================================================================================='

    TXN_LIST_HEADER = ' ID   | Date       | Type   |  Description                   | Payee                          |  Transfer Account              | Withdrawal | Deposit    | Balance\n'\
        '================================================================================================================================================================'

    NUM_TXNS_IN_PAGE = 50

    @staticmethod
    def get_page(items, num_txns_in_page, page=1):
        start = 0 + (page-1)*num_txns_in_page
        end = start+num_txns_in_page
        page_items = items[start:end]
        if end < len(items):
            more_items = True
        else:
            more_items = False
        return page_items, more_items

    def __init__(self, filename, print_file=None):
        self.storage = SQLiteStorage(filename)
        self.print = partial(print, file=print_file)

    def input(self, prompt='', prefill=None):
        #https://stackoverflow.com/a/2533142
        if (prefill is not None) and readline:
            readline.set_startup_hook(lambda: readline.insert_text(str(prefill)))
        self.print(prompt, end='')
        try:
            return input()
        finally:
            if (prefill is not None) and readline:
                readline.set_startup_hook()

    def _list_accounts(self):
        self.print(self.ACCOUNT_LIST_HEADER)
        for a in self.storage.get_accounts():
            if a.user_id:
                user_id = a.user_id
            else:
                user_id = ''
            if a.parent:
                parent = a.parent.name
            else:
                parent = ''
            self.print(' {0:<4} | {1:<11} | {2:<7} | {3:<30} | {4:<30}'.format(a.id, a.type.name, user_id[:7], a.name[:30], parent[:30]))

    def _get_and_save_account(self, account=None):
        acc_id = None
        name_prefill = acct_type_prefill = user_id_prefill = ''
        if account:
            acc_id = account.id
            name_prefill = account.name
            acct_type_prefill = account.type.value
            user_id_prefill = account.user_id
        name = self.input(prompt='  name: ', prefill=name_prefill)
        acct_type_options = ','.join(['%s-%s' % (t.value, t.name) for t in AccountType])
        acct_type = self.input(prompt='  type (%s): ' % acct_type_options, prefill=acct_type_prefill)
        user_id = self.input(prompt='  user id: ', prefill=user_id_prefill)
        parent_id = self.input(prompt='  parent account id: ')
        parent = None
        if parent_id:
            parent = self.storage.get_account(parent_id)
        self.storage.save_account(
                Account(id_=acc_id, name=name, type_=acct_type, user_id=user_id, parent=parent)
            )

    def _create_account(self):
        self.print('Create Account:')
        self._get_and_save_account()

    def _edit_account(self):
        acc_id = self.input('Account ID: ')
        account = self.storage.get_account(acc_id)
        self._get_and_save_account(account=account)

    def _list_account_txns(self, num_txns_in_page=None):
        if not num_txns_in_page:
            num_txns_in_page = self.NUM_TXNS_IN_PAGE
        acc_id = self.input('Account ID: ')
        ledger = self.storage.get_ledger(acc_id)
        ledger_balances = ledger.get_current_balances()
        summary_line = f'{ledger.account.name} (Current balance: {ledger_balances.current}; Cleared: {ledger_balances.current_cleared})'
        self.print(summary_line)
        self.print(self.TXN_LIST_HEADER)
        txns = ledger.get_sorted_txns_with_balance()
        page_index = 1
        while True:
            paged_txns, more_txns = CLI.get_page(txns, num_txns_in_page=num_txns_in_page, page=page_index)
            for t in paged_txns:
                tds = get_display_strings_for_ledger(self.storage.get_account(acc_id), t)
                self.print(' {8:<4} | {0:<10} | {1:<6} | {2:<30} | {3:<30} | {4:30} | {5:<10} | {6:<10} | {7:<10}'.format(
                    tds['txn_date'], tds['txn_type'], tds['description'], tds['payee'], tds['categories'], tds['withdrawal'], tds['deposit'], t.balance, t.id)
                )
            if more_txns:
                prompt = '(n)ext page '
                if page_index > 1:
                    prompt = '(p)revious page, ' + prompt
                x = self.input(prompt=prompt)
                if x == 'n':
                    page_index += 1
                elif x == 'p':
                    page_index -= 1
                else:
                    break
            else:
                break

    def _get_common_txn_info(self, txn=None):
        '''get pieces of data common to txns and scheduled txns'''
        info = {}
        self.print('Splits:')
        splits = {}
        if txn:
            for account, orig_amount in txn.splits.items():
                amount = self.input(prompt='%s amount: ' % account.name, prefill=orig_amount)
                if amount:
                    splits[account] = amount
        while True:
            acct_id = self.input(prompt='new account ID: ')
            if acct_id:
                amt = self.input(prompt=' amount: ')
                if amt:
                    splits[self.storage.get_account(acct_id)] = amt
                else:
                    break
            else:
                break
        info['splits'] = splits
        txn_type_prefill = ''
        payee_prefill = ''
        description_prefill = ''
        status_prefill = ''
        if txn:
            txn_type_prefill = txn.txn_type or ''
            if txn.payee:
                payee_prefill = '\'%s' % txn.payee.name
            else:
                payee_prefill = ''
            description_prefill = txn.description or ''
            status_prefill = txn.status or ''
        info['txn_type'] = self.input(prompt='  type: ', prefill=txn_type_prefill)
        payee = self.input(prompt='  payee (id or \'name): ', prefill=payee_prefill)
        if payee == 'p':
            self._list_payees()
            payee = self.input(prompt='  payee (id or \'name): ')
        if payee.startswith("'"):
            info['payee'] = Payee(payee[1:])
        else:
            info['payee'] = self.storage.get_payee(payee)
        info['description'] = self.input(prompt='  description: ', prefill=description_prefill)
        info['status'] = self.input(prompt='  status: ', prefill=status_prefill)
        return info

    def _get_and_save_txn(self, txn=None):
        info = {}
        if txn:
            if isinstance(txn, ScheduledTransaction):
                date_prefill = date.today()
            else:
                info['id_'] = txn.id
                date_prefill = txn.txn_date
        else:
            date_prefill = ''
        info['txn_date'] = self.input(prompt='  date: ', prefill=date_prefill)
        info.update(self._get_common_txn_info(txn=txn))
        self.storage.save_txn(Transaction(**info))

    def _create_txn(self):
        self.print('Create Transaction:')
        self._get_and_save_txn()

    def _edit_txn(self):
        txn_id = self.input(prompt='Txn ID: ')
        txn = self.storage.get_txn(txn_id)
        self._get_and_save_txn(txn=txn)

    def _list_payees(self):
        for p in self.storage.get_payees():
            self.print('%s: %s' % (p.id, p.name))

    def _list_scheduled_txns(self):
        for st in self.storage.get_scheduled_transactions():
            self.print(st)
        self._enter_scheduled_txn()

    def _enter_scheduled_txn(self):
        self.print('Enter next transaction for a scheduled transaction:')
        while True:
            scheduled_txn_id = self.input('Scheduled txn ID (blank to quit): ')
            if scheduled_txn_id:
                scheduled_txn = self.storage.get_scheduled_transaction(scheduled_txn_id)
                self._get_and_save_txn(txn=scheduled_txn)
                scheduled_txn.next_txn_entered()
                self.storage.save_scheduled_transaction(scheduled_txn)
            else:
                break

    def _display_scheduled_txn(self):
        scheduled_txn_id = self.input('Enter scheduled txn ID: ')
        scheduled_txn = self.storage.get_scheduled_transaction(scheduled_txn_id)
        self.print('%s: %s' % (scheduled_txn.id, scheduled_txn.name))
        self.print('  frequency: %s' % scheduled_txn.frequency.name)
        self.print('  next due date: %s' % scheduled_txn.next_due_date)
        splits_str = '; '.join(['%s-%s: %s' % (acc.id, acc.name, str(scheduled_txn.splits[acc])) for acc in scheduled_txn.splits.keys()])
        self.print('  splits: %s' % splits_str)
        if scheduled_txn.txn_type:
            self.print('  txn type: %s' % scheduled_txn.txn_type)
        if scheduled_txn.payee:
            self.print('  payee: %s' % scheduled_txn.payee)
        if scheduled_txn.description:
            self.print('  description: %s' % scheduled_txn.description)

    def _get_and_save_scheduled_txn(self, scheduled_txn=None):
        name = self.input('  name: ')
        frequency_options = ','.join(['%s-%s' % (f.value, f.name) for f in ScheduledTransactionFrequency])
        if scheduled_txn:
            frequency_prefill = scheduled_txn.frequency
        else:
            frequency_prefill = ''
        frequency = self.input('  frequency (%s): ' % frequency_options, prefill=frequency_prefill)
        if scheduled_txn:
            due_date_prefill = scheduled_txn.next_due_date
        else:
            due_date_prefill = ''
        next_due_date = self.input('  next due date (yyyy-mm-dd): ', prefill=due_date_prefill)
        common_info = self._get_common_txn_info(txn=scheduled_txn)
        id_ = None
        if scheduled_txn:
            id_ = scheduled_txn.id
        self.storage.save_scheduled_transaction(
            ScheduledTransaction(
                name=name,
                frequency=frequency,
                next_due_date=next_due_date,
                id_=id_,
                **common_info,
            )
        )

    def _create_scheduled_txn(self):
        self.print('Create Scheduled Transaction:')
        self._get_and_save_scheduled_txn()

    def _edit_scheduled_txn(self):
        scheduled_txn_id = self.input('Enter scheduled txn ID: ')
        scheduled_txn = self.storage.get_scheduled_transaction(scheduled_txn_id)
        self._get_and_save_scheduled_txn(scheduled_txn=scheduled_txn)

    def _list_budgets(self):
        for b in self.storage.get_budgets():
            self.print(b)

    def _display_budget(self):
        budget_id = self.input('Enter budget ID: ')
        budget = self.storage.get_budget(budget_id)
        self.print(budget)
        account_budget_info = budget.get_budget_data()
        for account, info in account_budget_info.items():
            self.print(f' {account}: {info}')

    def _display_budget_report(self):
        budget_id = self.input('Enter budget ID: ')
        budget = self.storage.get_budget(budget_id)
        self.print(budget)
        budget_report = budget.get_report_display()
        for account, info in budget_report['income'].items():
            self.print(f'{account}: {info}')
        for account, info in budget_report['expense'].items():
            self.print(f'{account}: {info}')

    def _create_budget(self):
        self.print('Create Budget:')
        start_date = self.input(prompt='  start date: ')
        end_date = self.input(prompt='  end date: ')
        account_info = {}
        while True:
            acct_id = self.input('new account ID: ')
            if acct_id:
                amt = self.input(' amount: ')
                if amt:
                    account = self.storage.get_account(acct_id)
                    account_info[account] = {'amount': amt}
                    carryover = self.input(' carryover: ')
                    if carryover:
                        account_info[account]['carryover'] = carryover
                    notes = self.input(' notes: ')
                    if notes:
                        account_info[account]['notes'] = notes
                else:
                    break
            else:
                break
        self.storage.save_budget(
                Budget(
                    start_date=start_date,
                    end_date=end_date,
                    account_budget_info=account_info,
                )
            )

    def _edit_budget(self):
        budget_id = self.input('Enter budget ID: ')
        budget = self.storage.get_budget(budget_id)
        start_date = self.input(prompt='  start date: ')
        end_date = self.input(prompt='  end date: ')
        account_info = {}
        #budget data includes all expense & income accounts
        for account, info in budget.get_budget_data().items():
            amt = self.input(' amount: ', prefill=info.get('amount', ''))
            account_info[account] = {'amount': amt}
            carryover = self.input(' carryover: ', prefill=info.get('carryover', ''))
            if carryover:
                account_info[account]['carryover'] = carryover
            notes = self.input(' notes: ', prefill=info.get('notes', ''))
            if notes:
                account_info[account]['notes'] = notes
        self.storage.save_budget(
                Budget(
                    start_date=start_date,
                    end_date=end_date,
                    account_budget_info=account_info,
                )
            )

    def _print_help(self, info):
        help_msg = 'h - help'
        for cmd, info in info.items():
            help_msg += f'\n{cmd} - {info["description"]}'
        help_msg += '\nq - quit'
        self.print(help_msg.strip())

    def _command_loop(self, info):
        while True:
            cmd = self.input('>>> ')
            try:
                if cmd == 'h':
                    self._print_help(info)
                elif cmd == 'q':
                    raise EOFError()
                else:
                    info[cmd]['function']()
            except KeyError:
                self.print('Invalid command: "%s"' % cmd)

    def run(self):
        info = {
            'a': {'description': 'list accounts', 'function': self._list_accounts},
            'ac': {'description': 'create account', 'function': self._create_account},
            'ae': {'description': 'edit account', 'function': self._edit_account},
            't': {'description': 'list txns', 'function': self._list_account_txns},
            'tc': {'description': 'create transaction', 'function': self._create_txn},
            'te': {'description': 'edit transaction', 'function': self._edit_txn},
            'st': {'description': 'list scheduled transactions', 'function': self._list_scheduled_txns},
            'stc': {'description': 'create scheduled transaction', 'function': self._create_scheduled_txn},
            'std': {'description': 'display scheduled transaction', 'function': self._display_scheduled_txn},
            'ste': {'description': 'edit scheduled transaction', 'function': self._edit_scheduled_txn},
            'b': {'description': 'list budgets', 'function': self._list_budgets},
            'bd': {'description': 'display budget', 'function': self._display_budget},
            'bdr': {'description': 'display budget report', 'function': self._display_budget_report},
            'bc': {'description': 'create budget', 'function': self._create_budget},
            'be': {'description': 'edit budget', 'function': self._edit_budget},
        }
        self.print('Command-line PFT')
        self._print_help(info)
        try:
            self._command_loop(info)
        except (EOFError, KeyboardInterrupt):
            self.print('\n')
        except:
            import traceback
            self.print(traceback.format_exc())
            sys.exit(1)


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

    if args.file_name and not os.path.exists(args.file_name):
        raise Exception('no such file: "%s"' % args.file_name)

    if args.cli:
        if not args.file_name:
            print('file name argument required for CLI mode')
            sys.exit(1)
        CLI(args.file_name).run()
        sys.exit(0)

    try:
        from PySide2 import QtWidgets
    except ImportError:
        install_qt_for_python()

    app = QtWidgets.QApplication([])
    if args.file_name:
        gui = GUI_QT(args.file_name)
    else:
        gui = GUI_QT()
    app.exec_()
