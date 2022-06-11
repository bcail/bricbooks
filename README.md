bricbooks
=========

![Build Status](https://github.com/bcail/bricbooks/workflows/.github/workflows/ci.yml/badge.svg)


ARCHITECTURE DECISIONS
----------------------
- [sqlite3 file](https://sqlite.org/appfileformat.html) for data storage
- use tkinter for GUI: comes as part of Python, so no extra dependencies or pip install needed

PROJECT GOALS
-------------
- easy to install/use on Windows/Mac/Linux
  * no dependencies besides Python
  * one script (.py file) to deploy
- convenient to use
- accurate finances
- good tests

USER TIPS
---------
- To add a starting balance to an account, create an "Opening Balances" Equity account, and make the first transaction a withdrawal from Opening Balances and deposit to the new account.

LICENSES
--------
- bricbooks is licensed under the MIT license

RESOURCES
---------
- [KMyMoney](https://kmymoney.org/) - [Handbook](https://docs.kde.org/stable5/en/extragear-office/kmymoney/index.html)
- [GnuCash](https://www.gnucash.org/) - [Docs](https://www.gnucash.org/docs.phtml)

