Python Finance Tracking
=======================

[![Build Status](https://travis-ci.com/bcail/python_finance_tracking.svg?branch=master)](https://travis-ci.com/bcail/python_finance_tracking)
[![Build status](https://ci.appveyor.com/api/projects/status/r8ri5uy970a38b36?svg=true)](https://ci.appveyor.com/project/bcail/python-finance-tracking)


TODO
----
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

