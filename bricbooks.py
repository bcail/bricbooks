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
import unicodedata
try:
    import readline
except ImportError:
    readline = None


__version__ = '0.5.dev'
TITLE = f'bricbooks {__version__}'
CUR_DIR = os.getcwd()
LOG_FILENAME = 'bricbooks.log'
SQLITE_VERSION = sqlite3.sqlite_version_info


def log(msg):
    log_filepath = os.path.join(CUR_DIR, LOG_FILENAME)
    with open(log_filepath, 'ab') as f:
        f.write(msg.encode('utf8'))


if SQLITE_VERSION < (3, 37, 0):
    msg = f'SQLite version {SQLITE_VERSION} is too old: need at least 3.37.0'
    log(msg)
    print(msg)
    sys.exit(1)


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


def to_ascii(s):
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')


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
    #a string could contain ',', so remove those
    if isinstance(value, str):
        value = value.replace(',', '')
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
    #a string could contain ',', so remove those
    if isinstance(value, str):
        value = value.replace(',', '')
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
    return '{0:,.2f}'.format(fraction_to_decimal(amount))


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
    if hasattr(txn, 'balance'):
        display_strings['balance'] = amount_display(txn.balance)
    return display_strings


LedgerBalances = namedtuple('LedgerBalances', ['current', 'current_cleared'])


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

class SQLiteStorage:

    SCHEMA_VERSION = 1

    DB_INIT_STATEMENTS = [
        'CREATE TABLE commodities ('
            'id INTEGER PRIMARY KEY,'
            'type TEXT NOT NULL,'
            'code TEXT UNIQUE,'
            'name TEXT NOT NULL,'
            'trading_currency_id INTEGER,'
            'trading_market TEXT,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'FOREIGN KEY(trading_currency_id) REFERENCES commodities(id) ON DELETE RESTRICT) STRICT',
        'CREATE TRIGGER commodity_updated UPDATE ON commodities BEGIN UPDATE commodities SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE institutions ('
            'id INTEGER PRIMARY KEY,'
            'name TEXT UNIQUE NOT NULL,'
            'address TEXT,'
            'routing_number TEXT,'
            'bic TEXT,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP) STRICT',
        'CREATE TRIGGER institution_updated UPDATE ON institutions BEGIN UPDATE institutions SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE accounts ('
            'id INTEGER PRIMARY KEY,'
            'type TEXT NOT NULL,'
            'commodity_id INTEGER NOT NULL,'
            'institution_id INTEGER,'
            'number TEXT UNIQUE,'
            'name TEXT NOT NULL,'
            'parent_id INTEGER,'
            'closed TEXT,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
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
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP) STRICT',
        'CREATE TRIGGER budget_updated UPDATE ON budgets BEGIN UPDATE budgets SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE budget_values ('
            'id INTEGER PRIMARY KEY,'
            'budget_id INTEGER NOT NULL,'
            'account_id INTEGER NOT NULL,'
            'amount TEXT,'
            'carryover TEXT,'
            'notes TEXT,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'FOREIGN KEY(budget_id) REFERENCES budgets(id) ON DELETE RESTRICT,'
            'FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE RESTRICT) STRICT',
        'CREATE TRIGGER budget_value_updated UPDATE ON budget_values BEGIN UPDATE budget_values SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE payees ('
            'id INTEGER PRIMARY KEY,'
            'name TEXT UNIQUE NOT NULL,'
            'notes TEXT,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP) STRICT',
        'CREATE TRIGGER payee_updated UPDATE ON payees BEGIN UPDATE payees SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE scheduled_transactions ('
            'id INTEGER PRIMARY KEY,'
            'name TEXT UNIQUE NOT NULL,'
            'frequency TEXT NOT NULL,'
            'next_due_date TEXT NOT NULL,'
            'type TEXT,'
            'payee_id INTEGER,'
            'description TEXT,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'FOREIGN KEY(payee_id) REFERENCES payees(id) ON DELETE RESTRICT) STRICT',
        'CREATE TRIGGER scheduled_transaction_updated UPDATE ON scheduled_transactions BEGIN UPDATE scheduled_transactions SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE scheduled_transaction_splits ('
            'id INTEGER PRIMARY KEY,'
            'scheduled_transaction_id INTEGER NOT NULL,'
            'account_id INTEGER NOT NULL,'
            'value TEXT,'
            'quantity TEXT,'
            'reconciled_state TEXT,'
            'description TEXT,'
            'action TEXT,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'FOREIGN KEY(scheduled_transaction_id) REFERENCES scheduled_transactions(id) ON DELETE RESTRICT,'
            'FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE RESTRICT) STRICT',
        'CREATE TRIGGER scheduled_transaction_split_updated UPDATE ON scheduled_transaction_splits BEGIN UPDATE scheduled_transaction_splits SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE transactions ('
            'id INTEGER PRIMARY KEY,'
            'currency_id INTEGER NOT NULL,'
            'type TEXT,'
            'date TEXT,'
            'payee_id INTEGER,'
            'description TEXT,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'FOREIGN KEY(currency_id) REFERENCES commodities(id) ON DELETE RESTRICT,'
            'FOREIGN KEY(payee_id) REFERENCES payees(id) ON DELETE RESTRICT) STRICT',
        'CREATE TRIGGER transaction_updated UPDATE ON transactions BEGIN UPDATE transactions SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE transaction_splits ('
            'id INTEGER PRIMARY KEY,'
            'transaction_id INTEGER NOT NULL,'
            'account_id INTEGER NOT NULL,'
            'value TEXT,'
            'quantity TEXT,'
            'reconciled_state TEXT,'
            'description TEXT,'
            'action TEXT,'
            'date_posted TEXT,'
            'date_reconciled TEXT,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE RESTRICT,'
            'FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE RESTRICT) STRICT',
        'CREATE TRIGGER transaction_split_updated UPDATE ON transaction_splits BEGIN UPDATE transaction_splits SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'CREATE TABLE misc ('
            'key TEXT UNIQUE NOT NULL,'
            'value ANY NOT NULL,'
            'created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,'
            'updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP) STRICT',
        'CREATE TRIGGER misc_updated UPDATE ON misc BEGIN UPDATE misc SET updated = CURRENT_TIMESTAMP WHERE id = old.id; END;',
        'INSERT INTO misc(key, value) VALUES("%s", %s)' % ('schema_version', SCHEMA_VERSION),
        'INSERT INTO commodities(type, code, name) VALUES("%s", "%s", "%s")' %
            (CommodityType.CURRENCY.value, 'USD', 'US Dollar'),
    ]

    def __init__(self, conn_name):
        if not conn_name:
            raise SQLiteStorageError(f'invalid SQLite connection name: {conn_name}')
        #conn_name is either ':memory:' or the name of the data file
        if not conn_name == ':memory:':
            conn_name = os.path.join(CUR_DIR, conn_name)
        self._db_connection = sqlite3.connect(conn_name)
        self._db_connection.execute('PRAGMA foreign_keys = ON;')
        result = self._db_connection.execute('PRAGMA foreign_keys').fetchall()
        if result[0][0] != 1:
            msg = 'WARNING: can\'t enable sqlite3 foreign_keys'
            log(msg)
            print(msg)
        tables = self._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        if not tables:
            self._setup_db()
        schema_version = self._db_connection.execute('SELECT value FROM misc WHERE key="schema_version"').fetchall()[0][0]
        if schema_version != SQLiteStorage.SCHEMA_VERSION:
            msg = f'ERROR: wrong schema version: {schema_version}'
            log(msg)
            raise SQLiteStorageError(msg)

    def _setup_db(self):
        '''
        Initialize empty DB.
        '''
        cur = self._db_connection.cursor()
        for statement in self.DB_INIT_STATEMENTS:
            cur.execute(statement)
        self._db_connection.commit()

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
        cur.execute('INSERT INTO commodities(type, code, name) VALUES(?, ?, ?)', (commodity.type.value, commodity.code, commodity.name))
        commodity.id = cur.lastrowid
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
        cur = self._db_connection.cursor()
        parent_id = None
        if account.parent:
            parent_id = account.parent.id
        if account.id:
            cur.execute('UPDATE accounts SET type = ?, commodity_id = ?, number = ?, name = ?, parent_id = ? WHERE id = ?',
                    (account.type.value, account.commodity.id, account.number, account.name, parent_id, account.id))
            if cur.rowcount < 1:
                raise Exception('no account with id %s to update' % account.id)
        else:
            cur.execute('INSERT INTO accounts(type, commodity_id, number, name, parent_id) VALUES(?, ?, ?, ?, ?)', (account.type.value, account.commodity.id, account.number, account.name, parent_id))
            account.id = cur.lastrowid
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
        cur = self._db_connection.cursor()
        if payee.id:
            cur.execute('UPDATE payees SET name = ?, notes = ?', (payee.name, payee.notes))
            if cur.rowcount < 1:
                raise Exception('no payee with id %s to update' % payee.id)
        else:
            cur.execute('INSERT INTO payees(name, notes) VALUES(?, ?)', (payee.name, payee.notes))
            payee.id = cur.lastrowid
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
        id_, currency_id, txn_type, txn_date, payee_id, description = db_info
        txn_date = get_date(txn_date)
        payee = self.get_payee(id_=payee_id)
        cur = self._db_connection.cursor()
        splits = {}
        split_records = cur.execute('SELECT account_id, value, quantity, reconciled_state FROM transaction_splits WHERE transaction_id = ?', (id_,))
        if split_records:
            for split_record in split_records:
                account_id = split_record[0]
                account = self.get_account(account_id)
                splits[account] = {'amount': split_record[1], 'quantity': split_record[2]}
                if split_record[3]:
                    splits[account]['status'] = split_record[3]
        return Transaction(splits=splits, txn_date=txn_date, txn_type=txn_type, payee=payee, description=description, id_=id_)

    def get_txn(self, txn_id):
        cur = self._db_connection.cursor()
        cur.execute('SELECT id,currency_id,type,date,payee_id,description FROM transactions WHERE id = ?', (txn_id,))
        db_info = cur.fetchone()
        return self._txn_from_db_record(db_info=db_info)

    def get_transactions(self):
        txns = []
        db_txn_id_records = self._db_connection.execute('SELECT id FROM transactions').fetchall()
        txn_ids = set([r[0] for r in db_txn_id_records])
        for txn_id in txn_ids:
            txn = self.get_txn(txn_id)
            txns.append(txn)
        return txns

    def save_txn(self, txn):
        cur = self._db_connection.cursor()
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
            cur.execute('UPDATE transactions SET type = ?, date = ?, payee_id = ?, description = ? WHERE id = ?',
                (txn.txn_type, txn.txn_date.strftime('%Y-%m-%d'), payee, txn.description, txn.id))
            if cur.rowcount < 1:
                raise Exception('no txn with id %s to update' % txn.id)
        else:
            cur.execute('INSERT INTO transactions(currency_id, type, date, payee_id, description) VALUES(?, ?, ?, ?, ?)',
                (1, txn.txn_type, txn.txn_date.strftime('%Y-%m-%d'), payee, txn.description))
            txn.id = cur.lastrowid
        #update transaction splits
        splits_db_info = cur.execute('SELECT account_id FROM transaction_splits WHERE transaction_id = ?', (txn.id,)).fetchall()
        old_txn_split_account_ids = [r[0] for r in splits_db_info]
        new_txn_split_account_ids = [a.id for a in txn.splits.keys()]
        split_account_ids_to_delete = set(old_txn_split_account_ids) - set(new_txn_split_account_ids)
        for account_id in split_account_ids_to_delete:
            cur.execute('DELETE FROM transaction_splits WHERE transaction_id = ? AND account_id = ?', (txn.id, account_id))
        for account, info in txn.splits.items():
            if not account.id:
                self.save_account(account)
            amount = info['amount']
            amount = f'{amount.numerator}/{amount.denominator}'
            quantity = info['quantity']
            quantity = f'{quantity.numerator}/{quantity.denominator}'
            status = info.get('status', None)
            if account.id in old_txn_split_account_ids:
                cur.execute('UPDATE transaction_splits SET value = ?, quantity = ?, reconciled_state = ? WHERE transaction_id = ? AND account_id = ?', (amount, quantity, status, txn.id, account.id))
            else:
                cur.execute('INSERT INTO transaction_splits(transaction_id, account_id, value, quantity, reconciled_state) VALUES(?, ?, ?, ?, ?)', (txn.id, account.id, amount, quantity, status))
        self._db_connection.commit()

    def delete_txn(self, txn_id):
        cur = self._db_connection.cursor()
        cur.execute('DELETE FROM transaction_splits WHERE transaction_id = ?', (txn_id,))
        cur.execute('DELETE FROM transactions WHERE id = ?', (txn_id,))
        self._db_connection.commit()

    def save_budget(self, budget):
        cur = self._db_connection.cursor()
        if budget.id:
            cur.execute('UPDATE budgets SET name = ?, start_date = ?, end_date = ? WHERE id = ?',
                (budget.name, str(budget.start_date), str(budget.end_date), budget.id))
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
                    carryover = str(info.get('carryover', ''))
                    notes = info.get('notes', '')
                    if account.id in old_account_ids:
                        values = (str(info['amount']), carryover, notes, budget.id, account.id)
                        cur.execute('UPDATE budget_values SET amount = ?, carryover = ?, notes = ? WHERE budget_id = ? AND account_id = ?', values)
                    else:
                        values = (budget.id, account.id, str(info['amount']), carryover, notes)
                        cur.execute('INSERT INTO budget_values(budget_id, account_id, amount, carryover, notes) VALUES (?, ?, ?, ?, ?)', values)
        else:
            cur.execute('INSERT INTO budgets(start_date, end_date) VALUES(?, ?)', (budget.start_date, budget.end_date))
            budget.id = cur.lastrowid
            budget_data = budget.get_budget_data()
            for account, info in budget_data.items():
                if info:
                    carryover = str(info.get('carryover', ''))
                    notes = info.get('notes', '')
                    values = (budget.id, account.id, str(info['amount']), carryover, notes)
                    cur.execute('INSERT INTO budget_values(budget_id, account_id, amount, carryover, notes) VALUES (?, ?, ?, ?, ?)', values)
        self._db_connection.commit()

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
            txn_splits_records = self._db_connection.execute('SELECT transaction_splits.value FROM transaction_splits INNER JOIN transactions ON transaction_splits.transaction_id = transactions.id WHERE transaction_splits.account_id = ? AND transactions.date > ? AND transactions.date < ?', (account.id, start_date, end_date)).fetchall()
            for record in txn_splits_records:
                amt = Fraction(record[0])
                if amt < Fraction(0):
                    income += amt * Fraction(-1)
                else:
                    spent += amt
            all_income_spending_info[account]['spent'] = spent
            all_income_spending_info[account]['income'] = income
            budget_records = cur.execute('SELECT amount, carryover, notes FROM budget_values WHERE budget_id = ? AND account_id = ?', (id_, account.id)).fetchall()
            if budget_records:
                r = budget_records[0]
                account_budget_info[account]['amount'] = r[0]
                account_budget_info[account]['carryover'] = r[1]
                account_budget_info[account]['notes'] = r[2]
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
        cur = self._db_connection.cursor()

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
            cur.execute('UPDATE scheduled_transactions SET name = ?, frequency = ?, next_due_date = ?, type = ?, payee_id = ?, description = ? WHERE id = ?',
                (scheduled_txn.name, scheduled_txn.frequency.value, scheduled_txn.next_due_date.strftime('%Y-%m-%d'), scheduled_txn.txn_type, payee, scheduled_txn.description, scheduled_txn.id))
            if cur.rowcount < 1:
                raise Exception('no scheduled transaction with id %s to update' % scheduled_txn.id)
            #handle splits
            splits_db_info = cur.execute('SELECT account_id FROM scheduled_transaction_splits WHERE scheduled_transaction_id = ?', (scheduled_txn.id,)).fetchall()
            old_split_account_ids = [r[0] for r in splits_db_info]
            new_split_account_ids = [a.id for a in scheduled_txn.splits.keys()]
            split_account_ids_to_delete = set(old_split_account_ids) - set(new_split_account_ids)
            for account_id in split_account_ids_to_delete:
                cur.execute('DELETE FROM scheduled_transaction_splits WHERE scheduled_transaction_id = ? AND account_id = ?', (scheduled_txn.id, account_id))
            for account, info in scheduled_txn.splits.items():
                amount = info['amount']
                amount = f'{amount.numerator}/{amount.denominator}'
                status = info.get('status', None)
                if account.id in old_split_account_ids:
                    cur.execute('UPDATE scheduled_transaction_splits SET value = ?, quantity = ?, reconciled_state = ? WHERE scheduled_transaction_id = ? AND account_id = ?', (amount, amount, status, scheduled_txn.id, account.id))
                else:
                    cur.execute('INSERT INTO scheduled_transaction_splits(scheduled_transaction_id, account_id, value, quantity, reconciled_state) VALUES (?, ?, ?, ?, ?)', (scheduled_txn.id, account.id, amount, amount, status))
        #add new scheduled transaction
        else:
            cur.execute('INSERT INTO scheduled_transactions(name, frequency, next_due_date, type, payee_id, description) VALUES (?, ?, ?, ?, ?, ?)',
                (scheduled_txn.name, scheduled_txn.frequency.value, scheduled_txn.next_due_date.strftime('%Y-%m-%d'), scheduled_txn.txn_type, payee, scheduled_txn.description))
            scheduled_txn.id = cur.lastrowid
            for account, info in scheduled_txn.splits.items():
                amount = info['amount']
                amount = f'{amount.numerator}/{amount.denominator}'
                status = info.get('status', None)
                cur.execute('INSERT INTO scheduled_transaction_splits(scheduled_transaction_id, account_id, value, quantity, reconciled_state) VALUES (?, ?, ?, ?, ?)', (scheduled_txn.id, account.id, amount, amount, status))
        self._db_connection.commit()

    def get_scheduled_transaction(self, id_):
        cur = self._db_connection.cursor()
        splits = {}
        split_records = cur.execute('SELECT account_id, value, reconciled_state FROM scheduled_transaction_splits WHERE scheduled_transaction_id = ?', (id_,))
        if split_records:
            for split_record in split_records:
                account_id = split_record[0]
                account = self.get_account(account_id)
                splits[account] = {'amount': split_record[1]}
                if split_record[2]:
                    splits[account]['status'] = split_record[2]
        rows = cur.execute('SELECT name,frequency,next_due_date,type,payee_id,description FROM scheduled_transactions WHERE id = ?', (id_,)).fetchall()
        payee = self.get_payee(id_=rows[0][4])
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
        cur = self._db_connection.cursor()
        scheduled_txns_records = cur.execute('SELECT id FROM scheduled_transactions').fetchall()
        scheduled_txns = []
        for st_record in scheduled_txns_records:
            scheduled_txns.append(self.get_scheduled_transaction(st_record[0]))
        return scheduled_txns


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

    def get_ledger_accounts(self):
        '''Retrieve accounts for Ledger display'''
        return self.get_accounts(types=[AccountType.ASSET, AccountType.SECURITY, AccountType.LIABILITY, AccountType.EQUITY])

    def save_account(self, account=None, id_=None, name=None, type_=None, commodity_id=None, number=None, parent_id=None):
        if not account:
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
            account = Account(id_=id_, type_=type_, commodity=commodity, number=number, name=name, parent=parent)
        self._storage.save_account(account)
        return account

    @staticmethod
    def sort_txns(txns, key='date'):
        return sorted(txns, key=lambda t: t.txn_date)

    @staticmethod
    def add_balance_to_txns(txns, account, balance_field='amount'):
        #txns must be sorted in chronological order (not reversed) already
        txns_with_balance = []
        balance = Fraction(0)
        for t in txns:
            balance = balance + t.splits[account][balance_field]
            t.balance = balance
            txns_with_balance.append(t)
        return txns_with_balance

    def get_transaction(self, id_):
        return self._storage.get_txn(id_)

    def get_transactions(self, accounts=None, query=None, status=None, sort='date', reverse=False):
        results = self._storage.get_transactions()
        if accounts:
            for acc in accounts:
                if status:
                    results = [t for t in results if acc in t.splits and t.splits[acc].get('status') == status]
                else:
                    results = [t for t in results if acc in t.splits]
        if query:
            query = query.lower()
            results = [t for t in results
                    if ((t.payee and query in t.payee.name.lower()) or (t.description and query in t.description.lower()))]
        sorted_results = Engine.sort_txns(results, key='date')
        #add balance if we have all the txns for a specific account, without limiting by another account, or a query, or a status, ...
        if accounts and len(accounts) == 1 and not any([query, status]):
            sorted_results = Engine.add_balance_to_txns(sorted_results, account=accounts[0])
        if reverse:
            return list(reversed(sorted_results))
        else:
            return sorted_results

    def get_current_balances_for_display(self, account, balance_field='amount'):
        sorted_txns = self.get_transactions(accounts=[account])
        current = Fraction(0)
        current_cleared = Fraction(0)
        today = date.today()
        for t in sorted_txns:
            if t.txn_date <= today:
                current = t.balance
                if t.splits[account].get('status', None) in [Transaction.CLEARED, Transaction.RECONCILED]:
                    current_cleared = current_cleared + t.splits[account][balance_field]
        return LedgerBalances(
                current=amount_display(current),
                current_cleared=amount_display(current_cleared),
            )

    def save_transaction(self, transaction):
        self._storage.save_txn(transaction)

    def delete_transaction(self, txn_id):
        self._storage.delete_txn(txn_id)

    def get_payee(self, id_=None, name=None):
        return self._storage.get_payee(id_=id_, name=name)

    def get_payees(self):
        return self._storage.get_payees()

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
                scheduled_txns = [st for st in scheduled_txns if acc in st.splits]
        return [t for t in scheduled_txns if t.is_due()]

    def save_scheduled_transaction(self, scheduled_txn):
        return self._storage.save_scheduled_transaction(scheduled_txn)

    def skip_scheduled_transaction(self, id_):
        scheduled_txn = self.get_scheduled_transaction(id_)
        scheduled_txn.advance_to_next_due_date()
        self.save_scheduled_transaction(scheduled_txn)

    def get_budget(self, id_):
        return self._storage.get_budget(id_=id_)

    def get_budgets(self):
        return self._storage.get_budgets()

    def save_budget(self, budget):
        return self._storage.save_budget(budget)

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
            txns = self.get_transactions(accounts=[acc])
            acc_file = os.path.join(export_dir, f'acc_{to_ascii(acc.name.lower())}.tsv')
            with open(acc_file, 'wb') as f:
                f.write('date\ttype\tpayee\tdescription\tamount\ttransfer_account\n'.encode('utf8'))
                for txn in txns:
                    if txn.payee:
                        payee = txn.payee.name
                    else:
                        payee = ''
                    if len(txn.splits.keys()) == 2:
                        transfer_account = [str(a) for a in txn.splits.keys() if a != acc][0]
                    else:
                        transfer_account = 'multiple'
                    data = [str(txn.txn_date), txn.txn_type or '', payee, txn.description or '',
                            amount_display(txn.splits[acc]['amount']), transfer_account]
                    line = self._create_export_line(data)
                    f.write(f'{line}\n'.encode('utf8'))

        for budget in self.get_budgets():
            file_name = os.path.join(export_dir, f'budget_{budget.start_date}_{budget.end_date}.tsv')
            with open(file_name, 'wb') as f:
                f.write('account\n'.encode('utf8'))


### IMPORT ###

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
        commodity = engine.get_commodity(id_=currency_id)
        print(f'  {account.attrib["type"]} {account.attrib["name"]} => {type_}')
        acc_obj = Account(
                    type_=type_,
                    commodity=commodity,
                    name=account.attrib['name'],
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
    print(f'{datetime.now()} migrating transactions...')
    transactions = root.find('TRANSACTIONS')
    for transaction in transactions.iter('TRANSACTION'):
        try:
            splits_el = transaction.find('SPLITS')
            splits = {}
            for split in splits_el.iter('SPLIT'):
                account_orig_id = split.attrib['account']
                account = engine.get_account(account_mapping_info[account_orig_id])
                #reconcileflag: '2'=Reconciled, '1'=Cleared, '0'=nothing
                splits[account] = {'amount': split.attrib['value']}
                if split.attrib['reconcileflag'] == '2':
                    splits[account]['status'] = Transaction.RECONCILED
                elif split.attrib['reconcileflag'] == '1':
                    splits[account]['status'] = Transaction.CLEARED
                payee = None
                if split.attrib['payee']:
                    payee = engine.get_payee(id_=payee_mapping_info[split.attrib['payee']])
            engine.save_transaction(
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


class CLI:

    ACCOUNT_LIST_HEADER = ' ID   | Type        | Number | Name                           | Parent\n'\
        '==============================================================================================='

    TXN_LIST_HEADER = ' ID   | Date       | Type   |  Description                   | Payee                          |  Transfer Account              | Withdrawal | Deposit    | Balance\n'\
        '================================================================================================================================================================'

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
        account = self._engine.get_account(id_=acc_id)
        self._get_and_save_account(account=account)

    def _list_account_txns(self, num_txns_in_page=None):
        if not num_txns_in_page:
            num_txns_in_page = self.NUM_TXNS_IN_PAGE
        user_input = self.input('Account ID (or search string): ')
        user_input_parts = user_input.split()
        account = self._engine.get_account(id_=int(user_input_parts[0]))
        status = None
        account_ids = []
        if len(user_input_parts) > 1:
            for clause in user_input_parts[1:]:
                if clause.startswith('status:'):
                    status = clause.replace('status:', '')
                elif clause.startswith('acc:'):
                    account_ids.append(int(clause.replace('acc:', '')))
        else:
            ledger_balances = self._engine.get_current_balances_for_display(account=account)
            summary_line = f'{account.name} (Current balance: {ledger_balances.current}; Cleared: {ledger_balances.current_cleared})'
            self.print(summary_line)
            scheduled_txns_due = self._engine.get_scheduled_transactions_due(accounts=[account])
            if scheduled_txns_due:
                self.print('Scheduled Transactions due:')
                for st in scheduled_txns_due:
                    self.print(f'{st.id} {st.name} {st.next_due_date}')
        self.print(self.TXN_LIST_HEADER)
        accounts = [account]
        if account_ids:
            accounts.extend([self._engine.get_account(id_=id_) for id_ in account_ids])
        txns = self._engine.get_transactions(accounts=accounts, status=status, reverse=True)
        page_index = 1
        while True:
            paged_txns, more_txns = pager(txns, num_txns_in_page=num_txns_in_page, page=page_index)
            for t in paged_txns:
                tds = get_display_strings_for_ledger(account, t)
                self.print(' {8:<4} | {0:<10} | {1:<6} | {2:<30} | {3:<30} | {4:30} | {5:<10} | {6:<10} | {7:<10}'.format(
                    tds['txn_date'], tds['txn_type'], tds['description'], tds['payee'], tds['categories'], tds['withdrawal'], tds['deposit'], tds.get('balance', ''), t.id)
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
                account = self._engine.get_account(id_=acct_id)
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
            txn_info['payee'] = self._engine.get_payee(id_=payee)
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
        self._engine.save_transaction(Transaction(**info))

    def _create_txn(self):
        self.print('Create Transaction:')
        self._get_and_save_txn()

    def _edit_txn(self):
        txn_id = self.input(prompt='Txn ID: ')
        txn = self._engine.get_transaction(id_=txn_id)
        self._get_and_save_txn(txn=txn)

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
                self._get_and_save_txn(txn=scheduled_txn)
                scheduled_txn.advance_to_next_due_date()
                self._engine.save_scheduled_transaction(scheduled_txn)
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
        engine = Engine(bb_filename)
        with open(file_to_import, 'rb') as f:
            import_kmymoney(f, engine)
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
