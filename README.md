Python Finance Tracking
=======================

[![Build Status](https://travis-ci.com/bcail/python_finance_tracking.svg?branch=master)](https://travis-ci.com/bcail/python_finance_tracking)
[![Build status](https://ci.appveyor.com/api/projects/status/r8ri5uy970a38b36?svg=true)](https://ci.appveyor.com/project/bcail/python-finance-tracking)


TODO
----
- Ledger - make sure ledger txns are aligned to the top if they don't fill the window (as they're added)
- Ledger - new transaction - fix tab order
- Ledger - reload payees list for new transactions after adding one
- Ledger - allow different date forms (ie. m/d/yyyy)
- Ledger - categories box - show expense account user id with name
- Accounts view - new account form should be at the bottom of the screen (accts list should expand as much as possible)
- catch exceptions and give good error messages in the UI
- add scheduled transactions

ARCHITECTURE DECISIONS
----------------------
- use Qt (even though it adds a dependency), because it handles Unicode better, and has better performance, than Tkinter (it's also an easy pip install on most computers)

PROJECT GOALS
-------------
- easy to install on Windows/Mac/Linux
  * no dependencies besides Python
  * one script (.py file) to deploy
- convenient to use
- accurate finances
- good tests

USER TIPS
---------
- To add a starting balance to an account, create an "Opening Balances" Equity account, and make the first transaction a withdrawal from Opening Balances and deposit to the new account.

RESOURCES
---------
- [KMyMoney](https://kmymoney.org/) [Handbook](https://docs.kde.org/stable5/en/extragear-office/kmymoney/index.html)
- [GnuCash](https://www.gnucash.org/) [Docs](https://www.gnucash.org/docs.phtml)

