#!/usr/bin/env python3
'''
Architecture:
    Business Objects - Account, Transaction, Ledger, ... classes. They know nothing about the storage or UI.
    Storage - SQLiteStorage (or another storage class). Handles saving & retrieving business objects from storage.
        - normalize user strings to NFC
        - store numbers as fractions - numerator integer field and denominator integer field
    Engine - has a storage object, and implements application logic.
    Outer Layer - UI (GUI, console). Has an engine object, and handles displaying data to the user and sending user actions to the engine.
    No objects should use private/hidden members of other objects.
'''
from collections import namedtuple
from contextlib import contextmanager
import copy
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from fractions import Fraction
from functools import partial
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unicodedata
try:
    import readline
except ImportError:
    readline = None
try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    tk = None


__version__ = '0.6.1.dev'
TITLE = f'bricbooks {__version__}'
SQLITE_VERSION = sqlite3.sqlite_version_info


if sys.platform == 'darwin':
    USER_DIR = os.path.expanduser('~/Library/Application Support')
    CONFIG_DIR = USER_DIR
elif sys.platform == 'win32':
    USER_DIR = os.path.expanduser('~')
    CONFIG_DIR = USER_DIR
else:
    USER_DIR = os.path.expanduser('~')
    CONFIG_DIR = os.path.expanduser('~/.config/bricbooks')


if SQLITE_VERSION < (3, 37, 0):
    msg = f'SQLite version {SQLITE_VERSION} is too old: need at least 3.37.0'
    log(msg)
    print(msg)
    sys.exit(1)


def log(msg):
    file_name = 'bricbooks.log'
    log_filepath = os.path.join(USER_DIR, file_name)
    msg = f'{datetime.now()} {msg}\n'
    with open(log_filepath, 'ab') as f:
        f.write(msg.encode('utf8'))


class Config:

    @staticmethod
    def save_recently_used_file(file_path, suppress_errors=False):
        config_path = os.path.join(CONFIG_DIR, 'bricbooks_config.sqlite3')
        os.makedirs(CONFIG_DIR, exist_ok=True)
        db = sqlite3.connect(config_path, isolation_level=None)
        cursor = db.cursor()
        try:
            tables = cursor.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
            if not tables:
                with sqlite_txn(cursor):
                    cursor.execute('CREATE TABLE recently_used (path TEXT NOT NULL UNIQUE) STRICT')
            with sqlite_txn(cursor):
                cursor.execute('INSERT INTO recently_used (path) VALUES (?)', (os.path.abspath(file_path),))
            db.close()
        except Exception:
            db.close()
            if suppress_errors:
                pass
            else:
                raise

    @staticmethod
    def get_recently_used_files():
        config_path = os.path.join(CONFIG_DIR, 'bricbooks_config.sqlite3')
        if os.path.exists(config_path):
            db = sqlite3.connect(config_path, isolation_level=None)
        else:
            return []
        try:
            results = db.execute('SELECT path FROM recently_used').fetchall()
            db.close()
            return [r[0] for r in results]
        except Exception:
            db.close()
            return []


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


class TransactionAction(Enum):
    DEFAULT = ''
    BUY = 'share-buy'
    SELL = 'share-sell'
    SPLIT = 'share-split'
    REINVEST = 'share-reinvest'
    ADD = 'share-add'
    REMOVE = 'share-remove'

    @staticmethod
    def get_combobox_choices():
        return {
            '': '',
            'Buy Shares': 'share-buy',
            'Sell Shares': 'share-sell',
            'Split Shares': 'share-split',
            'Reinvest': 'share-reinvest',
            'Add Shares': 'share-add',
            'Remove Shares': 'share-remove',
        }


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

class InvalidStorageFile(RuntimeError):
    pass

class DataImportError(RuntimeError):
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


def increment_month(date_obj):
    if date_obj.month == 12:
        return date(date_obj.year + 1, 1, date_obj.day)
    if date_obj.month == 1 and date_obj.day > 28:
        return date(date_obj.year, 2, 28)
    if date_obj.day == 31 and date_obj.month in [3, 5, 8, 10]:
        return date(date_obj.year, date_obj.month+1, 30)
    return date(date_obj.year, date_obj.month+1, date_obj.day)


def increment_half_month(date_obj):
    if date_obj.month == 12 and date_obj.day > 15:
        year = date_obj.year + 1
    else:
        year = date_obj.year
    if date_obj.month == 2:
        if date_obj.day > 27:
            return date(year, 3, 15)
        elif date_obj.day > 14:
            return date(year, 3, date_obj.day%14)
        else:
            return date(year, 2, date_obj.day+14)
    if date_obj.day > 15:
        month = date_obj.month+1
        if month == 13:
            month = 1
    else:
        month = date_obj.month
    if date_obj.day in [30, 31]:
        if date_obj.month == 1:
            return date(year, month, 14)
        return date(year, month, 15)
    if date_obj.day > 15:
        return date(year, month, date_obj.day%15)
    return date(year, month, date_obj.day+15)


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


def normalize(s):
    # save all user data as NFC
    if s:
        return unicodedata.normalize('NFC', s)
    return s


def to_ascii(s):
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')


class Commodity:
    __slots__ = ('id', 'type', 'code', 'name')

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
    __slots__ = ('id', 'type', 'commodity', 'number', 'name', 'parent', 'description', 'alternate_id', 'closed',
                 'other_data', 'child_level')

    def __init__(self, id_=None, type_=None, commodity=None, number=None, name=None, parent=None, alternate_id=None,
                 description=None, closed=None, other_data=None, child_level=0):
        self.id = id_
        if not type_:
            raise InvalidAccountError('Account must have a type')
        if not name:
            raise InvalidAccountNameError('Account must have a name')
        self.type = self._check_type(type_)
        self.commodity = commodity
        self.number = number or None
        self.name = name
        self.parent = parent
        self.description = description
        self.alternate_id = alternate_id
        self.closed = closed
        self.other_data = other_data
        self.child_level = child_level

    def __str__(self):
        if self.number:
            return '%s: %s' % (self.number, self.name)
        else:
            return self.name

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other_account):
        if not other_account:
            return False
        if not isinstance(other_account, Account):
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
    __slots__ = ('id', 'name', 'notes')

    def __init__(self, name, notes='', id_=None):
        if not name:
            raise Exception('must pass in a payee name')
        self.name = name
        self.notes = notes
        self.id = id_

    def __eq__(self, other_payee):
        if not other_payee:
            return False
        if not isinstance(other_payee, Payee):
            return False
        if self.id and other_payee.id:
            return self.id == other_payee.id
        else:
            raise InvalidPayeeError("Can't compare payees without an id")

    def __hash__(self):
        return self.id


def get_validated_amount(value):
    amount = None
    #a string could contain ',', so remove those
    if isinstance(value, str):
        value = value.replace(',', '')
    #try to only allow exact values (eg. no floats)
    if isinstance(value, (int, str, Fraction)):
        try:
            amount = Fraction(value)
        except Exception:
            raise InvalidAmount(f'invalid value "{value}"')
    else:
        raise InvalidAmount(f'invalid value type: {type(value)} {value}')
    if (100 % amount.denominator) != 0:
        raise InvalidAmount('no fractions of cents allowed: %s' % value)
    return amount


def get_validated_quantity(value):
    quantity = None
    #a string could contain ',', so remove those
    if isinstance(value, str):
        value = value.replace(',', '')
    #try to only allow exact values (eg. no floats)
    if isinstance(value, (int, str, Fraction)):
        try:
            quantity = Fraction(value)
        except InvalidOperation:
            raise InvalidQuantity(f'error generating Fraction from "{value}"')
    else:
        raise InvalidQuantity(f'invalid value type: {type(value)} {value}')
    return quantity


def fraction_to_decimal(f):
    return Decimal(f.numerator) / Decimal(f.denominator)


def amount_display(amount):
    return '{0:,.2f}'.format(fraction_to_decimal(amount))


def quantity_display(quantity):
    if quantity:
        return str(fraction_to_decimal(quantity))
    return ''


def check_txn_splits(splits):
    total = Fraction(0)
    for split in splits:
        total += split['amount']
        if split.get('action'):
            if split['account'].type != AccountType.SECURITY:
                raise InvalidTransactionError('actions can only be used with SECURITY accounts')
    if total != Fraction(0):
        amounts = []
        for split in splits:
            amounts.append(amount_display(split['amount']))
        raise InvalidTransactionError("splits don't balance: %s" % ', '.join(amounts))


def handle_txn_splits(splits):
    for split in splits:
        account = split['account']
        if not account:
            raise InvalidTransactionError('must have a valid account in splits')
        try:
            amount = get_validated_amount(split['amount'])
        except InvalidAmount as e:
            raise InvalidTransactionError('invalid split: %s' % e)
        if 'quantity' not in split or split['quantity'] == '':
            split['quantity'] = amount
        split['quantity'] = get_validated_quantity(split['quantity'])
        split['amount'] = amount
        if 'status' in split:
            split['status'] = split['status'].upper()
        if 'payee' in split:
            if split['payee']:
                payee = split['payee']
                if isinstance(payee, str):
                    split['payee'] = Payee(name=payee)
                elif isinstance(payee, Payee):
                    split['payee'] = payee
                else:
                    raise InvalidTransactionError(f'invalid payee: {payee}')
            else:
                split.pop('payee')
    return splits


class Transaction:
    __slots__ = ('id', 'splits', 'txn_date', 'entry_date', 'description', 'alternate_id', 'balance')

    CLEARED = 'C'
    RECONCILED = 'R'

    def __init__(self, txn_date=None, entry_date=None, splits=None, description='', id_=None, alternate_id=None):
        self.splits = handle_txn_splits(splits)
        self.txn_date = self._check_txn_date(txn_date)
        if entry_date and isinstance(entry_date, str):
            self.entry_date = date.fromisoformat(entry_date)
        else:
            self.entry_date = entry_date
        self.description = description
        self.id = id_
        self.alternate_id = alternate_id

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

    def get_status(self, account):
        for split in self.splits:
            if split['account'] == account:
                return split.get('status', '')

    def update_reconciled_state(self, account):
        #this updates the txn, instead of creating a new one - might want to change it
        for split in self.splits:
            if split['account'] == account:
                cur_status = split.get('status', '')
                if cur_status == Transaction.CLEARED:
                    split.pop('status')
                else:
                    split['status'] = Transaction.CLEARED
                return


def _transfer_account_display(splits, main_account):
    if len(splits) == 2:
        for split in splits:
            account = split['account']
            if account != main_account:
                return str(account)
    return 'multiple'


def get_display_strings_for_ledger(account, txn, date_format):
    '''txn can be either Transaction or ScheduledTransaction'''
    split = [s for s in txn.splits if s['account'] == account][0]
    amount = split['amount']
    if amount < Fraction(0):
        #make negative amount display as positive
        withdrawal = amount_display(amount * Fraction('-1'))
        deposit = ''
    else:
        withdrawal = ''
        deposit = amount_display(amount)
    quantity = quantity_display(split['quantity'])
    if 'payee' in split:
        payee = split['payee'].name
    else:
        payees = [s['payee'] for s in txn.splits if 'payee' in s]
        if payees:
            payee = payees[0].name
        else:
            payee = ''
    if split.get('description'):
        description = split['description']
    elif txn.description:
        description = txn.description
    else:
        description = ''
    display_strings = {
            'withdrawal': withdrawal,
            'deposit': deposit,
            'quantity': quantity,
            'description': description,
            'payee': payee,
            'transfer_account': _transfer_account_display(splits=txn.splits, main_account=account),
            'action': split.get('action', '')
        }
    if isinstance(txn, ScheduledTransaction):
        display_strings['name'] = txn.name
        display_strings['next_due_date'] = txn.next_due_date.strftime(date_format)
        display_strings['frequency'] = str(txn.frequency)
        display_strings['txn_date'] = txn.next_due_date.strftime(date_format)
    else:
        display_strings['status'] = split.get('status', '')
        display_strings['type'] = split.get('type', '')
        display_strings['txn_date'] = txn.txn_date.strftime(date_format)
    if hasattr(txn, 'balance'):
        display_strings['balance'] = amount_display(txn.balance)
    return display_strings


LedgerBalances = namedtuple('LedgerBalances', ['current', 'current_cleared'])


def splits_display(splits):
    account_amt_list = []
    for split in splits:
        account = split['account']
        amount = split['amount']
        account_amt_list.append(f'{account.name}: {amount_display(amount)}')
    return '; '.join(account_amt_list)


class ScheduledTransactionFrequency(Enum):
    WEEKLY = 'weekly'
    MONTHLY = 'monthly'
    SEMI_MONTHLY = 'semi_monthly'
    QUARTERLY = 'quarterly'
    YEARLY = 'yearly'


class ScheduledTransaction:
    __slots__ = ('id', 'name', 'frequency', 'next_due_date', 'splits', 'description', 'status')

    def __init__(self, name, frequency, next_due_date=None, splits=None, description='', status='', id_=None):
        self.name = name
        if isinstance(frequency, ScheduledTransactionFrequency):
            self.frequency = frequency
        else:
            try:
                self.frequency = ScheduledTransactionFrequency(frequency)
            except ValueError:
                raise InvalidScheduledTransactionError('invalid frequency "%s"' % frequency)
        self.next_due_date = self._check_date(next_due_date)
        self.splits = handle_txn_splits(splits or {})
        self.description = description
        self.status = status.upper()
        self.id = id_

    def __str__(self):
        return '%s: %s (%s %s) (%s)' % (self.id, self.name, self.frequency.name, self.next_due_date, splits_display(self.splits))

    def __repr__(self):
        return str(self)

    def _check_date(self, dt):
        if dt:
            try:
                return get_date(dt)
            except Exception:
                raise InvalidScheduledTransactionError('invalid date "%s"' % dt)

    def is_due(self):
        if self.next_due_date and self.next_due_date <= date.today():
            return True
        return False

    def advance_to_next_due_date(self):
        #update next_due_date since the txn has been entered
        if self.frequency == ScheduledTransactionFrequency.WEEKLY:
            self.next_due_date = self.next_due_date + timedelta(days=7)
        elif self.frequency == ScheduledTransactionFrequency.MONTHLY:
            self.next_due_date = increment_month(self.next_due_date)
        elif self.frequency == ScheduledTransactionFrequency.SEMI_MONTHLY:
            self.next_due_date = increment_half_month(self.next_due_date)
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
    __slots__ = ('id', 'start_date', 'end_date', 'name', '_budget_data', '_income_spending_info')

    @staticmethod
    def round_percent_available(percent):
        return percent.quantize(Decimal('1.'), rounding=ROUND_HALF_UP)

    @staticmethod
    def remaining_time_period(current_date, start_date, end_date):
        '''How much of the Budget time period is left'''
        days_in_budget = (end_date - start_date).days + 1
        days_passed = (current_date - start_date).days
        return Fraction(100) - (Fraction(days_passed, days_in_budget) * Fraction(100))

    @staticmethod
    def get_current_status(current_date, start_date, end_date, remaining_percent):
        '''Compare budget amount remaining to budget time period remaining'''
        if current_date and current_date < end_date and current_date > start_date:
            remaining_time_period = Budget.remaining_time_period(current_date, start_date, end_date)
            difference = remaining_time_period - remaining_percent
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
        self._income_spending_info = None
        if income_spending_info:
            self._income_spending_info = {}
            for account, info in income_spending_info.items():
                good_info = {}
                for key, val in info.items():
                    if val:
                        good_info[key] = get_validated_amount(val)
                    else:
                        good_info[key] = val
                self._income_spending_info[account] = good_info

    def __str__(self):
        return self.display()

    def display(self, show_id=True):
        s = f'{self.start_date} - {self.end_date}'
        if self.name:
            s = f'{self.name} ({s})'
        if show_id:
            s = f'{self.id}: {s}'
        return s

    def __eq__(self, other_budget):
        if not other_budget:
            return False
        if not isinstance(other_budget, Budget):
            return False
        if self.id and other_budget.id:
            return self.id == other_budget.id
        else:
            raise BudgetError("Can't compare budgets without an id")

    @staticmethod
    def sort_accounts(accounts):
        return sorted([a for a in accounts], key=lambda acc: acc.number or 'ZZZ')

    def _get_account_report_info(self, account, current_date):
        report_info = {'name': account.name}
        report_info.update(self._budget_data[account])
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
        return report_info

    def _process_account(self, account, current_date, report, expense_totals_info, income_totals_info, group_totals):
        report_info = self._get_account_report_info(account, current_date)
        carryover = report_info.get('carryover', Fraction(0))
        income = report_info.get('income', Fraction(0))
        amount = report_info.get('amount', Fraction(0))
        group_totals['amount'] += amount
        group_totals['carryover'] += carryover
        group_totals['income'] += income
        if account.type == AccountType.EXPENSE:
            spent = report_info.get('spent', Fraction(0))
            expense_totals_info['amount'] += amount
            expense_totals_info['carryover'] += carryover
            expense_totals_info['income'] += income
            expense_totals_info['spent'] += spent
            group_totals['spent'] += spent
            report['expense'].append(report_info)
        else:
            income_totals_info['amount'] += amount
            income_totals_info['carryover'] += carryover
            income_totals_info['income'] += income
            report['income'].append(report_info)

    def get_budget_data(self):
        '''returns {account1: {'amount': xxx}, account2: {}, ...}'''
        return self._budget_data

    def get_report_display(self, current_date=None):
        '''adds income & spending data to budget data, & converts to strings, for a budget report to display
        { 'expense': [
                {'name': ..., 'amount': '10', 'income': '5', 'carryover': '5', 'total_budget': '20', 'spent': '10', 'remaining': '10', 'remaining_percent': '50%', 'notes': 'note1'},
                {'name': ..., 'amount': '5', 'total_budget': '5', 'remaining': '5', 'remaining_percent': '100%'},
                {},
            ],
          'income': [
                {'name': ..., 'amount': '10', 'income': '7', 'remaining': '3', 'remaining_percent': '30%', 'notes': 'note2', 'current_status': '-1.2%'}, #based on date passed in, should be at 71.2% (only relevant if date is within the budget period (get percentage through budget period, compare to remaining_percent)
                {'name': ...},
          ] }
        '''
        if self._income_spending_info is None:
            raise BudgetError('must pass in income_spending_info to get the report display')
        report = {'expense': [], 'income': []}
        income_totals_info = {'name': 'Total Income', 'amount': Fraction(0), 'carryover': Fraction(0), 'income': Fraction(0)}
        expense_totals_info = {'name': 'Total Expense', 'amount': Fraction(0), 'carryover': Fraction(0), 'income': Fraction(0), 'spent': Fraction(0)}
        top_level_income_accounts = Budget.sort_accounts(list([a for a in self._budget_data.keys() if not a.parent and a.type == AccountType.INCOME]))
        top_level_expense_accounts = Budget.sort_accounts(list([a for a in self._budget_data.keys() if not a.parent and a.type == AccountType.EXPENSE]))
        for top_level_account in (top_level_income_accounts + top_level_expense_accounts):
            group_totals = {'name': f'Total {top_level_account.name}', 'amount': Fraction(0), 'carryover': Fraction(0), 'income': Fraction(0)}
            if top_level_account.type == AccountType.EXPENSE:
                group_totals['spent'] = Fraction(0)
            self._process_account(top_level_account, current_date, report, expense_totals_info, income_totals_info, group_totals)
            has_children = False
            for account in Budget.sort_accounts(list([a for a in self._budget_data.keys() if a.parent == top_level_account])):
                has_children = True
                self._process_account(account, current_date, report, expense_totals_info, income_totals_info, group_totals)
            if has_children:
                if top_level_account.type == AccountType.EXPENSE:
                    group_totals['total_budget'] = group_totals['amount'] + group_totals['carryover'] + group_totals['income']
                    group_totals['remaining'] = group_totals['total_budget'] - group_totals['spent']
                    if group_totals['total_budget']:
                        group_percent_available = (group_totals['remaining'] / group_totals['total_budget']) * Fraction(100)
                    else:
                        group_percent_available = Fraction(0)
                    group_totals['remaining_percent'] = '{}%'.format(Budget.round_percent_available(fraction_to_decimal(group_percent_available)))
                    group_totals['current_status'] = Budget.get_current_status(current_date, self.start_date, self.end_date, group_percent_available)
                    report['expense'].append(group_totals)
                else:
                    group_totals['remaining'] = group_totals['amount'] - group_totals['income']
                    if group_totals['amount']:
                        group_percent_available = (group_totals['remaining'] / group_totals['amount']) * Fraction(100)
                    else:
                        group_percent_available = Fraction(0)
                    group_totals['remaining_percent'] = '{}%'.format(Budget.round_percent_available(fraction_to_decimal(group_percent_available)))
                    group_totals['current_status'] = Budget.get_current_status(current_date, self.start_date, self.end_date, group_percent_available)
                    report['income'].append(group_totals)
        expense_totals_info['total_budget'] = expense_totals_info['amount'] + expense_totals_info['carryover'] + expense_totals_info['income']
        expense_totals_info['remaining'] = expense_totals_info['total_budget'] - expense_totals_info['spent']
        expense_percent_available = (expense_totals_info['remaining'] / expense_totals_info['total_budget']) * Fraction(100)
        expense_totals_info['remaining_percent'] = '{}%'.format(Budget.round_percent_available(fraction_to_decimal(expense_percent_available)))
        expense_totals_info['current_status'] = Budget.get_current_status(current_date, self.start_date, self.end_date, expense_percent_available)
        income_totals_info['remaining'] = income_totals_info['amount'] - income_totals_info['income']
        if income_totals_info['amount']:
            income_percent_available = (income_totals_info['remaining'] / income_totals_info['amount']) * Fraction(100)
        else:
            income_percent_available = Fraction(0)
        income_totals_info['remaining_percent'] = '{}%'.format(Budget.round_percent_available(fraction_to_decimal(income_percent_available)))
        income_totals_info['current_status'] = Budget.get_current_status(current_date, self.start_date, self.end_date, income_percent_available)
        report['income'].append(income_totals_info)
        report['expense'].append(expense_totals_info)
        for info in (report['income'] + report['expense']):
            for key in info.keys():
                if info[key] == Fraction(0):
                    info[key] = ''
                else:
                    if isinstance(info[key], Fraction):
                        info[key] = amount_display(info[key])
                    elif isinstance(info[key], str):
                        pass
                    else:
                        raise BudgetError(f'invalid value for display: {key} => {info[key]}')
        return report


### Storage ###

@contextmanager
def sqlite_txn(cursor):
    cursor.execute('BEGIN IMMEDIATE')
    try:
        yield
        cursor.execute('COMMIT')
    except BaseException as e:
        cursor.execute('ROLLBACK')
        raise SQLiteStorageError(str(e)) from e

class SQLiteStorage:

    SCHEMA_VERSION = 2

    DB_INIT_STATEMENTS = [
        'CREATE TABLE commodity_types ('
            'type TEXT NOT NULL PRIMARY KEY,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,' #UTC
            'CHECK (type != "")) STRICT',
        'CREATE TABLE commodities ('
            'id INTEGER PRIMARY KEY,'
            'type TEXT NOT NULL,'
            'code TEXT NOT NULL UNIQUE,'
            'name TEXT NOT NULL,'
            'trading_currency_id INTEGER,'
            'trading_market TEXT NOT NULL DEFAULT "",'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'CHECK (type != ""),'
            'CHECK (code != ""),'
            'CHECK (name != ""),'
            'FOREIGN KEY(type) REFERENCES commodity_types(type) ON DELETE RESTRICT,'
            'FOREIGN KEY(trading_currency_id) REFERENCES commodities(id) ON DELETE RESTRICT) STRICT',
        'CREATE TRIGGER commodity_updated UPDATE ON commodities BEGIN UPDATE commodities SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE institutions ('
            'id INTEGER PRIMARY KEY,'
            'name TEXT UNIQUE NOT NULL,'
            'address TEXT NOT NULL DEFAULT "",'
            'routing_number TEXT NOT NULL DEFAULT "",'
            'bic TEXT NOT NULL DEFAULT "",'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'CHECK (name != "")) STRICT',
        'CREATE TRIGGER institution_updated UPDATE ON institutions BEGIN UPDATE institutions SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE account_types ('
            'type TEXT NOT NULL PRIMARY KEY,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'CHECK (type != "")) STRICT',
        'CREATE TABLE accounts ('
            'id INTEGER PRIMARY KEY,'
            'type TEXT NOT NULL,'
            'commodity_id INTEGER NOT NULL,'
            'institution_id INTEGER,'
            'number TEXT UNIQUE,'
            'name TEXT NOT NULL,'
            'parent_id INTEGER,'
            'description TEXT NOT NULL DEFAULT "",'
            'closed INTEGER NOT NULL DEFAULT 0,'
            'alternate_id TEXT NOT NULL DEFAULT "",' # eg. the previous ID for migrated accounts
            'other_data TEXT NOT NULL DEFAULT "{}",'
            'open_date TEXT,'
            'close_date TEXT,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'CHECK (number != ""),'
            'CHECK (name != ""),'
            'CHECK (json_type(other_data) IS "object"),'
            'CHECK (closed = 0 OR closed = 1),'
            'CHECK (open_date IS NULL OR open_date IS strftime("%Y-%m-%d", open_date)),'
            'CHECK (close_date IS NULL OR (closed = 1 AND close_date IS strftime("%Y-%m-%d", close_date))),'
            'FOREIGN KEY(type) REFERENCES account_types(type) ON DELETE RESTRICT,'
            'FOREIGN KEY(parent_id) REFERENCES accounts(id) ON DELETE RESTRICT,'
            'FOREIGN KEY(commodity_id) REFERENCES commodities(id) ON DELETE RESTRICT,'
            'FOREIGN KEY(institution_id) REFERENCES institutions(id) ON DELETE RESTRICT,'
            'UNIQUE(name, parent_id)) STRICT',
        'CREATE TRIGGER account_updated UPDATE ON accounts BEGIN UPDATE accounts SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE budgets ('
            'id INTEGER PRIMARY KEY,'
            'name TEXT,'
            'start_date TEXT NOT NULL,'
            'end_date TEXT NOT NULL,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'CHECK (start_date IS strftime("%Y-%m-%d", start_date)),'
            'CHECK (end_date IS strftime("%Y-%m-%d", end_date))) STRICT',
        'CREATE TRIGGER budget_updated UPDATE ON budgets BEGIN UPDATE budgets SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE budget_values ('
            'id INTEGER PRIMARY KEY,'
            'budget_id INTEGER NOT NULL,'
            'account_id INTEGER NOT NULL,'
            'amount_numerator INTEGER NOT NULL,'
            'amount_denominator INTEGER NOT NULL,'
            'carryover_numerator INTEGER,'
            'carryover_denominator INTEGER,'
            'notes TEXT NOT NULL DEFAULT "",'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'CHECK (amount_denominator != 0),'
            'CHECK (carryover_denominator != 0),'
            'FOREIGN KEY(budget_id) REFERENCES budgets(id) ON DELETE RESTRICT,'
            'FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE RESTRICT) STRICT',
        'CREATE TRIGGER budget_value_updated UPDATE ON budget_values BEGIN UPDATE budget_values SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE payees ('
            'id INTEGER PRIMARY KEY,'
            'name TEXT UNIQUE NOT NULL,'
            'notes TEXT NOT NULL DEFAULT "",'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'CHECK (name != "")) STRICT',
        'CREATE TRIGGER payee_updated UPDATE ON payees BEGIN UPDATE payees SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE scheduled_transaction_frequencies ('
            'frequency TEXT NOT NULL PRIMARY KEY,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'CHECK (frequency != "")) STRICT',
        'CREATE TABLE scheduled_transactions ('
            'id INTEGER PRIMARY KEY,'
            'name TEXT UNIQUE NOT NULL,'
            'frequency TEXT NOT NULL,'
            'next_due_date TEXT,'
            'type TEXT,'
            'description TEXT NOT NULL DEFAULT "",'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'FOREIGN KEY(frequency) REFERENCES scheduled_transaction_frequencies(frequency) ON DELETE RESTRICT,'
            'CHECK (name != ""),'
            'CHECK (next_due_date IS NULL OR next_due_date IS strftime("%Y-%m-%d", next_due_date))) STRICT',
        'CREATE TRIGGER scheduled_transaction_updated UPDATE ON scheduled_transactions BEGIN UPDATE scheduled_transactions SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE scheduled_transaction_splits ('
            'id INTEGER PRIMARY KEY,'
            'scheduled_transaction_id INTEGER NOT NULL,'
            'account_id INTEGER NOT NULL,'
            'value_numerator INTEGER NOT NULL,'
            'value_denominator INTEGER NOT NULL,'
            'quantity_numerator INTEGER,'
            'quantity_denominator INTEGER,'
            'reconciled_state TEXT NOT NULL DEFAULT "",'
            'description TEXT NOT NULL DEFAULT "",'
            'action TEXT,'
            'payee_id INTEGER,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'FOREIGN KEY(scheduled_transaction_id) REFERENCES scheduled_transactions(id) ON DELETE RESTRICT,'
            'FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE RESTRICT,'
            'FOREIGN KEY(payee_id) REFERENCES payees(id) ON DELETE RESTRICT,'
            'CHECK (reconciled_state = "" OR reconciled_state = "C" OR reconciled_state = "R"),'
            'CHECK (value_denominator != 0),'
            'CHECK (quantity_denominator != 0)) STRICT',
        'CREATE TRIGGER scheduled_transaction_split_updated UPDATE ON scheduled_transaction_splits BEGIN UPDATE scheduled_transaction_splits SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE transaction_actions ('
            'action TEXT NOT NULL PRIMARY KEY,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP) STRICT',
        'CREATE TABLE transactions ('
            'id INTEGER PRIMARY KEY,'
            'commodity_id INTEGER NOT NULL,'
            'date TEXT,' # date the transaction took place
            'description TEXT NOT NULL DEFAULT "",'
            'entry_date TEXT NOT NULL DEFAULT (date(\'now\', \'localtime\')),' # date the transaction was entered
            'alternate_id TEXT NOT NULL DEFAULT "",' # eg. the previous ID for migrated txns
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'FOREIGN KEY(commodity_id) REFERENCES commodities(id) ON DELETE RESTRICT,'
            'CHECK (date IS NULL OR date IS strftime("%Y-%m-%d", date)),'
            'CHECK (entry_date IS strftime("%Y-%m-%d", entry_date))) STRICT',
        'CREATE TRIGGER transaction_updated UPDATE ON transactions BEGIN UPDATE transactions SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE transaction_splits ('
            'id INTEGER PRIMARY KEY,'
            'transaction_id INTEGER NOT NULL,'
            'account_id INTEGER NOT NULL,'
            'value_numerator INTEGER NOT NULL,' # can be 0 (for eg. memo transactions for stock splits), but not null
            'value_denominator INTEGER NOT NULL,'
            'quantity_numerator INTEGER,'
            'quantity_denominator INTEGER,'
            'reconciled_state TEXT NOT NULL DEFAULT "",'
            'type TEXT NOT NULL DEFAULT "",'
            'description TEXT NOT NULL DEFAULT "",'
            'action TEXT NOT NULL DEFAULT "",'
            'payee_id INTEGER,'
            'post_date TEXT,'
            'reconcile_date TEXT,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE RESTRICT,'
            'FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE RESTRICT,'
            'FOREIGN KEY(action) REFERENCES transaction_actions(action) ON DELETE RESTRICT,'
            'FOREIGN KEY(payee_id) REFERENCES payees(id) ON DELETE RESTRICT,'
            'CHECK (reconciled_state = "" OR reconciled_state = "C" OR reconciled_state = "R"),'
            'CHECK (post_date IS NULL OR (reconciled_state != "" AND post_date IS strftime("%Y-%m-%d", post_date))),'
            'CHECK (reconcile_date IS NULL OR (reconciled_state = "R" AND reconcile_date IS strftime("%Y-%m-%d", reconcile_date))),'
            'CHECK (value_denominator != 0),'
            'CHECK (quantity_denominator != 0)) STRICT',
        'CREATE INDEX transaction_split_txn_id_index ON transaction_splits(transaction_id)',
        'CREATE TRIGGER transaction_split_updated UPDATE ON transaction_splits BEGIN UPDATE transaction_splits SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE misc ('
            'key TEXT UNIQUE NOT NULL,'
            'value ANY NOT NULL,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'CHECK (key != "")) STRICT',
        'CREATE TRIGGER misc_updated UPDATE ON misc BEGIN UPDATE misc SET updated = CURRENT_TIMESTAMP WHERE key = old.key; END;',
        'CREATE TABLE bookmarked_accounts ('
            'account_id INTEGER UNIQUE NOT NULL,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE) STRICT',
    ] + [
        f'INSERT INTO commodity_types(type) VALUES("{commodity_type.value}")' for commodity_type in CommodityType
    ] + [
        f'INSERT INTO scheduled_transaction_frequencies(frequency) VALUES("{frequency.value}")' for frequency in ScheduledTransactionFrequency
    ] + [
        f'INSERT INTO account_types(type) VALUES("{account_type.value}")' for account_type in AccountType
    ] + [
        f'INSERT INTO transaction_actions(action) VALUES("{action.value}")' for action in TransactionAction
    ] + [
        "INSERT INTO misc(key, value) VALUES('%s', %s)" % ('schema_version', 1),
        "INSERT INTO commodities(type, code, name) VALUES('%s', '%s', '%s')" %
            (CommodityType.CURRENCY.value, 'USD', 'US Dollar'),
    ]

    MIGRATIONS = {
        1: [
            'CREATE TABLE preferences ('
                'name TEXT NOT NULL PRIMARY KEY,'
                'value ANY NOT NULL,'
                'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,' #UTC
                'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
                'CHECK (name != "")) STRICT',
            'CREATE TRIGGER preferences_updated UPDATE ON preferences BEGIN UPDATE preferences SET updated = CURRENT_TIMESTAMP WHERE name = old.name; END;',
            "UPDATE misc SET value = 2 WHERE key = 'schema_version'",
        ],
    }

    @staticmethod
    def get_db_connection(conn_name):
        #conn_name is either ':memory:' or the name of the data file
        conn = sqlite3.connect(conn_name, isolation_level=None)
        conn.execute('PRAGMA foreign_keys = ON;')
        result = conn.execute('PRAGMA foreign_keys').fetchall()
        if result[0][0] != 1:
            msg = 'WARNING: can\'t enable sqlite3 foreign_keys'
            log(msg)
            print(msg)
        return conn

    def __init__(self, conn_name):
        if not conn_name:
            raise SQLiteStorageError('must pass in conn_name')
        self._db_connection = SQLiteStorage.get_db_connection(conn_name)
        if not self._tables():
            self._setup_db()
        schema_version = self._db_connection.execute('SELECT value FROM misc WHERE key="schema_version"').fetchall()[0][0]
        if schema_version != SQLiteStorage.SCHEMA_VERSION:
            if schema_version == 1:
                log('Starting to migrate from version 1 to version 2')
                try:
                    cur = self._db_connection.cursor()
                    with sqlite_txn(cur):
                        for statement in self.MIGRATIONS[1]:
                            cur.execute(statement)
                except Exception as e:
                    log(f'Error migrating to version 2 {e}')
                    import tracback
                    log(traceback.format_exc())
                    raise SQLiteStorageError('Error migrating DB to version 2') from e
                log('Migrated to version 2')
            else:
                msg = f'ERROR: wrong schema version: {schema_version}'
                log(msg)
                raise SQLiteStorageError(msg)

    def _tables(self):
        results = self._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()

        return [r[0] for r in results]

    def _setup_db(self):
        '''
        Initialize empty DB.
        '''
        cur = self._db_connection.cursor()
        with sqlite_txn(cur):
            for statement in self.DB_INIT_STATEMENTS:
                cur.execute(statement)

        for schema, migrations in self.MIGRATIONS.items():
            with sqlite_txn(cur):
                for statement in migrations:
                    cur.execute(statement)

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
        cur = self._db_connection.cursor()
        with sqlite_txn(cur):
            cur.execute('INSERT INTO commodities(type, code, name) VALUES(?, ?, ?)',
                        (commodity.type.value, normalize(commodity.code), normalize(commodity.name)))
            commodity.id = cur.lastrowid

    def get_account(self, id_=None, number=None, name=None):
        fields = ['id', 'type', 'commodity_id', 'number', 'name', 'parent_id', 'alternate_id', 'description', 'closed', 'other_data']
        fields_str = ','.join(fields)
        if id_:
            account_info = self._db_connection.execute(f'SELECT {fields_str} FROM accounts WHERE id = ?', (id_,)).fetchone()
            if not account_info:
                raise Exception(f'no account with id "{id_}"')
        elif number:
            account_info = self._db_connection.execute(f'SELECT {fields_str} FROM accounts WHERE number = ?', (number,)).fetchone()
            if not account_info:
                raise Exception(f'no account with number "{number}"')
        elif name:
            account_info = self._db_connection.execute(f'SELECT {fields_str} FROM accounts WHERE name = ?', (name,)).fetchone()
            if not account_info:
                raise Exception(f'no account with name "{name}"')
        else:
            raise Exception('get_account: must pass in id_ or number or name')
        commodity = self.get_commodity(account_info[2])
        parent = None
        if account_info[5]:
            parent = self.get_account(account_info[5])
        alternate_id = account_info[6]
        description = account_info[7]
        if account_info[8] == 1:
            closed = True
        else:
            closed = False
        other_data = json.loads(account_info[9])
        if 'interest-rate-percent' in other_data:
            other_data['interest-rate-percent'] = Fraction(other_data['interest-rate-percent'])
        return Account(
                id_=account_info[0],
                type_=AccountType(account_info[1]),
                commodity=commodity,
                number=account_info[3],
                name=account_info[4],
                parent=parent,
                alternate_id=alternate_id,
                description=description,
                closed=closed,
                other_data=other_data,
            )

    def save_account(self, account):
        parent_id = None
        if account.parent:
            parent_id = account.parent.id
        field_names = ['type', 'number', 'name', 'parent_id']
        field_values = [account.type.value, normalize(account.number), normalize(account.name), parent_id]
        if account.commodity:
            field_names.append('commodity_id')
            field_values.append(account.commodity.id)
        if account.alternate_id is not None:
            field_names.append('alternate_id')
            field_values.append(account.alternate_id)
        if account.description is not None:
            field_names.append('description')
            field_values.append(account.description)
        if account.closed is not None:
            field_names.append('closed')
            if account.closed is True:
                value = 1
            elif account.closed is False:
                value = 0
            else:
                raise InvalidAccountError(f'invalid value for closed: {account.closed}')
            field_values.append(value)
        if account.other_data is not None:
            field_names.append('other_data')
            other_data = {**account.other_data}
            if other_data:
                allowed_keys = {'term', 'fixed-interest', 'interest-rate-percent'}
                keys = set(other_data.keys())
                invalid_keys = keys - allowed_keys
                if invalid_keys:
                    raise InvalidAccountError(f'invalid keys: {invalid_keys}')
                if 'term' in other_data:
                    term_value = other_data['term']
                    if (
                        not isinstance(term_value, str) or
                        not term_value[-1] in ['y', 'm', 'w', 'd'] or
                        not term_value[:-1].isdigit()
                    ):
                        raise InvalidAccountError(f'invalid term value: {term_value}')
                if 'fixed-interest' in other_data and other_data['fixed-interest'] not in [True, False]:
                    raise InvalidAccountError(f'invalid fixed-interest value: {other_data["fixed-interest"]}')
                if 'interest-rate-percent' in other_data:
                    ir = other_data['interest-rate-percent']
                    if not isinstance(ir, (Fraction, int, str)):
                        raise InvalidAccountError(f'invalid interest-rate-percent value: {ir}')
                    ir = Fraction(ir)
                    other_data['interest-rate-percent'] = f'{ir.numerator}/{ir.denominator}'
            field_values.append(normalize(json.dumps(other_data)))
        cur = self._db_connection.cursor()
        with sqlite_txn(cur):
            if account.id:
                field_names_s = ','.join([f'{fn} = ?' for fn in field_names])
                field_values.append(account.id)
                cur.execute(f'UPDATE accounts SET {field_names_s} WHERE id = ?', field_values)
                if cur.rowcount < 1:
                    raise Exception('no account with id %s to update' % account.id)
            else:
                if 'commodity_id' not in field_names:
                    field_names.append('commodity_id')
                    field_values.append(1) # default USD commodity
                field_names_s = ','.join(field_names)
                field_names_q = ','.join(['?' for _ in field_names])
                cur.execute(f'INSERT INTO accounts({field_names_s}) VALUES({field_names_q})', field_values)
                account.id = cur.lastrowid

    def bookmark_account(self, account_id):
        cur = self._db_connection.cursor()
        with sqlite_txn(cur):
            cur.execute('INSERT INTO bookmarked_accounts(account_id) VALUES(?) ON CONFLICT(account_id) DO NOTHING', (account_id,))

    def remove_account_bookmark(self, account_id):
        cur = self._db_connection.cursor()
        with sqlite_txn(cur):
            cur.execute('DELETE FROM bookmarked_accounts WHERE account_id = ?', (account_id,))

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
        field_values = [normalize(payee.name), normalize(payee.notes)]
        cur = self._db_connection.cursor()
        with sqlite_txn(cur):
            if payee.id:
                field_values.append(payee.id)
                cur.execute('UPDATE payees SET name = ?, notes = ? WHERE id = ?', field_values)
                if cur.rowcount < 1:
                    raise Exception('no payee with id %s to update' % payee.id)
            else:
                cur.execute('INSERT INTO payees(name, notes) VALUES(?, ?)', field_values)
                payee.id = cur.lastrowid

    def _get_account_children(self, account, child_level):
        children = []
        query = 'SELECT id FROM accounts WHERE closed = ? AND parent_id = ? ORDER BY number, name'
        db_records = self._db_connection.execute(query, (0, account.id)).fetchall()
        for r in db_records:
            account = self.get_account(r[0])
            account.child_level = child_level
            children.append(account)
            children.extend(self._get_account_children(account, child_level=child_level+1))
        return children

    def _get_accounts_by_type(self, type_):
        query = 'SELECT id FROM accounts WHERE type = ? AND closed = ? AND parent_id IS NULL ORDER BY number, name'
        db_records = self._db_connection.execute(query, (type_.value, 0)).fetchall()
        accounts = []
        for r in db_records:
            account = self.get_account(r[0])
            accounts.append(account)
            accounts.extend(self._get_account_children(account, child_level=1))
        return accounts

    def get_accounts(self, type_=None):
        if type_:
            return self._get_accounts_by_type(type_)
        else:
            accounts = []
            for type_ in [AccountType.ASSET, AccountType.SECURITY, AccountType.LIABILITY, AccountType.INCOME, AccountType.EXPENSE, AccountType.EQUITY]:
                accounts.extend(self._get_accounts_by_type(type_))
            return accounts

    def get_bookmarked_accounts(self):
        query = 'SELECT account_id FROM bookmarked_accounts ORDER BY created'
        db_records = self._db_connection.execute(query).fetchall()
        accounts = []
        for r in db_records:
            accounts.append(self.get_account(r[0]))
        return accounts

    def delete_account(self, account_id, set_children_parent_id_to_null=False):
        cur = self._db_connection.cursor()
        with sqlite_txn(cur):
            if set_children_parent_id_to_null:
                query = 'SELECT id FROM accounts WHERE parent_id = ?'
                db_records = cur.execute(query, (account_id,)).fetchall()
                for r in db_records:
                    if r[0]:
                        cur.execute('UPDATE accounts SET parent_id = null WHERE id = ?', (r[0],))
            cur.execute('DELETE FROM accounts where id = ?', (account_id,))

    def _txn_from_db_record(self, db_info=None):
        if not db_info:
            raise InvalidTransactionError('no db_info to construct transaction')
        id_, commodity_id, txn_date, description, alternate_id, entry_date = db_info
        txn_date = get_date(txn_date)
        cur = self._db_connection.cursor()
        splits = []
        split_records = cur.execute('SELECT account_id, type, value_numerator, value_denominator, quantity_numerator, quantity_denominator, reconciled_state, action, payee_id, description FROM transaction_splits WHERE transaction_id = ?', (id_,))
        if split_records:
            for split_record in split_records:
                account_id = split_record[0]
                account = self.get_account(account_id)
                type_ = split_record[1]
                amount = Fraction(split_record[2], split_record[3])
                split = {'account': account, 'amount': amount, 'type': type_}
                if split_record[4]:
                    quantity = Fraction(split_record[4], split_record[5])
                    split['quantity'] = quantity
                if split_record[6]:
                    split['status'] = split_record[6]
                split['action'] = split_record[7]
                if split_record[8]:
                    split['payee'] = self.get_payee(id_=split_record[8])
                if split_record[9]:
                    split['description'] = split_record[9]
                splits.append(split)
        return Transaction(splits=splits, txn_date=txn_date, description=description,
                           id_=id_, alternate_id=alternate_id, entry_date=entry_date)

    def get_txn(self, txn_id):
        cur = self._db_connection.cursor()
        cur.execute('SELECT id,commodity_id,date,description,alternate_id,entry_date FROM transactions WHERE id = ?', (txn_id,))
        db_info = cur.fetchone()
        return self._txn_from_db_record(db_info=db_info)

    def get_transactions(self, account_id):
        txns = []
        cur = self._db_connection.cursor()
        db_txn_id_records = cur.execute('SELECT DISTINCT transaction_id FROM transaction_splits WHERE account_id = ?', (account_id,)).fetchall()
        txn_ids = [r[0] for r in db_txn_id_records]
        for txn_id in txn_ids:
            txn = self.get_txn(txn_id)
            txns.append(txn)
        return txns

    def save_txn(self, txn):
        check_txn_splits(txn.splits)
        for split in txn.splits:
            account = split['account']
            if not account.id:
                self.save_account(account)
            if 'payee' in split:
                if not split['payee'].id: #Payee may not have been saved in DB yet
                    db_payee = self.get_payee(name=normalize(split['payee'].name))
                    if db_payee:
                        split['payee'].id = db_payee.id
                    else:
                        self.save_payee(split['payee'])
        field_names = ['date', 'description']
        field_values = [txn.txn_date.strftime('%Y-%m-%d'), normalize(txn.description or '')]
        if txn.alternate_id is not None:
            field_names.append('alternate_id')
            field_values.append(normalize(txn.alternate_id))
        if txn.entry_date:
            field_names.append('entry_date')
            field_values.append(txn.entry_date.strftime('%Y-%m-%d'))
        cur = self._db_connection.cursor()
        with sqlite_txn(cur):
            if txn.id:
                field_names_s = ', '.join([f'{name} = ?' for name in field_names])
                field_values.append(txn.id)
                cur.execute(f'UPDATE transactions SET {field_names_s} WHERE id = ?', field_values)
                if cur.rowcount < 1:
                    raise Exception('no txn with id %s to update' % txn.id)
                txn_id = txn.id
            else:
                field_names.append('commodity_id')
                field_values.append(1)
                field_names_s = ','.join(field_names)
                field_names_q = ','.join(['?' for _ in field_names])
                cur.execute(f'INSERT INTO transactions({field_names_s}) VALUES({field_names_q})', field_values)
                txn_id = cur.lastrowid
            #update transaction splits
            splits_db_info = cur.execute('SELECT account_id FROM transaction_splits WHERE transaction_id = ?', (txn_id,)).fetchall()
            old_txn_split_account_ids = [r[0] for r in splits_db_info]
            new_txn_split_account_ids = [split['account'].id for split in txn.splits]
            #this could result in losing data if there was data in the splits that wasn't exposed in the GUI...
            #   eg. post_date, reconcile_date aren't exposed in the GUI
            split_account_ids_to_delete = set(old_txn_split_account_ids) - set(new_txn_split_account_ids)
            for account_id in split_account_ids_to_delete:
                cur.execute('DELETE FROM transaction_splits WHERE transaction_id = ? AND account_id = ?', (txn_id, account_id))
            for split in txn.splits:
                if 'payee' in split:
                    payee_id = split['payee'].id
                else:
                    payee_id = None
                amount = split['amount']
                quantity = split['quantity']
                status = split.get('status', '')
                if 'reconcile_date' in split:
                    reconcile_date = str(split['reconcile_date'])
                else:
                    reconcile_date = None
                type_ = normalize(split.get('type', ''))
                description = normalize(split.get('description', ''))
                field_names = ['value_numerator', 'value_denominator', 'quantity_numerator', 'quantity_denominator', 'reconciled_state', 'reconcile_date', 'type', 'description', 'payee_id']
                field_values = [amount.numerator, amount.denominator, quantity.numerator, quantity.denominator, status, reconcile_date, type_, description, payee_id]
                action = split.get('action')
                if action is not None:
                    field_names.append('action')
                    field_values.append(action)
                account = split['account']
                field_values.extend([txn_id, account.id]) #add txn id and account id for insert and update
                if account.id in old_txn_split_account_ids:
                    field_names_s = ', '.join([f'{name} = ?' for name in field_names])
                    cur.execute(f'UPDATE transaction_splits SET {field_names_s} WHERE transaction_id = ? AND account_id = ?', field_values)
                else:
                    field_names.extend(['transaction_id', 'account_id'])
                    field_names_s = ','.join(field_names)
                    field_names_q = ','.join(['?' for _ in field_names])
                    cur.execute(f'INSERT INTO transaction_splits({field_names_s}) VALUES({field_names_q})', field_values)
            txn.id = txn_id

    def delete_txn(self, txn_id):
        cur = self._db_connection.cursor()
        with sqlite_txn(cur):
            cur.execute('DELETE FROM transaction_splits WHERE transaction_id = ?', (txn_id,))
            cur.execute('DELETE FROM transactions WHERE id = ?', (txn_id,))

    def save_budget(self, budget):
        cur = self._db_connection.cursor()
        with sqlite_txn(cur):
            if budget.id:
                cur.execute('UPDATE budgets SET name = ?, start_date = ?, end_date = ? WHERE id = ?',
                    (normalize(budget.name), str(budget.start_date), str(budget.end_date), budget.id))
                #handle budget_values
                values_db_info = cur.execute('SELECT account_id FROM budget_values WHERE budget_id = ?', (budget.id,)).fetchall()
                old_account_ids = [r[0] for r in values_db_info]
                budget_data = budget.get_budget_data()
                new_account_ids = [a.id for a in budget_data.keys()]
                account_ids_to_delete = set(old_account_ids) - set(new_account_ids)
                for account_id in account_ids_to_delete:
                    cur.execute('DELETE FROM budget_values WHERE budget_id = ? AND account_id = ?', (budget.id, account_id))
                for account, info in budget_data.items():
                    if info:
                        if 'carryover' in info:
                            carryover = info['carryover']
                            carryover_numerator = carryover.numerator
                            carryover_denominator = carryover.denominator
                        else:
                            carryover_numerator = None
                            carryover_denominator = None
                        notes = normalize(info.get('notes', ''))
                        amount = info['amount']
                        if account.id in old_account_ids:
                            values = (amount.numerator, amount.denominator, carryover_numerator, carryover_denominator, notes, budget.id, account.id)
                            cur.execute('UPDATE budget_values SET amount_numerator = ?, amount_denominator = ?, carryover_numerator = ?, carryover_denominator = ?, notes = ? WHERE budget_id = ? AND account_id = ?', values)
                        else:
                            values = (budget.id, account.id, amount.numerator, amount.denominator, carryover_numerator, carryover_denominator, notes)
                            cur.execute('INSERT INTO budget_values(budget_id, account_id, amount_numerator, amount_denominator, carryover_numerator, carryover_denominator, notes) VALUES (?, ?, ?, ?, ?, ?, ?)', values)
            else:
                cur.execute('INSERT INTO budgets(start_date, end_date) VALUES(?, ?)', (str(budget.start_date), str(budget.end_date)))
                budget.id = cur.lastrowid
                budget_data = budget.get_budget_data()
                for account, info in budget_data.items():
                    if info:
                        if 'carryover' in info:
                            carryover = info['carryover']
                            carryover_numerator = carryover.numerator
                            carryover_denominator = carryover.denominator
                        else:
                            carryover_numerator = None
                            carryover_denominator = None
                        notes = normalize(info.get('notes', ''))
                        amount = info['amount']
                        values = (budget.id, account.id, amount.numerator, amount.denominator, carryover_numerator, carryover_denominator, notes)
                        cur.execute('INSERT INTO budget_values(budget_id, account_id, amount_numerator, amount_denominator, carryover_numerator, carryover_denominator, notes) VALUES (?, ?, ?, ?, ?, ?, ?)', values)

    def get_budget(self, id_):
        cur = self._db_connection.cursor()
        records = cur.execute('SELECT start_date, end_date FROM budgets WHERE id = ?', (id_,)).fetchall()
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
            txn_splits_records = self._db_connection.execute('SELECT transaction_splits.value_numerator, transaction_splits.value_denominator FROM transaction_splits INNER JOIN transactions ON transaction_splits.transaction_id = transactions.id WHERE transaction_splits.account_id = ? AND transactions.date > ? AND transactions.date < ?', (account.id, str(start_date), str(end_date))).fetchall()
            for record in txn_splits_records:
                amt = Fraction(record[0], record[1])
                if amt < Fraction(0):
                    income += amt * Fraction(-1)
                else:
                    spent += amt
            all_income_spending_info[account]['spent'] = spent
            all_income_spending_info[account]['income'] = income
            budget_records = cur.execute('SELECT amount_numerator, amount_denominator, carryover_numerator, carryover_denominator, notes FROM budget_values WHERE budget_id = ? AND account_id = ?', (id_, account.id)).fetchall()
            if budget_records:
                r = budget_records[0]
                account_budget_info[account]['amount'] = Fraction(r[0], r[1])
                account_budget_info[account]['carryover'] = Fraction(r[2] or 0, r[3] or 1)
                account_budget_info[account]['notes'] = r[4]
            else:
                account_budget_info[account] = {}
        return Budget(id_=id_, start_date=start_date, end_date=end_date, account_budget_info=account_budget_info,
                income_spending_info=all_income_spending_info)

    def get_budgets(self):
        budgets = []
        cur = self._db_connection.cursor()
        budget_records = cur.execute('SELECT id FROM budgets ORDER BY start_date DESC').fetchall()
        for budget_record in budget_records:
            budget_id = int(budget_record[0])
            budgets.append(self.get_budget(budget_id))
        return budgets

    def save_scheduled_transaction(self, scheduled_txn):
        check_txn_splits(scheduled_txn.splits)
        if scheduled_txn.next_due_date:
            next_due_date = scheduled_txn.next_due_date.strftime('%Y-%m-%d')
        else:
            next_due_date = None

        for split in scheduled_txn.splits:
            if 'payee' in split:
                if not split['payee'].id: #Payee may not have been saved in DB yet
                    db_payee = self.get_payee(name=normalize(split['payee'].name))
                    if db_payee:
                        split['payee'].id = db_payee.id
                    else:
                        self.save_payee(split['payee'])

        field_names = ['name', 'frequency', 'next_due_date', 'description']
        field_values = [normalize(scheduled_txn.name), scheduled_txn.frequency.value, next_due_date, normalize(scheduled_txn.description)]

        cur = self._db_connection.cursor()
        with sqlite_txn(cur):
            #update existing scheduled transaction
            if scheduled_txn.id:
                field_names_s = ', '.join([f'{name} = ?' for name in field_names])
                field_values.append(scheduled_txn.id)
                cur.execute(f'UPDATE scheduled_transactions SET {field_names_s} WHERE id = ?', field_values)
                if cur.rowcount < 1:
                    raise Exception('no scheduled transaction with id %s to update' % scheduled_txn.id)
                #handle splits
                splits_db_info = cur.execute('SELECT account_id FROM scheduled_transaction_splits WHERE scheduled_transaction_id = ?', (scheduled_txn.id,)).fetchall()
                old_split_account_ids = [r[0] for r in splits_db_info]
                new_split_account_ids = [split['account'].id for split in scheduled_txn.splits]
                split_account_ids_to_delete = set(old_split_account_ids) - set(new_split_account_ids)
                for account_id in split_account_ids_to_delete:
                    cur.execute('DELETE FROM scheduled_transaction_splits WHERE scheduled_transaction_id = ? AND account_id = ?', (scheduled_txn.id, account_id))
                for split in scheduled_txn.splits:
                    if 'payee' in split:
                        payee = split['payee'].id
                    else:
                        payee = None
                    account = split['account']
                    amount = split['amount']
                    quantity = amount
                    status = split.get('status', '')
                    if account.id in old_split_account_ids:
                        cur.execute('UPDATE scheduled_transaction_splits SET value_numerator = ?, value_denominator = ?, quantity_numerator = ?, quantity_denominator = ?, reconciled_state = ?, payee_id = ? WHERE scheduled_transaction_id = ? AND account_id = ?', (amount.numerator, amount.denominator, quantity.numerator, quantity.denominator, status, payee, scheduled_txn.id, account.id))
                    else:
                        cur.execute('INSERT INTO scheduled_transaction_splits(scheduled_transaction_id, account_id, value_numerator, value_denominator, quantity_numerator, quantity_denominator, reconciled_state, payee_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (scheduled_txn.id, account.id, amount.numerator, amount.denominator, quantity.numerator, quantity.denominator, status, payee))
            #add new scheduled transaction
            else:
                field_names_s = ', '.join(field_names)
                field_names_q = ', '.join(['?' for _ in field_names])
                cur.execute(f'INSERT INTO scheduled_transactions({field_names_s}) VALUES ({field_names_q})', field_values)
                scheduled_txn.id = cur.lastrowid
                for split in scheduled_txn.splits:
                    if 'payee' in split:
                        payee = split['payee'].id
                    else:
                        payee = None
                    account = split['account']
                    amount = split['amount']
                    quantity = amount
                    status = split.get('status', '')
                    cur.execute('INSERT INTO scheduled_transaction_splits(scheduled_transaction_id, account_id, value_numerator, value_denominator, quantity_numerator, quantity_denominator, reconciled_state, payee_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (scheduled_txn.id, account.id, amount.numerator, amount.denominator, quantity.numerator, quantity.denominator, status, payee))

    def get_scheduled_transaction(self, id_):
        cur = self._db_connection.cursor()
        splits = []
        split_records = cur.execute('SELECT account_id, value_numerator, value_denominator, reconciled_state, payee_id FROM scheduled_transaction_splits WHERE scheduled_transaction_id = ?', (id_,))
        if split_records:
            for split_record in split_records:
                account_id = split_record[0]
                account = self.get_account(account_id)
                split = {'account': account, 'amount': Fraction(split_record[1], split_record[2])}
                if split_record[3]:
                    split['status'] = split_record[3]
                if split_record[4]:
                    split['payee'] = self.get_payee(id_=split_record[4])
                splits.append(split)
        rows = cur.execute('SELECT name,frequency,next_due_date,description FROM scheduled_transactions WHERE id = ?', (id_,)).fetchall()
        st = ScheduledTransaction(
                name=rows[0][0],
                frequency=ScheduledTransactionFrequency(rows[0][1]),
                next_due_date=rows[0][2],
                splits=splits,
                description=rows[0][3],
                id_=id_,
            )
        return st

    def get_scheduled_transactions(self):
        cur = self._db_connection.cursor()
        scheduled_txns_records = cur.execute('SELECT id FROM scheduled_transactions').fetchall()
        scheduled_txns = []
        for st_record in scheduled_txns_records:
            scheduled_txns.append(self.get_scheduled_transaction(st_record[0]))
        return scheduled_txns

    def delete_scheduled_transaction(self, id_):
        cur = self._db_connection.cursor()
        with sqlite_txn(cur):
            cur.execute('DELETE FROM scheduled_transaction_splits WHERE scheduled_transaction_id = ?', (id_,))
            cur.execute('DELETE FROM scheduled_transactions WHERE id = ?', (id_,))

    def get_preference(self, name):
        result = self._db_connection.execute('SELECT value FROM preferences WHERE name = ?', (name,)).fetchone()
        if result:
            return result[0]

    def save_preference(self, name, value):
        cur = self._db_connection.cursor()
        sql = 'INSERT INTO preferences (name, value) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET value = ?'
        with sqlite_txn(cur):
            cur.execute(sql, (name, value, value))


### ENGINE ###

class Engine:

    def __init__(self, file_name):
        try:
            self._storage = SQLiteStorage(file_name)
        except sqlite3.DatabaseError as e:
            raise InvalidStorageFile(str(e))

    def get_commodity(self, id_=None, code=None):
        return self._storage.get_commodity(id_=id_, code=code)

    def save_commodity(self, c):
        self._storage.save_commodity(c)

    def get_currencies(self):
        commodities = self._storage.get_commodities()
        return [c for c in commodities if c.type == CommodityType.CURRENCY]

    def get_account(self, id_=None, number=None, name=None):
        return self._storage.get_account(id_=id_, number=number, name=name)

    def get_accounts(self, types=None):
        if types:
            accounts = []
            for type_ in types:
                accounts.extend(self._storage.get_accounts(type_=type_))
            return accounts
        else:
            return self._storage.get_accounts()

    def get_bookmarked_accounts(self):
        return self._storage.get_bookmarked_accounts()

    def bookmark_account(self, account_id):
        return self._storage.bookmark_account(account_id)

    def remove_account_bookmark(self, account_id):
        return self._storage.remove_account_bookmark(account_id)

    def save_account(self, account=None, id_=None, name=None, type_=None, commodity_id=None, number=None, parent_id=None):
        if not account:
            parent = None
            if parent_id:
                parent = self._storage.get_account(id_=parent_id)
            if commodity_id:
                commodity = self._storage.get_commodity(id_=commodity_id)
            else:
                commodity = None
            account = Account(id_=id_, type_=type_, commodity=commodity, number=number, name=name, parent=parent)
        self._storage.save_account(account)
        return account

    def delete_account(self, account_id):
        self._storage.delete_account(account_id)

    @staticmethod
    def sort_txns(txns, key='date'):
        return sorted(txns, key=lambda t: t.txn_date)

    @staticmethod
    def add_balance_to_txns(txns, account, balance_field='amount'):
        #txns must be sorted in chronological order (not reversed) already
        txns_with_balance = []
        balance = Fraction(0)
        for t in txns:
            split = [s for s in t.splits if s['account'] == account][0]
            balance = balance + split[balance_field]
            t.balance = balance
            txns_with_balance.append(t)
        return txns_with_balance

    def get_transaction(self, id_):
        return self._storage.get_txn(id_)

    def get_transactions(self, account, filter_account=None, query=None, status=None, sort='date'):
        results = self._storage.get_transactions(account_id=account.id)
        if filter_account:
            results = [t for t in results if filter_account in [s['account'] for s in t.splits]]
        if status:
            results = [t for t in results if [s for s in t.splits if s['account'] == account][0].get('status') == status]
        if query:
            query = query.lower()
            results = [t for t in results
                    if (
                        [s for s in t.splits if 'payee' in s and query in s['payee'].name.lower()] or
                        (t.description and query in t.description.lower())
                    )
                ]
        sorted_results = Engine.sort_txns(results, key='date')
        #add balance if we have all the txns for a specific account, without limiting by another account, or a query, or a status, ...
        if not any([filter_account, query, status]):
            balance_field = 'amount'
            if account.type == AccountType.SECURITY:
                balance_field = 'quantity'
            sorted_results = Engine.add_balance_to_txns(sorted_results, account=account, balance_field=balance_field)
        return sorted_results

    def get_current_balances_for_display(self, account, sorted_txns=None):
        if not sorted_txns:
            sorted_txns = self.get_transactions(account=account)
        balance_field = 'amount'
        if account.type == AccountType.SECURITY:
            balance_field = 'quantity'
        current = Fraction(0)
        current_cleared = Fraction(0)
        today = date.today()
        for t in sorted_txns:
            if t.txn_date <= today:
                current = t.balance
                split = [s for s in t.splits if s['account'] == account][0]
                if split.get('status') in [Transaction.CLEARED, Transaction.RECONCILED]:
                    current_cleared = current_cleared + split[balance_field]
        return LedgerBalances(
                current=amount_display(current),
                current_cleared=amount_display(current_cleared),
            )

    def save_transaction(self, transaction):
        self._storage.save_txn(transaction)

    def delete_transaction(self, transaction_id):
        self._storage.delete_txn(transaction_id)

    def get_payee(self, id_=None, name=None):
        return self._storage.get_payee(id_=id_, name=name)

    def get_payees(self):
        return sorted(self._storage.get_payees(), key=lambda p: p.name)

    def save_payee(self, payee):
        return self._storage.save_payee(payee)

    def get_scheduled_transaction(self, id_):
        return self._storage.get_scheduled_transaction(id_)

    def get_scheduled_transactions(self):
        return self._storage.get_scheduled_transactions()

    def get_scheduled_transactions_due(self, accounts=None):
        scheduled_txns = self._storage.get_scheduled_transactions()
        if accounts:
            for acc in accounts:
                scheduled_txns = [st for st in scheduled_txns if acc in [s['account'] for s in st.splits]]
        return [t for t in scheduled_txns if t.is_due()]

    def save_scheduled_transaction(self, scheduled_txn):
        return self._storage.save_scheduled_transaction(scheduled_txn)

    def enter_scheduled_transaction(self, scheduled_txn, txn):
        self.save_transaction(transaction=txn)
        scheduled_txn.advance_to_next_due_date()
        self.save_scheduled_transaction(scheduled_txn)

    def skip_scheduled_transaction(self, id_):
        scheduled_txn = self.get_scheduled_transaction(id_)
        scheduled_txn.advance_to_next_due_date()
        self.save_scheduled_transaction(scheduled_txn)

    def delete_scheduled_transaction(self, id_):
        return self._storage.delete_scheduled_transaction(id_)

    def get_budget(self, id_):
        return self._storage.get_budget(id_=id_)

    def get_budgets(self):
        return self._storage.get_budgets()

    def save_budget(self, budget):
        return self._storage.save_budget(budget)

    def get_date_display_format(self):
        return '%Y-%m-%d'

    def _create_export_line(self, fields):
        return '\t'.join([f.replace('\t', '\\t') for f in fields])

    def export(self, directory):
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        export_dir = f'bricbooks_export_{timestamp}'
        if not os.path.exists(directory):
            print(f'creating {directory} for export')
            os.mkdir(directory)
        export_dir = os.path.join(directory, export_dir)
        os.mkdir(export_dir)
        accounts = self.get_accounts()
        accounts_file = os.path.join(export_dir, 'accounts.tsv')
        with open(accounts_file, 'wb') as f:
            f.write('type\tnumber\tname\n'.encode('utf8'))
            for acc in accounts:
                data = [acc.type.value, acc.number or '', acc.name]
                line = self._create_export_line(data)
                f.write(f'{line}\n'.encode('utf8'))
        for acc in accounts:
            if acc.type != AccountType.ASSET:
                continue
            txns = self.get_transactions(account=acc)
            acc_file = os.path.join(export_dir, f'acc_{to_ascii(acc.name.lower())}.tsv')
            with open(acc_file, 'wb') as f:
                f.write('date\ttype\tdescription\tamount\ttransfer_account\n'.encode('utf8'))
                for txn in txns:
                    if len(txn.splits) == 2:
                        transfer_account = [str(s['account']) for s in txn.splits if s['account'] != acc][0]
                    else:
                        transfer_account = 'multiple'
                    split = [s for s in txn.splits if s['account'] == acc][0]
                    data = [str(txn.txn_date), txn.description or '',
                            amount_display(split['amount']), transfer_account]
                    line = self._create_export_line(data)
                    f.write(f'{line}\n'.encode('utf8'))

        for budget in self.get_budgets():
            file_name = os.path.join(export_dir, f'budget_{budget.start_date}_{budget.end_date}.tsv')
            with open(file_name, 'wb') as f:
                f.write('account\n'.encode('utf8'))

    def get_income_expense_report(self):
        report = {'heading': 'Income/Expense Report'}
        year_totals = {}
        income_accounts = self.get_accounts(types=[AccountType.INCOME])
        expense_accounts = self.get_accounts(types=[AccountType.EXPENSE])
        income = {'total': Fraction(0), 'accounts': {}}
        expense = {'total': Fraction(0), 'accounts': {}}
        for a in income_accounts:
            txns = self.get_transactions(account=a)
            if txns:
                income['accounts'][a] = {'total': Fraction(0)}
                for t in txns:
                    year = t.txn_date.year
                    if year not in year_totals:
                        year_totals[year] = {'income': 0, 'expense': 0}
                    if year not in income['accounts'][a]:
                        income['accounts'][a][year] = Fraction(0)
                    split = [s for s in t.splits if s['account'] == a][0]
                    amount = split['amount'] * -1 # incomes are listed as negative amounts
                    year_totals[year]['income'] += amount
                    income['total'] += amount
                    income['accounts'][a]['total'] += amount
                    income['accounts'][a][year] += amount
        for a in expense_accounts:
            txns = self.get_transactions(account=a)
            if txns:
                expense['accounts'][a] = {'total': Fraction(0)}
                for t in txns:
                    year = t.txn_date.year
                    if year not in year_totals:
                        year_totals[year] = {'income': 0, 'expense': 0}
                    if year not in expense['accounts'][a]:
                        expense['accounts'][a][year] = Fraction(0)
                    split = [s for s in t.splits if s['account'] == a][0]
                    year_totals[year]['expense'] += split['amount']
                    expense['total'] += split['amount']
                    expense['accounts'][a]['total'] += split['amount']
                    expense['accounts'][a][year] += split['amount']
        report['income'] = income
        report['expense'] = expense
        report['year_totals'] = year_totals
        return report


### IMPORT ###
kmymoney_action_mapping = {
    'Buy': 'share-buy',
    'Sell': 'share-sell',
    'Split': 'share-split',
    'Reinvest': 'share-reinvest',
    'Add': 'share-add',
    'Remove': 'share-remove',
    'Amortization': '',
    'Interest': '',
}

def import_kmymoney(kmy_file, engine):
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
            commodity_mapping_info['USD'] = engine.get_commodity(code='USD').id
            continue
        commodity = Commodity(type_=CommodityType.CURRENCY, code=currency_id, name=currency.attrib['name'])
        try:
            engine.save_commodity(commodity)
            commodity_mapping_info[currency_id] = commodity.id
        except Exception as e:
            print(f'{datetime.now()} error migrating currency: {e}\n  {currency.attrib}')
    securities = root.find('SECURITIES')
    for security in securities.iter('SECURITY'):
        security_id = security.attrib['id']
        commodity = Commodity(type_=CommodityType.SECURITY, code=security_id, name=currency.attrib['name'])
        try:
            engine.save_commodity(commodity)
            commodity_mapping_info[security_id] = commodity.id
        except Exception as e:
            print(f'{datetime.now()} error migrating security: {e}\n  {security.attrib}')
    #migrate accounts
    #need to keep track of kmymoney account id mapping to our account id
    print(f'{datetime.now()} migrating accounts...')
    account_mapping_info = {}
    accounts = root.find('ACCOUNTS')
    for account in accounts.iter('ACCOUNT'):
        type_ = AccountType.ASSET # default
        kmy_type = None
        commodity = None
        parent_account = None
        name = None
        alternate_id = None
        description = None
        for key, value in account.attrib.items():
            if key == 'id':
                alternate_id = value
            elif key == 'type':
                kmy_type = value
                if value in ['4', '5', '10']:
                    type_ = AccountType.LIABILITY
                elif value in ['13']:
                    type_ = AccountType.EXPENSE
                elif value in ['12']:
                    type_ = AccountType.INCOME
                elif value in ['16']:
                    type_ = AccountType.EQUITY
                elif value in ['15']:
                    type_ = AccountType.SECURITY
            elif key == 'currency':
                currency_id = commodity_mapping_info[value]
                commodity = engine.get_commodity(id_=currency_id)
            elif key == 'parentaccount':
                if value:
                    parent_account = engine.get_account(account_mapping_info[value])
            elif key == 'name':
                name = value
            elif key == 'description':
                description = value
            elif key in ['opened', 'lastmodified', 'institution', 'number']: # ignore these attributes
                pass
            else:
                if value:
                    raise DataImportError(f'unhandled account attribute: {key} => {value}')
        closed = False
        other_data = {}
        key_value_pairs = account.find('KEYVALUEPAIRS')
        if key_value_pairs is not None:
            for pair in key_value_pairs.iter('PAIR'):
                key = pair.attrib.get('key', '')
                value = pair.attrib.get('value')
                if key.startswith('ir-'):
                    other_data['interest-rate-percent'] = Fraction(value)
                elif key == 'fixed-interest' and value == 'yes':
                    other_data['fixed-interest'] = True
                elif key == 'term':
                    other_data['term'] = f'{value}m'
                elif key == 'mm-closed':
                    if value == 'yes':
                        closed = True
                elif key in ['OpeningBalanceAccount', 'lastNumberUsed', 'compoundingFrequency', 'final-payment', 'priceMode',
                             'interest-calculation', 'loan-amount', 'periodic-payment', 'schedule', 'IBAN']: # ignore these
                    pass
                else:
                    if value:
                        raise DataImportError(f'unhandled account key/value: {key} => {value}')
        acc_obj = Account(
                    type_=type_,
                    commodity=commodity,
                    name=account.attrib['name'],
                    parent=parent_account,
                    alternate_id=alternate_id,
                    description=description,
                    closed=closed,
                    other_data=other_data,
                )
        engine.save_account(acc_obj)
        account_mapping_info[account.attrib['id']] = acc_obj.id
    #migrate payees
    print(f'{datetime.now()} migrating payees...')
    payee_mapping_info = {}
    payees = root.find('PAYEES')
    for payee in payees.iter('PAYEE'):
        payee_obj = Payee(name=payee.attrib['name'])
        engine.save_payee(payee_obj)
        payee_mapping_info[payee.attrib['id']] = payee_obj.id
    #migrate transactions
    #   Dates: kmymoney uses the "postdate" attribute for the main txn date - there's no separate date
    #       for when when the split clears the account.
    print(f'{datetime.now()} migrating transactions...')
    transactions = root.find('TRANSACTIONS')
    for transaction in transactions.iter('TRANSACTION'):
        has_income_or_expense = False
        payee_ids = []
        descriptions = []
        splits = []
        txn_id = transaction.attrib['id']
        entry_date = transaction.attrib['entrydate']
        try:
            splits_el = transaction.find('SPLITS')
            for split_el in splits_el.iter('SPLIT'):
                split = {}
                account_orig_id = split_el.attrib['account']
                account = engine.get_account(account_mapping_info[account_orig_id])
                split['account'] = account
                if account.type in [AccountType.INCOME, AccountType.EXPENSE]:
                    has_income_or_expense = True
                amount = split_el.attrib['value']
                quantity = split_el.attrib['shares']
                for key, value in split_el.attrib.items():
                    if key == 'account':
                        pass # already handled
                    elif key == 'value':
                        split['amount'] = value
                    elif key == 'shares':
                        split['quantity'] = value
                    elif key == 'reconcileflag':
                        #reconcileflag: '2'=Reconciled, '1'=Cleared, '0'=nothing
                        if value == '2':
                            split['status'] = Transaction.RECONCILED
                        elif value == '1':
                            split['status'] = Transaction.CLEARED
                        elif value == '0':
                            pass
                        else:
                            raise DataImportError(f'unhandled reconcileflag value: {value}')
                    elif key == 'reconciledate':
                        if value:
                            split['reconcile_date'] = get_date(value)
                    elif key == 'payee':
                        if value:
                            payee_ids.append(value)
                            split['payee'] = engine.get_payee(id_=payee_mapping_info[value])
                    elif key == 'number':
                        split['type'] = value
                    elif key == 'memo':
                        descriptions.append(value)
                        split['description'] = value
                    elif key == 'action':
                        if not value:
                            pass
                        elif value in kmymoney_action_mapping:
                            split['action'] = kmymoney_action_mapping[value]
                        else:
                            raise DataImportError(f'unhandled action "{value}"')
                    elif key == 'price':
                        # we probably don't care about the price
                        if value != '1/1':
                            price = Fraction(value)
                            diff = price - Fraction(amount)/Fraction(quantity)
                            # if the price is similar to amount/quantity, we'll ignore it
                            if abs(diff) > Fraction(1/10):
                                raise DataImportError(f'unhandled price {price} for txn {txn_id}; amount {amount}; quantity {quantity} (diff {diff})')
                    else:
                        if key == 'id':
                            pass
                        else:
                            if value:
                                raise DataImportError(f'unhandled txn attribute: {key} = {value}')
                splits.append(split)
            if has_income_or_expense and len(payee_ids) > 1 and len(set(payee_ids)) == 1:
                for s in splits:
                    if s['account'].type not in [AccountType.INCOME, AccountType.EXPENSE]:
                        s.pop('payee', None)
            if transaction.attrib.get('memo'):
                description = transaction.attrib['memo']
            elif len(descriptions) > 1 and len(set(descriptions)) == 1:
                description = descriptions[0]
                for s in splits:
                    s.pop('description', None)
            else:
                description = None
            engine.save_transaction(
                    Transaction(
                        splits=splits,
                        txn_date=transaction.attrib['postdate'],
                        description=description,
                        alternate_id=txn_id,
                        entry_date=entry_date or None,
                    )
                )
        except RuntimeError as e:
            print(f'{datetime.now()} error migrating transaction: {e}\n  account: {account}\n  {transaction.attrib}')
    scheduled = root.find('SCHEDULES')
    for scheduled_txn in scheduled.iter('SCHEDULED_TX'):
        name = scheduled_txn.attrib.get('name')
        frequency = scheduled_txn.attrib.get('occurence')
        if frequency == '4':
            frequency = ScheduledTransactionFrequency.WEEKLY
        elif frequency == '32':
            frequency = ScheduledTransactionFrequency.MONTHLY
        elif frequency == '18':
            frequency = ScheduledTransactionFrequency.SEMI_MONTHLY
        elif frequency == '4096':
            frequency = ScheduledTransactionFrequency.QUARTERLY
        elif frequency == '16384':
            frequency = ScheduledTransactionFrequency.YEARLY
        else:
            print(f'unhandled scheduled txn frequency value: {value}')
            continue
        occurence_multiplier = scheduled_txn.attrib.get('occurenceMultiplier')
        if occurence_multiplier != '1':
            print(f'unhandled scheduled txn occurenceMultiplier: {value}')
            continue
        splits = []
        splits_el = scheduled_txn.find('TRANSACTION').find('SPLITS')
        for split_el in splits_el.iter('SPLIT'):
            split = {}
            for key, value in split_el.attrib.items():
                if key == 'account':
                    account_orig_id = split_el.attrib['account']
                    account = engine.get_account(account_mapping_info[account_orig_id])
                    split['account'] = account
                split['amount'] = 0
            if split:
                splits.append(split)
        engine.save_scheduled_transaction(
                ScheduledTransaction(
                    name=name,
                    frequency=frequency,
                    splits=splits,
                )
            )
    for top_level_el in root:
        if top_level_el.tag not in ['CURRENCIES', 'SECURITIES', 'ACCOUNTS', 'PAYEES', 'TRANSACTIONS', 'SCHEDULES']:
            print(f"{datetime.now()} didn't migrate {top_level_el.tag} data")


### CLI/GUI ###

def pager(items, num_txns_in_page, page=1):
    start = 0 + (page-1)*num_txns_in_page
    end = start + num_txns_in_page
    page_items = items[start:end]
    if end < len(items):
        more_items = True
    else:
        more_items = False
    return page_items, more_items


class CLI:

    ACCOUNT_LIST_HEADER = ' ID   | Type        | Name                           | Parent\n'\
        '==============================================================================================='

    TXN_LIST_HEADER = ' ID   | Date       |  Description                   | Payee                          |  Transfer Account              | Withdrawal | Deposit    | Balance\n'\
        '======================================================================================================================================================='

    NUM_TXNS_IN_PAGE = 50

    def __init__(self, file_name, print_file=None):
        self._engine = Engine(file_name)
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
            if a.parent:
                parent = a.parent.name
            else:
                parent = ''
            self.print(' {0:<4} | {1:<11} | {2:<30} | {3:<30}'.format(a.id, a.type.name, str(a)[:30], parent[:30]))

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
        account = self._engine.get_account(id_=acc_id)
        self._get_and_save_account(account=account)

    def _delete_account(self):
        acc_id = self.input('ID of account to delete: ')
        if acc_id:
            self._engine.delete_account(int(acc_id))

    def _list_account_txns(self, num_txns_in_page=None):
        if not num_txns_in_page:
            num_txns_in_page = self.NUM_TXNS_IN_PAGE
        user_input = self.input('Account ID (or search string): ')
        user_input_parts = user_input.split()
        account = self._engine.get_account(id_=int(user_input_parts[0]))
        status = None
        filter_account = None
        if len(user_input_parts) > 1:
            for clause in user_input_parts[1:]:
                if clause.startswith('status:'):
                    status = clause.replace('status:', '')
                elif clause.startswith('acc:'):
                    if filter_account:
                        raise Exception('only search for one account at a time')
                    filter_account = self._engine.get_account(id_=int(clause.replace('acc:', '')))

        txns = self._engine.get_transactions(account=account, status=status, filter_account=filter_account)

        if not (len(user_input_parts) > 1):
            ledger_balances = self._engine.get_current_balances_for_display(account=account, sorted_txns=txns)
            summary_line = f'{account.name} (Current balance: {ledger_balances.current}; Cleared: {ledger_balances.current_cleared})'
            self.print(summary_line)
            scheduled_txns_due = self._engine.get_scheduled_transactions_due(accounts=[account])
            if scheduled_txns_due:
                self.print('Scheduled Transactions due:')
                for st in scheduled_txns_due:
                    self.print(f'{st.id} {st.name} {st.next_due_date}')
        reversed_txns = list(reversed(txns))
        self.print(self.TXN_LIST_HEADER)
        page_index = 1
        while True:
            paged_txns, more_txns = pager(reversed_txns, num_txns_in_page=num_txns_in_page, page=page_index)
            for t in paged_txns:
                tds = get_display_strings_for_ledger(account, t, self._engine.get_date_display_format())
                self.print(' {7:<4} | {0:<6} | {1:<30} | {2:<30} | {3:30} | {4:<10} | {5:<10} | {6:<10}'.format(
                    tds['txn_date'], tds['description'], tds['payee'], tds['transfer_account'], tds['withdrawal'], tds['deposit'], tds.get('balance', ''), t.id)
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

    def _get_common_txn_info(self, is_scheduled_txn=False, txn=None):
        '''get pieces of data common to txns and scheduled txns'''
        txn_info = {}
        self.print('Splits:')
        splits = []
        if txn:
            for split_info in txn.splits:
                account = split_info['account']
                amount = self.input(prompt='%s amount: ' % account.name, prefill=fraction_to_decimal(split_info['amount']))
                if amount:
                    split = {'account': account, 'amount': amount}
                    orig_status = split_info.get('status', '')
                    if orig_status:
                        orig_status = orig_status.value
                    reconciled_state = self.input(prompt=f'{account.name} reconciled state: ', prefill=orig_status)
                    if reconciled_state:
                        split['status'] = reconciled_state
                    if not is_scheduled_txn:
                        split['type'] = self.input(prompt=f'{account.name} type: ', prefill=split_info['type'])
                        split['action'] = self.input(prompt=f'{account.name} action: ', prefill=split_info['action'])
                    payee_prefill = ''
                    if 'payee' in split_info:
                        if split_info['payee']:
                            payee_prefill = '\'%s' % split_info['payee'].name
                        else:
                            payee_prefill = ''
                    payee = self.input(prompt='  payee (id or \'name): ', prefill=payee_prefill)
                    if payee == 'p':
                        self._list_payees()
                        payee = self.input(prompt='  payee (id or \'name): ')
                    if payee.startswith("'"):
                        split['payee'] = Payee(payee[1:])
                    else:
                        split['payee'] = self._engine.get_payee(id_=payee)
                    splits.append(split)
        while True:
            acct_id = self.input(prompt='new account ID: ')
            if acct_id:
                account = self._engine.get_account(id_=acct_id)
                amt = self.input(prompt=' amount: ')
                if amt:
                    split = {'account': account, 'amount': amt}
                    reconciled_state = self.input(prompt=f'{account.name} reconciled state: ')
                    if reconciled_state:
                        split['status'] = reconciled_state
                    if not is_scheduled_txn:
                        split['type'] = self.input(prompt=f'{account.name} type: ')
                        split['action'] = self.input(prompt=f'{account.name} action: ')
                    payee = self.input(prompt='  payee (id or \'name): ')
                    if payee == 'p':
                        self._list_payees()
                        payee = self.input(prompt='  payee (id or \'name): ')
                    if payee.startswith("'"):
                        split['payee'] = Payee(payee[1:])
                    else:
                        split['payee'] = self._engine.get_payee(id_=payee)
                    splits.append(split)
                else:
                    break
            else:
                break
        txn_info['splits'] = splits
        description_prefill = ''
        txn_info['description'] = self.input(prompt='  description: ', prefill=description_prefill)
        return txn_info

    def _get_txn(self, is_scheduled_txn=False, txn=None):
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
        info.update(self._get_common_txn_info(is_scheduled_txn=is_scheduled_txn, txn=txn))
        return Transaction(**info)

    def _create_txn(self):
        self.print('Create Transaction:')
        txn = self._get_txn()
        self._engine.save_transaction(txn)

    def _edit_txn(self):
        txn_id = self.input(prompt='Txn ID: ')
        txn = self._engine.get_transaction(id_=txn_id)
        updated_txn = self._get_txn(txn=txn)
        self._engine.save_transaction(updated_txn)

    def _list_payees(self):
        for p in self._engine.get_payees():
            self.print('%s: %s' % (p.id, p.name))

    def _list_scheduled_txns(self):
        for st in self._engine.get_scheduled_transactions():
            self.print(st)
        self._enter_scheduled_txn()
        self._skip_scheduled_txn()

    def _enter_scheduled_txn(self):
        self.print('Enter next transaction for a scheduled transaction:')
        while True:
            scheduled_txn_id = self.input('Scheduled txn ID (blank to quit): ')
            if scheduled_txn_id:
                scheduled_txn = self._engine.get_scheduled_transaction(scheduled_txn_id)
                txn = self._get_txn(is_scheduled_txn=True, txn=scheduled_txn)
                self._engine.enter_scheduled_transaction(scheduled_txn, txn)
            else:
                break

    def _skip_scheduled_txn(self):
        self.print('Skip next transaction for a scheduled transaction:')
        while True:
            scheduled_txn_id = self.input('Scheduled txn ID (blank to quit): ')
            if scheduled_txn_id:
                self._engine.skip_scheduled_transaction(scheduled_txn_id)
            else:
                break

    def _display_scheduled_txn(self):
        scheduled_txn_id = self.input('Enter scheduled txn ID: ')
        scheduled_txn = self._engine.get_scheduled_transaction(scheduled_txn_id)
        self.print('%s: %s' % (scheduled_txn.id, scheduled_txn.name))
        self.print('  frequency: %s' % scheduled_txn.frequency.name)
        self.print('  next due date: %s' % scheduled_txn.next_due_date)
        splits_str = '; '.join(['%s-%s: %s' % (split['account'].id, split['account'].name, str(split)) for split in scheduled_txn.splits])
        self.print('  splits: %s' % splits_str)
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
        common_info = self._get_common_txn_info(is_scheduled_txn=True, txn=scheduled_txn)
        id_ = None
        if scheduled_txn:
            id_ = scheduled_txn.id
        self._engine.save_scheduled_transaction(
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
        scheduled_txn = self._engine.get_scheduled_transaction(scheduled_txn_id)
        self._get_and_save_scheduled_txn(scheduled_txn=scheduled_txn)

    def _list_budgets(self):
        for b in self._engine.get_budgets():
            self.print(b)

    def _display_budget(self):
        budget_id = self.input('Enter budget ID: ')
        budget = self._engine.get_budget(budget_id)
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
        budget = self._engine.get_budget(budget_id)
        self.print(budget)
        budget_report = budget.get_report_display(current_date=date.today())
        for info in budget_report['income']:
            self.print(info)
        for info in budget_report['expense']:
            self.print(info)

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
                    account = self._engine.get_account(id_=acct_id)
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
        self._engine.save_budget(
                Budget(
                    start_date=start_date,
                    end_date=end_date,
                    account_budget_info=account_info,
                )
            )

    def _edit_budget(self):
        budget_id = self.input('Enter budget ID: ')
        budget = self._engine.get_budget(budget_id)
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
        self._engine.save_budget(
                Budget(
                    start_date=start_date,
                    end_date=end_date,
                    account_budget_info=account_info,
                )
            )

    def _display_reports(self):
        report = self._engine.get_income_expense_report()
        years = report['years'][-5:]
        self.print(report['heading'])
        self.print('                       ', end='')
        for year in years:
            self.print(f'   {year}     ', end='')
        self.print('   Total   ')
        for account, data in report['income']['accounts'].items():
            self.print('  {0:<20} :'.format(str(account)), end='')
            for year in years:
                if year in data:
                    self.print(' {0:<10} '.format(amount_display(data[year])), end='')
                else:
                    self.print('      ', end='')
            self.print(f' {amount_display(data["total"])} ')
        self.print('Total Income: ' + amount_display(report['income']['total']))
        for account, data in report['expense']['accounts'].items():
            self.print('  {0:<20} :'.format(str(account)), end='')
            for year in years:
                if year in data:
                    self.print(' {0:<10} '.format(amount_display(data[year])), end='')
                else:
                    self.print('      ', end='')
            self.print(f' {amount_display(data["total"])} ')
        self.print('Total Expense: ' + amount_display(report['expense']['total']))

    def _print_help(self, info):
        help_msg = 'h - help'
        for cmd, info in info.items():
            help_msg += f'\n{cmd} - {info["description"]}'
        help_msg += '\nq (or Ctrl-d) - quit'
        self.print(help_msg.strip())

    def _command_loop(self, info):
        while True:
            cmd = self.input('>>> ')
            if cmd == 'h':
                self._print_help(info)
            elif cmd == 'q':
                raise EOFError()
            else:
                if cmd in info:
                    info[cmd]['function']()
                else:
                    self.print('Invalid command: "%s"' % cmd)

    def run(self):
        info = {
            'a': {'description': 'list accounts', 'function': self._list_accounts},
            'ac': {'description': 'create account', 'function': self._create_account},
            'ae': {'description': 'edit account', 'function': self._edit_account},
            'ad': {'description': 'delete account', 'function': self._delete_account},
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
            'r': {'description': 'reports', 'function': self._display_reports},
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


class Combobox:
    def __init__(self, master, choices, selected=None):
        # choices is dict of display: value items
        self._choices = choices
        self._combo = ttk.Combobox(master=master, height=20)
        self._combo['values'] = list(self._choices.keys())
        self._set_selected(selected)
        self.popdown = self._tk(tk.Toplevel, master)
        self.listbox = self._tk(tk.Listbox, self.popdown)
        self.bind('<KeyPress>', self.handle_key_press)
        self.bind('<KeyRelease>', self.handle_key_release)

    # https://stackoverflow.com/a/59913585
    def _tk(self, cls, parent):
        obj = cls(parent)
        obj.destroy()
        if cls is tk.Toplevel:
            obj._w = self._combo.tk.call('ttk::combobox::PopdownWindow', self._combo)
        else:
            obj._w = '{}.{}'.format(parent._w, 'f.l')
        return obj

    def _set_selected(self, selected):
        if selected is not None:
            for index, display in enumerate(list(self._choices.keys())):
                if display == selected:
                    self._combo.current(index)
                    return
            for index, value in enumerate(list(self._choices.values())):
                if value == selected:
                    self._combo.current(index)
                    return

    def get_widget(self):
        return self._combo

    def handle_key_press(self, e):
        # Default Combobox event: 'Down' keypress event handler shows the dropdown
        # We want to be able to move down the options in the ListBox, so we disable
        #   the default handling.
        if e.keysym == 'Down':
            return 'break'

    def handle_key_release(self, e):
        if e.widget == self._combo:
            state = self.popdown.state()
            current_selection = self.listbox.curselection()

            if e.keysym == 'Up' and current_selection[0] > 0:
                    self.listbox.selection_clear(current_selection[0])
                    new_cur = current_selection[0]-1
                    self.listbox.selection_set(new_cur)
            elif e.keysym == 'Down' and current_selection[0] < (len(self._combo['values'])-1):
                    self.listbox.selection_clear(current_selection[0])
                    new_cur = current_selection[0]+1
                    self.listbox.selection_set(new_cur)
            elif e.keysym == 'Return':
                if state == 'normal':
                    value = self.listbox.get(current_selection[0])
                    self._combo.set(value)
                    self.popdown.withdraw()
                    self._combo.icursor(tk.END)
                    self._combo.event_generate('<<ComboboxSelected>>')
            elif e.keysym_num < 60000 or e.keysym_num == 65288: # 65288 is <BackSpace>
                self.filter()

                if state != 'withdrawn':
                    self.popdown.withdraw()

                self._combo.event_generate('<Button-1>')
                self._combo.after(10, self._combo.focus_set)

    def filter(self):
        val = self._combo.get()
        if val:
            val_lower = val.lower()
            self._combo['values'] = [v for v in self._choices.keys() if val_lower in v.lower()]
        else:
            self._combo['values'] = list(self._choices.keys())

    def current_value(self):
        current_selection = self._combo.get()
        if current_selection in self._choices:
            return self._choices[current_selection]
        else:
            return current_selection

    def current_display(self):
        return self._combo.get()

    def set_current_index(self, index):
        return self._combo.current(index)

    def state(self, arg):
        self._combo.state(arg)

    def insert(self, position, text):
        self._combo.insert(position, text)

    def delete(self, start, end):
        self._combo.delete(start, end)

    def bind(self, *args, **kwargs):
        self._combo.bind(*args, **kwargs)

    def event_generate(self, *args, **kwargs):
        self._combo.event_generate(*args, **kwargs)


class ErrorForm:

    def __init__(self, msg):
        self.form = tk.Toplevel()
        self.content = ttk.Frame(master=self.form)
        ttk.Label(master=self.content, text=msg).grid(row=0, column=0)
        self.ok_button = ttk.Button(master=self.content, text='OK', command=self.close)
        self.ok_button.grid(row=1, column=0)
        self.content.grid()
        self.form.grid()

    def close(self):
        self.form.destroy()


def show_error(msg):
    ErrorForm(msg=msg)


def handle_error(exc):
    import traceback
    log(traceback.format_exc())
    show_error(msg=str(exc))


class AccountForm:

    def __init__(self, accounts, save_account, update_display, account=None):
        self._accounts = [a for a in accounts if a != account]
        self._save_account = save_account
        self._update_display = update_display
        self._account = account
        #keep map of account types for display
        self._account_types = {}
        for type_ in AccountType:
            self._account_types[type_.name] = type_

    def get_widget(self):
        self.toplevel = tk.Toplevel()
        self.form = ttk.Frame(master=self.toplevel)
        for col, label in [(0, 'Type'), (1, 'Number'), (2, 'Name'), (3, 'Parent')]:
            ttk.Label(master=self.form, text=label).grid(row=0, column=col)
        selected = AccountType.ASSET
        if self._account:
            selected = self._account.type
        self.account_type_combo = Combobox(master=self.form, choices=self._account_types, selected=selected)
        self.number_entry = ttk.Entry(master=self.form)
        self.name_entry = ttk.Entry(master=self.form)
        parents = {}
        for account in self._accounts:
            parents[str(account)] = account
        self.parent_combo = Combobox(master=self.form, choices=parents, selected=getattr(self._account, 'parent', None))
        if self._account:
            self.number_entry.insert(0, self._account.number or '')
            self.name_entry.insert(0, self._account.name)
        self.account_type_combo.get_widget().grid(row=1, column=0, sticky=(tk.N, tk.W, tk.S))
        self.number_entry.grid(row=1, column=1, sticky=(tk.N, tk.W, tk.S))
        self.name_entry.grid(row=1, column=2, sticky=(tk.N, tk.W, tk.S))
        self.parent_combo.get_widget().grid(row=1, column=3, sticky=(tk.N, tk.W, tk.S))
        self.save_button = ttk.Button(master=self.form, text='Save', command=self._handle_save)
        self.save_button.grid(row=1, column=4, sticky=(tk.N, tk.W, tk.S))
        self.form.grid()
        return self.toplevel

    def _handle_save(self):
        id_ = None
        if self._account:
            id_ = self._account.id
        type_ = self.account_type_combo.current_value()
        number = self.number_entry.get()
        name = self.name_entry.get()
        parent = self.parent_combo.current_value()
        parent_id=None
        if parent:
            parent_id = parent.id
        try:
            self._save_account(id_=id_, type_=type_, number=number, name=name, parent_id=parent_id)
        except Exception as e:
            handle_error(e)
            return
        self.toplevel.destroy()
        self._update_display()


class AccountsDisplay:

    def __init__(self, master, engine):
        self._master = master
        self._engine = engine
        self.assets_tree = None
        self.income_tree = None
        self.frame = None

    def _show_accounts(self):
        if self.assets_tree:
            self.assets_tree.destroy()
        if self.income_tree:
            self.income_tree.destroy()

        columns = ('name')

        self.assets_tree = ttk.Treeview(master=self.frame, columns=columns, show='headings')
        self.assets_tree.heading('name', text='Assets/Liabilities')
        self.income_tree = ttk.Treeview(master=self.frame, columns=columns, show='headings')
        self.income_tree.heading('name', text='Income/Expense')

        accounts = self._engine.get_accounts(types=[AccountType.ASSET, AccountType.SECURITY, AccountType.LIABILITY, AccountType.EQUITY])
        for account in accounts:
            name = str(account)
            if account.child_level:
                name = ' -  ' * account.child_level + name
            values = (name,)
            self.assets_tree.insert(parent='', index=tk.END, iid=account.id, values=values)

        assets_scrollbar = ttk.Scrollbar(self.frame, orient=tk.VERTICAL, command=self.assets_tree.yview)
        self.assets_tree.configure(yscrollcommand=assets_scrollbar.set)

        self.assets_tree.bind('<Button-1>', partial(self._item_selected, tree=self.assets_tree))
        self.assets_tree.grid(row=1, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))
        assets_scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S))

        accounts = self._engine.get_accounts(types=[AccountType.INCOME, AccountType.EXPENSE])
        for account in accounts:
            name = str(account)
            if account.child_level:
                name = ' -  ' * account.child_level + name
            values = (name,)
            self.income_tree.insert(parent='', index=tk.END, iid=account.id, values=values)

        income_scrollbar = ttk.Scrollbar(self.frame, orient=tk.VERTICAL, command=self.income_tree.yview)
        self.income_tree.configure(yscrollcommand=income_scrollbar.set)

        self.income_tree.bind('<Button-1>', partial(self._item_selected, tree=self.income_tree))
        self.income_tree.grid(row=1, column=2, sticky=(tk.N, tk.W, tk.S, tk.E))
        income_scrollbar.grid(row=1, column=3, sticky=(tk.N, tk.S))

    def get_widget(self):
        self.frame = ttk.Frame(master=self._master)
        self.frame.columnconfigure(0, weight=1)
        self.frame.columnconfigure(2, weight=1)
        self.frame.rowconfigure(1, weight=1)

        self.add_button = ttk.Button(master=self.frame, text='New Account', command=self._open_new_account_form)
        self.add_button.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S))

        self._show_accounts()

        return self.frame

    def _open_new_account_form(self):
        accounts = self._engine.get_accounts()
        self.add_account_form = AccountForm(accounts, save_account=self._engine.save_account, update_display=self._show_accounts)
        widget = self.add_account_form.get_widget()
        widget.grid()

    def _item_selected(self, event, tree=None):
        row_id = tree.identify_row(event.y)
        if not row_id:
            return
        account_id = int(row_id) # iid was set to account.id above
        account = self._engine.get_account(id_=account_id)
        accounts = self._engine.get_accounts()
        self.edit_account_form = AccountForm(accounts, save_account=self._engine.save_account,
                update_display=self._show_accounts, account=account)
        widget = self.edit_account_form.get_widget()
        widget.grid()


class SplitsForm:

    def __init__(self, master, splits, accounts, payees, default_account=None):
        self._has_security_account = False
        if splits:
            self._splits = copy.deepcopy(splits)
            if any([split['account'] for split in self._splits if 'account' in split and split['account'].type == AccountType.SECURITY]):
                self._has_security_account = True
            self.mode = 'advanced'
        else:
            if default_account:
                self._splits = [{'account': default_account}, {}]
            else:
                self._splits = [{}, {}]
            self.mode = 'simple'
        self._accounts = accounts
        self._payees = payees
        self.action_label = None
        self.shares_label = None
        self.frame = ttk.Frame(master=master)

    def get_widget(self):
        self._create_splits_widgets(self._splits)

        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_columnconfigure(1, weight=1)
        self.frame.grid_columnconfigure(2, weight=1)
        self.frame.grid_columnconfigure(3, weight=1)
        self.frame.grid_columnconfigure(4, weight=1)
        self.frame.grid_columnconfigure(5, weight=1)
        self.frame.grid_columnconfigure(6, weight=1)
        self.frame.grid_columnconfigure(7, weight=1)
        self.frame.grid_columnconfigure(8, weight=1)

        self.add_button = ttk.Button(master=self.frame, text='New Split', command=self._add_row)

        ttk.Label(master=self.frame, text='Account').grid(row=0, column=0)
        ttk.Label(master=self.frame, text='Deposit').grid(row=0, column=1)
        ttk.Label(master=self.frame, text='Withdrawal').grid(row=0, column=2)
        ttk.Label(master=self.frame, text='Payer/Payee').grid(row=0, column=3)

        if self.mode == 'advanced':
            ttk.Label(master=self.frame, text='Status').grid(row=0, column=4)
            ttk.Label(master=self.frame, text='Type').grid(row=0, column=5)
            ttk.Label(master=self.frame, text='Description').grid(row=0, column=6)
            if self._has_security_account:
                self.action_label = ttk.Label(master=self.frame, text='Action')
                self.action_label.grid(row=0, column=7)
                self.shares_label = ttk.Label(master=self.frame, text='Shares')
                self.shares_label.grid(row=0, column=8)
            self.add_button.grid(row=len(self._splits)+2, column=0)
        else:
            self.transfer_account_label = ttk.Label(master=self.frame, text='Transfer Account')
            self.transfer_account_label.grid(row=0, column=4)
            self.switch_mode_button = ttk.Button(master=self.frame, text='Advanced', command=self._switch_mode)
            self.switch_mode_button.grid(row=3, column=0)

        self._show_splits(self._splits)

        self.frame.grid()
        return self.frame

    def _switch_mode(self):
        # only switch to advanced mode, for now (no switching back to simple)
        if self.mode == 'advanced':
            return
        self.mode = 'advanced'
        self.transfer_account_label.destroy()
        self.switch_mode_button.destroy()
        ttk.Label(master=self.frame, text='Status').grid(row=0, column=4)
        ttk.Label(master=self.frame, text='Type').grid(row=0, column=5)
        ttk.Label(master=self.frame, text='Description').grid(row=0, column=6)
        self._show_splits(self._splits)
        self.add_button.grid(row=len(self._splits)+2, column=0)

    def deposit_entered(self, event, split_index=None):
        if len(self._splits) == 2:
            self._splits[(split_index+1)%2]['withdrawal_amount'].set(self._splits[split_index]['deposit_amount'].get())

    def withdrawal_entered(self, event, split_index=None):
        if len(self._splits) == 2:
            self._splits[(split_index+1)%2]['deposit_amount'].set(self._splits[split_index]['withdrawal_amount'].get())

    def _get_action_combo(self, selected):
        return Combobox(master=self.frame, choices=TransactionAction.get_combobox_choices(), selected=selected)

    def _create_widgets_for_split(self, split_index, split):
        selected_account = split.get('account')
        account_choices = {}
        for account in self._accounts:
            if account.child_level:
                name = '- ' * account.child_level + str(account)
            else:
                name = str(account)
            account_choices[name] = account
        split['account_combo'] = Combobox(master=self.frame, choices=account_choices, selected=selected_account)
        split['account_combo'].bind('<<ComboboxSelected>>', partial(self._account_selected, split_index=split_index))
        deposit_amount = tk.StringVar()
        withdrawal_amount = tk.StringVar()
        deposit_amount.set('')
        withdrawal_amount.set('')
        split['deposit_entry'] = ttk.Entry(master=self.frame, textvariable=deposit_amount)
        split['withdrawal_entry'] = ttk.Entry(master=self.frame, textvariable=withdrawal_amount)
        if 'amount' in split:
            if split['amount'] >= 0:
                deposit_amount.set(amount_display(split['amount']))
            else:
                withdrawal_amount.set(amount_display(abs(split['amount'])))
        else:
            if split_index == 0 and len(self._splits) == 2:
                split['deposit_entry'].bind('<FocusOut>', partial(self.deposit_entered, split_index=split_index))
                split['withdrawal_entry'].bind('<FocusOut>', partial(self.withdrawal_entered, split_index=split_index))
        split['deposit_amount'] = deposit_amount
        split['withdrawal_amount'] = withdrawal_amount
        payee_choices = {}
        for p in self._payees:
            payee_choices[p.name] = p
        split['payee_combo'] = Combobox(master=self.frame, choices=payee_choices, selected=split.get('payee'))
        status_choices = {}
        for c in ['', Transaction.CLEARED]:
            status_choices[c] = c
        split['status_combo'] = Combobox(master=self.frame, choices=status_choices, selected=split.get('status', ''))
        split['status_combo'].state(['readonly'])
        split['type_entry'] = ttk.Entry(master=self.frame)
        split['type_entry'].insert(0, split.get('type', ''))
        split['description_entry'] = ttk.Entry(master=self.frame)
        split['description_entry'].insert(0, split.get('description', ''))

        if selected_account:
            if selected_account.type == AccountType.SECURITY:
                split['action_combo'] = self._get_action_combo(selected=split.get('action', ''))
                split['shares_entry'] = ttk.Entry(master=self.frame)
                split['shares_entry'].insert(0, quantity_display(split.get('quantity', '')))
            if selected_account.type not in [AccountType.INCOME, AccountType.EXPENSE]:
                split['payee_combo'].state(['disabled'])

    def _create_splits_widgets(self, splits):
        for split_index, split in enumerate(self._splits):
            self._create_widgets_for_split(split_index, split)

    def _show_split(self, split_index, split):
        row_index = split_index + 1
        split['account_combo'].get_widget().grid(row=row_index, column=0)
        split['deposit_entry'].grid(row=row_index, column=1)
        split['withdrawal_entry'].grid(row=row_index, column=2)
        split['payee_combo'].get_widget().grid(row=row_index, column=3)
        split['status_combo'].get_widget().grid(row=row_index, column=4)
        split['type_entry'].grid(row=row_index, column=5)
        split['description_entry'].grid(row=row_index, column=6)
        if 'account' in split and split['account'].type == AccountType.SECURITY:
            split['action_combo'].get_widget().grid(row=row_index, column=7)
            split['shares_entry'].grid(row=row_index, column=8)
        split['row_index'] = row_index

    def _show_splits(self, splits):
        if self.mode == 'advanced':
            for split_index, split in enumerate(self._splits):
                self._show_split(split_index, split)
        else:
            splits[0]['account_combo'].get_widget().grid(row=1, column=0)
            splits[0]['deposit_entry'].grid(row=1, column=1)
            splits[0]['withdrawal_entry'].grid(row=1, column=2)
            splits[1]['payee_combo'].get_widget().grid(row=1, column=3)
            splits[1]['account_combo'].get_widget().grid(row=1, column=4)

    def _add_row(self):
        split = {}
        split_index = len(self._splits)
        self._splits.append(split)
        self._create_widgets_for_split(split_index, split)
        self._show_split(split_index, split)
        self.add_button.grid(row=len(self._splits)+2, column=0)

    def _account_selected(self, event, split_index):
        split = self._splits[split_index]
        account = split['account_combo'].current_value()
        if account and account.type == AccountType.SECURITY:
            if self.mode != 'advanced':
                self._switch_mode()
            row_index = split['row_index']
            if not self.action_label:
                self.action_label = ttk.Label(master=self.frame, text='Action')
                self.action_label.grid(row=0, column=7)
                self.shares_label = ttk.Label(master=self.frame, text='Shares')
                self.shares_label.grid(row=0, column=8)
            split['action_combo'] = self._get_action_combo(selected='')
            split['shares_entry'] = ttk.Entry(master=self.frame)
            split['action_combo'].get_widget().grid(row=row_index, column=7)
            split['shares_entry'].grid(row=row_index, column=8)
        else:
            if self.action_label:
                self.action_label.destroy()
                self.action_label = None
                self.shares_label.destroy()
                self.shares_label = None
            if 'action_combo' in split:
                split['action_combo'].get_widget().destroy()
                split.pop('action_combo')
            if 'shares_entry' in split:
                split['shares_entry'].destroy()
                split.pop('shares_entry')
        if account and account.type in [AccountType.INCOME, AccountType.EXPENSE]:
            split['payee_combo'].state(['!disabled'])
        else:
            split['payee_combo'].state(['disabled'])

    def get_splits(self):
        splits = []
        for split in self._splits:
            s = {}
            account = split['account_combo'].current_value()
            deposit = split['deposit_amount'].get()
            withdrawal = split['withdrawal_amount'].get()
            if account:
                s['account'] = account
                if deposit and withdrawal:
                    raise Exception('can\'t have both deposit and withdrawal set')
                if deposit:
                    s['amount'] = deposit
                else:
                    s['amount'] = f'-{withdrawal}'
            else:
                if deposit or withdrawal:
                    raise Exception('must select account')
                else:
                    continue
            s['type'] = split['type_entry'].get()
            if split['status_combo'].current_value() != '':
                s['status'] = split['status_combo'].current_value()
            s['payee'] = split['payee_combo'].current_value()
            s['description'] = split['description_entry'].get()
            if 'action_combo' in split:
                s['action'] = split['action_combo'].current_value()
            if 'shares_entry' in split:
                s['quantity'] = split['shares_entry'].get()
            splits.append(s)
        return splits


class TransactionForm:

    def __init__(self, engine, account, save_transaction, skip_transaction=None, delete_transaction=None, id_=None, txn_info=None, splits=None):
        self._engine = engine
        self._accounts = self._engine.get_accounts(types=[AccountType.EXPENSE, AccountType.INCOME, AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY, AccountType.SECURITY])
        self._account = account
        self._payees = self._engine.get_payees()
        self._save_transaction = save_transaction
        self._skip_transaction = skip_transaction
        self._delete_transaction = delete_transaction
        self._id = id_
        self._txn_info = txn_info or {}
        self._splits = splits or []

    def get_widget(self):
        self.top_level = tk.Toplevel()
        self.top_level.grid_columnconfigure(0, weight=1)
        self.form = ttk.Frame(master=self.top_level)
        self.form.grid_columnconfigure(0, weight=1)
        self.form.grid_columnconfigure(2, weight=1)
        self.form.grid_columnconfigure(4, weight=1)

        for col, label in [(0, 'Date'), (1, 'Description')]:
            ttk.Label(master=self.form, text=label).grid(row=0, column=col)

        self.date_entry = ttk.Entry(master=self.form)
        self.description_entry = ttk.Entry(master=self.form)
        self.date_entry.insert(0, self._txn_info.get('date', str(date.today())))
        self.description_entry.insert(0, self._txn_info.get('description', ''))
        self.save_button = ttk.Button(master=self.form, text='Save', command=self._handle_save)
        self.date_entry.grid(row=1, column=0, sticky=(tk.N, tk.S))
        self.description_entry.grid(row=1, column=1, sticky=(tk.N, tk.S))

        entries = [self.save_button]
        if self._skip_transaction:
            self.save_button['text'] = 'Enter New'
            self.skip_button = ttk.Button(master=self.form, text='Skip Next', command=self._handle_skip)
            entries.append(self.skip_button)
        elif self._delete_transaction:
            self.delete_button = ttk.Button(master=self.form, text='Delete', command=self._handle_delete)
            entries.append(self.delete_button)
        for index, entry in enumerate(entries):
            entry.grid(row=1, column=index+3)

        self.splits_form = SplitsForm(master=self.form, splits=self._splits, accounts=self._accounts, payees=self._payees, default_account=self._account)
        self.splits_form.get_widget().grid(row=2, column=0, columnspan=5, sticky=(tk.N, tk.S, tk.E, tk.W))

        self.form.grid(sticky=(tk.N, tk.S, tk.E, tk.W))
        return self.top_level

    def _handle_save(self):
        try:
            splits = self.splits_form.get_splits()
            dt = self.date_entry.get()
            kwargs = {
                'id_': self._id,
                'txn_date': dt,
                'description': self.description_entry.get(),
                'splits': splits,
            }
            transaction = Transaction(**kwargs)
            self._save_transaction(transaction=transaction)
        except Exception as e:
            handle_error(e)
            return

        self.top_level.destroy()

    def _handle_delete(self):
        self.top_level.destroy()
        self._delete_transaction()

    def _handle_skip(self):
        self.top_level.destroy()
        self._skip_transaction()


class LedgerDisplay:

    def __init__(self, master, accounts, engine):
        self._master = master
        self._accounts = accounts
        self._bookmarked_accounts = engine.get_bookmarked_accounts()
        self._engine = engine
        if self._bookmarked_accounts:
            self._account = self._bookmarked_accounts[0]
        else:
            self._account = self._accounts[0]
        self.txns_widget = None
        self.cleared_var = tk.StringVar()
        self.balance_var = tk.StringVar()
        self.show_all_txns = False

    def _get_txns(self, status=None, filter_text='', filter_account=None):
        return self._engine.get_transactions(account=self._account, status=status, filter_account=filter_account, query=filter_text)

    def _show_transactions(self, status=None, filter_text='', filter_account=None):
        if self.txns_widget:
            self.txns_widget.destroy()

        self.txns_widget = ttk.Frame(master=self.frame)
        self.txns_widget.columnconfigure(0, weight=1)
        self.txns_widget.rowconfigure(0, weight=1)

        account = self._account
        columns = {
            'date': {'text': 'Date'},
            'payee': {'text': 'Payee'},
            'description': {'text': 'Description'},
            'status': {'text': 'Status'},
            'withdrawal': {'text': 'Withdrawal'},
            'deposit': {'text': 'Deposit'},
            'balance': {'text': 'Balance'},
            'transfer account': {'text': 'Transfer Account'},
        }
        if self._account.type == AccountType.SECURITY:
            columns = {
                'date': {'text': 'Date'},
                'payee': {'text': 'Payee'},
                'description': {'text': 'Description'},
                'status': {'text': 'Status'},
                'shares': {'text': 'Shares'},
                'withdrawal': {'text': 'Withdrawal'},
                'deposit': {'text': 'Deposit'},
                'balance': {'text': 'Balance'},
                'transfer account': {'text': 'Transfer Account'},
            }

        self.txns_tree = ttk.Treeview(master=self.txns_widget, columns=tuple(columns.keys()), show='headings')
        self.txns_tree.tag_configure('scheduled', background='gray')
        for column_name, column_info in columns.items():
            self.txns_tree.heading(column_name, text=column_info['text'])
            self.txns_tree.column(column_name, width=100, anchor='center')

        sorted_txns = self._get_txns(status=status, filter_text=filter_text, filter_account=filter_account)

        date_format = self._engine.get_date_display_format()

        if not any([status, filter_text, filter_account]):
            for st in self._engine.get_scheduled_transactions_due(accounts=[account]):
                tds = get_display_strings_for_ledger(account, st, date_format)
                values = (tds['txn_date'], tds['payee'], tds['description'], tds.get('status', ''),
                          tds['withdrawal'], tds['deposit'], tds.get('balance', ''), tds['transfer_account'])
                iid = f'st{st.id}'
                self.txns_tree.insert('', tk.END, iid=iid, values=values, tags='scheduled')

            balances = self._engine.get_current_balances_for_display(account=self._account, sorted_txns=sorted_txns)
            self.balance_var.set(f'Current Balance: {balances.current}')
            self.cleared_var.set(f'Cleared: {balances.current_cleared}')
        else:
            self.balance_var.set('')
            self.cleared_var.set('')

        reversed_txns = list(reversed(sorted_txns))
        if self.show_all_txns:
            txns = reversed_txns
        else:
            txns = reversed_txns[:100]
        for txn in txns:
            tds = get_display_strings_for_ledger(account, txn, date_format)
            if self._account.type == AccountType.SECURITY:
                values = (tds['txn_date'], tds['payee'], tds['description'], tds['status'], tds['quantity'],
                          tds['withdrawal'], tds['deposit'], tds.get('balance', ''), tds['transfer_account'])
            else:
                values = (tds['txn_date'], tds['payee'], tds['description'], tds['status'],
                          tds['withdrawal'], tds['deposit'], tds.get('balance', ''), tds['transfer_account'])
            self.txns_tree.insert('', tk.END, iid=txn.id, values=values)

        scrollbar = ttk.Scrollbar(self.txns_widget, orient=tk.VERTICAL, command=self.txns_tree)
        self.txns_tree.configure(yscrollcommand=scrollbar.set)

        self.txns_tree.bind('<Button-1>', self._item_selected)
        self.txns_tree.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        self.txns_widget.grid(row=1, column=0, columnspan=7, sticky=(tk.N, tk.W, tk.S, tk.E))

    def get_widget(self):
        self.frame = ttk.Frame(master=self._master)
        self.frame.columnconfigure(2, weight=1)
        self.frame.rowconfigure(1, weight=1)

        account_choices = {}
        for index, account in enumerate(self._bookmarked_accounts + self._accounts):
            if index < len(self._bookmarked_accounts):
                name = '* ' + str(account)
            elif account.child_level:
                name = ' - ' * account.child_level + str(account)
            else:
                name = str(account)
            account_choices[name] = account
        self.account_select_combo = Combobox(master=self.frame, choices=account_choices, selected=self._account)
        self.account_select_combo.bind('<<ComboboxSelected>>', self._update_account)

        self.add_button = ttk.Button(master=self.frame, text='New Transaction', command=self._open_new_transaction_form)
        if self._account in self._bookmarked_accounts:
            bookmark_text = 'Remove Bookmark'
        else:
            bookmark_text = 'Bookmark Account'
        self.bookmark_button = ttk.Button(master=self.frame, text=bookmark_text, command=self._toggle_bookmark)

        self.filter_entry = ttk.Entry(master=self.frame)
        all_accounts_text = 'All Transfer Accounts'
        filter_account_choices = {
            all_accounts_text: None,
        }
        accounts = self._engine.get_accounts(types=[AccountType.EXPENSE, AccountType.INCOME, AccountType.LIABILITY, AccountType.ASSET, AccountType.EQUITY, AccountType.SECURITY])
        for a in accounts:
            if a != self._account:
                filter_account_choices[str(a)] = a
        self.filter_account_combo = Combobox(master=self.frame, choices=filter_account_choices, selected=all_accounts_text)
        self.filter_button = ttk.Button(master=self.frame, text='Filter', command=self._filter_transactions)
        self.clear_filter_button = ttk.Button(master=self.frame, text='Clear Filter', command=self._clear_filter)

        balances_frame = ttk.Frame(master=self.frame)
        balances_frame.columnconfigure(0, weight=1)
        balances_frame.columnconfigure(1, weight=1)
        ttk.Label(master=balances_frame, textvariable=self.cleared_var).grid(row=0, column=0, sticky=(tk.W, tk.E))
        ttk.Label(master=balances_frame, textvariable=self.balance_var).grid(row=0, column=1, sticky=(tk.W, tk.E))
        self.show_all_button = ttk.Button(master=balances_frame, text='Show All', command=self._show_all_txns)
        self.show_all_button.grid(row=0, column=2)

        self.account_select_combo.get_widget().grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S), padx=2)
        self.add_button.grid(row=0, column=1, sticky=(tk.N, tk.W, tk.S), padx=2)
        self.bookmark_button.grid(row=0, column=2, sticky=(tk.N, tk.W, tk.S), padx=2)
        self.filter_entry.grid(row=0, column=3, sticky=(tk.N, tk.S, tk.E), padx=2)
        self.filter_account_combo.get_widget().grid(row=0, column=4, sticky=(tk.N, tk.S, tk.E), padx=2)
        self.filter_button.grid(row=0, column=5, sticky=(tk.N, tk.S, tk.E), padx=2)
        self.clear_filter_button.grid(row=0, column=6, sticky=(tk.N, tk.S, tk.E), padx=2)

        balances_frame.grid(row=2, column=1, columnspan=7, sticky=(tk.W, tk.E))

        self._show_transactions()

        return self.frame

    def _update_account(self, event):
        self._account = self.account_select_combo.current_value()
        self.show_all_txns = False
        self._show_transactions()

    def _open_new_transaction_form(self):
        self.add_transaction_form = TransactionForm(self._engine, account=self._account, save_transaction=self._save)
        widget = self.add_transaction_form.get_widget()
        widget.grid()

    def _toggle_bookmark(self):
        if self._account in self._bookmarked_accounts:
            self._engine.remove_account_bookmark(self._account.id)
            self.bookmark_button.configure(text='Bookmark Account')
        else:
            self._engine.bookmark_account(self._account.id)
            self.bookmark_button.configure(text='Remove Bookmark')

    def _item_selected(self, event):
        row = self.txns_tree.identify_row(event.y)
        txn_id = row
        if isinstance(txn_id, str) and txn_id.startswith('st'):
            st_id = int(txn_id.replace('st', ''))
            scheduled_transaction = self._engine.get_scheduled_transaction(id_=st_id)
            save_txn = partial(self._enter_scheduled_transaction, scheduled_transaction=scheduled_transaction)
            skip_txn = partial(self._skip_scheduled_transaction, scheduled_transaction_id=scheduled_transaction.id)
            self.edit_scheduled_transaction_form = TransactionForm(
                    engine=self._engine,
                    save_transaction=save_txn,
                    account=self._account,
                    skip_transaction=skip_txn,
                    txn_info={'date': scheduled_transaction.next_due_date, 'description': scheduled_transaction.description},
                    splits=scheduled_transaction.splits,
                )
            widget = self.edit_scheduled_transaction_form.get_widget()
            widget.grid()
        elif txn_id:
            txn_id = int(txn_id)
            transaction = self._engine.get_transaction(id_=txn_id)
            col = self.txns_tree.identify_column(event.x)
            if col == '#4':  # Status column is '#4'
                transaction.update_reconciled_state(self._account)
                self._engine.save_transaction(transaction)
                status = transaction.get_status(self._account)
                self.txns_tree.set(row, column=col, value=status)
                return 'break'  # So that default event handler doesn't run
            else:
                self.edit_transaction_form = TransactionForm(self._engine, account=self._account,
                        save_transaction=self._save,
                        delete_transaction=partial(self._delete, transaction_id=txn_id), id_=txn_id,
                        txn_info={'date': transaction.txn_date, 'description': transaction.description},
                        splits=transaction.splits)
                widget = self.edit_transaction_form.get_widget()
                widget.grid()

    def _save(self, transaction):
        self._engine.save_transaction(transaction)
        self._show_transactions()

    def _delete(self, transaction_id):
        self._engine.delete_transaction(transaction_id=transaction_id)
        self._show_transactions()

    def _enter_scheduled_transaction(self, scheduled_transaction, transaction):
        self._engine.enter_scheduled_transaction(scheduled_transaction, transaction)
        self._show_transactions()

    def _skip_scheduled_transaction(self, scheduled_transaction_id):
        self._engine.skip_scheduled_transaction(scheduled_transaction_id)
        self._show_transactions()

    def _filter_transactions(self):
        filter_account = self.filter_account_combo.current_value()
        filter_entry_value = self.filter_entry.get().strip()
        filter_parts = filter_entry_value.split()
        filter_text = ''
        status = ''
        for fp in filter_parts:
            if fp.startswith('status:'):
                status = fp.replace('status:', '')
            else:
                filter_text += f' {fp}'
        status = status or None
        self._show_transactions(status=status, filter_text=filter_text.strip(), filter_account=filter_account)

    def _clear_filter(self):
        self.filter_entry.delete(0, tk.END)
        self.filter_account_combo.set_current_index(0)
        self._show_transactions()

    def _show_all_txns(self):
        self.show_all_txns = True
        self._show_transactions()


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

    def get_widget(self):
        self._form = tk.Toplevel()
        self._form.geometry("800x600+0+0")
        self._form.rowconfigure(0, weight=1)
        self._form.columnconfigure(0, weight=1)

        from idlelib.configdialog import VerticalScrolledFrame
        self.content = VerticalScrolledFrame(parent=self._form)

        ttk.Label(master=self.content.interior, text='Start Date').grid(row=0, column=0)
        ttk.Label(master=self.content.interior, text='End Date').grid(row=0, column=1)
        self.start_date_entry = ttk.Entry(master=self.content.interior)
        self.end_date_entry = ttk.Entry(master=self.content.interior)
        if self._budget:
            self.start_date_entry.insert(0, str(self._budget.start_date))
            self.end_date_entry.insert(0, str(self._budget.end_date))
        self.start_date_entry.grid(row=1, column=0)
        self.end_date_entry.grid(row=1, column=1)

        ttk.Label(master=self.content.interior, text='Amount').grid(row=2, column=1)
        ttk.Label(master=self.content.interior, text='Carryover').grid(row=2, column=2)
        row = 3
        for account, info in self._budget_data.items():
            ttk.Label(master=self.content.interior, text=str(account)).grid(row=row, column=0)
            amount_entry = ttk.Entry(master=self.content.interior)
            carryover_entry = ttk.Entry(master=self.content.interior)
            amount_entry.insert(0, str(info.get('amount', '')))
            carryover_entry.insert(0, str(info.get('carryover', '')))
            self._widgets['budget_data'][account] = {
                    'amount': amount_entry,
                    'carryover': carryover_entry,
                }
            amount_entry.grid(row=row, column=1)
            carryover_entry.grid(row=row, column=2)
            row += 1
        self.save_button = ttk.Button(master=self.content.interior, text='Save', command=self._save)
        self.save_button.grid(row=row, column=0)

        self.content.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.W, tk.E))
        return self._form

    def _save(self):
        start_date = self.start_date_entry.get()
        end_date = self.end_date_entry.get()
        account_budget_info = {}
        for account, widgets in self._widgets['budget_data'].items():
            account_budget_info[account] = {'amount': widgets['amount'].get(), 'carryover': widgets['carryover'].get()}
        try:
            if self._budget:
                b = Budget(start_date=start_date, end_date=end_date, id_=self._budget.id, account_budget_info=account_budget_info)
            else:
                b = Budget(start_date=start_date, end_date=end_date, account_budget_info=account_budget_info)
            self._save_budget(b)
        except Exception as e:
            handle_error(e)
            return
        self._form.destroy()


class BudgetDisplay:

    def __init__(self, master, engine, current_budget):
        self._master = master
        self._engine = engine
        if not current_budget:
            budgets = self._engine.get_budgets()
            if budgets:
                current_budget = budgets[0]
        self._current_budget = current_budget
        self.tree = None

    def get_widget(self):
        self.frame = ttk.Frame(master=self._master)
        self.frame.columnconfigure(2, weight=1)
        self.frame.rowconfigure(1, weight=1)

        budget_choices = {}
        budgets = self._engine.get_budgets()
        for budget in budgets:
            budget_choices[budget.display(show_id=False)] = budget
        self.budget_select_combo = Combobox(master=self.frame, choices=budget_choices, selected=self._current_budget)
        self.budget_select_combo.bind('<<ComboboxSelected>>', self._update_budget)
        self.budget_select_combo.get_widget().grid(row=0, column=0, sticky=(tk.W,))

        self.add_button = ttk.Button(master=self.frame, text='New Budget', command=partial(self._open_form, budget=None))
        self.add_button.grid(row=0, column=1, sticky=(tk.W,))

        self._display_budget()

        return self.frame

    def _display_budget(self):
        if self.tree:
            self.tree.destroy()

        columns = ('account', 'amount', 'income', 'carryover', 'total budget', 'spent', 'remaining', 'remaining percent', 'current status')

        report_data = []
        if self._current_budget:
            budget_report = self._current_budget.get_report_display(current_date=date.today())
            for info in budget_report['income']:
                report_data.append(info)
            for info in budget_report['expense']:
                report_data.append(info)

            self.edit_button = ttk.Button(master=self.frame, text='Edit Budget', command=partial(self._open_form, budget=self._current_budget))
            self.edit_button.grid(row=0, column=2, sticky=(tk.W,))


        self.tree = ttk.Treeview(master=self.frame, columns=columns, show='headings')
        self.tree.heading('account', text='Account')
        self.tree.column('account', width=100, anchor='center')
        self.tree.heading('amount', text='Amount')
        self.tree.column('amount', width=100, anchor='center')
        self.tree.heading('income', text='Income')
        self.tree.column('income', width=100, anchor='center')
        self.tree.heading('carryover', text='Carryover')
        self.tree.column('carryover', width=100, anchor='center')
        self.tree.heading('total budget', text='Total Budget')
        self.tree.column('total budget', width=100, anchor='center')
        self.tree.heading('spent', text='Spent')
        self.tree.column('spent', width=100, anchor='center')
        self.tree.heading('remaining', text='Remaining')
        self.tree.column('remaining', width=100, anchor='center')
        self.tree.heading('remaining percent', text='Remaining Percent')
        self.tree.column('remaining percent', width=100, anchor='center')
        self.tree.heading('current status', text='Current Status')
        self.tree.column('current status', width=100, anchor='center')

        for row in report_data:
            values = row.get('name', ''), row.get('amount', ''), row.get('income', ''), row.get('carryover', ''), row.get('total_budget', ''), row.get('spent', ''), row.get('remaining', ''), row.get('remaining_percent', ''), row.get('current_status', '')
            self.tree.insert('', tk.END, values=values)

        self.tree.grid(row=1, column=0, columnspan=3, sticky=(tk.N, tk.S, tk.W, tk.E))

    def _update_budget(self, event):
        self._current_budget = self.budget_select_combo.current_value()
        self._display_budget()

    def _open_form(self, budget):
        if budget:
            self.budget_form = BudgetForm(budget=budget, save_budget=self._save_budget_and_reload)
        else:
            income_and_expense_accounts = self._engine.get_accounts(types=[AccountType.INCOME, AccountType.EXPENSE])
            self.budget_form = BudgetForm(accounts=income_and_expense_accounts, save_budget=partial(self._save_budget_and_reload, new_budget=True))
        widget = self.budget_form.get_widget()
        widget.grid()

    def _save_budget_and_reload(self, budget, new_budget=False):
        self._engine.save_budget(budget)
        self._current_budget = self._engine.get_budget(id_=budget.id)
        self._display_budget()


class ScheduledTransactionForm:
    '''Used for editing Scheduled Transactions (ie. frequency, ...)'''

    def __init__(self, engine, save_scheduled_transaction, delete_scheduled_transaction, scheduled_transaction=None):
        self._engine = engine
        self._accounts = self._engine.get_accounts(types=[AccountType.EXPENSE, AccountType.INCOME, AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY, AccountType.SECURITY])
        self._payees = self._engine.get_payees()
        self._scheduled_transaction = scheduled_transaction
        self._save_scheduled_txn = save_scheduled_transaction
        self._delete_scheduled_txn = delete_scheduled_transaction

    def get_widget(self):
        self._form = tk.Toplevel()
        self.content = ttk.Frame(master=self._form)

        ttk.Label(master=self.content, text='Name').grid(row=0, column=0, sticky=(tk.N, tk.S, tk.W, tk.E))
        ttk.Label(master=self.content, text='Frequency').grid(row=0, column=1, sticky=(tk.N, tk.S, tk.W, tk.E))
        ttk.Label(master=self.content, text='Next Due Date').grid(row=0, column=2, sticky=(tk.N, tk.S, tk.W, tk.E))
        self.name_entry = ttk.Entry(master=self.content)
        if self._scheduled_transaction:
            self.name_entry.insert(0, self._scheduled_transaction.name)
        frequency_choices = {}
        selected_frequency = None
        if self._scheduled_transaction:
            selected_frequency = self._scheduled_transaction.frequency
        else:
            selected_frequency = ScheduledTransactionFrequency.WEEKLY
        for index, frequency in enumerate(ScheduledTransactionFrequency):
            frequency_choices[frequency.name] = frequency
        self.frequency_combo = Combobox(master=self.content, choices=frequency_choices, selected=selected_frequency)
        self.next_due_date_entry = ttk.Entry(master=self.content)
        if self._scheduled_transaction:
            self.next_due_date_entry.insert(0, str(self._scheduled_transaction.next_due_date or ''))

        self.name_entry.grid(row=1, column=0, sticky=(tk.N, tk.S, tk.W, tk.E))
        self.frequency_combo.get_widget().grid(row=1, column=1, sticky=(tk.N, tk.S, tk.W, tk.E))
        self.next_due_date_entry.grid(row=1, column=2, sticky=(tk.N, tk.S, tk.W, tk.E))

        self.save_button = ttk.Button(master=self.content, text='Save', command=self._save)
        self.save_button.grid(row=1, column=3)

        if self._scheduled_transaction:
            self.delete_button = ttk.Button(master=self.content, text='Delete', command=self._delete)
            self.delete_button.grid(row=1, column=4)

            self.enter_new_txn_button = ttk.Button(master=self.content, text='Enter New Txn', command=self._open_enter_new_form)
            self.enter_new_txn_button.grid(row=1, column=5)

        if self._scheduled_transaction:
            splits = self._scheduled_transaction.splits
        else:
            splits = []

        self.splits_form = SplitsForm(master=self.content, splits=splits, accounts=self._accounts, payees=self._payees)
        self.splits_form.get_widget().grid(row=2, column=0, columnspan=6)

        self.content.grid(sticky=(tk.N, tk.S, tk.W, tk.E))

        return self._form

    def _save(self):
        if self._scheduled_transaction:
            id_ = self._scheduled_transaction.id
        else:
            id_ = None
        splits = self.splits_form.get_splits()
        try:
            st = ScheduledTransaction(
                    name=self.name_entry.get(),
                    frequency=self.frequency_combo.current_value(),
                    next_due_date=self.next_due_date_entry.get(),
                    splits=splits,
                    id_=id_,
                )
            self._save_scheduled_txn(scheduled_txn=st)
        except Exception as e:
            handle_error(e)
            return
        self._form.destroy()

    def _delete(self):
        if self._scheduled_transaction:
            try:
                id_ = self._scheduled_transaction.id
                self._delete_scheduled_txn(id_)
            except Exception as e:
                handle_error(e)
                return
            self._form.destroy()

    def _open_enter_new_form(self):
        scheduled_transaction = self._scheduled_transaction
        save_txn = partial(self._enter_new_transaction, scheduled_transaction=scheduled_transaction)
        skip_txn = partial(self._skip_transaction, scheduled_transaction=scheduled_transaction)
        self._new_txn_form = TransactionForm(
            engine=self._engine,
            save_transaction=save_txn,
            account=scheduled_transaction.splits[0]['account'],
            skip_transaction=skip_txn,
            splits=scheduled_transaction.splits,
        )
        widget = self._new_txn_form.get_widget()
        widget.grid()

        self._form.destroy()

    def _enter_new_transaction(self, scheduled_transaction, transaction):
        self._engine.enter_scheduled_transaction(scheduled_transaction, transaction)

    def _skip_transaction(self, scheduled_transaction):
        self._engine.skip_scheduled_transaction(scheduled_transaction.id)


class ScheduledTransactionsDisplay:

    def __init__(self, master, engine):
        self._master = master
        self._engine = engine
        self.scheduled_txns_frame = None
        self.tree = None

    def _show_scheduled_transactions(self):
        if self.scheduled_txns_frame:
            self.scheduled_txns_frame.destroy()

        self.scheduled_txns_frame = ttk.Frame(master=self.frame)
        self.scheduled_txns_frame.rowconfigure(0, weight=1)
        self.scheduled_txns_frame.columnconfigure(0, weight=1)

        columns = ('name', 'frequency', 'next_due_date', 'payee', 'splits')

        self.tree = ttk.Treeview(self.scheduled_txns_frame, columns=columns, show='headings')
        self.tree.heading('name', text='Name')
        self.tree.column('name', width=50, anchor='center')
        self.tree.heading('frequency', text='Frequency')
        self.tree.column('frequency', width=50, anchor='center')
        self.tree.heading('next_due_date', text='Next Due Date')
        self.tree.column('next_due_date', width=50, anchor='center')
        self.tree.heading('payee', text='Payee')
        self.tree.column('payee', width=50, anchor='center')
        self.tree.heading('splits', text='Splits')
        self.tree.column('splits', width=250, anchor='center')

        scheduled_txns = self._engine.get_scheduled_transactions()
        for scheduled_txn in scheduled_txns:
            payees = [s['payee'] for s in scheduled_txn.splits if 'payee' in s]
            if payees:
                payee = payees[0].name
            else:
                payee = ''
            values = (scheduled_txn.name, scheduled_txn.frequency.value, str(scheduled_txn.next_due_date or ''), payee, splits_display(scheduled_txn.splits))
            self.tree.insert('', tk.END, iid=scheduled_txn.id, values=values)

        self.tree.bind('<Button-1>', self._item_selected)
        self.tree.bind('<Button-3>', self._item_selected)

        scrollbar = ttk.Scrollbar(self.scheduled_txns_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, columnspan=2, sticky=(tk.N, tk.S, tk.E, tk.W))

        scrollbar.grid(row=0, column=1, columnspan=2, sticky=(tk.N, tk.S))

        self.scheduled_txns_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.N, tk.S, tk.E, tk.W))

    def get_widget(self):
        self.frame = ttk.Frame(master=self._master)
        self.frame.columnconfigure(1, weight=1)
        self.frame.rowconfigure(1, weight=1)

        self.add_button = ttk.Button(master=self.frame, text='New Scheduled Transaction', command=self._open_new_form)
        self.add_button.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S))

        self._show_scheduled_transactions()

        return self.frame

    def _open_new_form(self):
        self.new_form = ScheduledTransactionForm(self._engine,
                save_scheduled_transaction=self._save_and_reload, delete_scheduled_transaction=None)
        widget = self.new_form.get_widget()
        widget.grid()

    def _item_selected(self, event):
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        scheduled_transaction_id = int(row_id)
        scheduled_transaction = self._engine.get_scheduled_transaction(id_=scheduled_transaction_id)

        self.edit_form = ScheduledTransactionForm(
            self._engine,
            save_scheduled_transaction=self._save_and_reload,
            delete_scheduled_transaction=self._delete_and_reload,
            scheduled_transaction=scheduled_transaction
        )

        widget = self.edit_form.get_widget()
        widget.grid()

    def _save_and_reload(self, scheduled_txn):
        self._engine.save_scheduled_transaction(scheduled_txn=scheduled_txn)
        self._show_scheduled_transactions()

    def _delete_and_reload(self, scheduled_txn_id):
        self._engine.delete_scheduled_transaction(scheduled_txn_id)
        self._show_scheduled_transactions()


class IncomeExpenseReport:

    def __init__(self, master, report):
        self._master = master
        self._report = report

    def get_widget(self):
        report = self._report
        self.frame = ttk.Frame(master=self._master)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(1, weight=1)

        ttk.Label(master=self.frame, text=report['heading']).grid(row=0, column=0)

        years = list(report['year_totals'].keys())[-5:]

        columns = ('account',) + tuple([str(y) for y in years]) + ('total',)

        report_tree = ttk.Treeview(master=self.frame, columns=columns, show='headings')
        report_tree.heading('account', text='Account')

        for year in years:
            report_tree.heading(str(year), text=str(year))

        report_tree.heading('total', text='Total')

        for account, data in report['income']['accounts'].items():
            values = (str(account),) + tuple([amount_display(data.get(year, Fraction(0))) for year in years]) + (amount_display(data['total']),)
            report_tree.insert('', tk.END, values=values)

        values = ['Total Income']
        values += [amount_display(report['year_totals'].get(y, {}).get('income', Fraction(0))) for y in years]
        values += [amount_display(report['income']['total'])]
        report_tree.insert('', tk.END, values=values)

        for account, data in report['expense']['accounts'].items():
            values = (str(account),) + tuple([amount_display(data.get(year, Fraction(0))) for year in years]) + (amount_display(data['total']),)
            report_tree.insert('', tk.END, values=values)

        values = ['Total Expense']
        values += [amount_display(report['year_totals'].get(y, {}).get('expense', Fraction(0))) for y in years]
        values += [amount_display(report['income']['total'])]
        report_tree.insert('', tk.END, values=values)

        report_tree.grid(row=1, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))

        return self.frame


class ReportsDisplay:

    def __init__(self, master, engine):
        self._master = master
        self._engine = engine

    def get_widget(self):
        self.frame = ttk.Frame(master=self._master)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(1, weight=1)

        self.income_expense_button = ttk.Button(master=self.frame, text='Income/Expense', command=self._show_income_expense)
        self.income_expense_button.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S))

        return self.frame

    def _show_income_expense(self):
        report = self._engine.get_income_expense_report()
        report_display = IncomeExpenseReport(self.frame, report)
        widget = report_display.get_widget()
        widget.grid(row=1, column=0, sticky=(tk.N, tk.S, tk.W, tk.E))


class GUI_TK:

    def __init__(self, file_name):
        self.root = tk.Tk()
        self.root.title(TITLE)

        w, h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry("%dx%d+0+0" % (w, h))

        #make sure root container is set to resize properly
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        #this frame will contain everything the user sees
        self.content_frame = ttk.Frame(master=self.root, padding=(1, 1, 1, 1))
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.rowconfigure(1, weight=1)
        self.content_frame.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

        self.main_frame = None

        self._show_splash()
        if file_name:
            self._load_db(file_name)

    def _show_splash(self):
        self.main_frame = ttk.Frame(master=self.content_frame)
        new_button = ttk.Button(master=self.main_frame, text='New...', command=self._new_file)
        new_button.grid(row=0, column=0)
        open_button = ttk.Button(master=self.main_frame, text='Open...', command=self._open_file)
        open_button.grid(row=1, column=0)
        files = Config.get_recently_used_files()
        if files:
            ttk.Label(master=self.main_frame, text='Recently used files:').grid(row=2, column=0)
            for index, f in enumerate(files, start=3):
                button = ttk.Button(master=self.main_frame, text=f, command=partial(self._load_db, file_name=str(f)))
                button.grid(row=index, column=0)
        self.main_frame.grid()

    def _new_file(self):
        from tkinter import filedialog as fd
        d = fd.FileDialog(master=self.main_frame)
        file_name = d.go()
        if file_name:
            self._load_db(file_name=file_name)

    def _open_file(self):
        from tkinter import filedialog as fd
        # https://stackoverflow.com/a/54068050
        # call a dummy dialog with an impossible option to initialize the file
        # dialog without really getting a dialog window; this will throw a
        # TclError, so we need a try...except :
        try:
            self.root.tk.call('tk_getOpenFile', '-foobarbaz')
        except tk.TclError:
            pass
        self.root.tk.call('set', '::tk::dialog::file::showHiddenVar', '0')
        file_name = fd.askopenfilename()
        if file_name:
            self._load_db(file_name=file_name, save_recently_used=True)

    def _load_db(self, file_name, save_recently_used=False):
        try:
            self._engine = Engine(file_name)
            if save_recently_used:
                Config.save_recently_used_file(file_name)
        except InvalidStorageFile as e:
            if 'file is not a database' in str(e):
                handle_error(f'File {file_name} is not a database')
                return
            raise

        self._action_buttons_frame = self._init_action_buttons_frame(self.content_frame)
        self._action_buttons_frame.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

        accounts = self._engine.get_accounts()
        if accounts:
            self._show_ledger(accounts=accounts)
        else:
            self._show_accounts()

    def _init_action_buttons_frame(self, master):
        frame = ttk.Frame(master=master)
        self.accounts_button = ttk.Button(master=frame, text='Accounts', command=self._show_accounts)
        self.accounts_button.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S), padx=2, pady=2)
        self.ledger_button = ttk.Button(master=frame, text='Ledger', command=self._show_ledger)
        self.ledger_button.grid(row=0, column=1, sticky=(tk.N, tk.W, tk.S), padx=2, pady=2)
        self.budget_button = ttk.Button(master=frame, text='Budget', command=self._show_budget)
        self.budget_button.grid(row=0, column=2, sticky=(tk.N, tk.W, tk.S), padx=2, pady=2)
        self.scheduled_transactions_button = ttk.Button(master=frame, text='Scheduled Transactions', command=self._show_scheduled_transactions)
        self.scheduled_transactions_button.grid(row=0, column=3, sticky=(tk.N, tk.W, tk.S), padx=2, pady=2)
        self.reports_button = ttk.Button(master=frame, text='Reports', command=self._show_reports)
        self.reports_button.grid(row=0, column=4, sticky=(tk.N, tk.W, tk.S), padx=2, pady=2)
        return frame

    def _update_action_buttons(self, display):
        self.accounts_button['state'] = tk.NORMAL
        self.ledger_button['state'] = tk.NORMAL
        self.budget_button['state'] = tk.NORMAL
        self.scheduled_transactions_button['state'] = tk.NORMAL
        self.reports_button['state'] = tk.NORMAL
        if display == 'accounts':
            self.accounts_button['state'] = tk.DISABLED
        elif display == 'budget':
            self.budget_button['state'] = tk.DISABLED
        elif display == 'scheduled_transactions':
            self.scheduled_transactions_button['state'] = tk.DISABLED
        elif display == 'reports':
            self.reports_button['state'] = tk.DISABLED
        else:
            self.ledger_button['state'] = tk.DISABLED

    def _show_accounts(self):
        if self.main_frame:
            self.main_frame.destroy()
        self._update_action_buttons(display='accounts')
        self.accounts_display = AccountsDisplay(master=self.content_frame, engine=self._engine)
        self.main_frame = self.accounts_display.get_widget()
        self.main_frame.grid(row=1, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

    def _show_ledger(self, accounts=None):
        if not accounts:
            accounts = self._engine.get_accounts()
        if not accounts:
            handle_error('Please create an account first.')
            return
        if self.main_frame:
            self.main_frame.destroy()
        self._update_action_buttons(display='ledger')
        self.ledger_display = LedgerDisplay(master=self.content_frame, accounts=accounts, engine=self._engine)
        self.main_frame = self.ledger_display.get_widget()
        self.main_frame.grid(row=1, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

    def _show_budget(self, current_budget=None):
        if self.main_frame:
            self.main_frame.destroy()
        self._update_action_buttons(display='budget')
        self.budget_display = BudgetDisplay(master=self.content_frame, engine=self._engine, current_budget=current_budget)
        self.main_frame = self.budget_display.get_widget()
        self.main_frame.grid(row=1, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

    def _show_scheduled_transactions(self):
        if self.main_frame:
            self.main_frame.destroy()
        self._update_action_buttons(display='scheduled_transactions')
        self.scheduled_transactions_display = ScheduledTransactionsDisplay(master=self.content_frame, engine=self._engine)
        self.main_frame = self.scheduled_transactions_display.get_widget()
        self.main_frame.grid(row=1, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

    def _show_reports(self):
        if self.main_frame:
            self.main_frame.destroy()
        self._update_action_buttons(display='reports')
        self.reports_display = ReportsDisplay(master=self.content_frame, engine=self._engine)
        self.main_frame = self.reports_display.get_widget()
        self.main_frame.grid(row=1, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))


def import_file(file_to_import):
    if file_to_import.endswith('.kmy'):
        bb_filename = input('enter name of new bricbooks file to create for import: ')
        if os.path.exists(bb_filename):
            raise Exception(f'{bb_filename} already exists')
        print(f'{datetime.now()} importing {file_to_import} to {bb_filename}...')
        engine = Engine(bb_filename)
        with open(file_to_import, 'rb') as f:
            import_kmymoney(f, engine)
    else:
        print(f'invalid import file {file_to_import} - must end with .kmy')


def parse_args():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file_name', dest='file_name')
    parser.add_argument('--cli', dest='cli', action='store_true')
    parser.add_argument('-i', '--import', dest='file_to_import')
    parser.add_argument('-v', dest='version', action='store_true')
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    args = parse_args()

    if args.version:
        print(TITLE)
        sys.exit(0)

    if args.file_to_import:
        import_file(args.file_to_import)
        sys.exit(0)

    if args.file_name and not os.path.exists(args.file_name):
        raise Exception('no such file: "%s"' % args.file_name)

    if args.cli:
        if not args.file_name:
            msg = 'file name argument required for CLI mode'
            log(f'ERROR: {msg}')
            print(msg)
            sys.exit(1)
        try:
            CLI(args.file_name).run()
            sys.exit(0)
        except Exception:
            import traceback
            log(traceback.format_exc())
            raise

    if tk:
        app = GUI_TK(args.file_name)
        app.root.mainloop()
    else:
        msg = "tkinter missing - please make sure it's installed"
        log(f'ERROR: {msg}')
        print(msg)
        sys.exit(1)
