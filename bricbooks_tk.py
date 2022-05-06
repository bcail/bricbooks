from datetime import date
import os
import tkinter as tk
from tkinter import ttk

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
        account = self._save_account(id_=id_, type_=type_, number=number, name=name,
                parent_id=parent_id)
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


class LedgerDisplay:

    def __init__(self, master, accounts, current_account, show_ledger, engine):
        self._master = master
        self.show_ledger = show_ledger
        self.accounts = accounts
        self.account = current_account
        self.engine = engine

    def _get_txns(self):
        accounts = [self.account]
        # if self._filter_account_id:
        #     accounts.append(self.engine.get_account(id_=self._filter_account_id))
        # return self.engine.get_transactions(accounts=accounts, status=self._status.strip(), query=self._filter_text.strip())
        return self.engine.get_transactions(accounts=accounts)

    def get_widget(self):
        columns = ('type', 'date', 'payee', 'description', 'status', 'withdrawal', 'deposit', 'balance', 'transfer account')

        tree = ttk.Treeview(self._master, columns=columns, show='headings')
        tree.heading('type', text='Type')
        tree.column('type', width=100, anchor='center')
        tree.heading('date', text='Date')
        tree.column('date', width=100, anchor='center')
        tree.heading('payee', text='Payee')
        tree.column('payee', width=100, anchor='center')
        tree.heading('description', text='Description')
        tree.column('description', width=100, anchor='center')
        tree.heading('status', text='Status')
        tree.column('status', width=100, anchor='center')
        tree.heading('withdrawal', text='Withdrawal')
        tree.column('withdrawal', width=100, anchor='center')
        tree.heading('deposit', text='Deposit')
        tree.column('deposit', width=100, anchor='center')
        tree.heading('balance', text='Balance')
        tree.column('balance', width=100, anchor='center')
        tree.heading('transfer account', text='Transfer Account')
        tree.column('transfer account', width=100, anchor='center')

        for txn in self._get_txns():
            tds = bb.get_display_strings_for_ledger(self.account, txn)
            values = (tds['txn_type'], tds['txn_date'], tds['payee'], tds['description'], tds['status'],
                      tds['withdrawal'], tds['deposit'], tds.get('balance', ''), tds['categories'])
            tree.insert('', tk.END, values=values)

        return tree


class BudgetDisplay:

    def __init__(self, master, engine, current_budget):
        self._master = master
        self._engine = engine
        if not current_budget:
            budgets = self._engine.get_budgets()
            if budgets:
                current_budget = budgets[0]
        self._current_budget = current_budget
        self._budget_report = self._current_budget.get_report_display(current_date=date.today())
        self._report_data = []
        for info in self._budget_report['income']:
            self._report_data.append(info)
        for info in self._budget_report['expense']:
            self._report_data.append(info)

    def get_widget(self):
        columns = ('account', 'amount', 'income', 'carryover', 'total budget', 'spent', 'remaining', 'remaining percent', 'current status')

        tree = ttk.Treeview(self._master, columns=columns, show='headings')
        tree.heading('account', text='Account')
        tree.column('account', width=100, anchor='center')
        tree.heading('amount', text='Amount')
        tree.column('amount', width=100, anchor='center')
        tree.heading('income', text='Income')
        tree.column('income', width=100, anchor='center')
        tree.heading('carryover', text='Carryover')
        tree.column('carryover', width=100, anchor='center')
        tree.heading('total budget', text='Total Budget')
        tree.column('total budget', width=100, anchor='center')
        tree.heading('spent', text='Spent')
        tree.column('spent', width=100, anchor='center')
        tree.heading('remaining', text='Remaining')
        tree.column('remaining', width=100, anchor='center')
        tree.heading('remaining percent', text='Remaining Percent')
        tree.column('remaining percent', width=100, anchor='center')
        tree.heading('current status', text='Current Status')
        tree.column('current status', width=100, anchor='center')

        for row in self._report_data:
            values = row.get('name', ''), row.get('amount', ''), row.get('income', ''), row.get('carryover', ''), row.get('total_budget', ''), row.get('spent', ''), row.get('remaining', ''), row.get('remaining_percent', ''), row.get('current_status', '')
            tree.insert('', tk.END, values=values)

        return tree


class ScheduledTransactionsDisplay:

    def __init__(self, master, engine):
        self._master = master
        self._engine = engine

    def get_widget(self):
        columns = ('name', 'frequency', 'next_due_date', 'payee', 'splits')

        tree = ttk.Treeview(self._master, columns=columns, show='headings')
        tree.heading('name', text='Name')
        tree.column('name', width=50, anchor='center')
        tree.heading('frequency', text='Frequency')
        tree.column('frequency', width=50, anchor='center')
        tree.heading('next_due_date', text='Next Due Date')
        tree.column('next_due_date', width=50, anchor='center')
        tree.heading('payee', text='Payee')
        tree.column('payee', width=50, anchor='center')
        tree.heading('splits', text='Splits')
        tree.column('splits', width=250, anchor='center')

        scheduled_txns = self._engine.get_scheduled_transactions()
        for scheduled_txn in scheduled_txns:
            if scheduled_txn.payee:
                payee = scheduled_txn.payee.name
            else:
                payee = ''
            values = (scheduled_txn.name, scheduled_txn.frequency.value, str(scheduled_txn.next_due_date), payee, bb.splits_display(scheduled_txn.splits))
            tree.insert('', tk.END, values=values)

        return tree


class GUI_TK:

    def __init__(self, file_name):
        self._engine = bb.Engine(file_name)

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
