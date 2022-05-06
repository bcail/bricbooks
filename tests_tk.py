import tkinter
import unittest

import bricbooks_tk as bb_tk
from tests import get_test_account
from load_test_data import CHECKING


def destroy_default_root():
    if getattr(tkinter, '_default_root', None):
        tkinter._default_root.update_idletasks()
        tkinter._default_root.destroy()
        tkinter._default_root = None


class AbstractTkTest:

    @classmethod
    def setUpClass(cls):
        cls._old_support_default_root = tkinter._support_default_root
        destroy_default_root()
        cls.root = tkinter.Tk()
        cls.wantobjects = cls.root.wantobjects()
        # De-maximize main window.
        # Some window managers can maximize new windows.
        cls.root.wm_state('normal')
        try:
            cls.root.wm_attributes('-zoomed', False)
        except tkinter.TclError:
            pass

    @classmethod
    def tearDownClass(cls):
        cls.root.update_idletasks()
        cls.root.destroy()
        del cls.root
        tkinter._default_root = None
        tkinter._support_default_root = cls._old_support_default_root

    def setUp(self):
        self.root.deiconify()

    def tearDown(self):
        for w in self.root.winfo_children():
            w.destroy()
        self.root.withdraw()


class TestTkGUI(AbstractTkTest, unittest.TestCase):

    def test_accounts_display(self):
        gui = bb_tk.GUI_TK(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        gui._engine.save_account(account=checking)
        gui._engine.save_account(account=savings)
        #switch to ledger, then back to accounts to pick up the new accounts
        gui.ledger_button.invoke()
        gui.accounts_button.invoke()
        child_items = gui.accounts_display.tree.get_children()
        first_account_name = gui.accounts_display.tree.item(child_items[0])['values'][2]
        self.assertEqual(first_account_name, CHECKING)

    def test_edit_account(self):
        gui = bb_tk.GUI_TK(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        gui._engine.save_account(account=checking)
        gui._engine.save_account(account=savings)
        #switch to ledger, then back to accounts to pick up the new accounts
        gui.ledger_button.invoke()
        gui.accounts_button.invoke()
        gui.accounts_display.tree.event_generate('<Button-1>', x=1, y=5)
        self.assertEqual(gui.accounts_display.edit_account_form.name_entry.get(), CHECKING)
        gui.accounts_display.edit_account_form.name_entry.delete(0, tkinter.END)
        new_name = f'{CHECKING} updated'
        gui.accounts_display.edit_account_form.name_entry.insert(0, new_name)
        gui.accounts_display.edit_account_form.save_button.invoke()
        accounts = gui._engine.get_accounts()
        self.assertEqual(len(accounts), 2)
        account = gui._engine.get_account(id_=checking.id)
        self.assertEqual(account.name, new_name)


if __name__ == '__main__':
    import sys
    print(f'TkVersion: {tkinter.TkVersion}; TclVersion: {tkinter.TclVersion}')

    unittest.main()
