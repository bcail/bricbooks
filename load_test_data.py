from datetime import date, timedelta
import random
import bricbooks as bb


DEFAULT_DATA_FILENAME = 'data.sqlite3'
# add a char from unicode SMP, outside of BMP
#CHECKING = 'Ch€c₭ing 𝚫 𝄠' # b'Ch\xe2\x82\xacc\xe2\x82\xading \xf0\x9d\x9a\xab \xf0\x9d\x84\xa0'
CHECKING = 'Ch€c₭ing' # b'Ch\xe2\x82\xacc\xe2\x82\xading \xf0\x9d\x9a\xab \xf0\x9d\x84\xa0'


def _load_data(storage, many_txns):
    usd = storage.get_commodity(code='USD')
    stock_a_commodity = bb.Commodity(type_=bb.CommodityType.SECURITY, code='A', name='Stock A')
    storage.save_commodity(stock_a_commodity)

    opening_balances = bb.Account(type_=bb.AccountType.EQUITY, commodity=usd, name='Opening Balances')
    storage.save_account(opening_balances)

    checking = bb.Account(type_=bb.AccountType.ASSET, commodity=usd, name=CHECKING)
    storage.save_account(checking)

    savings = bb.Account(type_=bb.AccountType.ASSET, commodity=usd, name='Saving')
    storage.save_account(savings)

    mortgage = bb.Account(type_=bb.AccountType.LIABILITY, commodity=usd, name='Mortgagé')
    storage.save_account(mortgage)
    credit_card = bb.Account(type_=bb.AccountType.LIABILITY, commodity=usd, name='Credit Card')
    storage.save_account(credit_card)

    wages = bb.Account(type_=bb.AccountType.INCOME, commodity=usd, number='200', name='Wagès')
    storage.save_account(wages)

    food = bb.Account(type_=bb.AccountType.EXPENSE, commodity=usd, number='300', name='Food')
    storage.save_account(food)
    restaurants = bb.Account(type_=bb.AccountType.EXPENSE, commodity=usd, number='310', name='Restaurànts', parent=food)
    storage.save_account(restaurants)
    transportation = bb.Account(type_=bb.AccountType.EXPENSE, commodity=usd, number='400', name='Transportation')
    storage.save_account(transportation)
    gas_stations = bb.Account(type_=bb.AccountType.EXPENSE, commodity=usd, number='410', name='Gas Stations', parent=transportation)
    storage.save_account(gas_stations)
    car_insurance = bb.Account(type_=bb.AccountType.EXPENSE, commodity=usd, number='420', name='Car Insurance', parent=transportation)
    storage.save_account(car_insurance)
    housing = bb.Account(type_=bb.AccountType.EXPENSE, commodity=usd, number='500', name='Housing')
    storage.save_account(housing)
    rent = bb.Account(type_=bb.AccountType.EXPENSE, commodity=usd, number='510', name='Rent', parent=housing)
    storage.save_account(rent)
    mortgage_interest = bb.Account(type_=bb.AccountType.EXPENSE, commodity=usd, number='520', name='Mortgage Interest', parent=housing)
    storage.save_account(mortgage_interest)
    medical = bb.Account(type_=bb.AccountType.EXPENSE, commodity=usd, number='600', name='Medical')
    storage.save_account(medical)
    taxes = bb.Account(type_=bb.AccountType.EXPENSE, commodity=usd, number='700', name='Taxes')
    storage.save_account(taxes)

    retirement_401k = bb.Account(type_=bb.AccountType.ASSET, commodity=usd, number='800', name='401k')
    storage.save_account(retirement_401k)
    stock_a = bb.Account(type_=bb.AccountType.SECURITY, commodity=stock_a_commodity, number='805', name='Stock A', parent=retirement_401k)
    storage.save_account(stock_a)

    payee = bb.Payee("Joe's Burgers")
    storage.save_payee(payee)

    storage.save_txn(bb.Transaction(splits={opening_balances: {'amount': '-1000'}, checking: {'amount': 1000}}, txn_date='2018-01-01'))
    storage.save_txn(bb.Transaction(splits={opening_balances: {'amount': '-1000'}, savings: {'amount': 1000}}, txn_date='2018-01-01'))
    storage.save_txn(bb.Transaction(splits={wages: {'amount': '-1000'}, checking: {'amount': 900}, stock_a: {'amount': 100, 'quantity': '5.23'}}, txn_date='2018-01-01'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-10'}, restaurants: {'amount': 10}}, txn_date='2018-01-01', txn_type='123', payee=payee))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-20'}, restaurants: {'amount': 20}}, txn_date='2018-01-02'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-30'}, restaurants: {'amount': 30}}, txn_date='2018-01-04'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-40'}, restaurants: {'amount': 40}}, txn_date='2018-01-06'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-50'}, restaurants: {'amount': 50}}, txn_date='2018-01-07'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-60'}, restaurants: {'amount': 60}}, txn_date='2018-01-08'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '100'}, savings: {'amount': '-100'}}, txn_date='2018-01-09'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-70'}, restaurants: {'amount': 70}}, txn_date='2018-01-10'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-80'}, restaurants: {'amount': 80}}, txn_date='2018-01-11'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-90'}, restaurants: {'amount': 90}}, txn_date='2018-02-11'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-180'}, housing: {'amount': 180}}, txn_date='2018-02-12'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '80.13'}, savings: {'amount': '-80.13'}}, txn_date='2018-02-13'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-50'}, gas_stations: {'amount': 50}}, txn_date='2018-02-14'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-70'}, gas_stations: {'amount': 40}, restaurants: {'amount': 30}}, txn_date='2018-02-15'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-10'}, gas_stations: {'amount': 10}}, txn_date='2018-02-16'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-20'}, gas_stations: {'amount': 20}}, txn_date='2018-02-17'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-40'}, gas_stations: {'amount': 40}}, txn_date='2018-02-18'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-30'}, gas_stations: {'amount': 30}}, txn_date='2018-02-19'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-50'}, gas_stations: {'amount': 50}}, txn_date='2018-02-21'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-70'}, gas_stations: {'amount': 70}}, txn_date='2018-02-23'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '-90'}, gas_stations: {'amount': 90}}, txn_date='2018-02-24'))
    storage.save_txn(bb.Transaction(splits={checking: {'amount': '40'}, savings: {'amount': '-40'}}, txn_date='2018-02-25'))

    if many_txns:
        print('adding 1000 random txns')
        for i in range(1000):
            amt = random.randint(1, 500)
            day = random.randint(1, 30)
            txn = bb.Transaction(splits={checking: {'amount': amt * -1}, restaurants: {'amount': amt}}, txn_date='2018-04-%s' % day)
            storage.save_txn(txn)

    rent_scheduled_txn = bb.ScheduledTransaction(
            name='rent',
            frequency=bb.ScheduledTransactionFrequency.MONTHLY,
            splits={checking: {'amount': -100}, housing: {'amount': 100}},
            next_due_date=date.today()-timedelta(days=1)
        )
    storage.save_scheduled_transaction(rent_scheduled_txn)
    taxes_scheduled_txn = bb.ScheduledTransaction(
            name='taxes',
            frequency=bb.ScheduledTransactionFrequency.YEARLY,
            splits={checking: {'amount': -25}, taxes: {'amount': 25}},
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

