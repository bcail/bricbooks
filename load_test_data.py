from decimal import Decimal as D
import random
from pft import SQLiteStorage, Account, Category, Transaction, Budget, DATA_FILENAME


def _load_data(storage, many_txns):
    a = Account(name='Checking', starting_balance=D(1000))
    storage.save_account(a)

    savings = Account(name='Saving', starting_balance=D(1000))
    storage.save_account(savings)

    c = Category(name='Restaurants')
    storage.save_category(c)
    c2 = Category(name='Gas Stations')
    storage.save_category(c2)
    c3 = Category(name='Housing')
    storage.save_category(c3)

    storage.save_txn(Transaction(account=a, amount=D('-10'), txn_date='2018-01-01', categories=[c]))
    storage.save_txn(Transaction(account=a, amount=D('-20'), txn_date='2018-01-02'))
    storage.save_txn(Transaction(account=a, amount=D('-30'), txn_date='2018-01-04'))
    storage.save_txn(Transaction(account=a, amount=D('-40'), txn_date='2018-01-06'))
    storage.save_txn(Transaction(account=a, amount=D('-50'), txn_date='2018-01-07'))
    storage.save_txn(Transaction(account=a, amount=D('-60'), txn_date='2018-01-08'))
    storage.save_txn(Transaction(account=a, amount=D('100'), txn_date='2018-01-09'))
    storage.save_txn(Transaction(account=a, amount=D('-70'), txn_date='2018-01-10'))
    storage.save_txn(Transaction(account=a, amount=D('-80'), txn_date='2018-01-11'))
    storage.save_txn(Transaction(account=a, amount=D('-90'), txn_date='2018-02-11'))
    storage.save_txn(Transaction(account=a, amount=D('-180'), txn_date='2018-02-12'))
    storage.save_txn(Transaction(account=a, amount=D('80.13'), txn_date='2018-02-13'))
    storage.save_txn(Transaction(account=a, amount=D('-50'), txn_date='2018-02-14'))
    storage.save_txn(Transaction(account=a, amount=D('-70'), txn_date='2018-02-15', categories=[(c, D('15')), (c2, D('55'))]))
    storage.save_txn(Transaction(account=a, amount=D('-10'), txn_date='2018-02-16'))
    storage.save_txn(Transaction(account=a, amount=D('-20'), txn_date='2018-02-17'))
    storage.save_txn(Transaction(account=a, amount=D('-40'), txn_date='2018-02-18'))
    storage.save_txn(Transaction(account=a, amount=D('-30'), txn_date='2018-02-19'))
    storage.save_txn(Transaction(account=a, amount=D('-50'), txn_date='2018-02-21'))
    storage.save_txn(Transaction(account=a, amount=D('-70'), txn_date='2018-02-23'))
    storage.save_txn(Transaction(account=a, amount=D('-90'), txn_date='2018-02-24'))
    storage.save_txn(Transaction(account=a, amount=D('40'), txn_date='2018-02-25'))
    storage.save_txn(Transaction(account=a, amount=D('-75'), txn_date='2018-02-26'))
    storage.save_txn(Transaction(account=a, amount=D('80'), txn_date='2018-02-27'))
    storage.save_txn(Transaction(account=a, amount=D('800'), txn_date='2018-02-28'))
    storage.save_txn(Transaction(account=a, amount=D('-70'), txn_date='2018-03-01'))
    storage.save_txn(Transaction(account=a, amount=D('-10'), txn_date='2018-03-03'))
    storage.save_txn(Transaction(account=a, amount=D('-40'), txn_date='2018-03-04'))
    storage.save_txn(Transaction(account=a, amount=D('-60'), txn_date='2018-03-05'))
    storage.save_txn(Transaction(account=a, amount=D('45'), txn_date='2018-03-17'))
    storage.save_txn(Transaction(account=a, amount=D('89'), txn_date='2018-03-18'))
    storage.save_txn(Transaction(account=a, amount=D('81'), txn_date='2018-03-19'))
    storage.save_txn(Transaction(account=a, amount=D('82'), txn_date='2018-03-14'))

    if many_txns:
        print('adding 1000 random txns')
        for i in range(1000):
            amt = D(random.randint(1, 500))
            day = random.randint(1, 30)
            txn = Transaction(account=a, amount=amt, txn_date='2018-04-%s' % day)
            storage.save_txn(txn)

    storage.save_txn(Transaction(account=savings, amount=D(82), txn_date='2018-03-14'))
    storage.save_txn(Transaction(account=savings, amount=D(95), txn_date='2018-03-15'))

    budget_categories = {
            c: {'amount': D(35), 'carryover': D(0)},
            c2: {'amount': D(70), 'carryover': D(10)},
            c3: {'amount': D(100), 'carryover': D(0)},
        }
    budget = Budget('2018', category_budget_info=budget_categories)
    storage.save_budget(budget)


def main(file_name, many_txns=False):
    storage = SQLiteStorage(file_name)
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
        print('using default file_name: %s' % DATA_FILENAME)
        main(DATA_FILENAME, args.many_txns)

