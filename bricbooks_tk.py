import tkinter as tk
from tkinter import ttk
import os

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
        self.accounts_display = AccountsDisplay(master=self.content_frame, accounts=accounts, storage=self._engine._storage, show_accounts=self._show_accounts)
        self.main_frame = self.accounts_display.get_widget()
        self.main_frame.grid(row=1, column=0, columnspan=5, sticky=(tk.N, tk.W, tk.S, tk.E))


if __name__ == '__main__':
    args = bb.parse_args()

    if args.file_name and not os.path.exists(args.file_name):
        raise Exception('no such file: "%s"' % args.file_name)

    app = GUI_TK(args.file_name)
    app.root.mainloop()
