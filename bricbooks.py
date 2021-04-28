'''
Architecture:
    Business Objects - Account, Category, Transaction, Ledger, ... classes. They know nothing about the storage or UI.
    Storage - SQLiteStorage (or another storage class). Handles saving & retrieving business objects from storage.
    Engine - has a storage object, and implements application logic.
    Outer Layer - UI (Qt, console). Has an engine object, and handles displaying data to the user and sending user actions to the engine.
    No objects should use private/hidden members of other objects.
'''
from collections import namedtuple
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from fractions import Fraction
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


__version__ = '0.2.dev'
TITLE = f'bricbooks {__version__}'
PYSIDE2_VERSION = '5.15.1'
CUR_DIR = os.getcwd()
LOG_FILENAME = 'bricbooks.log'


def log(msg):
    log_filepath = CUR_DIR / LOG_FILENAME
    with open(log_filepath, 'ab') as f:
        f.write(msg.encode('utf8'))


class CommodityType(Enum):
    CURRENCY = 'currency'
    SECURITY = 'security'


class AccountType(Enum):
    ASSET = 'asset'
    SECURITY = 'security' #for mutual funds, stocks, ... anything traded in shares
    LIABILITY = 'liability'
    EQUITY = 'equity'
    INCOME = 'income'
    EXPENSE = 'expense'


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
    from PySide2 import QtWidgets, QtGui, QtCore
except ImportError:
    pass


class InvalidCommodityError(RuntimeError):
    pass

class InvalidAccountError(RuntimeError):
    pass

class InvalidAccountNameError(InvalidAccountError):
    pass

class InvalidPayeeError(RuntimeError):
    pass

class InvalidAmount(RuntimeError):
    pass

class InvalidQuantity(RuntimeError):
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


class Commodity:

    def __init__(self, id_=None, type_=None, code=None, name=None):
        self.id = id_
        if not type_:
            raise InvalidCommodityError('Commodity must have a type')
        if not code:
            raise InvalidCommodityError('Commodity must have a code')
        if not name:
            raise InvalidCommodityError('Commodity must have a name')
        self.type = self._check_type(type_)
        self.code = code
        self.name = name

    def _check_type(self, type_):
        if isinstance(type_, CommodityType):
            return type_
        else:
            try:
                return CommodityType(type_)
            except ValueError:
                raise InvalidCommityError('Invalid commodity type "%s"' % type_)


class Account:

    def __init__(self, id_=None, type_=None, commodity=None, number=None, name=None, parent=None):
        self.id = id_
        if not type_:
            raise InvalidAccountError('Account must have a type')
        if not commodity:
            raise InvalidAccountError('Account must have a commodity')
        if not name:
            raise InvalidAccountNameError('Account must have a name')
        self.type = self._check_type(type_)
        self.commodity = commodity
        self.number = number or None
        self.name = name
        self.parent = parent

    def __str__(self):
        if self.number:
            return '%s - %s' % (self.number, self.name)
        else:
            return self.name

    def __repr__(self):
        return self.__str__()

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
                return AccountType(type_)
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


def get_validated_amount(value):
    amount = None
    #try to only allow exact values (eg. no floats)
    if isinstance(value, (int, str, Fraction)):
        try:
            amount = Fraction(value)
        except InvalidOperation:
            raise InvalidAmount('error generating Fraction from "{value}"')
    else:
        raise InvalidAmount(f'invalid value type: {type(value)} {value}')
    if (100 % amount.denominator) != 0:
        raise InvalidAmount('no fractions of cents allowed: %s' % value)
    return amount


def get_validated_quantity(value):
    quantity = None
    #try to only allow exact values (eg. no floats)
    if isinstance(value, (int, str, Fraction)):
        try:
            quantity = Fraction(value)
        except InvalidOperation:
            raise InvalidQuantity('error generating Fraction from "{value}"')
    else:
        raise InvalidQuantity(f'invalid value type: {type(value)} {value}')
    return quantity


def fraction_to_decimal(f):
    return Decimal(f.numerator) / Decimal(f.denominator)


def amount_display(amount):
    return '{0:,}'.format(fraction_to_decimal(amount))


def check_txn_splits(splits):
    if not splits or len(splits.items()) < 2:
        raise InvalidTransactionError('transaction must have at least 2 splits')
    total = Fraction(0)
    for account, info in splits.items():
        if not account:
            raise InvalidTransactionError('must have a valid account in splits')
        try:
            amount = get_validated_amount(info['amount'])
        except InvalidAmount as e:
            raise InvalidTransactionError('invalid split: %s' % e)
        if 'quantity' not in info:
            info['quantity'] = amount
        info['quantity'] = get_validated_quantity(info['quantity'])
        total += amount
        info['amount'] = amount
        if 'status' in info:
            status = Transaction.handle_status(info['status'])
            if status:
                info['status'] = status
            else:
                info.pop('status')
    if total != Fraction(0):
        amounts = []
        for account, info in splits.items():
            amounts.append(amount_display(info['amount']))
        raise InvalidTransactionError("splits don't balance: %s" % ', '.join(amounts))
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
    def splits_from_user_info(account, deposit, withdrawal, input_categories, status=None):
        #input_categories: can be an account, or a dict like {acc: {'amount': '5', 'status': 'C'}, ...}
        splits = {}
        try:
            amount = get_validated_amount(deposit or withdrawal)
        except InvalidAmount as e:
            raise InvalidTransactionError('invalid deposit/withdrawal: %s' % e)
        if deposit:
            splits[account] = {'amount': amount}
        else:
            splits[account] = {'amount': amount * -1}
        if isinstance(input_categories, Account):
            if deposit:
                splits[input_categories] = {'amount': amount * -1}
            else:
                splits[input_categories] = {'amount': amount}
        elif isinstance(input_categories, dict):
            #don't need to negate any of the values here - should already be set correctly when user enters splits
            for acc, split_info in input_categories.items():
                if isinstance(split_info, dict) and 'amount' in split_info:
                    splits[acc] = split_info
                else:
                    raise InvalidTransactionError(f'invalid input categories: {input_categories}')
        else:
            raise InvalidTransactionError(f'invalid input categories: {input_categories}')
        status = Transaction.handle_status(status)
        if status:
            splits[account]['status'] = status
        return splits

    @staticmethod
    def from_user_info(account, deposit, withdrawal, txn_date, txn_type, categories, payee, description, status, id_=None):
        splits = Transaction.splits_from_user_info(account, deposit, withdrawal, categories, status)
        return Transaction(
                splits=splits,
                txn_date=txn_date,
                txn_type=txn_type,
                payee=payee,
                description=description,
                id_=id_
            )

    def __init__(self, txn_date=None, txn_type=None, splits=None, payee=None, description=None, id_=None):
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

    def update_reconciled_state(self, account):
        #this updates the txn, instead of creating a new one - might want to change it
        cur_status = self.splits[account].get('status', None)
        if cur_status == Transaction.CLEARED:
            self.splits[account]['status'] = Transaction.RECONCILED
        elif cur_status == Transaction.RECONCILED:
            self.splits[account].pop('status')
        else:
            self.splits[account]['status'] = Transaction.CLEARED


def _categories_display(splits, main_account):
    if len(splits.keys()) == 2:
        for account in splits.keys():
            if account != main_account:
                return str(account)
    return 'multiple'


def get_display_strings_for_ledger(account, txn):
    '''txn can be either Transaction or ScheduledTransaction'''
    amount = txn.splits[account]['amount']
    if amount < Fraction(0):
        #make negative amount display as positive
        withdrawal = amount_display(amount * Fraction('-1'))
        deposit = ''
    else:
        withdrawal = ''
        deposit = amount_display(amount)
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
        display_strings['txn_date'] = str(txn.next_due_date)
    else:
        display_strings['status'] = txn.splits[account].get('status', '')
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

    def _get_balance_field(self):
        if self.account.type == AccountType.SECURITY:
            field = 'quantity'
        else:
            field = 'amount'
        return field

    def _add_balance_to_txns(self, txns):
        #txns must be sorted in chronological order (not reversed) already
        txns_with_balance = []
        balance = Fraction(0)
        field = self._get_balance_field()
        for t in txns:
            balance = balance + t.splits[self.account][field]
            t.balance = balance
            txns_with_balance.append(t)
        return txns_with_balance

    def get_sorted_txns_with_balance(self, reverse=False):
        if reverse:
            sorted_txns = self._sort_txns(self._txns.values())
            sorted_txns_with_balance = self._add_balance_to_txns(sorted_txns)
            return list(reversed(sorted_txns_with_balance))
        else:
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

    def get_current_balances_for_display(self):
        sorted_txns = self.get_sorted_txns_with_balance()
        current = Fraction(0)
        current_cleared = Fraction(0)
        today = date.today()
        field = self._get_balance_field()
        for t in sorted_txns:
            if t.txn_date <= today:
                current = t.balance
                if t.splits[self.account].get('status', None) in [Transaction.CLEARED, Transaction.RECONCILED]:
                    current_cleared = current_cleared + t.splits[self.account][field]
        return LedgerBalances(
                current=amount_display(current),
                current_cleared=amount_display(current_cleared),
            )

    def get_payees(self):
        payees = set()
        for txn in self._txns.values():
            if txn.payee:
                payees.add(txn.payee)
        return sorted(list(payees), key=lambda p: p.name)

    def get_scheduled_transactions_due(self):
        all_scheduled_txns = list(self._scheduled_txns.values())
        return [t for t in all_scheduled_txns if t.is_due()]


def splits_display(splits):
    account_amt_list = []
    for account, info in splits.items():
        amount = info['amount']
        account_amt_list.append(f'{account.name}: {amount_display(amount)}')
    return '; '.join(account_amt_list)


class ScheduledTransactionFrequency(Enum):
    WEEKLY = 'weekly'
    MONTHLY = 'monthly'
    QUARTERLY = 'quarterly'
    YEARLY = 'yearly'


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
                self.frequency = ScheduledTransactionFrequency(frequency)
            except ValueError:
                raise InvalidScheduledTransactionError('invalid frequency "%s"' % frequency)
        self.next_due_date = self._check_date(next_due_date)
        self.splits = check_txn_splits(splits)
        self.txn_type = txn_type
        if payee:
            if isinstance(payee, str):
                self.payee = Payee(name=payee)
            elif isinstance(payee, Payee):
                self.payee = payee
            else:
                raise InvalidScheduledTransactionError('invalid payee: %s' % payee)
        else:
            self.payee = None
        self.description = description
        self.status = Transaction.handle_status(status)
        self.id = id_

    def __str__(self):
        return '%s: %s (%s %s) (%s)' % (self.id, self.name, self.frequency.name, self.next_due_date, splits_display(self.splits))

    def _check_date(self, dt):
        try:
            return get_date(dt)
        except Exception:
            raise InvalidScheduledTransactionError('invalid date "%s"' % dt)

    def is_due(self):
        if self.next_due_date <= date.today():
            return True
        return False

    def advance_to_next_due_date(self):
        #update next_due_date since the txn has been entered
        if self.frequency == ScheduledTransactionFrequency.WEEKLY:
            self.next_due_date = self.next_due_date + timedelta(days=7)
        elif self.frequency == ScheduledTransactionFrequency.MONTHLY:
            self.next_due_date = increment_month(self.next_due_date)
        elif self.frequency == ScheduledTransactionFrequency.QUARTERLY:
            self.next_due_date = increment_quarter(self.next_due_date)
        elif self.frequency == ScheduledTransactionFrequency.YEARLY:
            self.next_due_date = increment_year(self.next_due_date)
        else:
            raise Exception('invalid frequency %s' % self.frequency)


class Budget:
    '''Budget information that's entered by the user - no defaults or calculated values, but
    empty strings are dropped (so we can pass empty string from user form), and strings are converted to
    Fraction values. Note: all accounts are passed in - if there's no budget info, it just has an empty {}.
    '''

    @staticmethod
    def round_percent_available(percent):
        return percent.quantize(Decimal('1.'), rounding=ROUND_HALF_UP)

    @staticmethod
    def get_current_status(current_date, start_date, end_date, remaining_percent):
        if current_date and current_date < end_date and current_date > start_date:
            days_in_budget = (end_date - start_date).days
            days_passed = (current_date - start_date).days
            days_percent_remaining = Fraction(100) - (Fraction(days_passed, days_in_budget) * Fraction(100))
            difference = days_percent_remaining - remaining_percent
            difference = Budget.round_percent_available(fraction_to_decimal(difference))
            if difference > 0:
                return f'+{difference}%'
            else:
                return f'{difference}%'
        return ''

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
                        if isinstance(value, Fraction) and value:
                            keep_info[key] = value
                        elif not value:
                            continue
                        else:
                            try:
                                amt = get_validated_amount(value)
                                if amt:
                                    keep_info[key] = amt
                            except InvalidAmount as e:
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

    def get_report_display(self, current_date=None):
        '''adds income & spending data to budget data, & converts to strings, for a budget report to display
        { 'expense': {
                expense_account1: {'amount': '10', 'income': '5', 'carryover': '5', 'total_budget': '20', 'spent': '10', 'remaining': '10', 'remaining_percent': '50%', 'notes': 'note1'},
                expense_account2: {'amount': '5', 'total_budget': '5', 'remaining': '5', 'remaining_percent': '100%'},
                expense_account3: {},
            },
          'income': {
                income_account1: {'amount': '10', 'income': '7', 'remaining': '3', 'remaining_percent': '30%', 'notes': 'note2', 'current_status': '-1.2%'}, #based on date passed in, should be at 71.2% (only relevant if date is within the budget period (get percentage through budget period, compare to remaining_percent)
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
                carryover = report_info.get('carryover', Fraction(0))
                income = report_info.get('income', Fraction(0))
                if account.type == AccountType.EXPENSE:
                    report_info['total_budget'] = report_info['amount'] + carryover + income
                    spent = report_info.get('spent', Fraction(0))
                    report_info['remaining'] = report_info['total_budget'] - spent
                    try:
                        percent_available = (report_info['remaining'] / report_info['total_budget']) * Fraction(100)
                        report_info['remaining_percent'] = '{}%'.format(Budget.round_percent_available(fraction_to_decimal(percent_available)))
                        report_info['current_status'] = Budget.get_current_status(current_date, self.start_date, self.end_date, percent_available)
                    except InvalidOperation:
                        report_info['remaining_percent'] = 'error'
                else:
                    report_info['remaining'] = report_info['amount'] - income
                    remaining_percent = Fraction(100) - ((income / report_info['amount']) * Fraction(100))
                    report_info['remaining_percent'] = '{}%'.format(Budget.round_percent_available(fraction_to_decimal(remaining_percent)))
                    report_info['current_status'] = Budget.get_current_status(current_date, self.start_date, self.end_date, remaining_percent)
            for key in report_info.keys():
                if report_info[key] == Fraction(0):
                    report_info[key] = ''
                else:
                    if isinstance(report_info[key], Fraction):
                        report_info[key] = amount_display(report_info[key])
                    else:
                        report_info[key] = str(report_info[key])
            if account.type == AccountType.EXPENSE:
                report['expense'][account] = report_info
            else:
                report['income'][account] = report_info
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
            file_path = os.path.join(CUR_DIR, conn_name)
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
        conn.execute('CREATE TABLE commodities (id INTEGER PRIMARY KEY, type TEXT NOT NULL, code TEXT UNIQUE, name TEXT NOT NULL, trading_currency_id INTEGER, trading_market TEXT,'\
                'FOREIGN KEY(trading_currency_id) REFERENCES commodities(id))')
        conn.execute('CREATE TABLE institutions (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, address TEXT, routing_number TEXT, bic TEXT)')
        conn.execute('CREATE TABLE accounts (id INTEGER PRIMARY KEY, type TEXT NOT NULL, commodity_id INTEGER NOT NULL, institution_id INTEGER, number TEXT UNIQUE, name TEXT NOT NULL, parent_id INTEGER, closed TEXT,'\
                'FOREIGN KEY(parent_id) REFERENCES accounts(id), FOREIGN KEY(commodity_id) REFERENCES commodities(id), FOREIGN KEY(institution_id) REFERENCES institutions(id), UNIQUE(name, parent_id))')
        conn.execute('CREATE TABLE budgets (id INTEGER PRIMARY KEY, name TEXT, start_date TEXT NOT NULL, end_date TEXT NOT NULL)')
        conn.execute('CREATE TABLE budget_values (id INTEGER PRIMARY KEY, budget_id INTEGER NOT NULL, account_id INTEGER NOT NULL, amount TEXT, carryover TEXT, notes TEXT,'\
                'FOREIGN KEY(budget_id) REFERENCES budgets(id), FOREIGN KEY(account_id) REFERENCES accounts(id))')
        conn.execute('CREATE TABLE payees (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, notes TEXT)')
        conn.execute('CREATE TABLE scheduled_transactions (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, frequency TEXT NOT NULL, next_due_date TEXT NOT NULL, txn_type TEXT, payee_id INTEGER, description TEXT,'\
                'FOREIGN KEY(payee_id) REFERENCES payees(id))')
        conn.execute('CREATE TABLE scheduled_transaction_splits (id INTEGER PRIMARY KEY, scheduled_txn_id INTEGER NOT NULL, account_id INTEGER NOT NULL, value TEXT, quantity TEXT, reconciled_state TEXT, description TEXT,'\
                'FOREIGN KEY(scheduled_txn_id) REFERENCES scheduled_transactions(id), FOREIGN KEY(account_id) REFERENCES accounts(id))')
        conn.execute('CREATE TABLE transactions (id INTEGER PRIMARY KEY, currency_id INTEGER NOT NULL, type TEXT, date TEXT, payee_id INTEGER, description TEXT, date_entered TEXT,'\
                'FOREIGN KEY(currency_id) REFERENCES commodities(id), FOREIGN KEY(payee_id) REFERENCES payees(id))')
        conn.execute('CREATE TABLE transaction_splits (id INTEGER PRIMARY KEY, txn_id INTEGER NOT NULL, account_id INTEGER NOT NULL, value TEXT, quantity TEXT, reconciled_state TEXT, description TEXT, action TEXT,'\
                'FOREIGN KEY(txn_id) REFERENCES transactions(id), FOREIGN KEY(account_id) REFERENCES accounts(id))')
        conn.execute('CREATE TABLE misc (key TEXT UNIQUE NOT NULL, value TEXT)')
        conn.execute('INSERT INTO misc(key, value) VALUES(?, ?)', ('schema_version', '0'))
        conn.execute('INSERT INTO commodities(type, code, name) VALUES(?, ?, ?)', (CommodityType.CURRENCY.value, 'USD', 'US Dollar'))

    def get_commodity(self, id_=None, code=None):
        if id_:
            record = self._db_connection.execute('SELECT id, type, code, name FROM commodities WHERE id = ?', (id_,)).fetchone()
        elif code:
            record = self._db_connection.execute('SELECT id, type, code, name FROM commodities WHERE code = ?', (code,)).fetchone()
        else:
            raise Exception('get_commodity: must pass in id_ or code')
        return Commodity(id_=record[0], type_=CommodityType(record[1]), code=record[2], name=record[3])

    def get_commodities(self):
        currencies = []
        records = self._db_connection.execute('SELECT id, type, code, name FROM commodities').fetchall()
        for r in records:
            currencies.append(Commodity(id_=r[0], type_=CommodityType(r[1]), code=r[2], name=r[3]))
        return currencies

    def save_commodity(self, commodity):
        c = self._db_connection.cursor()
        c.execute('INSERT INTO commodities(type, code, name) VALUES(?, ?, ?)', (commodity.type.value, commodity.code, commodity.name))
        commodity.id = c.lastrowid
        self._db_connection.commit()

    def get_account(self, id_=None, number=None, name=None):
        if id_:
            account_info = self._db_connection.execute('SELECT id, type, commodity_id, number, name, parent_id FROM accounts WHERE id = ?', (id_,)).fetchone()
            if not account_info:
                raise Exception(f'no account with id "{id_}"')
        elif number:
            account_info = self._db_connection.execute('SELECT id, type, commodity_id, number, name, parent_id FROM accounts WHERE number = ?', (number,)).fetchone()
            if not account_info:
                raise Exception(f'no account with number "{number}"')
        elif name:
            account_info = self._db_connection.execute('SELECT id, type, commodity_id, number, name, parent_id FROM accounts WHERE name = ?', (name,)).fetchone()
            if not account_info:
                raise Exception(f'no account with name "{name}"')
        else:
            raise Exception('get_account: must pass in id_ or number or name')
        commodity = self.get_commodity(account_info[2])
        parent = None
        if account_info[5]:
            parent = self.get_account(account_info[5])
        return Account(
                id_=account_info[0],
                type_=AccountType(account_info[1]),
                commodity=commodity,
                number=account_info[3],
                name=account_info[4],
                parent=parent,
            )

    def save_account(self, account):
        c = self._db_connection.cursor()
        parent_id = None
        if account.parent:
            parent_id = account.parent.id
        if account.id:
            c.execute('UPDATE accounts SET type = ?, commodity_id = ?, number = ?, name = ?, parent_id = ? WHERE id = ?',
                    (account.type.value, account.commodity.id, account.number, account.name, parent_id, account.id))
            if c.rowcount < 1:
                raise Exception('no account with id %s to update' % account.id)
        else:
            c.execute('INSERT INTO accounts(type, commodity_id, number, name, parent_id) VALUES(?, ?, ?, ?, ?)', (account.type.value, account.commodity.id, account.number, account.name, parent_id))
            account.id = c.lastrowid
        self._db_connection.commit()

    def get_payee(self, id_=None, name=None):
        '''return None if object can't be found for whatever reason'''
        if id_:
            info = self._db_connection.execute('SELECT id, name, notes FROM payees WHERE id = ?', (id_,)).fetchone()
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
            for type_ in [AccountType.ASSET, AccountType.SECURITY, AccountType.LIABILITY, AccountType.INCOME, AccountType.EXPENSE, AccountType.EQUITY]:
                accounts.extend(self._get_accounts_by_type(type_))
            return accounts

    def _txn_from_db_record(self, db_info=None):
        if not db_info:
            raise InvalidTransactionError('no db_info to construct transaction')
        id_, currency_id, txn_type, txn_date, payee_id, description, date_entered = db_info
        txn_date = get_date(txn_date)
        payee = self.get_payee(payee_id)
        cursor = self._db_connection.cursor()
        splits = {}
        split_records = cursor.execute('SELECT account_id, value, quantity, reconciled_state FROM transaction_splits WHERE txn_id = ?', (id_,))
        if split_records:
            for split_record in split_records:
                account_id = split_record[0]
                account = self.get_account(account_id)
                splits[account] = {'amount': split_record[1], 'quantity': split_record[2]}
                if split_record[3]:
                    splits[account]['status'] = split_record[3]
        return Transaction(splits=splits, txn_date=txn_date, txn_type=txn_type, payee=payee, description=description, id_=id_)

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
            c.execute('UPDATE transactions SET type = ?, date = ?, payee_id = ?, description = ? WHERE id = ?',
                (txn.txn_type, txn.txn_date.strftime('%Y-%m-%d'), payee, txn.description, txn.id))
            if c.rowcount < 1:
                raise Exception('no txn with id %s to update' % txn.id)
        else:
            c.execute('INSERT INTO transactions(currency_id, type, date, payee_id, description) VALUES(?, ?, ?, ?, ?)',
                (1, txn.txn_type, txn.txn_date.strftime('%Y-%m-%d'), payee, txn.description))
            txn.id = c.lastrowid
        #update transaction splits
        splits_db_info = c.execute('SELECT account_id FROM transaction_splits WHERE txn_id = ?', (txn.id,)).fetchall()
        old_txn_split_account_ids = [r[0] for r in splits_db_info]
        new_txn_split_account_ids = [a.id for a in txn.splits.keys()]
        split_account_ids_to_delete = set(old_txn_split_account_ids) - set(new_txn_split_account_ids)
        for account_id in split_account_ids_to_delete:
            c.execute('DELETE FROM transaction_splits WHERE txn_id = ? AND account_id = ?', (txn.id, account_id))
        for account, info in txn.splits.items():
            if not account.id:
                self.save_account(account)
            amount = info['amount']
            amount = f'{amount.numerator}/{amount.denominator}'
            quantity = info['quantity']
            quantity = f'{quantity.numerator}/{quantity.denominator}'
            status = info.get('status', None)
            if account.id in old_txn_split_account_ids:
                c.execute('UPDATE transaction_splits SET value = ?, quantity = ?, reconciled_state = ? WHERE txn_id = ? AND account_id = ?', (amount, quantity, status, txn.id, account.id))
            else:
                c.execute('INSERT INTO transaction_splits(txn_id, account_id, value, quantity, reconciled_state) VALUES(?, ?, ?, ?, ?)', (txn.id, account.id, amount, quantity, status))
        self._db_connection.commit()

    def delete_txn(self, txn_id):
        self._db_connection.execute('DELETE FROM transaction_splits WHERE txn_id = ?', (txn_id,))
        self._db_connection.execute('DELETE FROM transactions WHERE id = ?', (txn_id,))
        self._db_connection.commit()

    def get_ledger(self, account):
        if not isinstance(account, Account):
            account = self.get_account(account)
        ledger = Ledger(account=account)
        db_txn_id_records = self._db_connection.execute('SELECT txn_id FROM transaction_splits WHERE account_id = ?', (account.id,)).fetchall()
        txn_ids = set([r[0] for r in db_txn_id_records])
        for txn_id in txn_ids:
            txn = self.get_txn(txn_id)
            ledger.add_transaction(txn)
        db_scheduled_txn_id_records = self._db_connection.execute('SELECT scheduled_txn_id FROM scheduled_transaction_splits WHERE account_id = ?', (account.id,)).fetchall()
        scheduled_txn_ids = set(r[0] for r in db_scheduled_txn_id_records)
        for scheduled_txn_id in scheduled_txn_ids:
            ledger.add_scheduled_transaction(self.get_scheduled_transaction(scheduled_txn_id))
        return ledger

    def save_budget(self, budget):
        c = self._db_connection.cursor()
        if budget.id:
            c.execute('UPDATE budgets SET name = ?, start_date = ?, end_date = ? WHERE id = ?',
                (budget.name, str(budget.start_date), str(budget.end_date), budget.id))
            #handle budget_values
            values_db_info = c.execute('SELECT account_id FROM budget_values WHERE budget_id = ?', (budget.id,)).fetchall()
            old_account_ids = [r[0] for r in values_db_info]
            budget_data = budget.get_budget_data()
            new_account_ids = [a.id for a in budget_data.keys()]
            account_ids_to_delete = set(old_account_ids) - set(new_account_ids)
            for account_id in account_ids_to_delete:
                c.execute('DELETE FROM budget_values WHERE budget_id = ? AND account_id = ?', (budget.id, account_id))
            for account, info in budget_data.items():
                if info:
                    carryover = str(info.get('carryover', ''))
                    notes = info.get('notes', '')
                    if account.id in old_account_ids:
                        values = (str(info['amount']), carryover, notes, budget.id, account.id)
                        c.execute('UPDATE budget_values SET amount = ?, carryover = ?, notes = ? WHERE budget_id = ? AND account_id = ?', values)
                    else:
                        values = (budget.id, account.id, str(info['amount']), carryover, notes)
                        c.execute('INSERT INTO budget_values(budget_id, account_id, amount, carryover, notes) VALUES (?, ?, ?, ?, ?)', values)
        else:
            c.execute('INSERT INTO budgets(start_date, end_date) VALUES(?, ?)', (budget.start_date, budget.end_date))
            budget.id = c.lastrowid
            budget_data = budget.get_budget_data()
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
            spent = Fraction(0)
            income = Fraction(0)
            txn_splits_records = self._db_connection.execute('SELECT transaction_splits.value FROM transaction_splits INNER JOIN transactions ON transaction_splits.txn_id = transactions.id WHERE transaction_splits.account_id = ? AND transactions.date > ? AND transactions.date < ?', (account.id, start_date, end_date)).fetchall()
            for record in txn_splits_records:
                amt = Fraction(record[0])
                if amt < Fraction(0):
                    income += amt * Fraction(-1)
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

        #update existing scheduled transaction
        if scheduled_txn.id:
            c.execute('UPDATE scheduled_transactions SET name = ?, frequency = ?, next_due_date = ?, txn_type = ?, payee_id = ?, description = ? WHERE id = ?',
                (scheduled_txn.name, scheduled_txn.frequency.value, scheduled_txn.next_due_date.strftime('%Y-%m-%d'), scheduled_txn.txn_type, payee, scheduled_txn.description, scheduled_txn.id))
            if c.rowcount < 1:
                raise Exception('no scheduled transaction with id %s to update' % scheduled_txn.id)
            #handle splits
            splits_db_info = c.execute('SELECT account_id FROM scheduled_transaction_splits WHERE scheduled_txn_id = ?', (scheduled_txn.id,)).fetchall()
            old_split_account_ids = [r[0] for r in splits_db_info]
            new_split_account_ids = [a.id for a in scheduled_txn.splits.keys()]
            split_account_ids_to_delete = set(old_split_account_ids) - set(new_split_account_ids)
            for account_id in split_account_ids_to_delete:
                c.execute('DELETE FROM scheduled_transaction_splits WHERE scheduled_txn_id = ? AND account_id = ?', (scheduled_txn.id, account_id))
            for account, info in scheduled_txn.splits.items():
                amount = info['amount']
                amount = f'{amount.numerator}/{amount.denominator}'
                status = info.get('status', None)
                if account.id in old_split_account_ids:
                    c.execute('UPDATE scheduled_transaction_splits SET value = ?, quantity = ?, reconciled_state = ? WHERE scheduled_txn_id = ? AND account_id = ?', (amount, amount, status, scheduled_txn.id, account.id))
                else:
                    c.execute('INSERT INTO scheduled_transaction_splits(scheduled_txn_id, account_id, value, quantity, reconciled_state) VALUES (?, ?, ?, ?, ?)', (scheduled_txn.id, account.id, amount, amount, status))
        #add new scheduled transaction
        else:
            c.execute('INSERT INTO scheduled_transactions(name, frequency, next_due_date, txn_type, payee_id, description) VALUES (?, ?, ?, ?, ?, ?)',
                (scheduled_txn.name, scheduled_txn.frequency.value, scheduled_txn.next_due_date.strftime('%Y-%m-%d'), scheduled_txn.txn_type, payee, scheduled_txn.description))
            scheduled_txn.id = c.lastrowid
            for account, info in scheduled_txn.splits.items():
                amount = info['amount']
                amount = f'{amount.numerator}/{amount.denominator}'
                status = info.get('status', None)
                c.execute('INSERT INTO scheduled_transaction_splits(scheduled_txn_id, account_id, value, quantity, reconciled_state) VALUES (?, ?, ?, ?, ?)', (scheduled_txn.id, account.id, amount, amount, status))
        self._db_connection.commit()

    def get_scheduled_transaction(self, id_):
        c = self._db_connection.cursor()
        splits = {}
        split_records = c.execute('SELECT account_id, value, reconciled_state FROM scheduled_transaction_splits WHERE scheduled_txn_id = ?', (id_,))
        if split_records:
            for split_record in split_records:
                account_id = split_record[0]
                account = self.get_account(account_id)
                splits[account] = {'amount': split_record[1]}
                if split_record[2]:
                    splits[account]['status'] = split_record[2]
        rows = c.execute('SELECT name,frequency,next_due_date,txn_type,payee_id,description FROM scheduled_transactions WHERE id = ?', (id_,)).fetchall()
        payee = self.get_payee(rows[0][4])
        st = ScheduledTransaction(
                name=rows[0][0],
                frequency=ScheduledTransactionFrequency(rows[0][1]),
                next_due_date=rows[0][2],
                splits=splits,
                txn_type=rows[0][3],
                payee=payee,
                description=rows[0][5],
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


### ENGINE ###

class Engine:

    def __init__(self, storage):
        self._storage = storage

    def save_commodity(self, c):
        self._storage.save_commodity(c)

    def get_currencies(self):
        commodities = self._storage.get_commodities()
        return [c for c in commodities if c.type == CommodityType.CURRENCY]

    def get_accounts(self):
        return self._storage.get_accounts()

    def get_ledger_accounts(self):
        '''Retrieve accounts for Ledger display'''
        accounts = []
        for account_type in [AccountType.ASSET, AccountType.SECURITY, AccountType.LIABILITY, AccountType.EQUITY]:
            accounts.extend(self._storage.get_accounts(type_=account_type))
        return accounts

    def save_account(self, id_=None, name=None, type_=None, commodity_id=None, number=None, parent_id=None):
        parent = None
        if parent_id:
            parent = self._storage.get_account(id_=parent_id)
        if commodity_id:
            commodity = self._storage.get_commodity(id_=commodity_id)
        else:
            if id_:
                commodity = self._storage.get_account(id_).commodity
            else:
                commodity = self.get_currencies()[0]
        self._storage.save_account(
                Account(id_=id_, type_=type_, commodity=commodity, number=number, name=name, parent=parent)
            )


### IMPORT ###

def import_kmymoney(kmy_file, storage):
    import gzip
    from xml.etree import ElementTree as ET
    print(f'{datetime.now()} uncompressing & parsing file...')
    uncompressed_file = gzip.GzipFile(fileobj=kmy_file)
    root = ET.parse(uncompressed_file).getroot()
    #migrate currencies
    #need to keep track of kmymoney currency id mapping to our commodity id
    print(f'{datetime.now()} migrating commodities (currencies & securities)...')
    commodity_mapping_info = {}
    currencies = root.find('CURRENCIES')
    for currency in currencies.iter('CURRENCY'):
        currency_id = currency.attrib['id']
        if currency_id == 'USD': #USD is added automatically when storage is initialized
            commodity_mapping_info['USD'] = storage.get_commodity(code='USD').id
            continue
        commodity = Commodity(type_=CommodityType.CURRENCY, code=currency_id, name=currency.attrib['name'])
        try:
            storage.save_commodity(commodity)
            commodity_mapping_info[currency_id] = commodity.id
        except Exception as e:
            print(f'{datetime.now()} error migrating currency: {e}\n  {currency.attrib}')
    securities = root.find('SECURITIES')
    for security in securities.iter('SECURITY'):
        security_id = security.attrib['id']
        commodity = Commodity(type_=CommodityType.SECURITY, code=security_id, name=currency.attrib['name'])
        try:
            storage.save_commodity(commodity)
            commodity_mapping_info[security_id] = commodity.id
        except Exception as e:
            print(f'{datetime.now()} error migrating security: {e}\n  {security.attrib}')
    #migrate accounts
    #need to keep track of kmymoney account id mapping to our account id
    print(f'{datetime.now()} migrating accounts...')
    account_mapping_info = {}
    accounts = root.find('ACCOUNTS')
    for account in accounts.iter('ACCOUNT'):
        type_ = AccountType.ASSET
        if account.attrib['type'] in ['10']:
            type_ = AccountType.LIABILITY
        elif account.attrib['type'] in ['13']:
            type_ = AccountType.EXPENSE
        elif account.attrib['type'] in ['12']:
            type_ = AccountType.INCOME
        elif account.attrib['type'] in ['16']:
            type_ = AccountType.EQUITY
        elif account.attrib['type'] in ['15']:
            type_ = AccountType.SECURITY
        currency_id = commodity_mapping_info[account.attrib['currency']]
        commodity = storage.get_commodity(id_=currency_id)
        print(f'  {account.attrib["type"]} {account.attrib["name"]} => {type_}')
        acc_obj = Account(
                    type_=type_,
                    commodity=commodity,
                    name=account.attrib['name'],
                )
        storage.save_account(acc_obj)
        account_mapping_info[account.attrib['id']] = acc_obj.id
    #migrate payees
    print(f'{datetime.now()} migrating payees...')
    payee_mapping_info = {}
    payees = root.find('PAYEES')
    for payee in payees.iter('PAYEE'):
        payee_obj = Payee(name=payee.attrib['name'])
        storage.save_payee(payee_obj)
        payee_mapping_info[payee.attrib['id']] = payee_obj.id
    #migrate transactions
    print(f'{datetime.now()} migrating transactions...')
    transactions = root.find('TRANSACTIONS')
    for transaction in transactions.iter('TRANSACTION'):
        try:
            splits_el = transaction.find('SPLITS')
            splits = {}
            for split in splits_el.iter('SPLIT'):
                account_orig_id = split.attrib['account']
                account = storage.get_account(account_mapping_info[account_orig_id])
                #reconcileflag: '2'=Reconciled, '1'=Cleared, '0'=nothing
                splits[account] = {'amount': split.attrib['value']}
                if split.attrib['reconcileflag'] == '2':
                    splits[account]['status'] = Transaction.RECONCILED
                elif split.attrib['reconcileflag'] == '1':
                    splits[account]['status'] = Transaction.CLEARED
                payee = None
                if split.attrib['payee']:
                    payee = storage.get_payee(id_=payee_mapping_info[split.attrib['payee']])
            storage.save_txn(
                    Transaction(
                        splits=splits,
                        txn_date=transaction.attrib['postdate'],
                        payee=payee,
                    )
                )
        except Exception as e:
            print(f'{datetime.now()} error migrating transaction: {e}\n  {transaction.attrib}')
    for top_level_el in root:
        if top_level_el.tag not in ['CURRENCIES', 'SECURITIES', 'ACCOUNTS', 'PAYEES', 'TRANSACTIONS']:
            print(f"{datetime.now()} didn't migrate {top_level_el.tag} data")


### CLI/GUI ###

def pager(items, num_txns_in_page, page=1):
    start = 0 + (page-1)*num_txns_in_page
    end = start+num_txns_in_page
    page_items = items[start:end]
    if end < len(items):
        more_items = True
    else:
        more_items = False
    return page_items, more_items


ACCOUNTS_GUI_FIELDS = {
        'type': {'column_number': 0, 'column_stretch': 2, 'label': 'Type'},
        'number': {'column_number': 1, 'column_stretch': 1, 'label': 'Number'},
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
        for index, f in enumerate(['type', 'number', 'name', 'parent']):
            layout.addWidget(QtWidgets.QLabel(ACCOUNTS_GUI_FIELDS[f]['label']), row, index)
        row += 1
        account_type = QtWidgets.QComboBox()
        for index, type_ in enumerate(AccountType):
            account_type.addItem(type_.name, type_)
            if self._account and self._account.type == type_:
                account_type.setCurrentIndex(index)
        layout.addWidget(account_type, row, ACCOUNTS_GUI_FIELDS['type']['column_number'])
        number = QtWidgets.QLineEdit()
        if self._account:
            number.setText(self._account.number)
        layout.addWidget(number, row, ACCOUNTS_GUI_FIELDS['number']['column_number'])
        name = QtWidgets.QLineEdit()
        if self._account:
            name.setText(self._account.name)
        layout.addWidget(name, row, ACCOUNTS_GUI_FIELDS['name']['column_number'])
        parent_combo = QtWidgets.QComboBox()
        parent_combo.addItem('---------', None)
        for index, acc in enumerate(self._all_accounts):
            parent_combo.addItem(acc.name, acc.id)
            if self._account and self._account.parent == acc:
                parent_combo.setCurrentIndex(index+1)
        layout.addWidget(parent_combo, row, ACCOUNTS_GUI_FIELDS['parent']['column_number'])
        button = QtWidgets.QPushButton('Save')
        button.clicked.connect(self._save_new_account)
        layout.addWidget(button, row, ACCOUNTS_GUI_FIELDS['buttons']['column_number'])
        widgets['type'] = account_type
        widgets['number'] = number
        widgets['name'] = name
        widgets['parent'] = parent_combo
        widgets['save_btn'] = button

    def _save_new_account(self):
        type_ = self._widgets['type'].currentData()
        number = self._widgets['number'].text()
        name = self._widgets['name'].text()
        parent_id = self._widgets['parent'].currentData()
        if self._account:
            id_ = self._account.id
            commodity_id = self._account.commodity.id
        else:
            id_ = None
            commodity_id = None
        try:
            self._save_account(id_=id_, type_=type_, commodity_id=commodity_id, number=number, name=name, parent_id=parent_id)
            self._display.accept()
        except InvalidAccountNameError:
            set_widget_error_state(self._widgets['name'])


def get_accounts_model_class():

    class Model(QtCore.QAbstractTableModel):

        def __init__(self, accounts):
            self._accounts = accounts
            super().__init__()

        def rowCount(self, parent):
            return len(self._accounts)

        def columnCount(self, parent):
            return 4

        def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
            if role == QtCore.Qt.DisplayRole:
                if orientation == QtCore.Qt.Horizontal:
                    if section == 0:
                        return 'Type'
                    elif section == 1:
                        return 'Number'
                    elif section == 2:
                        return 'Name'
                    elif section == 3:
                        return 'Parent'

        def data(self, index, role=QtCore.Qt.DisplayRole):
            if role == QtCore.Qt.DisplayRole:
                if index.column() == 0:
                    return self._accounts[index.row()].type.name
                if index.column() == 1:
                    return self._accounts[index.row()].number
                if index.column() == 2:
                    return self._accounts[index.row()].name
                if index.column() == 3:
                    if self._accounts[index.row()].parent:
                        return str(self._accounts[index.row()].parent)

        def get_account(self, index):
            return self._accounts[index.row()]

    return Model


class AccountsDisplay:

    def __init__(self, accounts, save_account, reload_accounts, model_class):
        self._accounts = accounts
        self._save_account = save_account
        self._reload = reload_accounts
        self._model_class = model_class
        self._accounts_model = self._get_accounts_model(self._accounts)
        self._accounts_widget = self._get_accounts_widget(self._accounts_model)

    def get_widget(self):
        main_widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        row = 0
        self.add_button = QtWidgets.QPushButton('New Account')
        self.add_button.clicked.connect(self._open_new_account_form)
        layout.addWidget(self.add_button, row, 0)
        row += 1
        layout.addWidget(self._accounts_widget, row, 0, 1, 5)
        main_widget.setLayout(layout)
        return main_widget

    def _get_accounts_model(self, accounts):
        return self._model_class(accounts)

    def _get_accounts_widget(self, model):
        widget = QtWidgets.QTableView()
        widget.setModel(model)
        widget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        widget.resizeColumnsToContents()
        widget.resizeRowsToContents()
        widget.clicked.connect(self._edit)
        return widget

    def _open_new_account_form(self):
        self.add_account_display = AccountForm(self._accounts, save_account=self._handle_new_account)
        self.add_account_display.show_form()

    def _handle_new_account(self, id_, type_, commodity_id, number, name, parent_id):
        self._save_account(id_=id_, type_=type_, commodity_id=commodity_id, number=number, name=name, parent_id=parent_id)
        self._reload()

    def _edit(self, index):
        account = self._accounts_model.get_account(index)
        self.edit_account_display = AccountForm(self._accounts, account=account, save_account=self._handle_new_account)
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
                self._final_txn_splits[value[1]] = {'amount': text}
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
            for acc, split_info in self._initial_txn_splits.items():
                amt = split_info['amount']
                if acc == account:
                    amount_entry.setText(amount_display(amt))
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


def get_txns_model_class():

    class Model(QtCore.QAbstractTableModel):

        def __init__(self, ledger):
            self._ledger = ledger
            self.set_txns_and_scheduled_txns()
            super().__init__()

        def rowCount(self, parent=None):
            return len(self._txns) + len(self._scheduled_txns_due)

        def columnCount(self, parent=None):
            return 9

        def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
            if role == QtCore.Qt.DisplayRole:
                if orientation == QtCore.Qt.Horizontal:
                    if section == 0:
                        return 'Type'
                    elif section == 1:
                        return 'Date'
                    elif section == 2:
                        return 'Payee'
                    elif section == 3:
                        return 'Description'
                    elif section == 4:
                        return 'Status'
                    elif section == 5:
                        return 'Withdrawal'
                    elif section == 6:
                        return 'Deposit'
                    elif section == 7:
                        return 'Balance'
                    elif section == 8:
                        return 'Transfer Account'

        def data(self, index, role=QtCore.Qt.DisplayRole):
            if role == QtCore.Qt.DisplayRole:
                row = index.row()
                column = index.column()
                is_scheduled_txn = False
                if row >= len(self._txns):
                    txn = self._scheduled_txns_due[row-len(self._txns)]
                    is_scheduled_txn = True
                else:
                    txn = self._txns[index.row()]
                tds = get_display_strings_for_ledger(self._ledger.account, txn)
                if column == 0:
                    return tds['txn_type']
                if column == 1:
                    return tds['txn_date']
                if column == 2:
                    return tds['payee']
                if column == 3:
                    return tds['description']
                if column == 4:
                    if not is_scheduled_txn:
                        return tds['status']
                if column == 5:
                    return tds['withdrawal']
                if column == 6:
                    return tds['deposit']
                if column == 7:
                    if not is_scheduled_txn:
                        return amount_display(txn.balance)
                if column == 8:
                    return tds['categories']
            elif role == QtCore.Qt.BackgroundRole:
                row = index.row()
                column = index.column()
                is_scheduled_txn = False
                if row >= len(self._txns):
                    txn = self._scheduled_txns_due[row-len(self._txns)]
                    is_scheduled_txn = True
                else:
                    txn = self._txns[index.row()]
                if is_scheduled_txn:
                    return QtGui.QBrush(QtCore.Qt.gray)

        def set_txns_and_scheduled_txns(self):
            #sets/updates self._txns & self._scheduled_txns_due
            # must call this whenever ledger is updated
            self._txns = self._ledger.get_sorted_txns_with_balance()
            self._scheduled_txns_due = self._ledger.get_scheduled_transactions_due()

        def get_txn(self, index):
            row = index.row()
            if row >= len(self._txns):
                return self._scheduled_txns_due[row-len(self._txns)]
            else:
                return self._txns[row]

        def get_bottom_right_index(self):
            return self.createIndex(self.rowCount(), self.columnCount()-1)

        def add_txn(self, txn):
            self._ledger.add_transaction(txn)
            self.set_txns_and_scheduled_txns()
            self.layoutChanged.emit()

        def update_txn(self, txn):
            #txn edited:
            #   date could have changed, and moved this row up or down in the table
            #   amount could have changed, and affected all the subsequence balances
            #   any of the fields of this txn could have changed
            #initial_row_index = -1
            #for index, t in enumerate(self._txns):
            #    if t == txn:
            #        initial_row_index = index
            #        break
            self._ledger.add_transaction(txn)
            self.set_txns_and_scheduled_txns()
            #final_row_index = -1
            #for index, t in enumerate(self._txns):
            #    if t == txn:
            #        final_row_index = index
            #        break
            #if initial_row_index > final_row_index:
            #    topLeft = self.createIndex(final_row_index, 0)
            #    bottomRight = self.createIndex(initial_row_index, self.columnCount())
            #else:
            #    topLeft = self.createIndex(initial_row_index, 0)
            #    bottomRight = self.createIndex(final_row_index, self.columnCount())
            #this updates everything - we should add checks so we only update what needs to be changed
            self.layoutChanged.emit()

        def update_txn_status(self, txn):
            row_index = -1
            for index, t in enumerate(self._txns):
                if t == txn:
                    row_index = index
                    break
            self._ledger.add_transaction(txn)
            self.set_txns_and_scheduled_txns()
            status_index = self.createIndex(row_index, 4)
            self.dataChanged.emit(status_index, status_index)

        def remove_txn(self, txn):
            self._ledger.remove_txn(txn.id)
            self.set_txns_and_scheduled_txns()
            self.layoutChanged.emit()

    return Model


class LedgerTxnsDisplay:

    def __init__(self, ledger, storage, filter_text, post_update_function, model_class, display_ledger):
        self.ledger = ledger
        self.storage = storage
        self._filter_text = filter_text
        self._scheduled_txn_widgets = []
        self._post_update_function = post_update_function
        self._display_ledger = display_ledger
        self._model_class = model_class
        self._txns_model = self._model_class(self.ledger)
        self._txns_widget = self._get_txns_widget(self._txns_model)

    def get_widget(self):
        self.main_widget = QtWidgets.QScrollArea()
        self.main_widget.setWidgetResizable(True)
        self.txns_layout = QtWidgets.QGridLayout() #need handle to this for display_new_txn
        set_ledger_column_widths(self.txns_layout)
        self.main_widget.setWidget(self._txns_widget)
        return self.main_widget

    def _get_txns_widget(self, txns_model):
        widget = QtWidgets.QTableView()
        widget.setModel(txns_model)
        widget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        widget.resizeColumnsToContents()
        widget.resizeRowsToContents()
        widget.clicked.connect(self._edit)
        return widget

    def display_new_txn(self, txn):
        self._txns_model.add_txn(txn)

    def _delete(self, txn):
        self.storage.delete_txn(txn.id)
        self._txns_model.remove_txn(txn)
        self._post_update_function()

    def _save_edit(self, txn):
        self.storage.save_txn(txn)
        self._txns_model.update_txn(txn)
        self._post_update_function()

    def _edit(self, index):
        txn = self._txns_model.get_txn(index)
        if isinstance(txn, ScheduledTransaction):
            self._show_scheduled_txn_form(txn)
        #if status column was clicked, just update status instead of opening edit form
        elif index.column() == 4:
            txn.update_reconciled_state(account=self.ledger.account)
            self.storage.save_txn(txn)
            self._txns_model.update_txn_status(txn)
        else:
            self.edit_txn_display = TxnForm(
                    payees=self.storage.get_payees(),
                    save_txn=self._save_edit,
                    storage=self.storage,
                    current_account=self.ledger.account,
                    txn=txn,
                    delete_txn=self._delete
                )
            self.edit_txn_display.show_form()

    def _enter_scheduled_txn(self, new_txn, scheduled_txn):
        scheduled_txn.advance_to_next_due_date()
        self.storage.save_scheduled_transaction(scheduled_txn)
        self.storage.save_txn(new_txn)
        self._display_ledger()

    def _skip_scheduled_txn(self, scheduled_txn):
        scheduled_txn.advance_to_next_due_date()
        self.storage.save_scheduled_transaction(scheduled_txn)
        self._display_ledger()

    def _show_scheduled_txn_form(self, scheduled_txn):
        save_txn = partial(self._enter_scheduled_txn, scheduled_txn=scheduled_txn)
        self.scheduled_txn_display = TxnForm(
                payees=self.storage.get_payees(),
                save_txn=save_txn,
                storage=self.storage,
                current_account=self.ledger.account,
                txn=scheduled_txn,
                skip_txn=partial(self._skip_scheduled_txn, scheduled_txn=scheduled_txn)
            )
        self.scheduled_txn_display.show_form()


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
            else:
                if name == 'txn_date':
                    entry.setText(str(date.today()))
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
            if isinstance(self._txn, ScheduledTransaction):
                button = QtWidgets.QPushButton('Skip Next Txn')
                button.clicked.connect(self._skip)
                self._widgets['skip_btn'] = button
                layout.addWidget(button, 2, GUI_FIELDS['buttons']['add_edit_column_number'])

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
        if self._txn and not isinstance(self._txn, ScheduledTransaction):
            kwargs['id_'] = self._txn.id
        txn = Transaction.from_user_info(**kwargs)
        self._txn_display.accept()
        self._save_txn(txn)

    def delete(self):
        self._txn_display.accept()
        self._delete_txn(self._txn)

    def _skip(self):
        self._txn_display.accept()
        self._skip_txn()


class ScheduledTxnForm:

    def __init__(self, save_scheduled_txn, storage, scheduled_txn=None):
        self._scheduled_txn = scheduled_txn
        self._save_scheduled_txn = save_scheduled_txn
        self._storage = storage
        self._accounts = storage.get_accounts()
        self._widgets = {}

    def show_form(self):
        self._display = QtWidgets.QDialog()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        set_ledger_column_widths(layout)
        self._show_widgets(layout)
        self._display.setLayout(layout)
        self._display.open()

    def _show_widgets(self, layout):
        layout.addWidget(QtWidgets.QLabel('Name'), 0, 0)
        name_entry = QtWidgets.QLineEdit()
        if self._scheduled_txn:
            name_entry.setText(self._scheduled_txn.name)
        self._widgets['name'] = name_entry
        layout.addWidget(name_entry, 0, 1)
        layout.addWidget(QtWidgets.QLabel('Frequency'), 1, 0)
        frequency_entry = QtWidgets.QComboBox()
        frequency_index = 0
        for index, frequency in enumerate(ScheduledTransactionFrequency):
            frequency_entry.addItem(frequency.name, frequency)
            if self._scheduled_txn and frequency == self._scheduled_txn.frequency:
                frequency_index = index
        if self._scheduled_txn:
            frequency_entry.setCurrentIndex(frequency_index)
        self._widgets['frequency'] = frequency_entry
        layout.addWidget(frequency_entry, 1, 1)
        layout.addWidget(QtWidgets.QLabel('Next Due Date'), 2, 0)
        next_due_date_entry = QtWidgets.QLineEdit()
        if self._scheduled_txn:
            next_due_date_entry.setText(str(self._scheduled_txn.next_due_date))
        self._widgets['next_due_date'] = next_due_date_entry
        layout.addWidget(next_due_date_entry, 2, 1)

        layout.addWidget(QtWidgets.QLabel('Payee'), 3, 0)
        payee_entry = QtWidgets.QComboBox()
        payee_entry.setEditable(True)
        payee_entry.addItem('')
        payee_index = 0
        for index, payee in enumerate(self._storage.get_payees()):
            payee_entry.addItem(payee.name, payee)
            if self._scheduled_txn and self._scheduled_txn.payee and self._scheduled_txn.payee.name == payee.name:
                payee_index = index + 1 #because of first empty item
        if self._scheduled_txn:
            payee_entry.setCurrentIndex(payee_index)
        self._widgets['payee'] = payee_entry
        layout.addWidget(payee_entry, 3, 1)

        account = deposit = withdrawal = None
        if self._scheduled_txn:
            account = list(self._scheduled_txn.splits.keys())[0]
            amount = self._scheduled_txn.splits[account]['amount']
            if amount > 0:
                deposit = amount_display(amount)
            else:
                withdrawal = amount_display(amount * Fraction(-1))

        layout.addWidget(QtWidgets.QLabel('Account'), 4, 0)
        account_entry = QtWidgets.QComboBox()
        account_index = -1
        for index, acct in enumerate(self._accounts):
            account_entry.addItem(acct.name, acct)
            if account and account == acct:
                account_index = index
        if account:
            account_entry.setCurrentIndex(account_index)
        self._widgets['account'] = account_entry
        layout.addWidget(account_entry, 4, 1)
        layout.addWidget(QtWidgets.QLabel('Withdrawal'), 5, 0)
        withdrawal_entry = QtWidgets.QLineEdit()
        if withdrawal:
            withdrawal_entry.setText(withdrawal)
        self._widgets['withdrawal'] = withdrawal_entry
        layout.addWidget(withdrawal_entry, 5, 1)
        layout.addWidget(QtWidgets.QLabel('Deposit'), 6, 0)
        deposit_entry = QtWidgets.QLineEdit()
        if deposit:
            deposit_entry.setText(deposit)
        self._widgets['deposit'] = deposit_entry
        layout.addWidget(deposit_entry, 6, 1)
        layout.addWidget(QtWidgets.QLabel('Categories'), 7, 0)
        txn_accounts_display = TxnAccountsDisplay(self._storage, txn=self._scheduled_txn, main_account=account)
        self._widgets['accounts_display'] = txn_accounts_display
        layout.addWidget(txn_accounts_display.get_widget(), 7, 1)
        save_button = QtWidgets.QPushButton('Save')
        save_button.clicked.connect(self._save)
        self._widgets['save_btn'] = save_button
        layout.addWidget(save_button, 8, 0)

    def _save(self):
        payee = self._widgets['payee'].currentData()
        if not payee:
            payee = self._widgets['payee'].currentText()
        account = self._widgets['account'].currentData()
        deposit = self._widgets['deposit'].text()
        withdrawal = self._widgets['withdrawal'].text()
        categories = self._widgets['accounts_display'].get_categories()
        splits = Transaction.splits_from_user_info(
                account=account,
                deposit=deposit,
                withdrawal=withdrawal,
                input_categories=categories
            )
        if self._scheduled_txn:
            id_ = self._scheduled_txn.id
        else:
            id_ = None
        st = ScheduledTransaction(
                name=self._widgets['name'].text(),
                frequency=self._widgets['frequency'].currentData(),
                next_due_date=self._widgets['next_due_date'].text(),
                splits=splits,
                payee=payee,
                id_=id_,
            )
        self._display.accept()
        self._save_scheduled_txn(scheduled_txn=st)


class LedgerDisplay:

    def __init__(self, engine, txns_model_class, current_account=None):
        self._engine = engine
        self.storage = self._engine._storage
        self._txns_model_class = txns_model_class
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
            self._display_balances_widget(self.layout, self.ledger)
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
                post_update_function=partial(self._display_balances_widget, layout=layout, ledger=self.ledger),
                model_class=self._txns_model_class,
                display_ledger=partial(self._display_ledger, layout=layout, account=account))
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
        balances = ledger.get_current_balances_for_display()
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
        accounts = self._engine.get_ledger_accounts()
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
        layout = QtWidgets.QGridLayout()
        self._show_widgets(layout, self._widgets)
        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        top_layout = QtWidgets.QGridLayout()
        top_layout.addWidget(scroll, 0, 0)
        self._display = QtWidgets.QDialog()
        self._display.setLayout(top_layout)
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


def get_budget_model_class():

    class Model(QtCore.QAbstractTableModel):

        def __init__(self, budget):
            self._budget_report = budget.get_report_display(current_date=date.today())
            self._report_data = []
            for account, info in self._budget_report['income'].items():
                self._report_data.append({'account': account, 'info': info})
            for account, info in self._budget_report['expense'].items():
                self._report_data.append({'account': account, 'info': info})
            super().__init__()

        def rowCount(self, parent):
            return len(self._report_data)

        def columnCount(self, parent):
            return 9

        def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
            if role == QtCore.Qt.DisplayRole:
                if orientation == QtCore.Qt.Horizontal:
                    if section == 0:
                        return 'Account'
                    elif section == 1:
                        return 'Amount'
                    elif section == 2:
                        return 'Income'
                    elif section == 3:
                        return 'Carryover'
                    elif section == 4:
                        return 'Total Budget'
                    elif section == 5:
                        return 'Spent'
                    elif section == 6:
                        return 'Remaining'
                    elif section == 7:
                        return 'Remaining Percent'
                    elif section == 8:
                        return 'Current Status'

        def data(self, index, role=QtCore.Qt.DisplayRole):
            if role == QtCore.Qt.DisplayRole:
                if index.column() == 0:
                    return self._report_data[index.row()]['account'].name
                if index.column() == 1:
                    return self._report_data[index.row()]['info'].get('amount', '')
                if index.column() == 2:
                    return self._report_data[index.row()]['info'].get('income', '')
                if index.column() == 3:
                    return self._report_data[index.row()]['info'].get('carryover', '')
                if index.column() == 4:
                    return self._report_data[index.row()]['info'].get('total_budget', '')
                if index.column() == 5:
                    return self._report_data[index.row()]['info'].get('total_budget', '')
                if index.column() == 6:
                    return self._report_data[index.row()]['info'].get('remaining', '')
                if index.column() == 7:
                    return self._report_data[index.row()]['info'].get('remaining_percent', '')
                if index.column() == 8:
                    return self._report_data[index.row()]['info'].get('current_status', '')

    return Model


class BudgetDataDisplay:
    '''Just for displaying budget values and income/expense data.'''

    def __init__(self, budget, save_budget, budget_model_class):
        self._budget = budget
        self._save_budget = save_budget
        self._budget_model_class = budget_model_class

    def _get_model(self):
        return self._budget_model_class(self._budget)

    def get_widget(self):
        model = self._get_model()
        self.main_widget = QtWidgets.QTableView()
        self.main_widget.setModel(model)
        self.main_widget.resizeColumnsToContents()
        return self.main_widget


class BudgetDisplay:

    @staticmethod
    def budget_display_for_list(budget):
        if budget.name:
            return '%s (%s - %s)' % (budget.name, budget.start_date, budget.end_date)
        else:
            return '%s - %s' % (budget.start_date, budget.end_date)

    def __init__(self, storage, budget_model_class, current_budget=None):
        self.storage = storage
        self._budget_model_class = budget_model_class
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
        self.budget_data_display = BudgetDataDisplay(budget, save_budget=self._save_budget_and_reload, budget_model_class=self._budget_model_class)
        if self._budget_data_display_widget:
            layout.removeWidget(self._budget_data_display_widget)
            self._budget_data_display_widget.deleteLater()
        self._budget_data_display_widget = self.budget_data_display.get_widget()
        layout.addWidget(self._budget_data_display_widget, row, 0, 1, 9)
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


def get_scheduled_txns_model_class():

    class Model(QtCore.QAbstractTableModel):

        def __init__(self, scheduled_txns):
            self._scheduled_txns = scheduled_txns
            super().__init__()

        def rowCount(self, parent):
            return len(self._scheduled_txns)

        def columnCount(self, parent):
            return 5

        def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
            if role == QtCore.Qt.DisplayRole:
                if orientation == QtCore.Qt.Horizontal:
                    if section == 0:
                        return 'Name'
                    elif section == 1:
                        return 'Frequency'
                    elif section == 2:
                        return 'Next Due Date'
                    elif section == 3:
                        return 'Payee'
                    elif section == 4:
                        return 'Splits'

        def data(self, index, role=QtCore.Qt.DisplayRole):
            if role == QtCore.Qt.DisplayRole:
                column = index.column()
                row = index.row()
                if column == 0:
                    return self._scheduled_txns[row].name
                elif column == 1:
                    return self._scheduled_txns[row].frequency.value
                elif column == 2:
                    return str(self._scheduled_txns[row].next_due_date)
                elif column == 3:
                    payee = self._scheduled_txns[row].payee
                    if payee:
                        return payee.name
                elif column == 4:
                    return splits_display(self._scheduled_txns[row].splits)

        def get_scheduled_txn_id(self, index):
            return self._scheduled_txns[index.row()].id

    return Model


class ScheduledTxnsDataDisplay:
    '''for displaying the list of scheduled transactions'''

    def __init__(self, scheduled_txns, storage, model_class, reload_function):
        self.scheduled_txns = scheduled_txns
        self.storage = storage
        self._model_class = model_class
        self._reload = reload_function
        self._model = model_class(self.scheduled_txns)
        self.widgets = {}

    def get_widget(self):
        self.main_widget = QtWidgets.QTableView()
        self.main_widget.setModel(self._model)
        self.main_widget.resizeColumnsToContents()
        self.main_widget.clicked.connect(self._edit)
        return self.main_widget

    def _edit(self, index):
        st_id = self._model.get_scheduled_txn_id(index)
        scheduled_txn = self.storage.get_scheduled_transaction(st_id)
        self.edit_form = ScheduledTxnForm(storage=self.storage, save_scheduled_txn=self._save_scheduled_txn_and_reload, scheduled_txn=scheduled_txn)
        self.edit_form.show_form()

    def _save_scheduled_txn_and_reload(self, scheduled_txn):
        self.storage.save_scheduled_transaction(scheduled_txn)
        self._reload()


class ScheduledTxnsDisplay:

    def __init__(self, storage, model_class):
        self.storage = storage
        self._model_class = model_class
        self._data_display_widget = None

    def get_widget(self):
        self.widget, self.layout, self._row_index = self._setup_main()
        self._display_scheduled_txns(self.layout)
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

    def _show_headings(self, layout, row):
        current_index = 0
        self.add_button = QtWidgets.QPushButton('New Scheduled Transaction')
        self.add_button.clicked.connect(partial(self._open_form, scheduled_txn=None))
        layout.addWidget(self.add_button, row, 0)
        return row + 1

    def _display_scheduled_txns(self, layout):
        scheduled_txns = self.storage.get_scheduled_transactions()
        if self._data_display_widget:
            layout.removeWidget(self._data_display_widget)
            self._data_display_widget.deleteLater()
        if scheduled_txns:
            self.data_display = ScheduledTxnsDataDisplay(scheduled_txns, storage=self.storage, model_class=self._model_class,
                    reload_function=partial(self._display_scheduled_txns, layout=layout))
            self._data_display_widget = self.data_display.get_widget()
            layout.addWidget(self._data_display_widget, self._row_index, 0, 1, 5)
            self._row_index += 1

    def _open_form(self, scheduled_txn):
        if scheduled_txn:
            self.form = ScheduledTxnForm(storage=self.storage, save_scheduled_txn=self._save_scheduled_txn_and_reload, scheduled_txn=scheduled_txn)
        else:
            self.form = ScheduledTxnForm(storage=self.storage, save_scheduled_txn=self._save_scheduled_txn_and_reload, scheduled_txn=scheduled_txn)
        self.form.show_form()

    def _save_scheduled_txn_and_reload(self, scheduled_txn):
        self.storage.save_scheduled_transaction(scheduled_txn)
        self._display_scheduled_txns(layout=self.layout)


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
        self.content_area = None
        self._accounts_model_class = get_accounts_model_class()
        self._txns_model_class = get_txns_model_class()
        self._budget_model_class = get_budget_model_class()
        self._scheduled_txns_model_class = get_scheduled_txns_model_class()

        if file_name:
            self._load_db(file_name)
        else:
            self._show_splash()
        self.parent_window.showMaximized()

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
        self._engine = Engine(self.storage)
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
        accounts = self._engine.get_accounts()
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
        self.scheduled_txns_button = QtWidgets.QPushButton('Scheduled Transactions')
        self.scheduled_txns_button.clicked.connect(self._show_scheduled_txns)
        layout.addWidget(self.scheduled_txns_button, 0, 3)

    def _show_accounts(self):
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        accounts = self._engine.get_accounts()
        self.accounts_display = AccountsDisplay(accounts, save_account=self._engine.save_account, reload_accounts=self._show_accounts, model_class=self._accounts_model_class)
        self.main_widget = self.accounts_display.get_widget()
        self.content_layout.addWidget(self.main_widget, 0, 0)

    def _show_ledger(self):
        accounts = self._engine._storage.get_accounts(type_=AccountType.ASSET)
        if not accounts:
            show_error('Enter an asset account first.')
            return
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self.ledger_display = LedgerDisplay(engine=self._engine, txns_model_class=self._txns_model_class)
        self.main_widget = self.ledger_display.get_widget()
        self.content_layout.addWidget(self.main_widget, 0, 0)

    def _show_budget(self, current_budget=None):
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self.budget_display = BudgetDisplay(self._engine._storage, budget_model_class=self._budget_model_class, current_budget=current_budget)
        self.main_widget = self.budget_display.get_widget()
        self.content_layout.addWidget(self.main_widget, 0, 0)

    def _show_scheduled_txns(self):
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self.scheduled_txns_display = ScheduledTxnsDisplay(self._engine._storage, model_class=self._scheduled_txns_model_class)
        self.main_widget = self.scheduled_txns_display.get_widget()
        self.content_layout.addWidget(self.main_widget, 0, 0)


class CLI:

    ACCOUNT_LIST_HEADER = ' ID   | Type        | Number | Name                           | Parent\n'\
        '==============================================================================================='

    TXN_LIST_HEADER = ' ID   | Date       | Type   |  Description                   | Payee                          |  Transfer Account              | Withdrawal | Deposit    | Balance\n'\
        '================================================================================================================================================================'

    NUM_TXNS_IN_PAGE = 50

    def __init__(self, filename, print_file=None):
        storage = SQLiteStorage(filename)
        self._engine = Engine(storage)
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
        for a in self._engine.get_accounts():
            if a.number:
                number = a.number
            else:
                number = ''
            if a.parent:
                parent = a.parent.name
            else:
                parent = ''
            self.print(' {0:<4} | {1:<11} | {2:<7} | {3:<30} | {4:<30}'.format(a.id, a.type.name, number[:7], a.name[:30], parent[:30]))

    def _get_and_save_account(self, account=None):
        acc_id = None
        name_prefill = acct_type_prefill = number_prefill = ''
        if account:
            acc_id = account.id
            name_prefill = account.name
            acct_type_prefill = account.type.value
            number_prefill = account.number
        name = self.input(prompt='  name: ', prefill=name_prefill)
        acct_type_options = ','.join([t.value for t in AccountType])
        acct_type = self.input(prompt='  type (%s): ' % acct_type_options, prefill=acct_type_prefill)
        number = self.input(prompt='  number: ', prefill=number_prefill)
        parent_id = self.input(prompt='  parent account id: ')
        commodity_id = None
        if account:
            commodity_id = account.commodity.id
        self._engine.save_account(id_=acc_id, name=name, type_=acct_type, commodity_id=commodity_id, number=number, parent_id=parent_id)

    def _create_account(self):
        self.print('Create Account:')
        self._get_and_save_account()

    def _edit_account(self):
        acc_id = self.input('Account ID: ')
        account = self._engine._storage.get_account(acc_id)
        self._get_and_save_account(account=account)

    def _list_account_txns(self, num_txns_in_page=None):
        if not num_txns_in_page:
            num_txns_in_page = self.NUM_TXNS_IN_PAGE
        acc_id = self.input('Account ID: ')
        ledger = self._engine._storage.get_ledger(acc_id)
        ledger_balances = ledger.get_current_balances_for_display()
        summary_line = f'{ledger.account.name} (Current balance: {ledger_balances.current}; Cleared: {ledger_balances.current_cleared})'
        self.print(summary_line)
        scheduled_txns_due = ledger.get_scheduled_transactions_due()
        if scheduled_txns_due:
            self.print('Scheduled Transactions due:')
            for st in scheduled_txns_due:
                self.print(f'{st.id} {st.name} {st.next_due_date}')
        self.print(self.TXN_LIST_HEADER)
        txns = ledger.get_sorted_txns_with_balance(reverse=True)
        page_index = 1
        while True:
            paged_txns, more_txns = pager(txns, num_txns_in_page=num_txns_in_page, page=page_index)
            for t in paged_txns:
                tds = get_display_strings_for_ledger(self._engine._storage.get_account(acc_id), t)
                self.print(' {8:<4} | {0:<10} | {1:<6} | {2:<30} | {3:<30} | {4:30} | {5:<10} | {6:<10} | {7:<10}'.format(
                    tds['txn_date'], tds['txn_type'], tds['description'], tds['payee'], tds['categories'], tds['withdrawal'], tds['deposit'], amount_display(t.balance), t.id)
                )
            if more_txns:
                prompt = '(o) older txns'
                if page_index > 1:
                    prompt = '(n) newer txns, ' + prompt
                x = self.input(prompt=f'{prompt} ')
                if x == 'o':
                    page_index += 1
                elif x == 'n':
                    page_index -= 1
                else:
                    break
            else:
                break

    def _get_common_txn_info(self, txn=None):
        '''get pieces of data common to txns and scheduled txns'''
        txn_info = {}
        self.print('Splits:')
        splits = {}
        if txn:
            for account, split_info in txn.splits.items():
                amount = self.input(prompt='%s amount: ' % account.name, prefill=fraction_to_decimal(split_info['amount']))
                if amount:
                    splits[account] = {'amount': amount}
                    orig_status = split_info.get('status', '')
                    if orig_status:
                        orig_status = orig_status.value
                    reconciled_state = self.input(prompt=f'{account.name} reconciled state: ', prefill=orig_status)
                    if reconciled_state:
                        splits[account]['status'] = reconciled_state
        while True:
            acct_id = self.input(prompt='new account ID: ')
            if acct_id:
                account = self._engine._storage.get_account(acct_id)
                amt = self.input(prompt=' amount: ')
                if amt:
                    splits[account] = {'amount': amt}
                    reconciled_state = self.input(prompt=f'{account.name} reconciled state: ')
                    if reconciled_state:
                        splits[account]['status'] = reconciled_state
                else:
                    break
            else:
                break
        txn_info['splits'] = splits
        txn_type_prefill = ''
        payee_prefill = ''
        description_prefill = ''
        if txn:
            txn_type_prefill = txn.txn_type or ''
            if txn.payee:
                payee_prefill = '\'%s' % txn.payee.name
            else:
                payee_prefill = ''
            description_prefill = txn.description or ''
        txn_info['txn_type'] = self.input(prompt='  type: ', prefill=txn_type_prefill)
        payee = self.input(prompt='  payee (id or \'name): ', prefill=payee_prefill)
        if payee == 'p':
            self._list_payees()
            payee = self.input(prompt='  payee (id or \'name): ')
        if payee.startswith("'"):
            txn_info['payee'] = Payee(payee[1:])
        else:
            txn_info['payee'] = self._engine._storage.get_payee(payee)
        txn_info['description'] = self.input(prompt='  description: ', prefill=description_prefill)
        return txn_info

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
        self._engine._storage.save_txn(Transaction(**info))

    def _create_txn(self):
        self.print('Create Transaction:')
        self._get_and_save_txn()

    def _edit_txn(self):
        txn_id = self.input(prompt='Txn ID: ')
        txn = self._engine._storage.get_txn(txn_id)
        self._get_and_save_txn(txn=txn)

    def _list_payees(self):
        for p in self._engine._storage.get_payees():
            self.print('%s: %s' % (p.id, p.name))

    def _list_scheduled_txns(self):
        for st in self._engine._storage.get_scheduled_transactions():
            self.print(st)
        self._enter_scheduled_txn()
        self._skip_scheduled_txn()

    def _enter_scheduled_txn(self):
        self.print('Enter next transaction for a scheduled transaction:')
        while True:
            scheduled_txn_id = self.input('Scheduled txn ID (blank to quit): ')
            if scheduled_txn_id:
                scheduled_txn = self._engine._storage.get_scheduled_transaction(scheduled_txn_id)
                self._get_and_save_txn(txn=scheduled_txn)
                scheduled_txn.advance_to_next_due_date()
                self._engine._storage.save_scheduled_transaction(scheduled_txn)
            else:
                break

    def _skip_scheduled_txn(self):
        self.print('Skip next transaction for a scheduled transaction:')
        while True:
            scheduled_txn_id = self.input('Scheduled txn ID (blank to quit): ')
            if scheduled_txn_id:
                scheduled_txn = self._engine._storage.get_scheduled_transaction(scheduled_txn_id)
                scheduled_txn.advance_to_next_due_date()
                self._engine._storage.save_scheduled_transaction(scheduled_txn)
            else:
                break

    def _display_scheduled_txn(self):
        scheduled_txn_id = self.input('Enter scheduled txn ID: ')
        scheduled_txn = self._engine._storage.get_scheduled_transaction(scheduled_txn_id)
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
        self._engine._storage.save_scheduled_transaction(
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
        scheduled_txn = self._engine._storage.get_scheduled_transaction(scheduled_txn_id)
        self._get_and_save_scheduled_txn(scheduled_txn=scheduled_txn)

    def _list_budgets(self):
        for b in self._engine._storage.get_budgets():
            self.print(b)

    def _display_budget(self):
        budget_id = self.input('Enter budget ID: ')
        budget = self._engine._storage.get_budget(budget_id)
        self.print(budget)
        account_budget_info = budget.get_budget_data()
        for account, info in account_budget_info.items():
            amount = info.get('amount', '')
            if amount:
                amount = amount_display(amount)
            display = f' {account}: {amount}'
            carryover = info.get('carryover', '')
            if carryover:
                carryover = amount_display(carryover)
                display += f' (carryover: {carryover})'
            if info.get('notes', None):
                display += f' {info["notes"]}'
            self.print(display)

    def _display_budget_report(self):
        budget_id = self.input('Enter budget ID: ')
        budget = self._engine._storage.get_budget(budget_id)
        self.print(budget)
        budget_report = budget.get_report_display(current_date=date.today())
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
                    account = self._engine._storage.get_account(acct_id)
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
        self._engine._storage.save_budget(
                Budget(
                    start_date=start_date,
                    end_date=end_date,
                    account_budget_info=account_info,
                )
            )

    def _edit_budget(self):
        budget_id = self.input('Enter budget ID: ')
        budget = self._engine._storage.get_budget(budget_id)
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
        self._engine._storage.save_budget(
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
        help_msg += '\nq (or Ctrl-d) - quit'
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
        self.print(f'*** {TITLE} ***')
        self._print_help(info)
        try:
            self._command_loop(info)
        except (EOFError, KeyboardInterrupt):
            self.print('\n')
        except:
            import traceback
            self.print(traceback.format_exc())
            sys.exit(1)


def import_file(file_to_import):
    if file_to_import.endswith('.kmy'):
        bb_filename = input('enter name of new bricbooks file to create for import: ')
        if os.path.exists(bb_filename):
            raise Exception(f'{bb_filename} already exists')
        print(f'{datetime.now()} importing {file_to_import} to {bb_filename}...')
        storage = SQLiteStorage(bb_filename)
        with open(file_to_import, 'rb') as f:
            import_kmymoney(f, storage)
    else:
        print(f'invalid import file {file_to_import} - must end with .kmy')


def parse_args():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--install_qt', dest='install_qt', action='store_true')
    parser.add_argument('-f', '--file_name', dest='file_name')
    parser.add_argument('--cli', dest='cli', action='store_true')
    parser.add_argument('-i', '--import', dest='file_to_import')
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    args = parse_args()
    if args.install_qt:
        _do_qt_install()
        sys.exit(0)

    if args.file_to_import:
        import_file(args.file_to_import)
        sys.exit(0)

    if args.file_name and not os.path.exists(args.file_name):
        raise Exception('no such file: "%s"' % args.file_name)

    if args.cli:
        if not args.file_name:
            print('file name argument required for CLI mode')
            sys.exit(1)
        try:
            CLI(args.file_name).run()
            sys.exit(0)
        except Exception:
            import traceback
            log(traceback.format_exc())
            raise

    try:
        from PySide2 import QtWidgets, QtGui, QtCore
    except ImportError:
        install_qt_for_python()

    app = QtWidgets.QApplication([])
    if args.file_name:
        gui = GUI_QT(args.file_name)
    else:
        gui = GUI_QT()
    try:
        app.exec_()
    except Exception:
        import traceback
        log(traceback.format_exc())
        raise
