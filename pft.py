'''
Architecture:
    Inner Layer - Account, Category, Transaction, Ledger classes. They know nothing about the storage or UI.
    Next Layer - SQLiteStorage (or another storage class). Knows about inner layer objects, but not the UI.
    Outer Layer - Tkinter widgets (or console UI, ...). Knows about storage layer and inner objects.
    No objects should use private/hidden members of other objects.
'''
from datetime import date, datetime
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
DEBUG = False


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

    def __init__(self, id_=None, name=None, starting_balance=None):
        self.id = id_
        if not name:
            raise InvalidAccountNameError('Account must have a name')
        self.name = name
        self.starting_balance = self._check_starting_balance(starting_balance)

    def __str__(self):
        return self.name

    def __eq__(self, other_account):
        if self.id:
            return self.id == other_account.id
        else:
            return self.name == other_account.name

    def _check_starting_balance(self, starting_balance):
        if isinstance(starting_balance, Decimal):
            return starting_balance
        elif isinstance(starting_balance, (int, str)):
            try:
                return Decimal(starting_balance)
            except InvalidOperation:
                raise InvalidAccountStartingBalanceError('invalid starting balance %s' % starting_balance)
        else:
            raise InvalidAccountStartingBalanceError('invalid type %s for starting_balance' % type(starting_balance))
        return starting_balance


class Category:

    def __init__(self, name, is_expense=True, id_=None, parent=None, user_id=None):
        self.name = name
        self.id = id_
        self.is_expense = is_expense
        self.parent = parent
        self.user_id = user_id

    def __str__(self):
        if self.id:
            return '%s - %s' % (self.id, self.name)
        elif self.user_id:
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
                'categories': txn_categories_display(self),
            }

    def update_from_user_strings(self, debit=None, credit=None, txn_date=None, txn_type=None, categories=None, payee=None, description=None, status=None):
        if debit:
            self.amount = self._check_amount('-%s' % debit)
        elif credit:
            self.amount = self._check_amount(credit)
        else:
            raise InvalidTransactionError('must have debit or credit value for a transaction')
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
        conn.execute('CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT, starting_balance TEXT)')
        conn.execute('CREATE TABLE budgets (id INTEGER PRIMARY KEY, name TEXT, start_date TEXT, end_date TEXT)')
        conn.execute('CREATE TABLE budget_values (id INTEGER PRIMARY KEY, budget_id INTEGER, category_id INTEGER, amount TEXT, carryover TEXT, notes TEXT)')
        conn.execute('CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT, is_expense INTEGER, parent_id INTEGER, user_id TEXT)')
        conn.execute('CREATE TABLE transactions (id INTEGER PRIMARY KEY, account_id INTEGER, txn_type TEXT, txn_date TEXT, payee TEXT, amount TEXT, description TEXT, status TEXT)')
        conn.execute('CREATE TABLE txn_categories (id INTEGER PRIMARY KEY, txn_id INTEGER, category_id INTEGER, amount TEXT)')

    def get_account(self, account_id):
        account_info = self._db_connection.execute('SELECT id, name, starting_balance FROM accounts WHERE id = ?', (account_id,)).fetchone()
        return Account(id_=account_info[0], name=account_info[1], starting_balance=Decimal(account_info[2]))

    def save_account(self, account):
        c = self._db_connection.cursor()
        if account.id:
            c.execute('UPDATE accounts SET name = ?, starting_balance = ?  WHERE id = ?', (account.name, str(account.starting_balance), account.id))
        else:
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


def parse_args():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--debug', action='store_true')
    parser.add_argument('-f', '--file_name', dest='file_name')
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    args = parse_args()
    if args.debug:
        DEBUG = True
    if args.file_name:
        app = PFT_GUI(args.file_name)
    else:
        app = PFT_GUI(DATA_FILENAME)
    if DEBUG:
        print('starting mainloop: %s' % datetime.now())
    app.root.mainloop()

