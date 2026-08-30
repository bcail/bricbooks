import unicodedata

import bricbooks as bb


# add a char from unicode SMP, outside of BMP
CHECKING = 'Ch€c₭íng 𝚫 𝄠' # b'Ch\xe2\x82\xacc\xe2\x82\xading \xf0\x9d\x9a\xab \xf0\x9d\x84\xa0'
CHECKING_NFD = unicodedata.normalize('NFD', CHECKING)
CHECKING_NFC = unicodedata.normalize('NFC', CHECKING)


def get_test_account(id_=None, commodity=None, name=CHECKING, type_=bb.AccountType.ASSET, number=None, parent=None, other_data=None):
    return bb.Account(id_=id_, commodity=commodity, type_=type_, number=number, name=name, parent=parent, other_data=other_data)


def get_test_txn(**kwargs):
    if 'currency' not in kwargs:
        kwargs['currency'] = {'denominator': 100}
    return bb.Transaction(**kwargs)
