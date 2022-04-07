import tkinter as tk
from tkinter import ttk
import os

import bricbooks as bb


class AccountsDisplayWidget(ttk.Frame):

    def __init__(self, master, accounts, storage, show_accounts):
        super().__init__(master=master)
        self._storage = storage
        self._show_accounts = show_accounts
        ttk.Label(self, text='Name').grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        ttk.Label(self, text='Starting Balance').grid(row=0, column=1, sticky=(tk.N, tk.S, tk.E, tk.W))
        row = 1
        self.data = {}
        for account in accounts:
            def _edit(acc_id=account.id):
                def _save(acc_id=acc_id):
                    a = Account(id_=acc_id,
                                name=self.data[acc_id]['entries']['name'].get(),
                                starting_balance=self.data[acc_id]['entries']['starting_balance'].get())
                    self._storage.save_account(a)
                    self._show_accounts()
                name_entry = ttk.Entry(self)
                name_entry.insert(0, self.data[acc_id]['account'].name)
                name_entry.grid(row=self.data[acc_id]['row'], column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
                starting_balance_entry = ttk.Entry(self)
                starting_balance_entry.insert(0, str(self.data[acc_id]['account'].starting_balance))
                starting_balance_entry.grid(row=self.data[acc_id]['row'], column=1, sticky=(tk.N, tk.S, tk.E, tk.W))
                self.data[acc_id]['entries'] = {'name': name_entry, 'starting_balance': starting_balance_entry}
                save_button = ttk.Button(self, text='Save', command=_save)
                save_button.grid(row=self.data[acc_id]['row'], column=2, sticky=(tk.N, tk.S, tk.E, tk.W))
                self.data[acc_id]['save_button'] = save_button
            ttk.Label(self, text=account.name).grid(row=row, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
            ttk.Label(self, text=str('account.starting_balance')).grid(row=row, column=1, sticky=(tk.N, tk.S, tk.E, tk.W))
            edit_button = ttk.Button(self, text='Edit', command=_edit)
            edit_button.grid(row=row, column=2, sticky=(tk.N, tk.S, tk.E, tk.W))
            self.data[account.id] = {'row': row, 'account': account, 'edit_button': edit_button}
            row += 1
        self.add_account_name_entry = ttk.Entry(self)
        self.add_account_name_entry.grid(row=row, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))
        self.add_account_starting_balance_entry = ttk.Entry(self)
        self.add_account_starting_balance_entry.grid(row=row, column=1, sticky=(tk.N, tk.W, tk.S, tk.E))
        self.add_account_button = ttk.Button(self, text='Add New', command=self._add)
        self.add_account_button.grid(row=row, column=2, sticky=(tk.N, tk.W, tk.S, tk.E))

    def _add(self):
        pass


class GUI_TK:

    def __init__(self, file_name):
        self._engine = bb.Engine(file_name)

        self.root = tk.Tk()
        self.root.title(bb.TITLE)
        #make sure root container is set to resize properly
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        #this frame will contain everything the user sees
        self.content_frame = self._init_content_frame(self.root)
        #self._show_action_buttons(self.content_frame)
        self.main_frame = None
        self.ledger_display_widget = None

        accounts = self._engine.get_accounts()
        #if accounts:
        #    self._show_ledger()
        #else:
        self._show_accounts()

        self.content_frame.grid(row=0, column=0, sticky=(tk.N, tk.W, tk.S, tk.E))

    def _init_content_frame(self, root):
        content_frame = ttk.Frame(master=root)
        content_frame.grid_columnconfigure(4, weight=1)
        content_frame.grid_rowconfigure(1, weight=1)
        return content_frame

    def _show_accounts(self):
        if self.main_frame and (self.main_frame == self.ledger_display_widget):
            self.ledger_display_widget.grid_forget()
        elif self.main_frame:
            self.main_frame.destroy()
        accounts = self._engine.get_accounts()
        #self._update_action_buttons(display='accounts')
        self.main_frame = self.adw = AccountsDisplayWidget(master=self.content_frame, accounts=accounts, storage=self._engine._storage, show_accounts=self._show_accounts)
        self.main_frame.grid(row=1, column=0, columnspan=5, sticky=(tk.N, tk.W, tk.S, tk.E))


if __name__ == '__main__':
    args = bb.parse_args()

    if args.file_name and not os.path.exists(args.file_name):
        raise Exception('no such file: "%s"' % args.file_name)

    app = GUI_TK(args.file_name)
    app.root.mainloop()
