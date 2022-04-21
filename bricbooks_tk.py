import os
import tkinter as tk
from tkinter import ttk

import bricbooks as bb


class AccountsDisplay:

    def __init__(self, master, accounts, storage, show_accounts):
        self._master = master
        self._storage = storage
        self._show_accounts = show_accounts
        self._accounts = accounts

    def get_widget(self):
        columns = ('type', 'number', 'name', 'parent')

        tree = ttk.Treeview(self._master, columns=columns, show='headings')
        tree.heading('type', text='Type')
        tree.heading('number', text='Number')
        tree.heading('name', text='Name')
        tree.heading('parent', text='Parent')

        for account in self._accounts:
            if account.parent:
                parent = account.parent.name
            else:
                parent = ''
            tree.insert('', tk.END, values=(account.type.name, account.number or '', account.name, parent))

        return tree


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
        self._current_budget = current_budget

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
        return frame

    def _update_action_buttons(self, display):
        self.accounts_button['state'] = tk.NORMAL
        self.ledger_button['state'] = tk.NORMAL
        self.budget_button['state'] = tk.NORMAL
        if display == 'accounts':
            self.accounts_button['state'] = tk.DISABLED
        elif display == 'budget':
            self.budget_button['state'] = tk.DISABLED
        else:
            self.ledger_button['state'] = tk.DISABLED

    def _show_accounts(self):
        if self.main_frame:
            self.main_frame.destroy()
        accounts = self._engine.get_accounts()
        self._update_action_buttons(display='accounts')
        self.accounts_display = AccountsDisplay(master=self.content_frame, accounts=accounts, storage=self._engine._storage, show_accounts=self._show_accounts)
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


if __name__ == '__main__':
    args = bb.parse_args()

    if args.file_name and not os.path.exists(args.file_name):
        raise Exception('no such file: "%s"' % args.file_name)

    app = GUI_TK(args.file_name)
    app.root.mainloop()
