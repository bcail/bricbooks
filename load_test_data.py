from datetime import date, timedelta
from decimal import Decimal as D
import random
import bricbooks as pft


DEFAULT_DATA_FILENAME = 'data.sqlite3'


def _load_data(storage, many_txns):
    opening_balances = pft.Account(type_=pft.AccountType.EQUITY, name='Opening Balances')
    storage.save_account(opening_balances)

    checking = pft.Account(type_=pft.AccountType.ASSET, name='Checking')
    storage.save_account(checking)

    savings = pft.Account(type_=pft.AccountType.ASSET, name='Saving')
    storage.save_account(savings)

    mortgage = pft.Account(type_=pft.AccountType.LIABILITY, name='Mortgage')
    storage.save_account(mortgage)
    credit_card = pft.Account(type_=pft.AccountType.LIABILITY, name='Credit Card')
    storage.save_account(credit_card)

    food = pft.Account(type_=pft.AccountType.EXPENSE, user_id='300', name='Food')
    storage.save_account(food)
    restaurants = pft.Account(type_=pft.AccountType.EXPENSE, user_id='310', name='Restaurants', parent=food)
    storage.save_account(restaurants)
    transportation = pft.Account(type_=pft.AccountType.EXPENSE, user_id='400', name='Transportation')
    storage.save_account(transportation)
    gas_stations = pft.Account(type_=pft.AccountType.EXPENSE, user_id='410', name='Gas Stations', parent=transportation)
    storage.save_account(gas_stations)
    car_insurance = pft.Account(type_=pft.AccountType.EXPENSE, user_id='420', name='Car Insurance', parent=transportation)
    storage.save_account(car_insurance)
    housing = pft.Account(type_=pft.AccountType.EXPENSE, user_id='500', name='Housing')
    storage.save_account(housing)
    rent = pft.Account(type_=pft.AccountType.EXPENSE, user_id='510', name='Rent', parent=housing)
    storage.save_account(rent)
    mortgage_interest = pft.Account(type_=pft.AccountType.EXPENSE, user_id='520', name='Mortgage Interest', parent=housing)
    storage.save_account(mortgage_interest)
    medical = pft.Account(type_=pft.AccountType.EXPENSE, user_id='600', name='Medical')
    storage.save_account(medical)
    taxes = pft.Account(type_=pft.AccountType.EXPENSE, user_id='700', name='Taxes')
    storage.save_account(taxes)

    payee = pft.Payee("Joe's Burgers")
    storage.save_payee(payee)

    storage.save_txn(pft.Transaction(splits={opening_balances: D('-1000'), checking: 1000}, txn_date='2018-01-01'))
    storage.save_txn(pft.Transaction(splits={opening_balances: D('-1000'), savings: 1000}, txn_date='2018-01-01'))
    storage.save_txn(pft.Transaction(splits={checking: D('-10'), restaurants: 10}, txn_date='2018-01-01', txn_type='123', payee=payee))
    storage.save_txn(pft.Transaction(splits={checking: D('-20'), restaurants: 20}, txn_date='2018-01-02'))
    storage.save_txn(pft.Transaction(splits={checking: D('-30'), restaurants: 30}, txn_date='2018-01-04'))
    storage.save_txn(pft.Transaction(splits={checking: D('-40'), restaurants: 40}, txn_date='2018-01-06'))
    storage.save_txn(pft.Transaction(splits={checking: D('-50'), restaurants: 50}, txn_date='2018-01-07'))
    storage.save_txn(pft.Transaction(splits={checking: D('-60'), restaurants: 60}, txn_date='2018-01-08'))
    storage.save_txn(pft.Transaction(splits={checking: D('100'), savings: '-100'}, txn_date='2018-01-09'))
    storage.save_txn(pft.Transaction(splits={checking: D('-70'), restaurants: 70}, txn_date='2018-01-10'))
    storage.save_txn(pft.Transaction(splits={checking: D('-80'), restaurants: 80}, txn_date='2018-01-11'))
    storage.save_txn(pft.Transaction(splits={checking: D('-90'), restaurants: 90}, txn_date='2018-02-11'))
    storage.save_txn(pft.Transaction(splits={checking: D('-180'), housing: 180}, txn_date='2018-02-12'))
    storage.save_txn(pft.Transaction(splits={checking: D('80.13'), savings: '-80.13'}, txn_date='2018-02-13'))
    storage.save_txn(pft.Transaction(splits={checking: D('-50'), gas_stations: 50}, txn_date='2018-02-14'))
    storage.save_txn(pft.Transaction(splits={checking: D('-70'), gas_stations: 40, restaurants: 30}, txn_date='2018-02-15'))
    storage.save_txn(pft.Transaction(splits={checking: D('-10'), gas_stations: 10}, txn_date='2018-02-16'))
    storage.save_txn(pft.Transaction(splits={checking: D('-20'), gas_stations: 20}, txn_date='2018-02-17'))
    storage.save_txn(pft.Transaction(splits={checking: D('-40'), gas_stations: 40}, txn_date='2018-02-18'))
    storage.save_txn(pft.Transaction(splits={checking: D('-30'), gas_stations: 30}, txn_date='2018-02-19'))
    storage.save_txn(pft.Transaction(splits={checking: D('-50'), gas_stations: 50}, txn_date='2018-02-21'))
    storage.save_txn(pft.Transaction(splits={checking: D('-70'), gas_stations: 70}, txn_date='2018-02-23'))
    storage.save_txn(pft.Transaction(splits={checking: D('-90'), gas_stations: 90}, txn_date='2018-02-24'))
    storage.save_txn(pft.Transaction(splits={checking: D('40'), savings: '-40'}, txn_date='2018-02-25'))

    if many_txns:
        print('adding 1000 random txns')
        for i in range(1000):
            amt = D(random.randint(1, 500))
            day = random.randint(1, 30)
            txn = pft.Transaction(splits={checking: amt * D(-1), restaurants: amt}, txn_date='2018-04-%s' % day)
            storage.save_txn(txn)

    rent_scheduled_txn = pft.ScheduledTransaction(
            name='rent',
            frequency=pft.ScheduledTransactionFrequency.MONTHLY,
            splits={checking: -100, housing: 100},
            next_due_date=date.today()-timedelta(days=1)
        )
    storage.save_scheduled_transaction(rent_scheduled_txn)
    taxes_scheduled_txn = pft.ScheduledTransaction(
            name='taxes',
            frequency=pft.ScheduledTransactionFrequency.ANNUALLY,
            splits={checking: -25, taxes: 25},
            next_due_date=date.today()+timedelta(days=1)
        )
    storage.save_scheduled_transaction(taxes_scheduled_txn)

    budget_categories = {
            restaurants: {'amount': D(500), 'carryover': D(0)},
            gas_stations: {'amount': D(450), 'carryover': D(10)},
            housing: {'amount': D(200), 'carryover': D(0)},
        }
    budget = pft.Budget('2018', account_budget_info=budget_categories)
    storage.save_budget(budget)


def main(file_name, many_txns=False):
    storage = pft.SQLiteStorage(file_name)
    _load_data(storage, many_txns)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file_name', dest='file_name')
    parser.add_argument('--many_txns', default=False, action='store_true', dest='many_txns')
    args = parser.parse_args()
    if args.file_name:
        print('filename: %s' % args.file_name)
        main(args.file_name, args.many_txns)
    else:
        print('using default file_name: %s' % DEFAULT_DATA_FILENAME)
        main(DEFAULT_DATA_FILENAME, args.many_txns)

