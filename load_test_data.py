from datetime import date, timedelta
import random
import bricbooks as bb


DEFAULT_DATA_FILENAME = 'data.sqlite3'


def _load_data(storage, many_txns):
    opening_balances = bb.Account(type_=bb.AccountType.EQUITY, name='Opening Balances')
    storage.save_account(opening_balances)

    checking = bb.Account(type_=bb.AccountType.ASSET, name='Checking')
    storage.save_account(checking)

    savings = bb.Account(type_=bb.AccountType.ASSET, name='Saving')
    storage.save_account(savings)

    mortgage = bb.Account(type_=bb.AccountType.LIABILITY, name='Mortgage')
    storage.save_account(mortgage)
    credit_card = bb.Account(type_=bb.AccountType.LIABILITY, name='Credit Card')
    storage.save_account(credit_card)

    food = bb.Account(type_=bb.AccountType.EXPENSE, user_id='300', name='Food')
    storage.save_account(food)
    restaurants = bb.Account(type_=bb.AccountType.EXPENSE, user_id='310', name='Restaurants', parent=food)
    storage.save_account(restaurants)
    transportation = bb.Account(type_=bb.AccountType.EXPENSE, user_id='400', name='Transportation')
    storage.save_account(transportation)
    gas_stations = bb.Account(type_=bb.AccountType.EXPENSE, user_id='410', name='Gas Stations', parent=transportation)
    storage.save_account(gas_stations)
    car_insurance = bb.Account(type_=bb.AccountType.EXPENSE, user_id='420', name='Car Insurance', parent=transportation)
    storage.save_account(car_insurance)
    housing = bb.Account(type_=bb.AccountType.EXPENSE, user_id='500', name='Housing')
    storage.save_account(housing)
    rent = bb.Account(type_=bb.AccountType.EXPENSE, user_id='510', name='Rent', parent=housing)
    storage.save_account(rent)
    mortgage_interest = bb.Account(type_=bb.AccountType.EXPENSE, user_id='520', name='Mortgage Interest', parent=housing)
    storage.save_account(mortgage_interest)
    medical = bb.Account(type_=bb.AccountType.EXPENSE, user_id='600', name='Medical')
    storage.save_account(medical)
    taxes = bb.Account(type_=bb.AccountType.EXPENSE, user_id='700', name='Taxes')
    storage.save_account(taxes)

    payee = bb.Payee("Joe's Burgers")
    storage.save_payee(payee)

    storage.save_txn(bb.Transaction(splits={opening_balances: '-1000', checking: 1000}, txn_date='2018-01-01'))
    storage.save_txn(bb.Transaction(splits={opening_balances: '-1000', savings: 1000}, txn_date='2018-01-01'))
    storage.save_txn(bb.Transaction(splits={checking: '-10', restaurants: 10}, txn_date='2018-01-01', txn_type='123', payee=payee))
    storage.save_txn(bb.Transaction(splits={checking: '-20', restaurants: 20}, txn_date='2018-01-02'))
    storage.save_txn(bb.Transaction(splits={checking: '-30', restaurants: 30}, txn_date='2018-01-04'))
    storage.save_txn(bb.Transaction(splits={checking: '-40', restaurants: 40}, txn_date='2018-01-06'))
    storage.save_txn(bb.Transaction(splits={checking: '-50', restaurants: 50}, txn_date='2018-01-07'))
    storage.save_txn(bb.Transaction(splits={checking: '-60', restaurants: 60}, txn_date='2018-01-08'))
    storage.save_txn(bb.Transaction(splits={checking: '100', savings: '-100'}, txn_date='2018-01-09'))
    storage.save_txn(bb.Transaction(splits={checking: '-70', restaurants: 70}, txn_date='2018-01-10'))
    storage.save_txn(bb.Transaction(splits={checking: '-80', restaurants: 80}, txn_date='2018-01-11'))
    storage.save_txn(bb.Transaction(splits={checking: '-90', restaurants: 90}, txn_date='2018-02-11'))
    storage.save_txn(bb.Transaction(splits={checking: '-180', housing: 180}, txn_date='2018-02-12'))
    storage.save_txn(bb.Transaction(splits={checking: '80.13', savings: '-80.13'}, txn_date='2018-02-13'))
    storage.save_txn(bb.Transaction(splits={checking: '-50', gas_stations: 50}, txn_date='2018-02-14'))
    storage.save_txn(bb.Transaction(splits={checking: '-70', gas_stations: 40, restaurants: 30}, txn_date='2018-02-15'))
    storage.save_txn(bb.Transaction(splits={checking: '-10', gas_stations: 10}, txn_date='2018-02-16'))
    storage.save_txn(bb.Transaction(splits={checking: '-20', gas_stations: 20}, txn_date='2018-02-17'))
    storage.save_txn(bb.Transaction(splits={checking: '-40', gas_stations: 40}, txn_date='2018-02-18'))
    storage.save_txn(bb.Transaction(splits={checking: '-30', gas_stations: 30}, txn_date='2018-02-19'))
    storage.save_txn(bb.Transaction(splits={checking: '-50', gas_stations: 50}, txn_date='2018-02-21'))
    storage.save_txn(bb.Transaction(splits={checking: '-70', gas_stations: 70}, txn_date='2018-02-23'))
    storage.save_txn(bb.Transaction(splits={checking: '-90', gas_stations: 90}, txn_date='2018-02-24'))
    storage.save_txn(bb.Transaction(splits={checking: '40', savings: '-40'}, txn_date='2018-02-25'))

    if many_txns:
        print('adding 1000 random txns')
        for i in range(1000):
            amt = random.randint(1, 500)
            day = random.randint(1, 30)
            txn = bb.Transaction(splits={checking: amt * -1, restaurants: amt}, txn_date='2018-04-%s' % day)
            storage.save_txn(txn)

    rent_scheduled_txn = bb.ScheduledTransaction(
            name='rent',
            frequency=bb.ScheduledTransactionFrequency.MONTHLY,
            splits={checking: -100, housing: 100},
            next_due_date=date.today()-timedelta(days=1)
        )
    storage.save_scheduled_transaction(rent_scheduled_txn)
    taxes_scheduled_txn = bb.ScheduledTransaction(
            name='taxes',
            frequency=bb.ScheduledTransactionFrequency.ANNUALLY,
            splits={checking: -25, taxes: 25},
            next_due_date=date.today()+timedelta(days=1)
        )
    storage.save_scheduled_transaction(taxes_scheduled_txn)

    budget_categories = {
            restaurants: {'amount': 500, 'carryover': 0},
            gas_stations: {'amount': 450, 'carryover': 10},
            housing: {'amount': 200, 'carryover': 0},
        }
    budget = bb.Budget('2018', account_budget_info=budget_categories)
    storage.save_budget(budget)


def main(file_name, many_txns=False):
    storage = bb.SQLiteStorage(file_name)
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

