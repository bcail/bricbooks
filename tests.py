from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
import io
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import bricbooks as bb
import load_test_data


def get_test_account(id_=None, name='Checking', type_=bb.AccountType.ASSET):
    return bb.Account(id_=id_, type_=type_, name=name)


class TestUtils(unittest.TestCase):

    def test_get_date(self):
        self.assertEqual(bb.get_date(date(2018, 1, 1)), date(2018, 1, 1))
        self.assertEqual(bb.get_date('2018-01-01'), date(2018, 1, 1))
        with self.assertRaises(RuntimeError):
            bb.get_date(10)

    def test_increment_month(self):
        new_date = bb.increment_month(date(2018, 1, 1))
        self.assertEqual(new_date, date(2018, 2, 1))
        new_date = bb.increment_month(date(2018, 12, 1))
        self.assertEqual(new_date, date(2019, 1, 1))
        new_date = bb.increment_month(date(2018, 1, 31))
        self.assertEqual(new_date, date(2018, 2, 28))
        new_date = bb.increment_month(date(2018, 3, 31))
        self.assertEqual(new_date, date(2018, 4, 30))

    def test_increment_quarter(self):
        new_date = bb.increment_quarter(date(2018, 1, 31))
        self.assertEqual(new_date, date(2018, 4, 30))
        new_date = bb.increment_quarter(date(2018, 12, 31))
        self.assertEqual(new_date, date(2019, 3, 31))
        new_date = bb.increment_quarter(date(2018, 11, 30))
        self.assertEqual(new_date, date(2019, 2, 28))

    def test_find_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path1 = os.path.join(tmp, 'file.txt')
            path2 = os.path.join(tmp, 'file.sqlite3')
            path3 = os.path.join(tmp, 'db.sqlite3')
            path4 = os.path.join(tmp, 'file.sql')
            for path in [path1, path2, path3, path4]:
                with open(path, 'wb') as f: pass
            self.assertEqual(sorted([str(f) for f in bb.get_files(tmp)]), [path3, path2])


class TestAccount(unittest.TestCase):

    def test_init(self):
        a = bb.Account(id_=1, type_=bb.AccountType.ASSET, number='400', name='Checking')
        self.assertEqual(a.type, bb.AccountType.ASSET)
        self.assertEqual(a.name, 'Checking')
        self.assertEqual(a.parent, None)
        self.assertEqual(a.number, '400')

    def test_str(self):
        a = bb.Account(id_=1, type_=bb.AccountType.ASSET, number='400', name='Checking')
        self.assertEqual(str(a), '400 - Checking')

    def test_account_type(self):
        with self.assertRaises(bb.InvalidAccountError) as cm:
            bb.Account(id_=1, name='Checking')
        self.assertEqual(str(cm.exception), 'Account must have a type')
        with self.assertRaises(bb.InvalidAccountError) as cm:
            bb.Account(id_=1, type_='asdf', name='Checking')
        self.assertEqual(str(cm.exception), 'Invalid account type "asdf"')
        a = bb.Account(id_=1, type_='asset', name='Checking')
        self.assertEqual(a.type, bb.AccountType.ASSET)

    def test_eq(self):
        a = bb.Account(id_=1, type_=bb.AccountType.ASSET, name='Checking')
        a2 = bb.Account(id_=2, type_=bb.AccountType.ASSET, name='Savings')
        self.assertNotEqual(a, a2)
        self.assertEqual(a, a)
        a3 = bb.Account(type_=bb.AccountType.ASSET, name='Other')
        with self.assertRaises(bb.InvalidAccountError) as cm:
            a == a3
        self.assertEqual(str(cm.exception), "Can't compare accounts without an id")

    def test_parent(self):
        housing = bb.Account(id_=1, type_=bb.AccountType.EXPENSE, name='Housing')
        rent = bb.Account(id_=2, type_=bb.AccountType.EXPENSE, name='Rent', parent=housing)
        self.assertEqual(rent.parent, housing)

    def test_empty_strings_for_non_required_elements(self):
        a = bb.Account(id_=1, type_=bb.AccountType.EXPENSE, name='Test', number='')
        self.assertEqual(a.number, None)


class TestTransaction(unittest.TestCase):

    def setUp(self):
        self.checking = get_test_account(id_=1)
        self.savings = get_test_account(id_=2, name='Savings')
        self.valid_splits = {self.checking: {'amount': '100'}, self.savings: {'amount': '-100'}}

    def test_splits_required(self):
        with self.assertRaises(bb.InvalidTransactionError) as cm:
            bb.Transaction()
        self.assertEqual(str(cm.exception), 'transaction must have at least 2 splits')

    def test_splits_must_balance(self):
        with self.assertRaises(bb.InvalidTransactionError) as cm:
            bb.Transaction(splits={self.checking: {'amount': -100}, self.savings: {'amount': 90}})
        self.assertEqual(str(cm.exception), "splits don't balance: -100, 90")

    def test_invalid_split_amounts(self):
        with self.assertRaises(bb.InvalidTransactionError) as cm:
            bb.Transaction(splits={self.checking: {'amount': 101.1}, self.savings: {'amount': '-101.1'}})
        self.assertEqual(str(cm.exception), 'invalid split: invalid value type: <class \'float\'> 101.1')
        with self.assertRaises(bb.InvalidTransactionError) as cm:
            bb.Transaction(splits={self.checking: {'amount': '123.456'}, self.savings: {'amount': '-123.45'}})
        self.assertEqual(str(cm.exception), 'invalid split: no fractions of cents allowed: 123.456')
        with self.assertRaises(bb.InvalidTransactionError) as cm:
            bb.Transaction(splits={self.checking: {'amount': '123.456'}, self.savings: {'amount': 123}})
        self.assertEqual(str(cm.exception), 'invalid split: no fractions of cents allowed: 123.456')

    def test_invalid_txn_date(self):
        with self.assertRaises(bb.InvalidTransactionError) as cm:
            bb.Transaction(splits=self.valid_splits)
        self.assertEqual(str(cm.exception), 'transaction must have a txn_date')
        with self.assertRaises(bb.InvalidTransactionError) as cm:
            bb.Transaction(splits=self.valid_splits, txn_date=10)
        self.assertEqual(str(cm.exception), 'invalid txn_date "10"')

    def test_txn_date(self):
        t = bb.Transaction(splits=self.valid_splits, txn_date=date.today())
        self.assertEqual(t.txn_date, date.today())
        t = bb.Transaction(splits=self.valid_splits, txn_date='2018-03-18')
        self.assertEqual(t.txn_date, date(2018, 3, 18))
        t = bb.Transaction(splits=self.valid_splits, txn_date='3/18/2018')
        self.assertEqual(t.txn_date, date(2018, 3, 18))

    def test_init(self):
        splits = {self.checking: {'amount': '100', 'status': 'c'}, self.savings: {'amount': '-100'}}
        t = bb.Transaction(
                splits=splits,
                txn_date=date.today(),
                txn_type='1234',
                payee=bb.Payee('payee 1'),
                description='2 hamburgers',
            )
        txn_splits = {self.checking: {'amount': Fraction(100), 'status': 'C'}, self.savings: {'amount': Fraction(-100)}}
        self.assertEqual(t.splits, txn_splits)
        self.assertTrue(isinstance(t.splits[self.checking]['amount'], Fraction))
        self.assertEqual(t.txn_date, date.today())
        self.assertEqual(t.txn_type, '1234')
        self.assertEqual(t.payee.name, 'payee 1')
        self.assertEqual(t.description, '2 hamburgers')

    def test_sparse_init(self):
        #pass minimal amount of info into Transaction & verify values
        t = bb.Transaction(
                splits=self.valid_splits,
                txn_date=date.today(),
            )
        self.assertEqual(t.id, None)
        self.assertEqual(t.txn_type, None)
        self.assertEqual(t.payee, None)
        self.assertEqual(t.description, None)

    def test_splits(self):
        t = bb.Transaction(
                splits={self.checking: {'amount': '-1'}, self.savings: {'amount': '1'}},
                txn_date=date.today(),
            )
        self.assertEqual(t.splits, {self.checking: {'amount': Fraction(-1)}, self.savings: {'amount': Fraction(1)}})

    def test_txn_payee(self):
        t = bb.Transaction(
                splits=self.valid_splits,
                txn_date=date.today(),
                payee='',
            )
        self.assertEqual(t.payee, None)
        t = bb.Transaction(
                splits=self.valid_splits,
                txn_date=date.today(),
                payee='Burgers',
            )
        self.assertEqual(t.payee.name, 'Burgers')

    def test_txn_from_user_info(self):
        #construct txn from user strings, as much as possible (except account & categories)
        t = bb.Transaction.from_user_info(
                account=self.checking,
                txn_type='1234',
                deposit='101',
                withdrawal='',
                txn_date='2017-10-15',
                description='something',
                payee=bb.Payee('payee 1'),
                status='C',
                categories=self.savings, #what to call this? it's the other accounts, the categories, ... (& many times, it's just one expense account)
            )
        self.assertEqual(t.splits, {
            self.checking: {'amount': 101, 'status': 'C'},
            self.savings: {'amount': -101},
        })

    def test_txn_status(self):
        t = bb.Transaction(
                splits={
                    self.checking: {'amount': '-101', 'status': 'c'},
                    self.savings: {'amount': '101'},
                },
                txn_date=date.today(),
            )
        self.assertEqual(t.splits[self.checking]['status'], 'C')
        t = bb.Transaction(
                splits={
                    self.checking: {'amount': '-101', 'status': ''},
                    self.savings: {'amount': '101'},
                },
                txn_date=date.today(),
            )
        self.assertEqual(t.splits[self.checking], {'amount': -101})
        with self.assertRaises(bb.InvalidTransactionError) as cm:
            bb.Transaction(
                    splits={
                        self.checking: {'amount': '-101', 'status': 'd'},
                        self.savings: {'amount': '101'},
                    },
                    txn_date=date.today(),
                )
        self.assertEqual(str(cm.exception), 'invalid status "d"')

    def test_txn_splits_from_user_info(self):
        #test passing in list, just one account, ...
        house = get_test_account(id_=3, name='House')
        splits = bb.Transaction.splits_from_user_info(
                account=self.checking,
                deposit='',
                withdrawal='100',
                input_categories={self.savings: {'amount': -45}, house: {'amount': -55}},
                status='R',
            )
        self.assertEqual(splits,
                {
                    self.checking: {'amount': '-100', 'status': 'R'},
                    self.savings: {'amount': -45},
                    house: {'amount': -55},
                }
            )

    def test_get_display_strings(self):
        t = bb.Transaction(
                splits={self.checking: {'amount': '-1.23', 'status': 'C'}, self.savings: {'amount': '1.23'}},
                txn_type='1234',
                txn_date=date.today(),
                description='something',
                payee=bb.Payee('asdf'),
            )
        self.assertDictEqual(
                bb.get_display_strings_for_ledger(account=self.checking, txn=t),
                {
                    'txn_type': '1234',
                    'withdrawal': '1.23',
                    'deposit': '',
                    'description': 'something',
                    'txn_date': str(date.today()),
                    'payee': 'asdf',
                    'status': 'C',
                    'categories': 'Savings',
                }
            )
        self.assertDictEqual(
                bb.get_display_strings_for_ledger(account=self.savings, txn=t),
                {
                    'txn_type': '1234',
                    'withdrawal': '',
                    'deposit': '1.23',
                    'description': 'something',
                    'txn_date': str(date.today()),
                    'payee': 'asdf',
                    'status': '',
                    'categories': 'Checking',
                }
            )

    def test_get_display_strings_sparse(self):
        t = bb.Transaction(
                splits=self.valid_splits,
                txn_date=date.today(),
            )
        self.assertDictEqual(bb.get_display_strings_for_ledger(account=self.checking, txn=t),
                {
                    'txn_type': '',
                    'withdrawal': '',
                    'deposit': '100',
                    'description': '',
                    'txn_date': str(date.today()),
                    'payee': '',
                    'status': '',
                    'categories': 'Savings',
                }
            )

    def test_txn_categories_display(self):
        a = get_test_account(id_=1)
        a2 = get_test_account(id_=2, name='Savings')
        a3 = get_test_account(id_=3, name='Other')
        t = bb.Transaction(
                splits={
                    a: {'amount': -100},
                    a2: {'amount': 65},
                    a3: {'amount': 35},
                },
                txn_date=date.today(),
            )
        self.assertEqual(bb._categories_display(t.splits, main_account=a), 'multiple')
        t = bb.Transaction(
                splits={
                    a: {'amount': -100},
                    a2: {'amount': 100},
                },
                txn_date=date.today(),
            )
        self.assertEqual(bb._categories_display(t.splits, main_account=a), 'Savings')


class TestLedger(unittest.TestCase):

    def setUp(self):
        self.checking = get_test_account(id_=1)
        self.savings = get_test_account(id_=2, name='Savings')

    def test_init(self):
        with self.assertRaises(bb.InvalidLedgerError) as cm:
            bb.Ledger()
        self.assertEqual(str(cm.exception), 'ledger must have an account')
        ledger = bb.Ledger(account=self.checking)
        self.assertEqual(ledger.account, self.checking)

    def test_add_transaction(self):
        ledger = bb.Ledger(account=self.checking)
        self.assertEqual(ledger._txns, {})
        splits = {self.checking: {'amount': 100}, self.savings: {'amount': -100}}
        txn = bb.Transaction(id_=1, splits=splits, txn_date=date.today())
        ledger.add_transaction(txn)
        self.assertEqual(ledger._txns, {1: txn})

    def test_add_scheduled_txn(self):
        ledger = bb.Ledger(account=self.checking)
        self.assertEqual(ledger._scheduled_txns, {})
        splits = {self.checking: {'amount': 100}, self.savings: {'amount': -100}}
        scheduled_txn = bb.ScheduledTransaction(
            id_=1,
            name='weekly',
            frequency=bb.ScheduledTransactionFrequency.WEEKLY,
            splits=splits,
            next_due_date=date.today()
        )
        ledger.add_scheduled_transaction(scheduled_txn)
        self.assertEqual(ledger._scheduled_txns,
            {1: scheduled_txn})

    def test_get_ledger_txns(self):
        ledger = bb.Ledger(account=self.checking)
        splits1 = {self.checking: {'amount': '32.45'}, self.savings: {'amount': '-32.45'}}
        splits2 = {self.checking: {'amount': -12}, self.savings: {'amount': 12}}
        splits3 = {self.checking: {'amount': 1}, self.savings: {'amount': -1}}
        splits4 = {self.checking: {'amount': 10}, self.savings: {'amount': -10}}
        ledger.add_transaction(bb.Transaction(id_=1, splits=splits1, txn_date=date(2017, 8, 5)))
        ledger.add_transaction(bb.Transaction(id_=2, splits=splits2, txn_date=date(2017, 6, 5)))
        ledger.add_transaction(bb.Transaction(id_=3, splits=splits3, txn_date=date(2017, 7, 30)))
        ledger.add_transaction(bb.Transaction(id_=4, splits=splits4, txn_date=date(2017, 4, 25)))
        ledger_records = ledger.get_sorted_txns_with_balance()
        self.assertEqual(ledger_records[0].txn_date, date(2017, 4, 25))
        self.assertEqual(ledger_records[0].balance, 10)
        self.assertEqual(ledger_records[1].txn_date, date(2017, 6, 5))
        self.assertEqual(ledger_records[1].balance, -2)
        self.assertEqual(ledger_records[2].txn_date, date(2017, 7, 30))
        self.assertEqual(ledger_records[2].balance, -1)
        self.assertEqual(ledger_records[3].txn_date, date(2017, 8, 5))
        self.assertEqual(ledger_records[3].balance, Fraction('31.45'))

        reversed_ledger_records = ledger.get_sorted_txns_with_balance(reverse=True)
        self.assertEqual(reversed_ledger_records[0].txn_date, date(2017, 8, 5))
        self.assertEqual(reversed_ledger_records[0].balance, Fraction('31.45'))
        self.assertEqual(reversed_ledger_records[3].txn_date, date(2017, 4, 25))
        self.assertEqual(reversed_ledger_records[3].balance, 10)

    def test_balances(self):
        ledger = bb.Ledger(account=self.checking)
        splits0 = {self.checking: {'amount': 50, 'status': bb.Transaction.RECONCILED}, self.savings: {'amount': '-50'}}
        splits1 = {self.checking: {'amount': '32.45', 'status': bb.Transaction.CLEARED}, self.savings: {'amount': '-32.45'}}
        splits2 = {self.checking: {'amount': -12}, self.savings: {'amount': 12}}
        splits3 = {self.checking: {'amount': 1}, self.savings: {'amount': -1}}
        splits4 = {self.checking: {'amount': 10}, self.savings: {'amount': -10}}
        ledger.add_transaction(bb.Transaction(id_=1, splits=splits0, txn_date=date(2017, 6, 24)))
        ledger.add_transaction(bb.Transaction(id_=2, splits=splits1, txn_date=date(2017, 8, 5)))
        ledger.add_transaction(bb.Transaction(id_=3, splits=splits2, txn_date=date(2017, 6, 5)))
        ledger.add_transaction(bb.Transaction(id_=4, splits=splits3, txn_date=date.today()+timedelta(days=3)))
        ledger.add_transaction(bb.Transaction(id_=5, splits=splits4, txn_date=date.today()+timedelta(days=5)))
        expected_balances = bb.LedgerBalances(current='70.45', current_cleared='82.45')
        self.assertEqual(ledger.get_current_balances_for_display(), expected_balances)

    def test_get_scheduled_txns_due(self):
        ledger = bb.Ledger(account=self.checking)
        splits = {self.checking: {'amount': 100}, self.savings: {'amount': -100}}
        not_due_txn = bb.ScheduledTransaction(
            id_=1,
            name='not due',
            frequency=bb.ScheduledTransactionFrequency.WEEKLY,
            splits=splits,
            next_due_date=date.today() + timedelta(days=1),
        )
        due_txn = bb.ScheduledTransaction(
            id_=2,
            name='due',
            frequency=bb.ScheduledTransactionFrequency.MONTHLY,
            splits=splits,
            next_due_date=date.today()
        )
        ledger.add_scheduled_transaction(not_due_txn)
        ledger.add_scheduled_transaction(due_txn)
        self.assertEqual(ledger.get_scheduled_transactions_due(),
            [due_txn])

    def test_search(self):
        ledger = bb.Ledger(account=self.checking)
        splits1 = {self.checking: {'amount': '32.45'}, self.savings: {'amount': '-32.45'}}
        splits2 = {self.checking: {'amount': -12}, self.savings: {'amount': 12}}
        splits3 = {self.checking: {'amount': 1}, self.savings: {'amount': -1}}
        splits4 = {self.checking: {'amount': 10}, self.savings: {'amount': -10}}
        ledger.add_transaction(bb.Transaction(id_=1, splits=splits1, payee=bb.Payee('someone'), txn_date=date(2017, 8, 5)))
        ledger.add_transaction(bb.Transaction(id_=2, splits=splits2, txn_date=date(2017, 6, 5)))
        ledger.add_transaction(bb.Transaction(id_=3, splits=splits3, description='Some description', txn_date=date(2017, 7, 30)))
        ledger.add_transaction(bb.Transaction(id_=4, splits=splits4, txn_date=date(2017, 4, 25)))
        results = ledger.search('some')
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].description, 'Some description')

    def test_get_txn(self):
        ledger = bb.Ledger(account=self.checking)
        splits1 = {self.checking: {'amount': '-32.45'}, self.savings: {'amount': '32.45'}}
        splits2 = {self.checking: {'amount': -12}, self.savings: {'amount': 12}}
        ledger.add_transaction(bb.Transaction(id_=1, splits=splits1, txn_date=date(2017, 8, 5)))
        ledger.add_transaction(bb.Transaction(id_=2, splits=splits2, txn_date=date(2017, 6, 5)))
        txn = ledger.get_txn(id_=2)
        self.assertEqual(txn.splits[self.checking]['amount'], -12)

    def test_clear_txns(self):
        ledger = bb.Ledger(account=self.checking)
        splits = {self.checking: {'amount': 100}, self.savings: {'amount': -100}}
        ledger.add_transaction(bb.Transaction(id_=1, splits=splits, txn_date=date(2017, 8, 5)))
        ledger.clear_txns()
        self.assertEqual(ledger.get_sorted_txns_with_balance(), [])

    def test_get_payees(self):
        ledger = bb.Ledger(account=self.checking)
        splits = {self.checking: {'amount': '12.34'}, self.savings: {'amount': '-12.34'}}
        burger_king = bb.Payee('Burger King', id_=1)
        mcdonalds = bb.Payee('McDonalds', id_=2)
        ledger.add_transaction(bb.Transaction(id_=1, splits=splits, txn_date=date(2017, 8, 5), payee=mcdonalds))
        ledger.add_transaction(bb.Transaction(id_=2, splits=splits, txn_date=date(2017, 8, 5), payee=burger_king))
        ledger.add_transaction(bb.Transaction(id_=3, splits=splits, txn_date=date(2017, 8, 5), payee=burger_king))
        self.assertEqual(ledger.get_payees(), [burger_king, mcdonalds])


class TestScheduledTransaction(unittest.TestCase):

    def setUp(self):
        self.checking = get_test_account(id_=1)
        self.savings = get_test_account(id_=2, name='Savings')
        self.valid_splits={
                self.checking: {'amount': -101},
                self.savings: {'amount': 101},
            }

    def test_invalid_frequency(self):
        with self.assertRaises(bb.InvalidScheduledTransactionError) as cm:
            bb.ScheduledTransaction(
                name='w',
                frequency=1,
                next_due_date='2019-01-01',
                splits=self.valid_splits,
            )
        self.assertEqual(str(cm.exception), 'invalid frequency "1"')

    def test_invalid_splits(self):
        with self.assertRaises(bb.InvalidTransactionError) as cm:
            bb.ScheduledTransaction(
                name='w',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-01',
                splits={},
            )
        self.assertEqual(str(cm.exception), 'transaction must have at least 2 splits')

    def test_invalid_next_due_date(self):
        with self.assertRaises(bb.InvalidScheduledTransactionError) as cm:
            bb.ScheduledTransaction(
                name='w',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='abcd',
                splits=self.valid_splits,
            )
        self.assertEqual(str(cm.exception), 'invalid date "abcd"')
        with self.assertRaises(bb.InvalidScheduledTransactionError) as cm:
            bb.ScheduledTransaction(
                name='w',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date=None,
                splits=self.valid_splits,
            )
        self.assertEqual(str(cm.exception), 'invalid date "None"')

    def test_init(self):
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=self.valid_splits,
                txn_type='a',
                payee='Wendys',
                description='something',
            )
        self.assertEqual(st.name, 'weekly 1')
        self.assertEqual(st.frequency, bb.ScheduledTransactionFrequency.WEEKLY)
        self.assertEqual(st.next_due_date, date(2019, 1, 2))
        self.assertEqual(st.splits, self.valid_splits)
        self.assertEqual(st.txn_type, 'a')
        self.assertEqual(st.payee, 'Wendys')
        self.assertEqual(st.description, 'something')

    def test_init_frequency(self):
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency='quarterly',
                next_due_date='2019-01-02',
                splits=self.valid_splits,
            )
        self.assertEqual(st.frequency, bb.ScheduledTransactionFrequency.QUARTERLY)

    def test_display_strings(self):
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=self.valid_splits,
                txn_type='a',
                payee=bb.Payee('Wendys'),
                description='something',
            )
        tds = bb.get_display_strings_for_ledger(account=self.checking, txn=st)

    def test_advance_to_next_due_date(self):
        #WEEKLY
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=self.valid_splits,
            )
        st.advance_to_next_due_date()
        self.assertEqual(st.next_due_date, date(2019, 1, 9))
        #MONTHLY
        st = bb.ScheduledTransaction(
                name='monthly 1',
                frequency=bb.ScheduledTransactionFrequency.MONTHLY,
                next_due_date='2019-01-02',
                splits=self.valid_splits,
            )
        st.advance_to_next_due_date()
        self.assertEqual(st.next_due_date, date(2019, 2, 2))
        #QUARTERLY
        st = bb.ScheduledTransaction(
                name='quarterly 1',
                frequency=bb.ScheduledTransactionFrequency.QUARTERLY,
                next_due_date='2019-01-02',
                splits=self.valid_splits,
            )
        st.advance_to_next_due_date()
        self.assertEqual(st.next_due_date, date(2019, 4, 2))
        #YEARLY
        st = bb.ScheduledTransaction(
                name='annually 1',
                frequency=bb.ScheduledTransactionFrequency.YEARLY,
                next_due_date='2018-01-02',
                splits=self.valid_splits,
            )
        st.advance_to_next_due_date()
        self.assertEqual(st.next_due_date, date(2019, 1, 2))


class TestBudget(unittest.TestCase):

    def test_init_dates(self):
        with self.assertRaises(bb.BudgetError) as cm:
            bb.Budget()
        self.assertEqual(str(cm.exception), 'must pass in dates')
        b = bb.Budget(year=2018, account_budget_info={})
        self.assertEqual(b.start_date, date(2018, 1, 1))
        self.assertEqual(b.end_date, date(2018, 12, 31))
        b = bb.Budget(year='2018', account_budget_info={})
        self.assertEqual(b.start_date, date(2018, 1, 1))
        b = bb.Budget(start_date=date(2018, 1, 15), end_date=date(2019, 1, 14), account_budget_info={})
        self.assertEqual(b.start_date, date(2018, 1, 15))
        self.assertEqual(b.end_date, date(2019, 1, 14))

    def test_init(self):
        housing = get_test_account(id_=1, type_=bb.AccountType.EXPENSE, name='Housing')
        food = get_test_account(id_=2, type_=bb.AccountType.EXPENSE, name='Food')
        transportation = get_test_account(id_=3, type_=bb.AccountType.EXPENSE, name='Transportation')
        rent = get_test_account(id_=4, type_=bb.AccountType.EXPENSE, name='Rent')
        account_budget_info = {
                housing: {'amount': 15, 'carryover': 5, 'notes': 'some important info'},
                food: {'amount': '35', 'carryover': '0'},
                transportation: {},
                rent: {'amount': 0, 'notes': ''},
            }
        b = bb.Budget(year=2018, account_budget_info=account_budget_info)
        self.maxDiff = None
        self.assertEqual(b.get_budget_data(), {
                    housing: {'amount': Fraction(15), 'carryover': Fraction(5), 'notes': 'some important info'},
                    food: {'amount': Fraction(35)},
                    transportation: {},
                    rent: {},
                })

    def test_sparse_init(self):
        b = bb.Budget(year=2018)
        self.assertEqual(b.start_date, date(2018, 1, 1))

    def test_percent_rounding(self):
        self.assertEqual(bb.Budget.round_percent_available(Decimal('1.1')), 1)
        self.assertEqual(bb.Budget.round_percent_available(Decimal('1.8')), 2)
        self.assertEqual(bb.Budget.round_percent_available(Decimal('1.5')), 2)
        self.assertEqual(bb.Budget.round_percent_available(Decimal('2.5')), 3)

    def test_get_report_display(self):
        housing = get_test_account(id_=1, type_=bb.AccountType.EXPENSE, name='Housing')
        food = get_test_account(id_=2, type_=bb.AccountType.EXPENSE, name='Food')
        transportation = get_test_account(id_=3, type_=bb.AccountType.EXPENSE, name='Transportation')
        something = get_test_account(id_=4, type_=bb.AccountType.EXPENSE, name='Something')
        wages = get_test_account(id_=5, type_=bb.AccountType.INCOME, name='Wages')
        interest = get_test_account(id_=6, type_=bb.AccountType.INCOME, name='Interest')
        account_budget_info = {
                housing: {'amount': 15, 'carryover': 5},
                food: {},
                transportation: {'amount': 10},
                something: {'amount': 0},
                wages: {'amount': 100, 'notes': 'note 1'},
                interest: {},
            }
        budget = bb.Budget(year=2018, account_budget_info=account_budget_info)
        with self.assertRaises(bb.BudgetError) as cm:
            budget.get_report_display()
        self.assertEqual(str(cm.exception), 'must pass in income_spending_info to get the report display')
        income_spending_info = {housing: {'income': 5, 'spent': 10}, food: {'income': ''}, wages: {'income': 80}}
        budget = bb.Budget(year=2018, account_budget_info=account_budget_info, income_spending_info=income_spending_info)
        budget_report = budget.get_report_display(current_date=date(2018, 7, 1))
        housing_info = budget_report['expense'][housing]
        self.assertEqual(housing_info['amount'], '15')
        self.assertEqual(housing_info['carryover'], '5')
        self.assertEqual(housing_info['income'], '5')
        self.assertEqual(housing_info['total_budget'], '25')
        self.assertEqual(housing_info['spent'], '10')
        self.assertEqual(housing_info['remaining'], '15')
        self.assertEqual(housing_info['percent_available'], '60%')
        self.assertEqual(housing_info['current_status'], '-10%')
        food_info = budget_report['expense'][food]
        self.assertEqual(food_info, {})
        transportation_info = budget_report['expense'][transportation]
        self.assertEqual(transportation_info,
                {
                    'amount': '10',
                    'total_budget': '10',
                    'remaining': '10',
                    'percent_available': '100%',
                    'current_status': '-50%',
                }
            )
        wages_info = budget_report['income'][wages]
        self.assertEqual(wages_info,
                {
                    'amount': '100',
                    'income': '80',
                    'remaining': '20',
                    'remaining_percent': '20%',
                    'notes': 'note 1',
                    'current_status': '+30%',
                }
            )
        self.assertEqual(budget_report['income'][interest], {})


TABLES = [('commodities',), ('institutions',), ('accounts',), ('budgets',), ('budget_values',), ('payees',), ('scheduled_transactions',), ('scheduled_transaction_splits',), ('transactions',), ('transaction_splits',), ('misc',)]


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
        storage = bb.SQLiteStorage(':memory:')
        tables = storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, TABLES)
        misc_table_records = storage._db_connection.execute('SELECT * FROM misc').fetchall()
        self.assertEqual(misc_table_records, [('schema_version', '0')])
        commodities_table_records = storage._db_connection.execute('SELECT * FROM commodities').fetchall()
        self.assertEqual(commodities_table_records, [(1, 'currency', 'USD', 'US Dollar')])

    def test_init_no_filename(self):
        with self.assertRaises(bb.SQLiteStorageError) as exc_cm:
            bb.SQLiteStorage('')
        with self.assertRaises(bb.SQLiteStorageError) as exc_cm:
            bb.SQLiteStorage(None)

    def test_init_file_doesnt_exist(self):
        storage = bb.SQLiteStorage(self.file_name)
        tables = storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, TABLES)

    def test_init_empty_file(self):
        with open(self.file_name, 'wb') as f:
            pass
        storage = bb.SQLiteStorage(self.file_name)
        tables = storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, TABLES)

    def test_init_db_already_setup(self):
        #set up file
        init_storage = bb.SQLiteStorage(self.file_name)
        tables = init_storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, TABLES)
        #and now open it again and make sure everything's fine
        storage = bb.SQLiteStorage(self.file_name)
        tables = init_storage._db_connection.execute('SELECT name from sqlite_master WHERE type="table"').fetchall()
        self.assertEqual(tables, TABLES)

    def test_save_account(self):
        storage = bb.SQLiteStorage(':memory:')
        assets = bb.Account(type_=bb.AccountType.ASSET, name='All Assets')
        storage.save_account(assets)
        checking = bb.Account(type_=bb.AccountType.ASSET, number='4010', name='Checking', parent=assets)
        storage.save_account(checking)
        #make sure we save the id to the account object
        self.assertEqual(assets.id, 1)
        self.assertEqual(checking.id, 2)
        c = storage._db_connection.cursor()
        c.execute('SELECT * FROM accounts WHERE id = ?', (checking.id,))
        db_info = c.fetchone()
        self.assertEqual(db_info,
                (checking.id, 'asset', 1, None, '4010', 'Checking', assets.id, None))
        savings = bb.Account(id_=checking.id, type_=bb.AccountType.ASSET, name='Savings')
        storage.save_account(savings)
        c.execute('SELECT * FROM accounts WHERE id = ?', (savings.id,))
        db_info = c.fetchall()
        self.assertEqual(db_info,
                [(savings.id, 'asset', 1, None, None, 'Savings', None, None)])

    def test_save_account_error_invalid_id(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = bb.Account(type_=bb.AccountType.ASSET, name='Checking', id_=1)
        #checking has an id, so it should already be in the DB...
        # it's not, so raise an exception
        with self.assertRaises(Exception) as cm:
            storage.save_account(checking)
        self.assertEqual(str(cm.exception), 'no account with id 1 to update')
        account_records = storage._db_connection.execute('SELECT * FROM accounts').fetchall()
        self.assertEqual(account_records, [])

    def test_save_account_parent_not_in_db(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = bb.Account(type_=bb.AccountType.ASSET, name='Checking', id_=9)
        checking_child = bb.Account(type_=bb.AccountType.ASSET, name='Checking Child', parent=checking)
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            storage.save_account(checking_child)
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')

    def test_cant_delete_parent_account(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = bb.Account(type_=bb.AccountType.ASSET, name='Checking', id_=9)
        checking_child = bb.Account(type_=bb.AccountType.ASSET, name='Checking Child', parent=checking)
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            storage.save_account(checking_child)
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')

    def test_cant_delete_account_with_txns(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = bb.Account(type_=bb.AccountType.ASSET, name='Checking')
        savings = bb.Account(type_=bb.AccountType.ASSET, name='Savings')
        storage.save_account(checking)
        storage.save_account(savings)
        txn = bb.Transaction(txn_date=date(2020,10,15), splits={checking: {'amount': 10}, savings: {'amount': -10}})
        storage.save_txn(txn)
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            storage._db_connection.execute('DELETE FROM accounts WHERE id=1')
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')

    def test_account_number_must_be_unique(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = bb.Account(type_=bb.AccountType.ASSET, number='4-1', name='Checking')
        checking2 = bb.Account(type_=bb.AccountType.ASSET, number='4-1', name='Checking')
        storage.save_account(checking)
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            storage.save_account(checking2)
        self.assertEqual(str(cm.exception), 'UNIQUE constraint failed: accounts.number')
        #make sure saving works once number is updated
        checking2 = bb.Account(type_=bb.AccountType.INCOME, number='5-1', name='Checking')
        storage.save_account(checking2)

    def test_account_name_and_parent_must_be_unique(self):
        storage = bb.SQLiteStorage(':memory:')
        bank_accounts = bb.Account(type_=bb.AccountType.ASSET, name='Bank Accounts')
        checking = bb.Account(type_=bb.AccountType.ASSET, name='Checking', parent=bank_accounts)
        storage.save_account(bank_accounts)
        storage.save_account(checking)
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            storage.save_account(
                    bb.Account(type_=bb.AccountType.ASSET, name='Checking', parent=bank_accounts)
                )
        self.assertEqual(str(cm.exception), 'UNIQUE constraint failed: accounts.name, accounts.parent_id')

    def test_account_institution_id_foreign_key(self):
        storage = bb.SQLiteStorage(':memory:')
        c = storage._db_connection.cursor()
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            c.execute('INSERT INTO accounts(type, commodity_id, institution_id, number, name) VALUES (?, ?, ?, ?, ?)', (bb.AccountType.EXPENSE.value, 1, 1, '4010', 'Checking'))
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')

    def test_get_account(self):
        storage = bb.SQLiteStorage(':memory:')
        c = storage._db_connection.cursor()
        c.execute('INSERT INTO accounts(type, commodity_id, number, name) VALUES (?, ?, ?, ?)', (bb.AccountType.EXPENSE.value, 1, '4010', 'Checking'))
        account_id = c.lastrowid
        c.execute('INSERT INTO accounts(type, commodity_id, name, parent_id) VALUES (?, ?, ?, ?)', (bb.AccountType.EXPENSE.value, 1, 'Sub-Checking', account_id))
        sub_checking_id = c.lastrowid
        account = storage.get_account(account_id)
        self.assertEqual(account.id, account_id)
        self.assertEqual(account.type, bb.AccountType.EXPENSE)
        self.assertEqual(account.number, '4010')
        self.assertEqual(account.name, 'Checking')
        self.assertEqual(account.parent, None)
        sub_checking = storage.get_account(sub_checking_id)
        self.assertEqual(sub_checking.parent, account)

    def test_get_accounts(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        savings = get_test_account(name='Savings')
        storage.save_account(savings)
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        accounts = storage.get_accounts()
        self.assertEqual(len(accounts), 3)
        self.assertEqual(accounts[0].name, 'Checking')
        self.assertEqual(accounts[1].name, 'Savings')
        self.assertEqual(accounts[2].name, 'Housing')
        accounts = storage.get_accounts(type_=bb.AccountType.EXPENSE)
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].name, 'Housing')

    def test_payee_unique(self):
        storage = bb.SQLiteStorage(':memory:')
        payee = bb.Payee('payee')
        storage.save_payee(payee)
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            storage.save_payee(bb.Payee('payee'))
        self.assertEqual(str(cm.exception), 'UNIQUE constraint failed: payees.name')

    def test_save_txn(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        storage.save_account(checking)
        storage.save_account(savings)
        chickfila = bb.Payee('Chick-fil-A')
        storage.save_payee(chickfila)
        t = bb.Transaction(
                splits={checking: {'amount': '-101', 'status': bb.Transaction.CLEARED}, savings: {'amount': 101}},
                txn_date=date.today(),
                txn_type='',
                payee=chickfila,
                description='chicken sandwich',
            )
        storage.save_txn(t)
        self.assertEqual(t.id, 1) #make sure we save the id to the txn object
        c = storage._db_connection.cursor()
        c.execute('SELECT * FROM transactions')
        db_info = c.fetchone()
        self.assertEqual(db_info,
                (1, 1, '', date.today().strftime('%Y-%m-%d'), 1, 'chicken sandwich', None))
        c.execute('SELECT id,txn_id,account_id,value,quantity,reconciled_state,description FROM transaction_splits')
        txn_split_records = c.fetchall()
        self.assertEqual(txn_split_records, [(1, 1, 1, '-101/1', '-101/1', 'C', None),
                                             (2, 1, 2, '101/1', '101/1', None, None)])

    def test_save_txn_payee_string(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        storage.save_account(checking)
        storage.save_account(savings)
        t = bb.Transaction(
                splits={checking: {'amount': '-101'}, savings: {'amount': 101}},
                txn_date=date.today(),
                payee='someone',
            )
        storage.save_txn(t)
        txn_from_db = storage.get_txn(t.id)
        self.assertEqual(txn_from_db.payee.name, 'someone')

    def test_save_transaction_error(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        storage.save_account(checking)
        storage.save_account(savings)
        t = bb.Transaction(
                splits={checking: {'amount': '-101'}, savings: {'amount': 101}},
                txn_date=date.today(),
                id_=1
            )
        #t has an id, so it should already be in the DB...
        # it's not, so raise an exception
        with self.assertRaises(Exception):
            storage.save_txn(t)
        c = storage._db_connection.cursor()
        c.execute('SELECT * FROM transactions')
        transaction_records = c.fetchall()
        self.assertEqual(transaction_records, [])
        c.execute('SELECT * FROM transaction_splits')
        txn_split_records = c.fetchall()
        self.assertEqual(txn_split_records, [])

    def test_save_transaction_payee_foreignkey_error(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        storage.save_account(checking)
        storage.save_account(savings)
        payee = bb.Payee('payee', id_=1)
        t = bb.Transaction(
                splits={checking: {'amount': '-101'}, savings: {'amount': 101}},
                txn_date=date.today(),
                payee=payee,
            )
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            storage.save_txn(t)
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')

    def test_save_sparse_txn(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        storage.save_account(checking)
        storage.save_account(savings)
        t = bb.Transaction(
                splits={checking: {'amount': '101'}, savings: {'amount': '-101'}},
                txn_date=date.today(),
            )
        storage.save_txn(t)
        c = storage._db_connection.cursor()
        c.execute('SELECT * FROM transactions')
        db_info = c.fetchone()
        self.assertEqual(db_info,
                (1, 1, None, date.today().strftime('%Y-%m-%d'), None, None, None))
        c.execute('SELECT * FROM transaction_splits')
        txn_split_records = c.fetchall()
        self.assertEqual(txn_split_records, [(1, 1, 1, '101/1', '101/1', None, None, None),
                                             (2, 1, 2, '-101/1', '-101/1', None, None, None)])

    def test_round_trip(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        savings = get_test_account(name='Savings')
        storage.save_account(savings)
        another_acct = get_test_account(name='Another')
        storage.save_account(another_acct)
        payee = bb.Payee('Some restaurant')
        storage.save_payee(payee)
        #create txn & save it
        t = bb.Transaction(
                splits={checking: {'amount': '-101', 'status': 'C'}, savings: {'amount': 101}},
                txn_date=date.today(),
                txn_type='123',
                payee=payee,
            )
        storage.save_txn(t)
        txn_id = t.id
        #verify db
        c = storage._db_connection.cursor()
        txn_db_info = c.execute('SELECT * FROM transactions').fetchall()
        self.assertEqual(txn_db_info,
                [(txn_id, 1, '123', date.today().strftime('%Y-%m-%d'), 1, None, None)])
        splits_db_info = c.execute('SELECT * FROM transaction_splits').fetchall()
        self.assertEqual(splits_db_info,
                [(1, txn_id, checking.id, '-101/1', '-101/1', 'C', None, None),
                 (2, txn_id, savings.id, '101/1', '101/1', None, None, None)])
        #update a db field that the Transaction object isn't aware of
        c.execute('UPDATE transaction_splits SET action = ? WHERE account_id = ?', ('buy', checking.id))
        storage._db_connection.commit()
        splits_db_info = c.execute('SELECT * FROM transaction_splits').fetchall()
        self.assertEqual(splits_db_info,
                [(1, txn_id, checking.id, '-101/1', '-101/1', 'C', None, 'buy'),
                 (2, txn_id, savings.id, '101/1', '101/1', None, None, None)])
        #read it back from the db
        txn_from_db = storage.get_txn(txn_id)
        self.assertEqual(txn_from_db.txn_type, '123')
        self.assertEqual(txn_from_db.payee, payee)
        self.assertEqual(txn_from_db.splits[checking], {'amount': -101, 'status': 'C'})
        #update it & save again
        splits = {
                checking: {'amount': '-101'},
                another_acct: {'amount': '101'},
            }
        updated_txn = bb.Transaction(
                splits=splits,
                txn_date=date.today(),
                id_=txn_id,
            )
        storage.save_txn(updated_txn)
        c = storage._db_connection.cursor()
        c.execute('SELECT * FROM transactions')
        db_info = c.fetchall()
        self.assertEqual(db_info,
                [(txn_id, 1, None, date.today().strftime('%Y-%m-%d'), None, None, None)])
        splits_db_info = c.execute('SELECT * FROM transaction_splits').fetchall()
        self.assertEqual(splits_db_info,
                [(1, txn_id, checking.id, '-101/1', '-101/1', None, None, 'buy'),
                 (2, txn_id, another_acct.id, '101/1', '101/1', None, None, None)])

    def test_get_ledger(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        savings = get_test_account(name='Savings')
        storage.save_account(savings)
        savings2 = get_test_account(name='Savings 2')
        storage.save_account(savings2)
        pizza_hut = bb.Payee('Pizza Hut')
        storage.save_payee(pizza_hut)
        subway = bb.Payee('Subway')
        storage.save_payee(subway)
        wendys = bb.Payee('Wendys')
        storage.save_payee(wendys)
        txn1 = bb.Transaction(txn_type='BP', txn_date=date(2017, 1, 25), payee=pizza_hut, description='inv #1', splits={checking: {'amount': '101'}, savings: {'amount': '-101'}})
        storage.save_txn(txn1)
        txn2 = bb.Transaction(txn_type='BP', txn_date=date(2017, 1, 28), payee=subway, description='inv #42', splits={checking: {'amount': '46.23'}, savings: {'amount': '-46.23'}})
        storage.save_txn(txn2)
        txn3 = bb.Transaction(txn_type='BP', txn_date=date(2017, 1, 28), payee=subway, description='inv #42', splits={savings2: {'amount': '-6.53'}, savings: {'amount': '6.53'}})
        storage.save_txn(txn3)
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits={checking: {'amount': -1}, savings: {'amount': 1}},
                txn_type='a',
                payee=wendys,
                description='something',
            )
        storage.save_scheduled_transaction(st)
        st2 = bb.ScheduledTransaction(
                name='weekly 2',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits={savings: {'amount': -1}, savings2: {'amount': 1}},
                txn_type='a',
                payee=wendys,
                description='something',
            )
        storage.save_scheduled_transaction(st2)
        ledger = storage.get_ledger(account=checking)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(len(txns), 2)
        self.assertEqual(txns[0].splits[checking]['amount'], 101)
        self.assertEqual(txns[1].splits[checking]['amount'], Fraction('46.23'))
        scheduled_txns_due = ledger.get_scheduled_transactions_due()
        self.assertEqual(len(scheduled_txns_due), 1)
        self.assertEqual(scheduled_txns_due[0].id, st.id)
        ledger_by_id = storage.get_ledger(account=checking.id)
        self.assertEqual(len(txns), 2)

    def test_delete_txn_from_db(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        savings = get_test_account(name='Savings')
        storage.save_account(savings)
        payee = bb.Payee('Waffle House')
        subway_payee = bb.Payee('Subway')
        storage.save_payee(payee)
        storage.save_payee(subway_payee)
        txn = bb.Transaction(txn_type='BP', txn_date=date(2017, 1, 25), payee=payee,
                splits={checking: {'amount': '101'}, savings: {'amount': '-101'}})
        storage.save_txn(txn)
        txn2 = bb.Transaction(txn_date=date(2017, 1, 28), payee=subway_payee,
                splits={checking: {'amount': '46.23'}, savings: {'amount': '-46.23'}})
        storage.save_txn(txn2)
        storage.delete_txn(txn.id)
        c = storage._db_connection.cursor()
        c.execute('SELECT date FROM transactions')
        txn_records = c.fetchall()
        self.assertEqual(len(txn_records), 1)
        self.assertEqual(txn_records[0][0], '2017-01-28')
        txn_splits_records = c.execute('SELECT txn_id FROM transaction_splits').fetchall()
        self.assertEqual(len(txn_splits_records), 2)
        self.assertEqual([r[0] for r in txn_splits_records], [txn2.id, txn2.id])

    def test_save_budget(self):
        storage = bb.SQLiteStorage(':memory:')
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        account_budget_info = {
                housing: {'amount': '15.34', 'carryover': '0.34', 'notes': 'hello'},
                food: {'amount': 25, 'carryover': 0}
            }
        b = bb.Budget(year=2018, account_budget_info=account_budget_info)
        storage.save_budget(b)
        cursor = storage._db_connection.cursor()
        records = cursor.execute('SELECT * FROM budgets WHERE start_date = "2018-01-01"').fetchall()
        self.assertEqual(len(records), 1)
        self.assertEqual(b.id, 1)
        records = cursor.execute('SELECT * FROM budget_values').fetchall()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0][1], 1)
        self.assertEqual(records[0][2], 1)
        self.assertEqual(records[0][3], '767/50')
        self.assertEqual(records[0][4], '17/50')
        self.assertEqual(records[0][5], 'hello')
        self.assertEqual(records[1][1], 1)
        self.assertEqual(records[1][2], 2)
        self.assertEqual(records[1][3], '25')
        self.assertEqual(records[1][4], '')
        #test that old budget values are deleted
        b = bb.Budget(start_date='2018-01-01', end_date='2018-12-24', account_budget_info={
                housing: {'amount': 35, 'carryover': 0},
                food: {'amount': 45, 'carryover': 0},
            }, id_=b.id)
        storage.save_budget(b)
        records = cursor.execute('SELECT * FROM budgets').fetchall()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0], (1, None, '2018-01-01', '2018-12-24'))
        records = cursor.execute('SELECT amount FROM budget_values ORDER BY amount').fetchall()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0][0], '35')

    def test_save_budget_empty_category_info(self):
        storage = bb.SQLiteStorage(':memory:')
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        account_budget_info = {
                housing: {'amount': 15, 'carryover': 0},
                food: {},
            }
        b = bb.Budget(year=2018, account_budget_info=account_budget_info)
        storage.save_budget(b)
        cursor = storage._db_connection.cursor()
        records = cursor.execute('SELECT * FROM budgets').fetchall()
        self.assertEqual(len(records), 1)
        records = cursor.execute('SELECT amount FROM budget_values ORDER BY amount').fetchall()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][0], '15')

    def test_save_budget_sparse(self):
        storage = bb.SQLiteStorage(':memory:')
        b = bb.Budget(year=2018)
        storage.save_budget(b)
        cursor = storage._db_connection.cursor()
        records = cursor.execute('SELECT * FROM budgets').fetchall()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][2], '2018-01-01')
        records = cursor.execute('SELECT * FROM budget_values').fetchall()
        self.assertEqual(records, [])

    def test_save_budget_file(self):
        #test that save actually gets committed
        storage = bb.SQLiteStorage(self.file_name)
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        b = bb.Budget(year=2018, account_budget_info={
            housing: {'amount': 15, 'carryover': 0},
            food: {'amount': 25, 'carryover': 0},
        })
        storage.save_budget(b)
        storage = bb.SQLiteStorage(self.file_name)
        cursor = storage._db_connection.cursor()
        records = cursor.execute('SELECT * FROM budgets WHERE start_date = "2018-01-01"').fetchall()
        self.assertEqual(len(records), 1)

    def test_save_budget_account_foreignkey_error(self):
        storage = bb.SQLiteStorage(':memory:')
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food', id_=5)
        account_budget_info = {
                housing: {'amount': '15.34', 'carryover': '0.34', 'notes': 'hello'},
                food: {'amount': 25, 'carryover': 0}
            }
        b = bb.Budget(year=2018, account_budget_info=account_budget_info)
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            storage.save_budget(b)
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')

    def test_get_budget(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        savings = get_test_account(name='Savings')
        storage.save_account(savings)
        wages = get_test_account(name='Wages', type_=bb.AccountType.INCOME)
        storage.save_account(wages)
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        transportation = get_test_account(type_=bb.AccountType.EXPENSE, name='Transportation')
        storage.save_account(transportation)
        txn1 = bb.Transaction(txn_date=date(2018, 1, 25),
                splits={checking: {'amount': '-101'}, housing: {'amount': '101'}})
        txn2 = bb.Transaction(txn_date=date(2018, 2, 28),
                splits={checking: {'amount': '-46.23'}, food: {'amount': '46.23'}})
        txn3 = bb.Transaction(txn_date=date(2018, 3, 28),
                splits={savings: {'amount': '-56.23'}, food: {'amount': '56.23'}})
        txn4 = bb.Transaction(txn_date=date(2018, 4, 28),
                splits={checking: {'amount': '-15'}, savings: {'amount': 15}})
        txn5 = bb.Transaction(txn_date=date(2018, 5, 28),
                splits={checking: {'amount': 15}, food: {'amount': '-15'}})
        txn6 = bb.Transaction(txn_date=date(2017, 1, 26),
                splits={checking: {'amount': '-108'}, housing: {'amount': '108'}})
        txn7 = bb.Transaction(txn_date=date(2018, 2, 5),
                splits={checking: {'amount': '100'}, wages: {'amount': '-100'}})
        for t in [txn1, txn2, txn3, txn4, txn5, txn6, txn7]:
            storage.save_txn(t)
        cursor = storage._db_connection.cursor()
        cursor.execute('INSERT INTO budgets (start_date, end_date) VALUES (?, ?)', ('2018-01-01', '2018-12-31'))
        budget_id = cursor.lastrowid
        cursor.execute('INSERT INTO budget_values (budget_id, account_id, amount, notes) VALUES (?, ?, ?, ?)', (budget_id, housing.id, '135/1', 'hello'))
        cursor.execute('INSERT INTO budget_values (budget_id, account_id, amount, carryover) VALUES (?, ?, ?, ?)', (budget_id, food.id, '70/1', '15'))
        cursor.execute('INSERT INTO budget_values (budget_id, account_id, amount, carryover) VALUES (?, ?, ?, ?)', (budget_id, wages.id, '70/1', None))
        budget = storage.get_budget(budget_id)
        self.assertEqual(budget.id, budget_id)
        self.assertEqual(budget.start_date, date(2018, 1, 1))
        self.assertEqual(budget.end_date, date(2018, 12, 31))

        budget_data = budget.get_budget_data()
        self.assertEqual(budget_data[housing], {'amount': Fraction(135), 'notes': 'hello'})
        self.assertEqual(type(budget_data[housing]['amount']), Fraction)
        self.assertEqual(budget_data[wages], {'amount': Fraction(70)})

        report_display = budget.get_report_display()['expense']
        self.assertEqual(report_display[housing]['amount'], '135')
        self.assertEqual(report_display[housing]['spent'], '101')
        self.assertEqual(report_display[housing]['notes'], 'hello')

        self.assertEqual(report_display[food]['amount'], '70')
        self.assertEqual(report_display[food]['carryover'], '15')
        self.assertEqual(report_display[food]['income'], '15')
        self.assertEqual(report_display[food]['spent'], '102.46')

        self.assertEqual(report_display[transportation], {})

    def test_get_budgets(self):
        storage = bb.SQLiteStorage(':memory:')
        b = bb.Budget(year=2018)
        storage.save_budget(b)
        b2 = bb.Budget(year=2019)
        storage.save_budget(b2)
        budgets = storage.get_budgets()
        self.assertEqual(budgets[0].start_date, date(2019, 1, 1))
        self.assertEqual(budgets[1].start_date, date(2018, 1, 1))

    def test_get_budget_reports(self):
        storage = bb.SQLiteStorage(':memory:')
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        cursor = storage._db_connection.cursor()
        cursor.execute('INSERT INTO budgets (start_date, end_date) VALUES (?, ?)', ('2018-01-01', '2018-12-31'))
        budget_id = cursor.lastrowid
        cursor.execute('INSERT INTO budget_values (budget_id, account_id, amount) VALUES (?, ?, ?)', (budget_id, housing.id, '35'))
        cursor.execute('INSERT INTO budget_values (budget_id, account_id, amount) VALUES (?, ?, ?)', (budget_id, food.id, '70'))
        budgets = storage.get_budgets()
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets[0].start_date, date(2018, 1, 1))
        self.assertEqual(budgets[0].end_date, date(2018, 12, 31))
        expense_account = list(budgets[0].get_report_display()['expense'].keys())[0]
        self.assertEqual(expense_account.name, 'Housing')

    def test_save_scheduled_txn(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        storage.save_account(checking)
        storage.save_account(savings)
        wendys = bb.Payee('Wendys')
        storage.save_payee(wendys)
        valid_splits={
                checking: {'amount': -101, 'status': 'R'},
                savings: {'amount': 101},
            }
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
                txn_type='a',
                payee=wendys,
                description='something',
            )
        storage.save_scheduled_transaction(st)
        self.assertEqual(st.id, 1)
        st_records = storage._db_connection.execute('SELECT * FROM scheduled_transactions').fetchall()
        self.assertEqual(len(st_records), 1)
        self.assertEqual(st_records[0],
                (1, 'weekly 1', bb.ScheduledTransactionFrequency.WEEKLY.value, '2019-01-02', 'a', 1, 'something'))
        st_split_records = storage._db_connection.execute('SELECT scheduled_txn_id,account_id,value,quantity,reconciled_state FROM scheduled_transaction_splits').fetchall()
        self.assertEqual(len(st_split_records), 2)
        self.assertEqual(st_split_records[0], (st.id, checking.id, '-101/1', '-101/1', 'R'))
        self.assertEqual(st_split_records[1], (st.id, savings.id, '101/1', '101/1', None))

    def test_save_scheduled_transaction_error(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        storage.save_account(checking)
        storage.save_account(savings)
        valid_splits={
                checking: {'amount': -101},
                savings: {'amount': 101},
            }
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
                id_=1
            )
        #st has an id, so it should already be in the DB...
        # it's not, so raise an exception
        with self.assertRaises(Exception):
            storage.save_scheduled_transaction(st)
        c = storage._db_connection.cursor()
        c.execute('SELECT * FROM scheduled_transactions')
        scheduled_transaction_records = c.fetchall()
        self.assertEqual(scheduled_transaction_records, [])
        c.execute('SELECT * FROM scheduled_transaction_splits')
        scheduled_txn_split_records = c.fetchall()
        self.assertEqual(scheduled_txn_split_records, [])

    def test_save_scheduled_txn_account_foreignkey_error(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings', id_=2)
        storage.save_account(checking)
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits={
                    checking: {'amount': -101},
                    savings: {'amount': 101},
                }
            )
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            storage.save_scheduled_transaction(st)
        self.assertEqual(str(cm.exception), 'FOREIGN KEY constraint failed')

    def test_update_scheduled_txn(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        another_acct = get_test_account(name='Another')
        storage.save_account(checking)
        storage.save_account(savings)
        storage.save_account(another_acct)
        wendys = bb.Payee('Wendys')
        storage.save_payee(wendys)
        valid_splits={
                checking: {'amount': -101},
                savings: {'amount': 101},
            }
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
                txn_type='a',
                payee=wendys,
                description='something',
            )
        storage.save_scheduled_transaction(st)
        st_id = st.id
        #update due date & save
        st.next_due_date = date(2019, 1, 9)
        storage.save_scheduled_transaction(st)
        st_records = storage._db_connection.execute('SELECT * FROM scheduled_transactions').fetchall()
        self.assertEqual(len(st_records), 1)
        retrieved_scheduled_txn = storage.get_scheduled_transaction(st_id)
        self.assertEqual(retrieved_scheduled_txn.next_due_date, date(2019, 1, 9))
        #now create a ScheduledTransaction object for the same record
        new_st = bb.ScheduledTransaction(
                name='monthly 1 updated',
                frequency=bb.ScheduledTransactionFrequency.MONTHLY,
                next_due_date=date(2019, 1, 16),
                splits={
                    checking: {'amount': -101},
                    another_acct: {'amount': 101},
                },
                id_=st_id
            )
        storage.save_scheduled_transaction(new_st)
        st_records = storage._db_connection.execute('SELECT * FROM scheduled_transactions').fetchall()
        self.assertEqual(len(st_records), 1)
        retrieved_scheduled_txn = storage.get_scheduled_transaction(st_id)
        self.assertEqual(retrieved_scheduled_txn.next_due_date, date(2019, 1, 16))
        split_records = storage._db_connection.execute('SELECT * FROM scheduled_transaction_splits').fetchall()
        self.assertEqual(split_records,
                [(1, st_id, checking.id, '-101/1', '-101/1', None, None),
                 (2, st_id, another_acct.id, '101/1', '101/1', None, None)])

    def test_get_scheduled_transaction(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        storage.save_account(checking)
        storage.save_account(savings)
        wendys = bb.Payee('Wendys')
        storage.save_payee(wendys)
        valid_splits={
                checking: {'amount': -101, 'status': bb.Transaction.CLEARED},
                savings: {'amount': 101},
            }
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
                txn_type='a',
                payee=wendys,
                description='something',
                status='C',
            )
        storage.save_scheduled_transaction(st)
        scheduled_txn = storage.get_scheduled_transaction(st.id)
        self.assertEqual(scheduled_txn.name, 'weekly 1')
        self.assertEqual(scheduled_txn.frequency, bb.ScheduledTransactionFrequency.WEEKLY)
        self.assertEqual(scheduled_txn.next_due_date, date(2019, 1, 2))
        self.assertEqual(scheduled_txn.txn_type, 'a')
        self.assertEqual(scheduled_txn.payee.name, 'Wendys')
        self.assertEqual(scheduled_txn.description, 'something')
        self.assertEqual(scheduled_txn.splits, valid_splits)

    def test_get_scheduled_transaction_sparse(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        storage.save_account(checking)
        storage.save_account(savings)
        valid_splits={
                checking: {'amount': -101},
                savings: {'amount': 101},
            }
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
            )
        storage.save_scheduled_transaction(st)
        scheduled_txn = storage.get_scheduled_transaction(st.id)
        self.assertEqual(scheduled_txn.next_due_date, date(2019, 1, 2))


class TestCLI(unittest.TestCase):

    ACCOUNT_FORM_OUTPUT = '  name:   type (asset,liability,equity,income,expense):   number:   parent account id: '

    def setUp(self):
        #https://realpython.com/python-print/#mocking-python-print-in-unit-tests
        self.memory_buffer = io.StringIO()
        self.cli = bb.CLI(':memory:', print_file=self.memory_buffer)

    @patch('builtins.input')
    def test_run(self, input_mock):
        checking = get_test_account(name='Checking account')
        self.cli.storage.save_account(checking)
        input_mock.side_effect = ['h', 'a', 'q']
        self.cli.run()
        self.assertTrue('| Checking account' in self.memory_buffer.getvalue())

    def test_list_accounts(self):
        checking = get_test_account(name='Checking account with long name cut off')
        self.cli.storage.save_account(checking)
        self.cli._list_accounts()
        output = '%s\n' % bb.CLI.ACCOUNT_LIST_HEADER
        output += ' 1    | ASSET       |         | Checking account with long nam |                               \n'
        self.assertEqual(self.memory_buffer.getvalue(), output)

    @patch('builtins.input')
    def test_create_account(self, input_mock):
        savings = get_test_account(name='Savings')
        self.cli.storage.save_account(savings)
        input_mock.side_effect = ['Checking', 'asset', '400', str(savings.id)]
        self.cli._create_account()
        accounts = self.cli.storage.get_accounts()
        self.assertEqual(accounts[1].name, 'Checking')
        self.assertEqual(accounts[1].type, bb.AccountType.ASSET)
        self.assertEqual(accounts[1].parent, savings)
        output = 'Create Account:\n%s' % self.ACCOUNT_FORM_OUTPUT
        self.assertEqual(self.memory_buffer.getvalue(), output)

    @patch('builtins.input')
    def test_edit_account(self, input_mock):
        input_mock.side_effect = ['1', 'Checking updated', 'asset', '400', '2']
        checking = get_test_account()
        self.cli.storage.save_account(checking)
        savings = get_test_account(name='Savings')
        self.cli.storage.save_account(savings)
        self.cli._edit_account()
        accounts = self.cli.storage.get_accounts()
        self.assertEqual(accounts[0].name, 'Checking updated')
        self.assertEqual(accounts[0].type, bb.AccountType.ASSET)
        self.assertEqual(accounts[0].number, '400')
        self.assertEqual(accounts[0].parent, savings)
        output = 'Account ID: %s' % self.ACCOUNT_FORM_OUTPUT
        self.assertEqual(self.memory_buffer.getvalue(), output)

    @patch('builtins.input')
    def test_list_account_txns(self, input_mock):
        self.maxDiff = None
        input_mock.return_value = '1'
        checking = get_test_account()
        self.cli.storage.save_account(checking)
        savings = get_test_account(name='Savings')
        self.cli.storage.save_account(savings)
        txn = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date(2017, 1, 1), txn_type='ACH', payee='some payee', description='description')
        txn2 = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date(2017, 1, 2), payee='payee 2')
        self.cli.storage.save_txn(txn)
        self.cli.storage.save_txn(txn2)
        self.cli.storage.save_scheduled_transaction(
                bb.ScheduledTransaction(
                    name='scheduled txn',
                    frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                    next_due_date=date(2019, 1, 13),
                    splits={checking: {'amount': 14}, savings: {'amount': -14}},
                )
            )
        self.cli._list_account_txns()
        txn1_output = ' 1    | 2017-01-01 | ACH    | description                    | some payee                     | Savings                        |            | 5          | 5         \n'
        txn2_output = ' 2    | 2017-01-02 |        |                                | payee 2                        | Savings                        |            | 5          | 10        \n'
        printed_output = self.memory_buffer.getvalue()
        self.assertTrue('Account ID: Checking (Current balance: 10; Cleared: 0)' in printed_output)
        self.assertTrue('scheduled txn' in printed_output)
        self.assertTrue(bb.CLI.TXN_LIST_HEADER in printed_output)
        self.assertTrue(txn1_output in printed_output)
        self.assertTrue(txn2_output in printed_output)

    @patch('builtins.input')
    def test_list_account_txns_paged(self, input_mock):
        input_mock.return_value = '1'
        checking = get_test_account()
        self.cli.storage.save_account(checking)
        savings = get_test_account(name='Savings')
        self.cli.storage.save_account(savings)
        txn = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date(2017, 1, 1), txn_type='ACH', payee='some payee', description='description')
        txn2 = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date(2017, 1, 2), payee='payee 2')
        self.cli.storage.save_txn(txn)
        self.cli.storage.save_txn(txn2)
        self.cli._list_account_txns(num_txns_in_page=1)
        printed_output = self.memory_buffer.getvalue()
        self.assertTrue('(n)ext page' in printed_output)

    def test_pager(self):
        self.assertEqual(bb.pager([1, 2, 3], num_txns_in_page=1, page=1), ([1], True))
        self.assertEqual(bb.pager([1, 2, 3], num_txns_in_page=1, page=3), ([3], False))
        self.assertEqual(bb.pager([1, 2, 3, 4, 5], num_txns_in_page=2, page=3), ([5], False))
        self.assertEqual(bb.pager([1, 2, 3, 4, 5], num_txns_in_page=2, page=2), ([3, 4], True))
        self.assertEqual(bb.pager([1, 2, 3, 4], num_txns_in_page=2, page=2), ([3, 4], False))

    @patch('builtins.input')
    def test_create_txn(self, input_mock):
        checking = get_test_account()
        self.cli.storage.save_account(checking)
        savings = get_test_account(name='Savings')
        self.cli.storage.save_account(savings)
        payee = bb.Payee(name='payee 1')
        self.cli.storage.save_payee(payee)
        input_mock.side_effect = ['2019-02-24', '1', '-15', 'C', '2', '15', '', '',
                'type 1', str(payee.id), 'description']
        self.cli._create_txn()
        ledger = self.cli.storage.get_ledger(1)
        txn = ledger.get_sorted_txns_with_balance()[0]
        self.assertEqual(txn.txn_date, date(2019, 2, 24))
        self.assertEqual(txn.splits[checking], {'amount': -15, 'status': 'C'})
        self.assertEqual(txn.splits[savings], {'amount': 15})
        self.assertEqual(txn.txn_type, 'type 1')
        self.assertEqual(txn.payee, payee)
        self.assertEqual(txn.description, 'description')
        output = 'Create Transaction:\n  date: Splits:\nnew account ID:  amount: new account ID:  amount: new account ID:   type:   payee (id or \'name):   description:   status: '
        buffer_value = self.memory_buffer.getvalue()
        self.assertTrue('Create Transaction:\n' in buffer_value)

    @patch('builtins.input')
    def test_create_txn_new_payee(self, input_mock):
        checking = get_test_account()
        self.cli.storage.save_account(checking)
        savings = get_test_account(name='Savings')
        self.cli.storage.save_account(savings)
        input_mock.side_effect = ['2019-02-24', '1', '-15', '', '2', '15', '', '',
                'type 1', "'payee 1", 'description']
        self.cli._create_txn()
        ledger = self.cli.storage.get_ledger(1)
        txn = ledger.get_sorted_txns_with_balance()[0]
        self.assertEqual(txn.payee.name, 'payee 1')

    @patch('builtins.input')
    def test_create_txn_existing_payee_by_name(self, input_mock):
        '''make sure the user can enter the payee's name, even if the payee is already
        in the DB'''
        checking = get_test_account()
        self.cli.storage.save_account(checking)
        savings = get_test_account(name='Savings')
        self.cli.storage.save_account(savings)
        payee = bb.Payee(name='payee 1')
        self.cli.storage.save_payee(payee)
        input_mock.side_effect = ['2019-02-24', '1', '-15', '', '2', '15', '', '',
                'type 1', "'payee 1", 'description']
        self.cli._create_txn()
        ledger = self.cli.storage.get_ledger(1)
        txn = ledger.get_sorted_txns_with_balance()[0]
        self.assertEqual(txn.payee.name, 'payee 1')

    @patch('builtins.input')
    def test_create_txn_list_payees(self, input_mock):
        '''make sure user can list payees if desired'''
        checking = get_test_account()
        self.cli.storage.save_account(checking)
        savings = get_test_account(name='Savings')
        self.cli.storage.save_account(savings)
        payee = bb.Payee(name='payee 1')
        self.cli.storage.save_payee(payee)
        input_mock.side_effect = ['2019-02-24', '1', '-15', '', '2', '15', '', '',
                'type 1', 'p', "'payee 1", 'description']
        self.cli._create_txn()
        buffer_value = self.memory_buffer.getvalue()
        self.assertTrue('1: payee 1' in buffer_value)

    @patch('builtins.input')
    def test_edit_txn(self, input_mock):
        input_mock.side_effect = ['1', '2017-02-13', '-90', '', '50', '', '3', '40', '', '',
                '', '', 'new description']
        checking = get_test_account()
        self.cli.storage.save_account(checking)
        savings = get_test_account(name='Savings')
        self.cli.storage.save_account(savings)
        another_account = get_test_account(name='Another')
        self.cli.storage.save_account(another_account)
        txn = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date(2017, 1, 1))
        self.cli.storage.save_txn(txn)
        self.cli._edit_txn()
        ledger = self.cli.storage.get_ledger(1)
        edited_txn = ledger.get_txn(id_=txn.id)
        self.assertEqual(edited_txn.txn_date, date(2017, 2, 13))
        self.assertEqual(edited_txn.splits[checking], {'amount': -90})
        self.assertEqual(edited_txn.splits[savings], {'amount': 50})
        self.assertEqual(edited_txn.splits[another_account], {'amount': 40})
        self.assertEqual(edited_txn.description, 'new description')
        buffer_value = self.memory_buffer.getvalue()
        self.assertTrue('Checking amount' in buffer_value)
        self.assertTrue('Savings amount' in buffer_value)

    @patch('builtins.input')
    def test_list_scheduled_txns(self, input_mock):
        input_mock.side_effect = ['', '']
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.cli.storage.save_account(checking)
        self.cli.storage.save_account(savings)
        valid_splits={
                checking: {'amount': -101},
                savings: {'amount': 101},
            }
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
            )
        self.cli.storage.save_scheduled_transaction(st)
        self.cli._list_scheduled_txns()
        output = '1: weekly 1'
        buffer_value = self.memory_buffer.getvalue()
        self.assertTrue(buffer_value.startswith(output))

    @patch('builtins.input')
    def test_display_scheduled_txn(self, input_mock):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.cli.storage.save_account(checking)
        self.cli.storage.save_account(savings)
        valid_splits={
                checking: {'amount': -101},
                savings: {'amount': 101},
            }
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
            )
        self.cli.storage.save_scheduled_transaction(st)
        input_mock.side_effect = [str(st.id)]
        self.cli._display_scheduled_txn()
        buffer_value = self.memory_buffer.getvalue()
        self.assertTrue('2019-01-02' in buffer_value)

    @patch('builtins.input')
    def test_enter_scheduled_txn(self, input_mock):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.cli.storage.save_account(checking)
        self.cli.storage.save_account(savings)
        valid_splits={
             checking: {'amount': -101},
             savings: {'amount': 101},
        }
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
            )
        self.cli.storage.save_scheduled_transaction(st)
        input_mock.side_effect = [str(st.id), '2019-01-02', '-101', '', '101', '', '', '', '', '', '', '', '']
        self.cli._list_scheduled_txns()
        ledger = self.cli.storage.get_ledger(checking.id)
        txn = ledger.get_sorted_txns_with_balance()[0]
        self.assertEqual(txn.splits, valid_splits)
        self.assertEqual(txn.txn_date, date(2019, 1, 2))
        scheduled_txn = self.cli.storage.get_scheduled_transaction(st.id)
        self.assertEqual(scheduled_txn.next_due_date, date(2019, 1, 9))

    @patch('builtins.input')
    def test_skip_scheduled_txn(self, input_mock):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.cli.storage.save_account(checking)
        self.cli.storage.save_account(savings)
        valid_splits={
                checking: {'amount': -101},
                savings: {'amount': 101},
            }
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
            )
        self.cli.storage.save_scheduled_transaction(st)
        input_mock.side_effect = ['', str(st.id), '']
        self.cli._list_scheduled_txns()
        scheduled_txn = self.cli.storage.get_scheduled_transaction(st.id)
        self.assertEqual(scheduled_txn.next_due_date, date(2019, 1, 9))
        ledger = self.cli.storage.get_ledger(checking.id)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(txns, [])

    @patch('builtins.input')
    def test_create_scheduled_txn(self, input_mock):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.cli.storage.save_account(checking)
        self.cli.storage.save_account(savings)
        input_mock.side_effect = ['weekly 1', 'weekly', '2020-01-16', '1', '-15', 'R', '2', '15', '', '', 't', '\'payee', 'desc']
        self.cli._create_scheduled_txn()
        scheduled_txns = self.cli.storage.get_scheduled_transactions()
        self.assertEqual(len(scheduled_txns), 1)
        self.assertEqual(scheduled_txns[0].name, 'weekly 1')
        self.assertEqual(scheduled_txns[0].frequency, bb.ScheduledTransactionFrequency.WEEKLY)
        self.assertEqual(scheduled_txns[0].splits,
                {
                    checking: {'amount': -15, 'status': 'R'},
                    savings: {'amount': 15},
                })
        self.assertEqual(scheduled_txns[0].txn_type, 't')
        self.assertEqual(scheduled_txns[0].payee.name, 'payee')
        self.assertEqual(scheduled_txns[0].description, 'desc')

    @patch('builtins.input')
    def test_edit_scheduled_txn(self, input_mock):
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        self.cli.storage.save_account(checking)
        self.cli.storage.save_account(savings)
        valid_splits={
                checking: {'amount': -101},
                savings: {'amount': 101},
            }
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits=valid_splits,
            )
        self.cli.storage.save_scheduled_transaction(st)
        input_mock.side_effect = [str(st.id), 'weekly 1', 'weekly', '2020-01-16', '-15', '', '15', '', '', 't', '\'payee', 'desc']
        self.cli._edit_scheduled_txn()
        scheduled_txns = self.cli.storage.get_scheduled_transactions()
        self.assertEqual(len(scheduled_txns), 1)
        self.assertEqual(scheduled_txns[0].splits[checking], {'amount': -15})
        self.assertEqual(scheduled_txns[0].frequency, bb.ScheduledTransactionFrequency.WEEKLY)
        self.assertEqual(scheduled_txns[0].txn_type, 't')
        self.assertEqual(scheduled_txns[0].payee.name, 'payee')
        self.assertEqual(scheduled_txns[0].description, 'desc')

    def test_list_budgets(self):
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        self.cli.storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        self.cli.storage.save_account(food)
        wages = get_test_account(type_=bb.AccountType.INCOME, name='Wages')
        self.cli.storage.save_account(wages)
        b = bb.Budget(year=2018, account_budget_info={
            housing: {'amount': 15, 'carryover': 0},
            food: {'amount': 25, 'carryover': 0},
            wages: {'amount': 100},
        })
        self.cli.storage.save_budget(b)
        self.cli._list_budgets()
        output = '1: 2018-01-01 - 2018-12-31\n'
        buffer_value = self.memory_buffer.getvalue()
        self.assertEqual(buffer_value, output)

    @patch('builtins.input')
    def test_display_budget(self, input_mock):
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        self.cli.storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        self.cli.storage.save_account(food)
        wages = get_test_account(type_=bb.AccountType.INCOME, name='Wages')
        self.cli.storage.save_account(wages)
        b = bb.Budget(year=2018, account_budget_info={
            housing: {'amount': 15, 'carryover': 0},
            food: {'amount': 25, 'carryover': 0},
            wages: {'amount': 100},
        })
        self.cli.storage.save_budget(b)
        input_mock.side_effect = [str(b.id)]
        self.cli._display_budget()
        buffer_value = self.memory_buffer.getvalue()
        self.assertTrue('2018-01-01 - 2018-12-31' in buffer_value)

    @patch('builtins.input')
    def test_display_budget_report(self, input_mock):
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        self.cli.storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        self.cli.storage.save_account(food)
        wages = get_test_account(type_=bb.AccountType.INCOME, name='Wages')
        self.cli.storage.save_account(wages)
        b = bb.Budget(year=2018, account_budget_info={
            housing: {'amount': 15, 'carryover': 0},
            food: {'amount': 25, 'carryover': 0},
            wages: {'amount': 100},
        })
        self.cli.storage.save_budget(b)
        self.cli.storage.save_txn(
                bb.Transaction(
                    txn_date='2019-01-13',
                    splits={wages: {'amount': '-101'}, housing: {'amount': 101}},
                )
            )
        input_mock.side_effect = [str(b.id)]
        self.cli._display_budget_report()
        buffer_value = self.memory_buffer.getvalue()
        self.assertTrue('2018-01-01 - 2018-12-31' in buffer_value)

    @patch('builtins.input')
    def test_create_budget(self, input_mock):
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        self.cli.storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        self.cli.storage.save_account(food)
        wages = get_test_account(type_=bb.AccountType.INCOME, name='Wages')
        self.cli.storage.save_account(wages)
        input_mock.side_effect = ['2019-01-10', '2019-11-30', str(housing.id), '100', '', '', '']
        self.cli._create_budget()
        budget = self.cli.storage.get_budgets()[0]
        self.assertEqual(budget.start_date, date(2019, 1, 10))
        self.assertEqual(budget.end_date, date(2019, 11, 30))
        budget_data = budget.get_budget_data()
        self.assertEqual(budget_data[housing], {'amount': 100})
        self.assertEqual(budget_data[food], {})
        self.assertEqual(budget_data[wages], {})

    @patch('builtins.input')
    def test_edit_budget(self, input_mock):
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        self.cli.storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        self.cli.storage.save_account(food)
        wages = get_test_account(type_=bb.AccountType.INCOME, name='Wages')
        self.cli.storage.save_account(wages)
        b = bb.Budget(year=2018, account_budget_info={
            housing: {'amount': 15, 'carryover': 0},
            food: {},
            wages: {'amount': 100},
        })
        self.cli.storage.save_budget(b)
        input_mock.side_effect = [str(b.id), '2019-01-10', '2019-11-30', '40', '', '', '', '', '', '100', '', '']
        self.cli._edit_budget()
        budget = self.cli.storage.get_budgets()[0]
        self.assertEqual(budget.start_date, date(2019, 1, 10))
        budget_data = budget.get_budget_data()
        self.assertEqual(budget_data[housing]['amount'], 40)
        self.assertEqual(budget_data[food], {})
        self.assertEqual(budget_data[wages]['amount'], 100)


def fake_method():
    pass


class TestQtGUI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication([])

    def test_bb_qt_gui(self):
        bb_qt_gui = bb.GUI_QT(':memory:')

    def test_account(self):
        storage = bb.SQLiteStorage(':memory:')
        a = get_test_account()
        storage.save_account(a)
        accounts_display = bb.AccountsDisplay(storage, reload_accounts=fake_method)
        widget = accounts_display.get_widget()
        QtTest.QTest.mouseClick(accounts_display.add_button, QtCore.Qt.LeftButton)
        accounts_display.add_account_display._widgets['number'].setText('400')
        accounts_display.add_account_display._widgets['name'].setText('Savings')
        accounts_display.add_account_display._widgets['parent'].setCurrentIndex(1)
        QtTest.QTest.mouseClick(accounts_display.add_account_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        accounts = storage.get_accounts()
        self.assertEqual(len(accounts), 2)
        self.assertEqual(accounts[1].type.name, 'ASSET')
        self.assertEqual(accounts[1].number, '400')
        self.assertEqual(accounts[1].name, 'Savings')
        self.assertEqual(accounts[1].parent.name, 'Checking')

    def test_account_edit(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = bb.Account(type_=bb.AccountType.ASSET, name='Checking')
        storage.save_account(checking)
        savings = bb.Account(type_=bb.AccountType.ASSET, name='Savings')
        storage.save_account(savings)
        accounts_display = bb.AccountsDisplay(storage, reload_accounts=fake_method)
        widget = accounts_display.get_widget()
        QtTest.QTest.mouseClick(accounts_display.accounts_widgets[savings.id]['labels']['name'], QtCore.Qt.LeftButton)
        accounts_display.edit_account_display._widgets['name'].setText('New Savings')
        accounts_display.edit_account_display._widgets['parent'].setCurrentIndex(1)
        QtTest.QTest.mouseClick(accounts_display.edit_account_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        self.assertEqual(len(storage.get_accounts()), 2)
        self.assertEqual(storage.get_accounts()[1].name, 'New Savings')
        self.assertEqual(storage.get_accounts()[1].parent.name, 'Checking')

    def test_expense_account_edit(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = bb.Account(type_=bb.AccountType.ASSET, name='Checking')
        storage.save_account(checking)
        food = bb.Account(type_=bb.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        accounts_display = bb.AccountsDisplay(storage, reload_accounts=fake_method)
        widget = accounts_display.get_widget()
        QtTest.QTest.mouseClick(accounts_display.accounts_widgets[food.id]['labels']['name'], QtCore.Qt.LeftButton)
        accounts_display.edit_account_display._widgets['name'].setText('New Food')
        QtTest.QTest.mouseClick(accounts_display.edit_account_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        self.assertEqual(len(storage.get_accounts()), 2)
        self.assertEqual(storage.get_accounts()[1].name, 'New Food')

    @patch('bricbooks.set_widget_error_state')
    def test_account_exception(self, mock_method):
        storage = bb.SQLiteStorage(':memory:')
        accounts_display = bb.AccountsDisplay(storage, reload_accounts=fake_method)
        widget = accounts_display.get_widget()
        account_form = bb.AccountForm(storage.get_accounts())
        account_form.show_form()
        QtTest.QTest.mouseClick(account_form._widgets['save_btn'], QtCore.Qt.LeftButton)
        mock_method.assert_called_once_with(account_form._widgets['name'])

    def test_empty_ledger(self):
        storage = bb.SQLiteStorage(':memory:')
        ledger_display = bb.LedgerDisplay(storage)

    def test_ledger_add(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        savings = get_test_account(name='Savings')
        storage.save_account(savings)
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        txn = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date.today())
        txn2 = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date(2017, 1, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        ledger_display = bb.LedgerDisplay(storage)
        ledger_display.get_widget()
        QtTest.QTest.mouseClick(ledger_display.add_button, QtCore.Qt.LeftButton)
        self.assertEqual(ledger_display.add_txn_display._widgets['accounts_display']._categories_combo.count(), 4)
        ledger_display.add_txn_display._widgets['txn_date'].setText('2017-01-05')
        ledger_display.add_txn_display._widgets['withdrawal'].setText('18')
        ledger_display.add_txn_display._widgets['payee'].setCurrentText('Burgers')
        ledger_display.add_txn_display._widgets['accounts_display']._categories_combo.setCurrentIndex(1)
        QtTest.QTest.mouseClick(ledger_display.add_txn_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        #make sure new txn was saved
        ledger = storage.get_ledger(account=checking)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(len(txns), 3)
        self.assertEqual(txns[1].splits[checking], {'amount': -18})
        self.assertEqual(txns[1].payee.name, 'Burgers')
        #check new txn display
        self.assertEqual(len(ledger_display.ledger.get_sorted_txns_with_balance()), 3)
        self.assertEqual(ledger_display.txns_display.txn_display_data[txns[1].id]['row'], 1)

    def test_ledger_add_not_first_account(self):
        #test that correct accounts are set for the new txn (not just first account in the list)
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        savings = get_test_account(name='Savings')
        storage.save_account(savings)
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        ledger_display = bb.LedgerDisplay(storage, current_account=savings)
        ledger_display.get_widget()
        QtTest.QTest.mouseClick(ledger_display.add_button, QtCore.Qt.LeftButton)
        ledger_display.add_txn_display._widgets['txn_date'].setText('2017-01-05')
        ledger_display.add_txn_display._widgets['withdrawal'].setText('18')
        ledger_display.add_txn_display._widgets['accounts_display']._categories_combo.setCurrentIndex(1)
        QtTest.QTest.mouseClick(ledger_display.add_txn_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        #make sure new txn was saved correctly
        ledger = storage.get_ledger(account=savings)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].splits,
                {savings: {'amount': -18}, housing: {'amount': 18}}
            )

    def test_add_txn_multiple_splits(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        rent = get_test_account(type_=bb.AccountType.EXPENSE, name='Rent')
        storage.save_account(rent)
        ledger_display = bb.LedgerDisplay(storage)
        ledger_display.get_widget()
        QtTest.QTest.mouseClick(ledger_display.add_button, QtCore.Qt.LeftButton)
        txn_accounts_display_splits = {rent: {'amount': 3}, housing: {'amount': 7}}
        ledger_display.add_txn_display._widgets['txn_date'].setText('2017-01-05')
        ledger_display.add_txn_display._widgets['withdrawal'].setText('10')
        bb.get_new_txn_splits = MagicMock(return_value=txn_accounts_display_splits)
        QtTest.QTest.mouseClick(ledger_display.add_txn_display._widgets['accounts_display'].split_button, QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(ledger_display.add_txn_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        #make sure new txn was saved
        ledger = storage.get_ledger(account=checking)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].splits[checking], {'amount': -10})

    def test_ledger_choose_account(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = bb.Account(type_=bb.AccountType.ASSET, name='Checking')
        savings = bb.Account(type_=bb.AccountType.ASSET, name='Savings')
        storage.save_account(checking)
        storage.save_account(savings)
        txn = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date.today())
        txn2 = bb.Transaction(splits={savings: {'amount': 5}, checking: {'amount': -5}}, txn_date=date(2017, 1, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        ledger_display = bb.LedgerDisplay(storage, current_account=savings)
        ledger_display.get_widget()
        self.assertEqual(ledger_display._current_account, savings)
        self.assertEqual(ledger_display.action_combo.currentIndex(), 1)
        self.assertEqual(ledger_display.action_combo.currentText(), 'Savings')

    def test_ledger_switch_account(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = bb.Account(type_=bb.AccountType.ASSET, name='Checking')
        savings = bb.Account(type_=bb.AccountType.ASSET, name='Savings')
        restaurant = bb.Account(type_=bb.AccountType.EXPENSE, name='Restaurants')
        storage.save_account(checking)
        storage.save_account(savings)
        storage.save_account(restaurant)
        txn = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date.today())
        txn2 = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date(2017, 1, 2))
        txn3 = bb.Transaction(splits={savings: {'amount': 5}, checking: {'amount': -5}}, txn_date=date(2018, 1, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        storage.save_txn(txn3)
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits={restaurant: {'amount': 5}, checking: {'amount': -5}},
                txn_type='a',
                payee=bb.Payee('Wendys'),
                description='something',
            )
        storage.save_scheduled_transaction(st)
        ledger_display = bb.LedgerDisplay(storage)
        ledger_display.get_widget()
        self.assertEqual(ledger_display._current_account, checking)
        self.assertEqual(ledger_display.action_combo.currentIndex(), 0)
        self.assertEqual(ledger_display.action_combo.currentText(), 'Checking')
        ledger_display.action_combo.setCurrentIndex(1)
        self.assertEqual(ledger_display._current_account, savings)
        self.assertEqual(ledger_display.action_combo.currentText(), 'Savings')

    def test_ledger_txn_edit(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        savings = get_test_account(name='Savings')
        storage.save_account(savings)
        payee = bb.Payee('some payee')
        storage.save_payee(payee)
        txn = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date(2017, 1, 3))
        txn2 = bb.Transaction(splits={checking: {'amount': 17}, savings: {'amount': -17}}, txn_date=date(2017, 5, 2), payee=payee)
        txn3 = bb.Transaction(splits={checking: {'amount': 25}, savings: {'amount': -25}}, txn_date=date(2017, 10, 18))
        txn4 = bb.Transaction(splits={checking: {'amount': 10}, savings: {'amount': -10}}, txn_date=date(2018, 6, 6))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        storage.save_txn(txn3)
        storage.save_txn(txn4)
        ledger_display = bb.LedgerDisplay(storage)
        ledger_display.get_widget()
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn.id]['widgets']['labels']['balance'].text(), '5')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['labels']['balance'].text(), '22')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn2.id]['row'], 1)
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn3.id]['widgets']['labels']['balance'].text(), '47')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn4.id]['widgets']['labels']['balance'].text(), '57')

        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['labels']['date'], QtCore.Qt.LeftButton)

        self.assertEqual(ledger_display.txns_display.edit_txn_display._widgets['txn_date'].text(), '2017-05-02')
        self.assertEqual(ledger_display.txns_display.edit_txn_display._widgets['payee'].currentText(), 'some payee')

        ledger_display.txns_display.edit_txn_display._widgets['txn_date'].setText('2017-12-31')
        ledger_display.txns_display.edit_txn_display._widgets['deposit'].setText('20')
        QtTest.QTest.mouseClick(ledger_display.txns_display.edit_txn_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        #make sure edit was saved
        ledger = storage.get_ledger(account=checking)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(len(txns), 4)
        self.assertEqual(txns[2].txn_date, date(2017, 12, 31))
        self.assertEqual(txns[2].splits[checking], {'amount': 20})
        self.assertEqual(txns[2].splits[savings], {'amount': -20})
        #check display with edits
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn.id]['widgets']['labels']['balance'].text(), '5')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn.id]['row'], 0)
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn3.id]['widgets']['labels']['balance'].text(), '30')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn3.id]['row'], 1)
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['labels']['balance'].text(), '50')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn2.id]['row'], 2)
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn4.id]['widgets']['labels']['balance'].text(), '60')
        self.assertEqual(ledger_display.txns_display.txn_display_data[txn4.id]['row'], 3)

    def test_ledger_txn_edit_expense_account(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        restaurants = get_test_account(type_=bb.AccountType.EXPENSE, name='Restaurants')
        storage.save_account(restaurants)
        txn = bb.Transaction(splits={checking: {'amount': 5}, housing: {'amount': -5}}, txn_date=date(2017, 1, 3))
        txn2 = bb.Transaction(splits={checking: {'amount': 17}, housing: {'amount': -17}}, txn_date=date(2017, 5, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        ledger_display = bb.LedgerDisplay(storage)
        ledger_display.get_widget()
        #activate editing
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn2.id]['widgets']['labels']['date'], QtCore.Qt.LeftButton)
        #change expense account
        ledger_display.txns_display.edit_txn_display._widgets['accounts_display']._categories_combo.setCurrentIndex(2)
        #save the change
        QtTest.QTest.mouseClick(ledger_display.txns_display.edit_txn_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        #make sure new category was saved
        ledger = storage.get_ledger(account=checking)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(txns[1].splits[restaurants], {'amount': -17})

    def test_ledger_txn_edit_multiple_splits(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        storage.save_account(checking)
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        restaurants = get_test_account(type_=bb.AccountType.EXPENSE, name='Restaurants')
        storage.save_account(restaurants)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        initial_splits = {checking: {'amount': -25}, housing: {'amount': 20}, restaurants: {'amount': 5}}
        txn_account_display_splits = {housing: {'amount': 15}, restaurants: {'amount': 10}}
        final_splits = {checking: {'amount': -25}, housing: {'amount': 15}, restaurants: {'amount': 10}}
        txn = bb.Transaction(splits=initial_splits, txn_date=date(2017, 1, 3))
        storage.save_txn(txn)
        ledger_display = bb.LedgerDisplay(storage)
        ledger_display.get_widget()
        #activate editing
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn.id]['widgets']['labels']['date'], QtCore.Qt.LeftButton)
        self.assertEqual(ledger_display.txns_display.edit_txn_display._widgets['accounts_display']._categories_combo.currentText(), 'multiple')
        self.assertEqual(ledger_display.txns_display.edit_txn_display._widgets['accounts_display']._categories_combo.currentData(), initial_splits)
        bb.get_new_txn_splits = MagicMock(return_value=txn_account_display_splits)
        QtTest.QTest.mouseClick(ledger_display.txns_display.edit_txn_display._widgets['accounts_display'].split_button, QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(ledger_display.txns_display.edit_txn_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        updated_txn = storage.get_txn(txn.id)
        self.assertDictEqual(updated_txn.splits, final_splits)

    def test_ledger_txn_delete(self):
        storage = bb.SQLiteStorage(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        storage.save_account(checking)
        storage.save_account(savings)
        txn = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date.today())
        txn2 = bb.Transaction(splits={checking: {'amount': 23}, savings: {'amount': -23}}, txn_date=date(2017, 1, 2))
        storage.save_txn(txn)
        storage.save_txn(txn2)
        ledger_display = bb.LedgerDisplay(storage)
        ledger_display.get_widget()
        QtTest.QTest.mouseClick(ledger_display.txns_display.txn_display_data[txn.id]['widgets']['labels']['date'], QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(ledger_display.txns_display.edit_txn_display._widgets['delete_btn'], QtCore.Qt.LeftButton)
        #make sure txn was deleted
        ledger = storage.get_ledger(account=checking)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].splits[checking], {'amount': 23})

    def test_ledger_skip_scheduled_txn(self):
        gui = bb.GUI_QT(':memory:') #goes to accounts page, b/c no accounts yet
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        housing = get_test_account(name='Housing', type_=bb.AccountType.EXPENSE)
        gui.storage.save_account(checking)
        gui.storage.save_account(savings)
        gui.storage.save_account(housing)
        splits = {checking: {'amount': -100}, housing: {'amount': 100}}
        scheduled_txn = bb.ScheduledTransaction(
            name='weekly',
            frequency=bb.ScheduledTransactionFrequency.WEEKLY,
            splits=splits,
            next_due_date=date(2018, 1, 13),
        )
        gui.storage.save_scheduled_transaction(scheduled_txn)
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton) #go to ledger page
        QtTest.QTest.mouseClick(gui.ledger_display.txns_display._scheduled_txn_widgets[2], QtCore.Qt.LeftButton) #click to show form
        QtTest.QTest.mouseClick(gui.ledger_display.txns_display.scheduled_txn_display._widgets['skip_btn'], QtCore.Qt.LeftButton) #click to skip next txn
        scheduled_txns = gui.storage.get_scheduled_transactions()
        self.assertEqual(len(scheduled_txns), 1)
        self.assertEqual(scheduled_txns[0].next_due_date, date(2018, 1, 20))

    def test_ledger_update_reconciled_state(self):
        gui = bb.GUI_QT(':memory:') #goes to accounts page, b/c no accounts yet
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        gui.storage.save_account(checking)
        gui.storage.save_account(savings)
        txn = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date.today())
        gui.storage.save_txn(txn)
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton) #go to ledger page
        QtTest.QTest.mouseClick(gui.ledger_display.txns_display.txn_display_data[txn.id]['widgets']['labels']['status'], QtCore.Qt.LeftButton) #click to change status
        txns = gui.storage.get_ledger(checking).get_sorted_txns_with_balance()
        self.assertEqual(txns[0].splits[checking]['status'], bb.Transaction.CLEARED)

    def test_budget_display(self):
        storage = bb.SQLiteStorage(':memory:')
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        wages = get_test_account(type_=bb.AccountType.INCOME, name='Wages')
        storage.save_account(wages)
        b = bb.Budget(year=2018, account_budget_info={
            housing: {'amount': 15, 'carryover': 0},
            food: {'amount': 25, 'carryover': 0},
            wages: {'amount': 100},
        })
        storage.save_budget(b)
        budget = storage.get_budgets()[0]
        budget_display = bb.BudgetDisplay(storage=storage, current_budget=budget)
        widget = budget_display.get_widget()

    def test_budget_create(self):
        storage = bb.SQLiteStorage(':memory:')
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        storage.save_account(housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        storage.save_account(food)
        budget_display = bb.BudgetDisplay(storage=storage)
        budget_display.get_widget()
        self.assertEqual(budget_display._current_budget, None)
        self.assertEqual(budget_display._budget_select_combo.currentText(), '')
        self.assertEqual(budget_display._budget_select_combo.currentData(), None)
        QtTest.QTest.mouseClick(budget_display.add_button, QtCore.Qt.LeftButton)
        budget_display.budget_form._widgets['start_date'].setText('2020-01-01')
        budget_display.budget_form._widgets['end_date'].setText('2020-12-31')
        budget_display.budget_form._widgets['budget_data'][housing]['amount'].setText('500')
        budget_display.budget_form._save()
        #verify budget saved in storage
        budget = storage.get_budgets()[0]
        self.assertEqual(budget.start_date, date(2020, 1, 1))
        self.assertEqual(budget.get_budget_data()[housing]['amount'], 500)
        #verify BudgetDisplay updated
        self.assertEqual(budget_display._current_budget, budget)
        self.assertEqual(budget_display._budget_select_combo.currentText(), '2020-01-01 - 2020-12-31')
        self.assertEqual(budget_display._budget_select_combo.currentData(), budget)

    def test_add_scheduled_txn(self):
        gui = bb.GUI_QT(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        gui.storage.save_account(checking)
        gui.storage.save_account(savings)
        QtTest.QTest.mouseClick(gui.scheduled_txns_button, QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(gui.scheduled_txns_display.add_button, QtCore.Qt.LeftButton)
        gui.scheduled_txns_display.form._widgets['name'].setText('test st')
        gui.scheduled_txns_display.form._widgets['next_due_date'].setText('2020-01-15')
        gui.scheduled_txns_display.form._widgets['account'].setCurrentIndex(0)
        gui.scheduled_txns_display.form._widgets['withdrawal'].setText('37')
        gui.scheduled_txns_display.form._widgets['accounts_display']._categories_combo.setCurrentIndex(2)
        QtTest.QTest.mouseClick(gui.scheduled_txns_display.form._widgets['save_btn'], QtCore.Qt.LeftButton)
        scheduled_txns = gui.storage.get_scheduled_transactions()
        self.assertEqual(scheduled_txns[0].name, 'test st')
        self.assertEqual(scheduled_txns[0].splits[checking], {'amount': -37})
        self.assertEqual(scheduled_txns[0].splits[savings], {'amount': 37})

    def test_edit_scheduled_txn(self):
        gui = bb.GUI_QT(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        housing = get_test_account(name='Housing', type_=bb.AccountType.EXPENSE)
        gui.storage.save_account(checking)
        gui.storage.save_account(savings)
        gui.storage.save_account(housing)
        splits = {checking: {'amount': -100}, housing: {'amount': 100}}
        scheduled_txn = bb.ScheduledTransaction(
            name='weekly',
            frequency=bb.ScheduledTransactionFrequency.WEEKLY,
            splits=splits,
            next_due_date=date.today()
        )
        gui.storage.save_scheduled_transaction(scheduled_txn)
        #go to scheduled txns, click on one to activate edit form, update values, & save it
        QtTest.QTest.mouseClick(gui.scheduled_txns_button, QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(gui.scheduled_txns_display.data_display.widgets[scheduled_txn.id]['name'], QtCore.Qt.LeftButton)
        gui.scheduled_txns_display.data_display.edit_form._widgets['name'].setText('updated')
        gui.scheduled_txns_display.data_display.edit_form._widgets['withdrawal'].setText('15')
        self.assertEqual(gui.scheduled_txns_display.data_display.edit_form._widgets['accounts_display']._categories_combo.currentData(), housing)
        QtTest.QTest.mouseClick(gui.scheduled_txns_display.data_display.edit_form._widgets['save_btn'], QtCore.Qt.LeftButton)
        scheduled_txns = gui.storage.get_scheduled_transactions()
        self.assertEqual(len(scheduled_txns), 1)
        self.assertEqual(scheduled_txns[0].name, 'updated')
        self.assertEqual(scheduled_txns[0].splits[checking], {'amount': -15})
        self.assertEqual(scheduled_txns[0].splits[housing], {'amount': 15})


class TestLoadTestData(unittest.TestCase):

    def test_load(self):
        storage = bb.SQLiteStorage(':memory:')
        load_test_data._load_data(storage, many_txns=False)
        accounts = storage.get_accounts()


class TestImport(unittest.TestCase):

    def test_kmymoney(self):
        filename = 'import_test.kmy'
        storage = bb.SQLiteStorage(':memory:')
        with open(filename, 'rb') as f:
            bb.import_kmymoney(kmy_file=f, storage=storage)
        accounts = storage.get_accounts()
        self.assertEqual(len(accounts), 34)
        assets = storage.get_accounts(type_=bb.AccountType.ASSET)
        self.assertEqual(len(assets), 5)
        liabilities = storage.get_accounts(type_=bb.AccountType.LIABILITY)
        self.assertEqual(len(liabilities), 1)
        expenses = storage.get_accounts(type_=bb.AccountType.EXPENSE)
        self.assertEqual(len(expenses), 17)
        incomes = storage.get_accounts(type_=bb.AccountType.INCOME)
        self.assertEqual(len(incomes), 9)
        equities = storage.get_accounts(type_=bb.AccountType.EQUITY)
        self.assertEqual(len(equities), 2)
        payees = storage.get_payees()
        self.assertEqual(len(payees), 2)
        checking = storage.get_account(name='Checking')
        ledger = storage.get_ledger(checking)
        txns = ledger.get_sorted_txns_with_balance()
        self.assertEqual(len(txns), 4)
        self.assertEqual(txns[1].payee.name, 'A restaurant')
        balances = ledger.get_current_balances_for_display()
        expected_balances = bb.LedgerBalances(current='742.78', current_cleared='842.78')
        self.assertEqual(balances, expected_balances)


if __name__ == '__main__':
    import sys
    print(sys.version)
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-gui', dest='no_gui', action='store_true')
    args = parser.parse_args()
    if args.no_gui:
        suite = unittest.TestSuite()
        suite.addTest(unittest.makeSuite(TestAccount, 'test'))
        suite.addTest(unittest.makeSuite(TestTransaction, 'test'))
        suite.addTest(unittest.makeSuite(TestScheduledTransaction, 'test'))
        suite.addTest(unittest.makeSuite(TestLedger, 'test'))
        suite.addTest(unittest.makeSuite(TestBudget, 'test'))
        suite.addTest(unittest.makeSuite(TestSQLiteStorage, 'test'))
        suite.addTest(unittest.makeSuite(TestCLI, 'test'))
        suite.addTest(unittest.makeSuite(TestLoadTestData, 'test'))
        suite.addTest(unittest.makeSuite(TestImport, 'test'))
        runner = unittest.TextTestRunner()
        runner.run(suite)
    else:
        from PySide2 import QtWidgets, QtTest, QtCore
        unittest.main()

