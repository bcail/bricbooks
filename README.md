bricbooks
=========

![Build Status](https://github.com/bcail/bricbooks/workflows/.github/workflows/ci.yml/badge.svg)


TODO
----
- update Payee for transaction form - change to "Pay to / From"? change it dynamically based on deposit or withdrawal? Update heading for ledger view?
- Ledger - make sure ledger txns are aligned to the top if they don't fill the window (as they're added)
- catch exceptions and give good error messages in the UI
- add scheduled transactions

ARCHITECTURE DECISIONS
----------------------
- [sqlite3 file](https://sqlite.org/appfileformat.html) for data storage
- use Qt (even though it adds a dependency), because it handles Unicode better, and has better performance, than Tkinter (it's also an easy pip install on most computers)
    - on Debian 10, the python3-pyside2.qtcore, python3-pyside2.qtgui, and python3-pyside2.qtwidgets packages provide what's needed (python3-pyside2.qttest for tests)

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

LICENSES
--------
- bricbooks is licensed under the MIT license
- the Windows executables include [LGPL](https://www.gnu.org/licenses/lgpl-3.0.txt) [Qt](https://download.qt.io/official_releases/qt/5.15/5.15.1/single/qt-everywhere-src-5.15.1.zip) and [Pyside2](https://download.qt.io/official_releases/QtForPython/pyside2/PySide2-5.15.1-src/pyside-setup-opensource-src-5.15.1.zip) code

RESOURCES
---------
- [KMyMoney](https://kmymoney.org/) - [Handbook](https://docs.kde.org/stable5/en/extragear-office/kmymoney/index.html)
- [GnuCash](https://www.gnucash.org/) - [Docs](https://www.gnucash.org/docs.phtml)

