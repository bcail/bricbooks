from datetime import date
from fractions import Fraction
from functools import partial
import os
import tkinter as tk
from tkinter import ttk
import sys

import bricbooks as bb


class AccountForm:

    def __init__(self, accounts, save_account, update_display, account=None):
        self._accounts = [a for a in accounts if a != account]
        self._save_account = save_account
        self._update_display = update_display
        self._account = account
        #keep map of account types for display
        self._account_types = {}
        for type_ in bb.AccountType:
            self._account_types[type_.name] = type_

    def get_widget(self):
        self.form = tk.Toplevel()
        for col, label in [(0, 'Type'), (1, 'Number'), (2, 'Name'), (3, 'Parent')]:
            ttk.Label(master=self.form, text=label).grid(row=0, column=col)
        self.account_type_combo = ttk.Combobox(master=self.form)
        selected = 0
        for index, type_ in enumerate(bb.AccountType):
            if self._account and self._account.type == type_:
                selected = index
        self.account_type_combo['values'] = list(self._account_types.keys())
        self.account_type_combo.current(selected)
        self.number_entry = ttk.Entry(master=self.form)
        self.name_entry = ttk.Entry(master=self.form)
        self.parent_combo = ttk.Combobox(master=self.form)
        account_values = ['']
        selected = 0
        for index, account in enumerate(self._accounts):
            account_values.append(str(account))
            if self._account and self._account.parent == account:
                selected = index + 1
        self.parent_combo['values'] = account_values
        self.parent_combo.current(selected)
        if self._account:
            self.number_entry.insert(0, self._account.number or '')
            self.name_entry.insert(0, self._account.name)
        self.account_type_combo.grid(row=1, column=0, sticky=(tk.N, tk.W, tk.S))
        self.number_entry.grid(row=1, column=1, sticky=(tk.N, tk.W, tk.S))
        self.name_entry.grid(row=1, column=2, sticky=(tk.N, tk.W, tk.S))
        self.parent_combo.grid(row=1, column=3, sticky=(tk.N, tk.W, tk.S))
        self.save_button = ttk.Button(master=self.form, text='Save', command=self._handle_save)
        self.save_button.grid(row=1, column=4, sticky=(tk.N, tk.W, tk.S))
        return self.form

    def _handle_save(self):
        id_ = None
        if self._account:
            id_ = self._account.id
        type_ = self._account_types[self.account_type_combo.get()]
        number = self.number_entry.get()
        name = self.name_entry.get()
        parent_index = self.parent_combo.current()
        parent_id=None
        if parent_index != 0:
            parent = self._accounts[parent_index-1]
            if self._account != parent:
                parent_id = parent.id
        self._save_account(id_=id_, type_=type_, number=number, name=name, parent_id=parent_id)
        self.form.destroy()
        self._update_display()


class AccountsDisplay:

    def __init__(self, master, engine):
        self._master = master
        self._engine = engine
        self.tree = None
        self.frame = None

    def _show_accounts(self):
        if self.tree:
            self.tree.destroy()

        columns = ('type', 'number', 'name', 'parent')

        self.tree = ttk.Treeview(master=self.frame, columns=columns, show='headings')
        self.tree.heading('type', text='Type')
        self.tree.heading('number', text='Number')
        self.tree.heading('name', text='Name')
        self.tree.heading('parent', text='Parent')

        accounts = self._engine.get_accounts()
        for account in accounts:
            if account.parent:
                parent = account.parent.name
            else:
                parent = ''
            values = (account.type.name, account.number or '', account.name, parent)
            self.tree.insert(parent='', index=tk.END, iid=account.id, values=values)

        self.tree.bind('<Button-1>', self._item_selected)
        self.tree.grid(row=1, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

    def get_widget(self):
        self.frame = ttk.Frame(master=self._master)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(1, weight=1)

        self.add_button = ttk.Button(master=self.frame, text='New Account', command=self._open_new_account_form)
        self.add_button.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S))

        self._show_accounts()

        return self.frame

    def _open_new_account_form(self):
        accounts = self._engine.get_accounts()
        self.add_account_form = AccountForm(accounts, save_account=self._engine.save_account, update_display=self._show_accounts)
        widget = self.add_account_form.get_widget()
        widget.grid()

    def _item_selected(self, event):
        accounts = self._engine.get_accounts()
        account_id = int(self.tree.identify_row(event.y))
        account = self._engine.get_account(id_=account_id)
        self.edit_account_form = AccountForm(accounts, save_account=self._engine.save_account,
                update_display=self._show_accounts, account=account)
        widget = self.edit_account_form.get_widget()
        widget.grid()


class SplitTransactionEditor:

    def __init__(self, all_accounts, initial_txn_splits, save_splits):
        self._all_accounts = all_accounts
        self._initial_txn_splits = initial_txn_splits
        self._save_splits = save_splits
        self._final_txn_splits = {}
        self._entries = {}
        self._show_split_editor()

    def _get_txn_splits(self):
        for entry, account in self._entries.values():
            text = entry.get()
            if text:
                self._final_txn_splits[account] = {'amount': text}
        self._save_splits(self._final_txn_splits)
        self.form.destroy()

    def _show_split_editor(self):
        self.form = tk.Toplevel()
        row = 0
        for account in self._all_accounts:
            ttk.Label(master=self.form, text=str(account)).grid(row=row, column=0)
            amount_entry = ttk.Entry(master=self.form)
            for acc, split_info in self._initial_txn_splits.items():
                amt = split_info['amount']
                if acc == account:
                    amount_entry.insert(0, bb.amount_display(amt))
            self._entries[account.id] = (amount_entry, account)
            amount_entry.grid(row=row, column=1)
            row += 1
        self.ok_button = ttk.Button(master=self.form, text='Done', command=self._get_txn_splits)
        self.ok_button.grid(row=row, column=0)
        self.cancel_button = ttk.Button(master=self.form, text='Cancel', command=self.form.destroy)
        self.cancel_button.grid(row=row, column=1)
        self.form.grid()


class TransferAccountsDisplay:

    def __init__(self, master, accounts=None, main_account=None, transaction=None):
        self._master = master
        self._accounts = accounts
        self._main_account = main_account
        self._transaction = transaction
        self._widget = ttk.Frame(master=self._master)
        self.transfer_accounts_combo = ttk.Combobox(master=self._widget)
        self._transfer_accounts_display_list = ['----------']
        self._transfer_accounts_list = [None]
        current_index = 0
        index = 0
        for account in self._accounts:
            if account != self._main_account:
                #find correct account in the list if txn has just two splits
                if self._transaction and len(self._transaction.splits.keys()) == 2:
                    if account in self._transaction.splits:
                         current_index = index + 1
                self._transfer_accounts_display_list.append(str(account))
                self._transfer_accounts_list.append(account)
                index += 1
        self._transfer_accounts_display_list.append('multiple')
        self._transfer_accounts_list.append({})
        self.transfer_accounts_combo['values'] = self._transfer_accounts_display_list
        if self._transaction:
            if len(self._transaction.splits.keys()) > 2:
                current_index = len(self._transfer_accounts_display_list) - 1
            self.transfer_accounts_combo.current(current_index)
        self.transfer_accounts_combo.grid(row=0, column=0, sticky=(tk.N, tk.S))
        # self._multiple_entry_index = index + 1
        # current_categories = []
        # if txn and len(txn.splits.keys()) > 2:
        #     current_categories = txn.splits
        #     current_index = self._multiple_entry_index
        # self._categories_combo.addItem('multiple', current_categories)
        # self._categories_combo.setCurrentIndex(current_index)
        # layout.addWidget(self._categories_combo, 0, 0)
        self.split_button = ttk.Button(master=self._widget, text='Split', command=self._show_splits_editor)
        self.split_button.grid(row=1, column=0, sticky=(tk.N, tk.S))
        # txn_id = None
        # if txn:
        #     txn_id = txn.id
        # self.split_button.clicked.connect(self._split_transactions)
        # layout.addWidget(self.split_button)
        # self._widget = QtWidgets.QWidget()
        # self._widget.setLayout(layout)

    def _show_splits_editor(self):
        initial_txn_splits = {}
        if self._transaction:
            initial_txn_splits = self._transaction.splits
        self.splits_editor = SplitTransactionEditor(self._accounts, initial_txn_splits, save_splits=self._save_splits)

    def _save_splits(self, txn_splits):
        if txn_splits:
            self.transfer_accounts_combo.current(len(self._transfer_accounts_display_list)-1)
            self._multiple_splits = txn_splits

    def get_transfer_accounts(self):
        transfer_account_index = self.transfer_accounts_combo.current()
        if transfer_account_index == (len(self._transfer_accounts_display_list) - 1):
            splits = self._multiple_splits
        else:
            splits = self._transfer_accounts_list[transfer_account_index]
        #remove main account split (if present), because that comes from withdrawal/deposit fields
        if isinstance(splits, dict):
            splits.pop(self._main_account, None)
        return splits

    def get_widget(self):
        return self._widget


class TransactionForm:

    def __init__(self, accounts, account, payees, save_transaction, update_display, transaction=None):
        self._accounts = accounts
        self._account = account
        self._payees = payees
        self._save_transaction = save_transaction
        self._update_display = update_display
        self._transaction = transaction

    def get_widget(self):
        self.form = tk.Toplevel()
        self.form.columnconfigure(0, weight=1)
        self.form.columnconfigure(1, weight=1)
        self.form.columnconfigure(2, weight=2)
        self.form.columnconfigure(3, weight=3)
        self.form.columnconfigure(4, weight=1)
        self.form.columnconfigure(5, weight=1)
        self.form.columnconfigure(6, weight=1)
        self.form.columnconfigure(7, weight=2)
        self.form.columnconfigure(8, weight=1)
        for col, label in [(0, 'Type'), (1, 'Date'), (2, 'Payee'), (3, 'Description'), (4, 'Status')]:
            ttk.Label(master=self.form, text=label).grid(row=0, column=col)
        for col, label in [(0, 'Withdrawal'), (1, 'Deposit'), (2, 'Transfer Accounts')]:
            ttk.Label(master=self.form, text=label).grid(row=2, column=col)
        tds = {}
        if self._transaction:
            tds = bb.get_display_strings_for_ledger(self._account, self._transaction)
        self.type_entry = ttk.Entry(master=self.form)
        self.date_entry = ttk.Entry(master=self.form)
        self.payee_combo = ttk.Combobox(master=self.form)
        payee_values = ['']
        payee_index = 0
        for index, payee in enumerate(self._payees):
            payee_values.append(payee.name)
            if self._transaction and payee.name == tds['payee']:
                payee_index = index + 1 #because of first empty item
        self.payee_combo['values'] = payee_values
        self.description_entry = ttk.Entry(master=self.form)
        if self._transaction:
            self.type_entry.insert(0, tds['txn_type'])
            self.date_entry.insert(0, tds['txn_date'])
            self.payee_combo.current(payee_index)
            self.description_entry.insert(0, tds['description'])
        self.status_combo = ttk.Combobox(master=self.form)
        status_values = ['', bb.Transaction.CLEARED, bb.Transaction.RECONCILED]
        self.status_combo['values'] = status_values
        self.withdrawal_entry = ttk.Entry(master=self.form)
        self.deposit_entry = ttk.Entry(master=self.form)
        if self._transaction:
            for index, status in enumerate(status_values):
                try:
                    if self._transaction.splits[self._account].get('status') == status:
                        self.status_combo.current(index)
                except AttributeError: #ScheduledTxn doesn't have a status
                    pass
            self.withdrawal_entry.insert(0, tds['withdrawal'])
            self.deposit_entry.insert(0, tds['deposit'])
        self.transfer_accounts_display = TransferAccountsDisplay(
                master=self.form,
                accounts=self._accounts,
                main_account=self._account,
                transaction=self._transaction
            )
        self.transfer_accounts_widget = self.transfer_accounts_display.get_widget()
        self.type_entry.grid(row=1, column=0, sticky=(tk.N, tk.S))
        self.date_entry.grid(row=1, column=1, sticky=(tk.N, tk.S))
        self.payee_combo.grid(row=1, column=2, sticky=(tk.N, tk.S))
        self.description_entry.grid(row=1, column=3, sticky=(tk.N, tk.S))
        self.status_combo.grid(row=1, column=4, sticky=(tk.N, tk.S))
        self.withdrawal_entry.grid(row=3, column=0, sticky=(tk.N, tk.S))
        self.deposit_entry.grid(row=3, column=1, sticky=(tk.N, tk.S))
        self.transfer_accounts_widget.grid(row=3, column=2, sticky=(tk.N, tk.S))
        self.save_button = ttk.Button(master=self.form, text='Save', command=self._handle_save)
        self.save_button.grid(row=3, column=4, sticky=(tk.N, tk.S))
        return self.form

    def _handle_save(self):
        id_ = None
        if self._transaction:
            id_ = self._transaction.id
        kwargs = {
            'id_': id_,
            'account': self._account,
            'txn_type': self.type_entry.get(),
            'deposit': self.deposit_entry.get(),
            'withdrawal': self.withdrawal_entry.get(),
            'txn_date': self.date_entry.get(),
            'payee': self.payee_combo.get(),
            'description': self.description_entry.get(),
            'status': self.status_combo.get(),
            'categories': self.transfer_accounts_display.get_transfer_accounts(),
        }
        transaction = bb.Transaction.from_user_info(**kwargs)
        self._save_transaction(transaction)
        self.form.destroy()
        self._update_display()


class LedgerDisplay:

    def __init__(self, master, accounts, current_account, show_ledger, engine):
        if not current_account:
            raise Exception('must pass current_account into LedgerDisplay')
        self._master = master
        self.show_ledger = show_ledger
        self._accounts = accounts
        self._account = current_account
        self._engine = engine
        self.txns_widget = None

    def _get_txns(self):
        accounts = [self._account]
        # if self._filter_account_id:
        #     accounts.append(self.engine.get_account(id_=self._filter_account_id))
        # return self.engine.get_transactions(accounts=accounts, status=self._status.strip(), query=self._filter_text.strip())
        return self._engine.get_transactions(accounts=accounts)

    def _show_transactions(self):
        master = self.frame
        account = self._account
        columns = ('type', 'date', 'payee', 'description', 'status', 'withdrawal', 'deposit', 'balance', 'transfer account')

        if self.txns_widget:
            self.txns_widget.destroy()

        self.txns_widget = ttk.Treeview(master=master, columns=columns, show='headings')
        self.txns_widget.heading('type', text='Type')
        self.txns_widget.column('type', width=50, anchor='center')
        self.txns_widget.heading('date', text='Date')
        self.txns_widget.column('date', width=100, anchor='center')
        self.txns_widget.heading('payee', text='Payee')
        self.txns_widget.column('payee', width=100, anchor='center')
        self.txns_widget.heading('description', text='Description')
        self.txns_widget.column('description', width=100, anchor='center')
        self.txns_widget.heading('status', text='Status')
        self.txns_widget.column('status', width=100, anchor='center')
        self.txns_widget.heading('withdrawal', text='Withdrawal')
        self.txns_widget.column('withdrawal', width=100, anchor='center')
        self.txns_widget.heading('deposit', text='Deposit')
        self.txns_widget.column('deposit', width=100, anchor='center')
        self.txns_widget.heading('balance', text='Balance')
        self.txns_widget.column('balance', width=100, anchor='center')
        self.txns_widget.heading('transfer account', text='Transfer Account')
        self.txns_widget.column('transfer account', width=100, anchor='center')

        for txn in self._get_txns():
            tds = bb.get_display_strings_for_ledger(account, txn)
            values = (tds['txn_type'], tds['txn_date'], tds['payee'], tds['description'], tds['status'],
                      tds['withdrawal'], tds['deposit'], tds.get('balance', ''), tds['categories'])
            self.txns_widget.insert('', tk.END, iid=txn.id, values=values)

        self.txns_widget.bind('<Button-1>', self._item_selected)
        self.txns_widget.grid(row=1, column=0, columnspan=2, sticky=(tk.N, tk.W, tk.S, tk.E))

    def get_widget(self):
        self.frame = ttk.Frame(master=self._master)
        self.frame.columnconfigure(1, weight=1)
        self.frame.rowconfigure(1, weight=1)

        self.account_select_combo = ttk.Combobox(master=self.frame)
        selected = -1
        account_values = []
        for index, account in enumerate(self._accounts):
            account_values.append(str(account))
            if account == self._account:
                selected = index
        self.account_select_combo['values'] = account_values
        self.account_select_combo.current(selected)
        self.account_select_combo.bind('<<ComboboxSelected>>', self._update_account)
        self.account_select_combo.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S))

        self.add_button = ttk.Button(master=self.frame, text='New Transaction', command=self._open_new_transaction_form)
        self.add_button.grid(row=0, column=1, sticky=(tk.N, tk.W, tk.S))

        self._show_transactions()
        return self.frame

    def _update_account(self, event):
        current_account_index = self.account_select_combo.current()
        self._account = self._accounts[current_account_index]
        self._show_transactions()

    def _open_new_transaction_form(self):
        accounts = self._engine.get_accounts()
        payees = self._engine.get_payees()
        self.add_transaction_form = TransactionForm(accounts, account=self._account, payees=payees, save_transaction=self._engine.save_transaction, update_display=self._show_transactions)
        widget = self.add_transaction_form.get_widget()
        widget.grid()

    def _item_selected(self, event):
        txn_id = int(self.txns_widget.identify_row(event.y))
        transaction = self._engine.get_transaction(id_=txn_id)
        accounts = self._engine.get_accounts()
        payees = self._engine.get_payees()
        self.edit_transaction_form = TransactionForm(accounts, account=self._account, payees=payees, save_transaction=self._engine.save_transaction, update_display=self._show_transactions, transaction=transaction)
        widget = self.edit_transaction_form.get_widget()
        widget.grid()


class BudgetForm:
    '''Handle editing an existing budget or creating a new one'''

    def __init__(self, budget=None, accounts=None, save_budget=None):
        if budget and accounts:
            raise BudgetError('pass budget or accounts, not both')
        self._budget = budget
        self._widgets = {'budget_data': {}}
        self._save_budget = save_budget
        self._accounts = accounts
        if self._budget:
            self._budget_data = self._budget.get_budget_data()
        else:
            self._budget_data = {}
            for account in self._accounts:
                self._budget_data[account] = {}

    def get_widget(self):
        self._form = tk.Toplevel()
        self.content = ttk.Frame(master=self._form)

        ttk.Label(master=self.content, text='Start Date').grid(row=0, column=0)
        ttk.Label(master=self.content, text='End Date').grid(row=0, column=1)
        self.start_date_entry = ttk.Entry(master=self.content)
        self.start_date_entry.grid(row=1, column=0)
        self.end_date_entry = ttk.Entry(master=self.content)
        self.end_date_entry.grid(row=1, column=1)

        return self._form


class BudgetDisplay:

    def __init__(self, master, engine, current_budget):
        self._master = master
        self._engine = engine
        if not current_budget:
            budgets = self._engine.get_budgets()
            if budgets:
                current_budget = budgets[0]
        self._current_budget = current_budget
        self._report_data = []
        if self._current_budget:
            self._budget_report = self._current_budget.get_report_display(current_date=date.today())
            for info in self._budget_report['income']:
                self._report_data.append(info)
            for info in self._budget_report['expense']:
                self._report_data.append(info)
        else:
            self._budget_report = {}

    def get_widget(self):
        self.frame = ttk.Frame(master=self._master)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(1, weight=1)

        self.add_button = ttk.Button(master=self.frame, text='New Budget', command=partial(self._open_form, budget=None))
        self.add_button.grid(row=0, column=0, sticky=(tk.W,))

        columns = ('account', 'amount', 'income', 'carryover', 'total budget', 'spent', 'remaining', 'remaining percent', 'current status')

        self.tree = ttk.Treeview(self.frame, columns=columns, show='headings')
        self.tree.heading('account', text='Account')
        self.tree.column('account', width=100, anchor='center')
        self.tree.heading('amount', text='Amount')
        self.tree.column('amount', width=100, anchor='center')
        self.tree.heading('income', text='Income')
        self.tree.column('income', width=100, anchor='center')
        self.tree.heading('carryover', text='Carryover')
        self.tree.column('carryover', width=100, anchor='center')
        self.tree.heading('total budget', text='Total Budget')
        self.tree.column('total budget', width=100, anchor='center')
        self.tree.heading('spent', text='Spent')
        self.tree.column('spent', width=100, anchor='center')
        self.tree.heading('remaining', text='Remaining')
        self.tree.column('remaining', width=100, anchor='center')
        self.tree.heading('remaining percent', text='Remaining Percent')
        self.tree.column('remaining percent', width=100, anchor='center')
        self.tree.heading('current status', text='Current Status')
        self.tree.column('current status', width=100, anchor='center')

        for row in self._report_data:
            values = row.get('name', ''), row.get('amount', ''), row.get('income', ''), row.get('carryover', ''), row.get('total_budget', ''), row.get('spent', ''), row.get('remaining', ''), row.get('remaining_percent', ''), row.get('current_status', '')
            self.tree.insert('', tk.END, values=values)

        self.tree.grid(row=1, column=0, sticky=(tk.N, tk.S, tk.W, tk.E))

        return self.frame

    def _open_form(self, budget):
        if budget:
            self.budget_form = BudgetForm(budget=budget, save_budget=self._save_budget_and_reload)
        else:
            income_and_expense_accounts = self._engine.get_accounts(types=[bb.AccountType.INCOME, bb.AccountType.EXPENSE])
            self.budget_form = BudgetForm(accounts=income_and_expense_accounts, save_budget=partial(self._save_budget_and_reload, new_budget=True))
        widget = self.budget_form.get_widget()
        widget.grid()

    def _save_budget_and_reload(self, budget, new_budget=False):
        pass


class ScheduledTransactionForm:

    def __init__(self, accounts, payees, save_scheduled_transaction, scheduled_transaction=None):
        self._accounts = accounts
        self._payees = payees
        self._scheduled_transaction = scheduled_transaction
        self._save_scheduled_txn = save_scheduled_transaction

    def get_widget(self):
        self._form = tk.Toplevel()
        self.content = ttk.Frame(master=self._form)

        ttk.Label(master=self.content, text='Name').grid(row=0, column=0)
        self.name_entry = ttk.Entry(master=self.content)
        if self._scheduled_transaction:
            self.name_entry.insert(0, self._scheduled_transaction.name)
        self.name_entry.grid(row=0, column=1)
        # self._widgets['name'] = name_entry
        #layout.addWidget(name_entry, 0, 1)
        ttk.Label(master=self.content, text='Frequency').grid(row=1, column=0)
        self.frequency_combo = ttk.Combobox(master=self.content)
        # frequency_entry = QtWidgets.QComboBox()
        frequency_index = 0
        self.frequency_values = []
        self.frequencies = []
        for index, frequency in enumerate(bb.ScheduledTransactionFrequency):
            self.frequency_values.append(frequency.name)
            self.frequencies.append(frequency)
            #frequency_entry.addItem(frequency.name, frequency)
            if self._scheduled_transaction and frequency == self._scheduled_transaction.frequency:
                frequency_index = index
        self.frequency_combo['values'] = self.frequency_values
        if self._scheduled_transaction:
            self.frequency_combo.current(frequency_index)
        #self._widgets['frequency'] = frequency_entry
        #layout.addWidget(frequency_entry, 1, 1)
        self.frequency_combo.grid(row=1, column=1)
        ttk.Label(master=self.content, text='Next Due Date').grid(row=2, column=0)
        self.next_due_date_entry = ttk.Entry(master=self.content)
        if self._scheduled_transaction:
            self.next_due_date_entry.insert(0, str(self._scheduled_transaction.next_due_date))
        #self._widgets['next_due_date'] = next_due_date_entry
        self.next_due_date_entry.grid(row=2, column=1)

        ttk.Label(master=self.content, text='Payee').grid(row=3, column=0)
        self.payee_combo = ttk.Combobox(master=self.content)
        #payee_entry.setEditable(True)
        #self.payee_combo.addItem('')
        payee_values = [p.name for p in self._payees]
        payee_values.insert(0, '')
        payee_index = 0
        for index, payee in enumerate(self._payees):
            #payee_entry.addItem(payee.name, payee)
            if self._scheduled_transaction and self._scheduled_transaction.payee and self._scheduled_transaction.payee.name == payee.name:
                payee_index = index + 1 #because of first empty item
        self.payee_combo['values'] = payee_values
        if self._scheduled_transaction:
            self.payee_combo.current(payee_index)
        #self._widgets['payee'] = payee_entry
        self.payee_combo.grid(row=3, column=1)

        account = deposit = withdrawal = None
        if self._scheduled_transaction:
            account = list(self._scheduled_transaction.splits.keys())[0]
            amount = self._scheduled_transaction.splits[account]['amount']
            if amount > 0:
                deposit = bb.amount_display(amount)
            else:
                withdrawal = bb.amount_display(amount * Fraction(-1))

        ttk.Label(master=self.content, text='Account').grid(row=4, column=0)
        self.account_combo = ttk.Combobox(master=self.content)
        account_values = [a.name for a in self._accounts]
        self.account_combo['values'] = account_values
        account_index = -1
        for index, acct in enumerate(self._accounts):
            #account_entry.addItem(acct.name, acct)
            if account and account == acct:
                account_index = index
        if account:
            self.account_combo.current(account_index)
        #self._widgets['account'] = account_entry
        self.account_combo.grid(row=4, column=1)
        ttk.Label(master=self.content, text='Withdrawal').grid(row=5, column=0)
        self.withdrawal_entry = ttk.Entry(master=self.content)
        if withdrawal:
            self.withdrawal_entry.insert(0, withdrawal)
        #self._widgets['withdrawal'] = withdrawal_entry
        self.withdrawal_entry.grid(row=5, column=1)
        ttk.Label(master=self.content, text='Deposit').grid(row=6, column=0)
        self.deposit_entry = ttk.Entry(master=self.content)
        if deposit:
            self.deposit_entry.insert(0, deposit)
        #self._widgets['deposit'] = deposit_entry
        self.deposit_entry.grid(row=6, column=1)
        ttk.Label(master=self.content, text='Categories').grid(row=7, column=0)
        self.transfer_accounts_display = TransferAccountsDisplay(
                master=self.content,
                accounts=self._accounts,
                transaction=self._scheduled_transaction,
                main_account=account
            )
        #self._widgets['accounts_display'] = txn_accounts_display
        self.transfer_accounts_display.get_widget().grid(row=7, column=1)
        self.save_button = ttk.Button(master=self.content, text='Save', command=self._save)
        #save_button.clicked.connect(self._save)
        #self._widgets['save_btn'] = save_button
        self.save_button.grid(row=8, column=0)

        self.content.grid()

        return self._form

    def _save(self):
        payee = self.payee_combo.get()
        account_index = self.account_combo.current()
        account = self._accounts[account_index]
        deposit = self.deposit_entry.get()
        withdrawal = self.withdrawal_entry.get()
        categories = self.transfer_accounts_display.get_transfer_accounts()
        splits = bb.Transaction.splits_from_user_info(
                account=account,
                deposit=deposit,
                withdrawal=withdrawal,
                input_categories=categories
            )
        if self._scheduled_transaction:
            id_ = self._scheduled_transaction.id
        else:
            id_ = None
        st = bb.ScheduledTransaction(
                name=self.name_entry.get(),
                frequency=self.frequencies[self.frequency_combo.current()],
                next_due_date=self.next_due_date_entry.get(),
                splits=splits,
                payee=payee,
                id_=id_,
            )
        self._save_scheduled_txn(scheduled_txn=st)
        self._form.destroy()


class ScheduledTransactionsDisplay:

    def __init__(self, master, engine):
        self._master = master
        self._engine = engine

    def get_widget(self):
        self.frame = ttk.Frame(master=self._master)
        self.frame.columnconfigure(1, weight=1)
        self.frame.rowconfigure(1, weight=1)

        self.add_button = ttk.Button(master=self.frame, text='New Scheduled Transaction', command=self._open_new_form)
        self.add_button.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S))

        columns = ('name', 'frequency', 'next_due_date', 'payee', 'splits')

        self.tree = ttk.Treeview(self.frame, columns=columns, show='headings')
        self.tree.heading('name', text='Name')
        self.tree.column('name', width=50, anchor='center')
        self.tree.heading('frequency', text='Frequency')
        self.tree.column('frequency', width=50, anchor='center')
        self.tree.heading('next_due_date', text='Next Due Date')
        self.tree.column('next_due_date', width=50, anchor='center')
        self.tree.heading('payee', text='Payee')
        self.tree.column('payee', width=50, anchor='center')
        self.tree.heading('splits', text='Splits')
        self.tree.column('splits', width=250, anchor='center')

        scheduled_txns = self._engine.get_scheduled_transactions()
        for scheduled_txn in scheduled_txns:
            if scheduled_txn.payee:
                payee = scheduled_txn.payee.name
            else:
                payee = ''
            values = (scheduled_txn.name, scheduled_txn.frequency.value, str(scheduled_txn.next_due_date), payee, bb.splits_display(scheduled_txn.splits))
            self.tree.insert('', tk.END, iid=scheduled_txn.id, values=values)

        self.tree.bind('<Button-1>', self._item_selected)

        self.tree.grid(row=1, column=0, columnspan=2, sticky=(tk.N, tk.S, tk.E, tk.W))

        return self.frame

    def _open_new_form(self):
        accounts = self._engine.get_accounts()
        payees = self._engine.get_payees()
        self.new_form = ScheduledTransactionForm(accounts, payees=payees,
                save_scheduled_transaction=self._engine.save_scheduled_transaction)
        widget = self.new_form.get_widget()
        widget.grid()

    def _item_selected(self, event):
        scheduled_transaction_id = int(self.tree.identify_row(event.y))
        scheduled_transaction = self._engine.get_scheduled_transaction(id_=scheduled_transaction_id)
        accounts = self._engine.get_accounts()
        payees = self._engine.get_payees()
        self.edit_form = ScheduledTransactionForm(accounts, payees=payees,
                save_scheduled_transaction=self._engine.save_scheduled_transaction,
                scheduled_transaction=scheduled_transaction)
        widget = self.edit_form.get_widget()
        widget.grid()


class GUI_TK:

    def __init__(self, file_name):
        self.root = tk.Tk()
        self.root.title(bb.TITLE)

        w, h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry("%dx%d+0+0" % (w, h))

        #make sure root container is set to resize properly
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        #this frame will contain everything the user sees
        self.content_frame = ttk.Frame(master=self.root)
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.rowconfigure(1, weight=1)
        self.content_frame.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

        if file_name:
            self._load_db(file_name)
        else:
            self._show_splash()

    def _show_splash(self):
        content = ttk.Frame(master=self.content_frame)
        content.grid()
        new_button = ttk.Button(master=content, text='New...', command=partial(self._new_file, splash_screen=content))
        new_button.grid(row=0, column=0)
        open_button = ttk.Button(master=content, text='Open...', command=partial(self._open_file, splash_screen=content))
        open_button.grid(row=1, column=0)
        files = bb.get_files(bb.CUR_DIR)
        for index, f in enumerate(files, start=2):
            button = ttk.Button(master=content, text=f.name, command=partial(self._handle_splash_selection, file_name=str(f), splash_screen=content))
            button.grid(row=index, column=0)

    def _new_file(self, splash_screen):
        from tkinter import filedialog as fd
        d = fd.FileDialog(master=splash_screen)
        file_name = d.go()
        if file_name:
            self._handle_splash_selection(file_name=file_name, splash_screen=splash_screen)

    def _open_file(self, splash_screen):
        from tkinter import filedialog as fd
        file_names = fd.askopenfilenames()
        if file_names:
            self._handle_splash_selection(file_name=file_names[0], splash_screen=splash_screen)

    def _handle_splash_selection(self, file_name, splash_screen):
        splash_screen.destroy()
        self._load_db(file_name)

    def _load_db(self, file_name):
        try:
            self._engine = bb.Engine(file_name)
        except bb.InvalidStorageFile as e:
            if 'file is not a database' in str(e):
                print(msg='File %s is not a database' % file_name)
                sys.exit(1)
            raise

        self._action_buttons_frame = self._init_action_buttons_frame(self.content_frame)
        self._action_buttons_frame.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

        self.main_frame = None

        accounts = self._engine.get_accounts()
        if accounts:
            self._show_ledger()
        else:
            self._show_accounts()

    def _init_action_buttons_frame(self, master):
        frame = ttk.Frame(master=master)
        self.accounts_button = ttk.Button(master=frame, text='Accounts', command=self._show_accounts)
        self.accounts_button.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S))
        self.ledger_button = ttk.Button(master=frame, text='Ledger', command=self._show_ledger)
        self.ledger_button.grid(row=0, column=1, sticky=(tk.N, tk.W, tk.S))
        self.budget_button = ttk.Button(master=frame, text='Budget', command=self._show_budget)
        self.budget_button.grid(row=0, column=2, sticky=(tk.N, tk.W, tk.S))
        self.scheduled_transactions_button = ttk.Button(master=frame, text='Scheduled Transactions', command=self._show_scheduled_transactions)
        self.scheduled_transactions_button.grid(row=0, column=3, sticky=(tk.N, tk.W, tk.S))
        return frame

    def _update_action_buttons(self, display):
        self.accounts_button['state'] = tk.NORMAL
        self.ledger_button['state'] = tk.NORMAL
        self.budget_button['state'] = tk.NORMAL
        self.scheduled_transactions_button['state'] = tk.NORMAL
        if display == 'accounts':
            self.accounts_button['state'] = tk.DISABLED
        elif display == 'budget':
            self.budget_button['state'] = tk.DISABLED
        elif display == 'scheduled_transactions':
            self.scheduled_transactions_button['state'] = tk.DISABLED
        else:
            self.ledger_button['state'] = tk.DISABLED

    def _show_accounts(self):
        if self.main_frame:
            self.main_frame.destroy()
        self._update_action_buttons(display='accounts')
        self.accounts_display = AccountsDisplay(master=self.content_frame, engine=self._engine)
        self.main_frame = self.accounts_display.get_widget()
        self.main_frame.grid(row=1, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

    def _show_ledger(self, current_account=None):
        if self.main_frame:
            self.main_frame.destroy()
        accounts = self._engine.get_accounts()
        if not current_account:
            current_account = accounts[0]
        self._update_action_buttons(display='ledger')
        self.ledger_display = LedgerDisplay(master=self.content_frame, accounts=accounts, current_account=current_account, show_ledger=self._show_ledger, engine=self._engine)
        self.main_frame = self.ledger_display.get_widget()
        self.main_frame.grid(row=1, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

    def _show_budget(self, current_budget=None):
        if self.main_frame:
            self.main_frame.destroy()
        self._update_action_buttons(display='budget')
        self.budget_display = BudgetDisplay(master=self.content_frame, engine=self._engine, current_budget=current_budget)
        self.main_frame = self.budget_display.get_widget()
        self.main_frame.grid(row=1, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

    def _show_scheduled_transactions(self):
        if self.main_frame:
            self.main_frame.destroy()
        self._update_action_buttons(display='scheduled_transactions')
        self.scheduled_transactions_display = ScheduledTransactionsDisplay(master=self.content_frame, engine=self._engine)
        self.main_frame = self.scheduled_transactions_display.get_widget()
        self.main_frame.grid(row=1, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))


if __name__ == '__main__':
    args = bb.parse_args()

    if args.file_name and not os.path.exists(args.file_name):
        raise Exception('no such file: "%s"' % args.file_name)

    app = GUI_TK(args.file_name)
    app.root.mainloop()
