from datetime import date
from fractions import Fraction
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
        assets = get_test_account(name='All Assets')
        gui._engine.save_account(account=assets)
        checking = get_test_account(parent=assets)
        savings = get_test_account(name='Savings')
        gui._engine.save_account(account=checking)
        gui._engine.save_account(account=savings)
        #switch to ledger, then back to accounts to pick up the new accounts
        gui.ledger_button.invoke()
        gui.accounts_button.invoke()
        #click on a the checking account item, so it opens for editing
        gui.accounts_display.tree.event_generate('<Button-1>', x=1, y=25)
        edit_account_form = gui.accounts_display.edit_account_form
        self.assertEqual(edit_account_form.name_entry.get(), CHECKING)
        self.assertEqual(edit_account_form.parent_combo.get(), 'All Assets')
        #update some data and save
        new_name = f'{CHECKING} updated'
        edit_account_form.name_entry.delete(0, tkinter.END)
        edit_account_form.name_entry.insert(0, new_name)
        edit_account_form.parent_combo.current(2)
        edit_account_form.save_button.invoke()
        #verify changes
        accounts = gui._engine.get_accounts()
        self.assertEqual(len(accounts), 3)
        account = gui._engine.get_account(id_=checking.id)
        self.assertEqual(account.name, new_name)
        self.assertEqual(account.parent, savings)

    def test_ledger_new_transaction(self):
        gui = bb_tk.GUI_TK(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        gui._engine.save_account(account=checking)
        gui._engine.save_account(account=savings)
        gui.ledger_button.invoke()
        gui.ledger_display.add_button.invoke()
        add_form = gui.ledger_display.add_transaction_form
        add_form.date_entry.insert(0, '2021-01-13')
        add_form.withdrawal_entry.insert(0, '20.05')
        add_form.transfer_accounts_display.transfer_accounts_combo.current(1)
        add_form.save_button.invoke()
        txns = gui._engine.get_transactions(accounts=[checking])
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].txn_date, date(2021, 1, 13))
        self.assertEqual(txns[0].splits[checking]['amount'], Fraction(-401, 20))

    def test_ledger_new_transaction_multiple_transfer(self):
        gui = bb_tk.GUI_TK(':memory:')
        checking = get_test_account()
        food = get_test_account(name='Food')
        restaurants = get_test_account(name='Restaurants')
        gui._engine.save_account(account=checking)
        gui._engine.save_account(account=food)
        gui._engine.save_account(account=restaurants)
        gui.ledger_button.invoke()
        gui.ledger_display.add_button.invoke()
        add_form = gui.ledger_display.add_transaction_form
        add_form.date_entry.insert(0, '2021-01-13')
        add_form.withdrawal_entry.insert(0, '20.05')
        add_form.transfer_accounts_display.split_button.invoke()
        add_form.transfer_accounts_display.splits_editor._entries[checking.id][0].insert(0, '-20.05')
        add_form.transfer_accounts_display.splits_editor._entries[food.id][0].insert(0, '10.05')
        add_form.transfer_accounts_display.splits_editor._entries[restaurants.id][0].insert(0, '10')
        add_form.transfer_accounts_display.splits_editor.ok_button.invoke()
        add_form.save_button.invoke()
        txns = gui._engine.get_transactions(accounts=[checking])
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].txn_date, date(2021, 1, 13))
        self.assertEqual(txns[0].splits[checking]['amount'], Fraction(-401, 20))

    def test_ledger_update_transaction(self):
        gui = bb_tk.GUI_TK(':memory:')
        checking = get_test_account()
        food = get_test_account(name='Food')
        restaurants = get_test_account(name='Restaurants')
        gui._engine.save_account(account=checking)
        gui._engine.save_account(account=food)
        gui._engine.save_account(account=restaurants)
        payee = bb_tk.bb.Payee('some payee')
        gui._engine.save_payee(payee)
        txn = bb_tk.bb.Transaction(splits={checking: {'amount': -5}, food: {'amount': 5}}, txn_date=date(2017, 1, 3))
        txn2 = bb_tk.bb.Transaction(splits={checking: {'amount': -17, 'status': bb_tk.bb.Transaction.CLEARED}, restaurants: {'amount': 17}}, txn_date=date(2017, 5, 2), payee=payee, description='description')
        gui._engine.save_transaction(txn)
        gui._engine.save_transaction(txn2)
        gui.ledger_button.invoke()
        gui.ledger_display.txns_widget.event_generate('<Button-1>', x=1, y=25)

        #verify that data is loaded into form
        self.assertEqual(gui.ledger_display.edit_transaction_form.withdrawal_entry.get(), '17.00')
        self.assertEqual(gui.ledger_display.edit_transaction_form.transfer_accounts_display.transfer_accounts_combo.get(), 'Restaurants')

        #update values & save
        gui.ledger_display.edit_transaction_form.withdrawal_entry.delete(0, tkinter.END)
        gui.ledger_display.edit_transaction_form.withdrawal_entry.insert(0, '21')
        gui.ledger_display.edit_transaction_form.save_button.invoke()

        #verify transaction updates saved
        txns = gui._engine.get_transactions(accounts=[checking])
        self.assertEqual(len(txns), 2)
        self.assertEqual(txns[0].txn_date, date(2017, 1, 3))
        self.assertEqual(txns[1].txn_date, date(2017, 5, 2))
        self.assertEqual(txns[1].splits[checking]['amount'], -21)
        self.assertEqual(txns[1].splits[checking]['status'], bb_tk.bb.Transaction.CLEARED)
        self.assertEqual(txns[1].splits[restaurants]['amount'], 21)
        self.assertEqual(txns[1].payee.name, 'some payee')
        self.assertEqual(txns[1].description, 'description')

    def test_ledger_update_transaction_multiple_transfer(self):
        gui = bb_tk.GUI_TK(':memory:')
        checking = get_test_account()
        food = get_test_account(name='Food')
        restaurants = get_test_account(name='Restaurants')
        gui._engine.save_account(account=checking)
        gui._engine.save_account(account=food)
        gui._engine.save_account(account=restaurants)
        payee = bb_tk.bb.Payee('some payee')
        gui._engine.save_payee(payee)
        splits = {checking: {'amount': -20}, food: {'amount': 5}, restaurants: {'amount': 15}}
        txn = bb_tk.bb.Transaction(splits=splits, txn_date=date(2017, 1, 3))
        gui._engine.save_transaction(txn)
        gui.ledger_button.invoke()
        gui.ledger_display.txns_widget.event_generate('<Button-1>', x=1, y=10)

        #verify that data is loaded into form
        self.assertEqual(gui.ledger_display.edit_transaction_form.withdrawal_entry.get(), '20.00')
        self.assertEqual(gui.ledger_display.edit_transaction_form.transfer_accounts_display.transfer_accounts_combo.get(), 'multiple')

        #update values & save
        gui.ledger_display.edit_transaction_form.withdrawal_entry.delete(0, tkinter.END)
        gui.ledger_display.edit_transaction_form.withdrawal_entry.insert(0, '40')
        gui.ledger_display.edit_transaction_form.transfer_accounts_display.split_button.invoke()
        self.assertEqual(gui.ledger_display.edit_transaction_form.transfer_accounts_display.splits_editor._entries[checking.id][0].get(), '-20.00')
        self.assertEqual(gui.ledger_display.edit_transaction_form.transfer_accounts_display.splits_editor._entries[food.id][0].get(), '5.00')
        self.assertEqual(gui.ledger_display.edit_transaction_form.transfer_accounts_display.splits_editor._entries[restaurants.id][0].get(), '15.00')
        gui.ledger_display.edit_transaction_form.transfer_accounts_display.splits_editor._entries[checking.id][0].delete(0, tkinter.END)
        gui.ledger_display.edit_transaction_form.transfer_accounts_display.splits_editor._entries[checking.id][0].insert(0, '-40')
        gui.ledger_display.edit_transaction_form.transfer_accounts_display.splits_editor._entries[food.id][0].delete(0, tkinter.END)
        gui.ledger_display.edit_transaction_form.transfer_accounts_display.splits_editor._entries[food.id][0].insert(0, '17')
        gui.ledger_display.edit_transaction_form.transfer_accounts_display.splits_editor._entries[restaurants.id][0].delete(0, tkinter.END)
        gui.ledger_display.edit_transaction_form.transfer_accounts_display.splits_editor._entries[restaurants.id][0].insert(0, '23')
        gui.ledger_display.edit_transaction_form.transfer_accounts_display.splits_editor.ok_button.invoke()

        gui.ledger_display.edit_transaction_form.save_button.invoke()

        #verify transaction updates saved
        txns = gui._engine.get_transactions(accounts=[checking])
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].txn_date, date(2017, 1, 3))
        self.assertEqual(txns[0].splits[checking]['amount'], -40)
        self.assertEqual(txns[0].splits[food]['amount'], 17)
        self.assertEqual(txns[0].splits[restaurants]['amount'], 23)

    def test_ledger_enter_next_scheduled_transaction(self):
        gui = bb_tk.GUI_TK(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        housing = get_test_account(name='Housing', type_=bb_tk.bb.AccountType.EXPENSE)
        gui._engine.save_account(account=checking)
        gui._engine.save_account(account=savings)
        gui._engine.save_account(account=housing)
        txn = bb_tk.bb.Transaction(splits={checking: {'amount': -5}, savings: {'amount': 5}}, txn_date=date(2017, 1, 3))
        gui._engine.save_transaction(txn)
        splits = {checking: {'amount': -100}, housing: {'amount': 100}}
        scheduled_txn = bb_tk.bb.ScheduledTransaction(
            name='weekly',
            frequency=bb_tk.bb.ScheduledTransactionFrequency.WEEKLY,
            splits=splits,
            next_due_date=date(2020, 1, 15)
        )
        gui._engine.save_scheduled_transaction(scheduled_txn)

        gui.ledger_button.invoke()
        gui.ledger_display.txns_widget.event_generate('<Button-1>', x=1, y=25)
        gui.ledger_display.edit_scheduled_transaction_form.save_button.invoke()

        scheduled_txns = gui._engine.get_scheduled_transactions()
        self.assertEqual(len(scheduled_txns), 1)
        self.assertEqual(scheduled_txns[0].next_due_date, date(2020, 1, 22))

        txns = gui._engine.get_transactions(accounts=[checking])
        self.assertEqual(len(txns), 2)
        self.assertEqual(txns[1].txn_date, date(2020, 1, 15))
        self.assertEqual(txns[1].splits[checking]['amount'], -100)

    def test_ledger_skip_scheduled_transaction(self):
        gui = bb_tk.GUI_TK(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        housing = get_test_account(name='Housing', type_=bb_tk.bb.AccountType.EXPENSE)
        gui._engine.save_account(account=checking)
        gui._engine.save_account(account=savings)
        gui._engine.save_account(account=housing)
        txn = bb_tk.bb.Transaction(splits={checking: {'amount': -5}, savings: {'amount': 5}}, txn_date=date(2017, 1, 3))
        gui._engine.save_transaction(txn)
        splits = {checking: {'amount': -100}, housing: {'amount': 100}}
        scheduled_txn = bb_tk.bb.ScheduledTransaction(
            name='weekly',
            frequency=bb_tk.bb.ScheduledTransactionFrequency.WEEKLY,
            splits=splits,
            next_due_date=date(2020, 1, 15)
        )
        gui._engine.save_scheduled_transaction(scheduled_txn)

        gui.ledger_button.invoke()
        gui.ledger_display.txns_widget.event_generate('<Button-1>', x=1, y=25)
        gui.ledger_display.edit_scheduled_transaction_form.skip_button.invoke()

        scheduled_txns = gui._engine.get_scheduled_transactions()
        self.assertEqual(len(scheduled_txns), 1)
        self.assertEqual(scheduled_txns[0].next_due_date, date(2020, 1, 22))

        txns = gui._engine.get_transactions(accounts=[checking])
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].txn_date, date(2017, 1, 3))

    def test_scheduled_transaction_add(self):
        gui = bb_tk.GUI_TK(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        housing = get_test_account(name='Housing', type_=bb_tk.bb.AccountType.EXPENSE)
        gui._engine.save_account(account=checking)
        gui._engine.save_account(account=savings)
        gui._engine.save_account(account=housing)
        gui.scheduled_transactions_button.invoke()
        gui.scheduled_transactions_display.add_button.invoke()
        gui.scheduled_transactions_display.new_form.name_entry.insert(0, 'test 1')
        gui.scheduled_transactions_display.new_form.next_due_date_entry.insert(0, '2020-01-16')
        gui.scheduled_transactions_display.new_form.withdrawal_entry.insert(0, '100')
        gui.scheduled_transactions_display.new_form.account_combo.current(0)
        gui.scheduled_transactions_display.new_form.transfer_accounts_display.transfer_accounts_combo.current(2)
        gui.scheduled_transactions_display.new_form.save_button.invoke()
        scheduled_txns = gui._engine.get_scheduled_transactions()
        self.assertEqual(len(scheduled_txns), 1)
        self.assertEqual(scheduled_txns[0].name, 'test 1')
        self.assertEqual(scheduled_txns[0].splits[checking], {'amount': -100, 'quantity': -100})
        self.assertEqual(scheduled_txns[0].splits[savings], {'amount': 100, 'quantity': 100})

    def test_scheduled_transaction_update(self):
        gui = bb_tk.GUI_TK(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        housing = get_test_account(name='Housing', type_=bb_tk.bb.AccountType.EXPENSE)
        gui._engine.save_account(account=checking)
        gui._engine.save_account(account=savings)
        gui._engine.save_account(account=housing)
        splits = {checking: {'amount': -100}, housing: {'amount': 100}}
        scheduled_txn = bb_tk.bb.ScheduledTransaction(
            name='weekly',
            frequency=bb_tk.bb.ScheduledTransactionFrequency.WEEKLY,
            splits=splits,
            next_due_date=date.today()
        )
        gui._engine.save_scheduled_transaction(scheduled_txn)
        #go to scheduled txns, click on one to activate edit form, update values, & save it
        gui.scheduled_transactions_button.invoke()
        gui.scheduled_transactions_display.tree.event_generate('<Button-1>', x=1, y=10)

        self.assertEqual(gui.scheduled_transactions_display.edit_form.withdrawal_entry.get(), '100.00')

        gui.scheduled_transactions_display.edit_form.name_entry.delete(0, tkinter.END)
        gui.scheduled_transactions_display.edit_form.name_entry.insert(0, 'weekly updated')
        gui.scheduled_transactions_display.edit_form.withdrawal_entry.delete(0, tkinter.END)
        gui.scheduled_transactions_display.edit_form.withdrawal_entry.insert(0, '15')
        gui.scheduled_transactions_display.edit_form.save_button.invoke()
        scheduled_txns = gui._engine.get_scheduled_transactions()
        self.assertEqual(len(scheduled_txns), 1)
        self.assertEqual(scheduled_txns[0].name, 'weekly updated')
        self.assertEqual(scheduled_txns[0].splits[checking], {'amount': -15, 'quantity': -15})
        self.assertEqual(scheduled_txns[0].splits[housing], {'amount': 15, 'quantity': 15})

    def test_new_budget(self):
        gui = bb_tk.GUI_TK(':memory:')
        checking = get_test_account()
        food = get_test_account(name='Food', type_=bb_tk.bb.AccountType.EXPENSE)
        housing = get_test_account(name='Housing', type_=bb_tk.bb.AccountType.EXPENSE)
        gui._engine.save_account(account=checking)
        gui._engine.save_account(account=food)
        gui._engine.save_account(account=housing)
        gui.budget_button.invoke()
        gui.budget_display.add_button.invoke()
        budget_form = gui.budget_display.budget_form
        budget_form.start_date_entry.insert(0, '2020-01-01')
        budget_form.end_date_entry.insert(0, '2020-12-31')
        budget_form._widgets['budget_data'][food]['amount'].insert(0, '20')
        budget_form.save_button.invoke()
        budget = gui._engine.get_budgets()[0]
        self.assertEqual(budget.start_date, date(2020, 1, 1))
        self.assertEqual(budget.get_budget_data()[food]['amount'], 20)

    def test_edit_budget(self):
        gui = bb_tk.GUI_TK(':memory:')
        housing = get_test_account(type_=bb_tk.bb.AccountType.EXPENSE, name='Housing')
        gui._engine.save_account(account=housing)
        food = get_test_account(type_=bb_tk.bb.AccountType.EXPENSE, name='Food')
        gui._engine.save_account(account=food)
        wages = get_test_account(type_=bb_tk.bb.AccountType.INCOME, name='Wages')
        gui._engine.save_account(account=wages)
        b = bb_tk.bb.Budget(year=2018, account_budget_info={
            housing: {'amount': 15, 'carryover': 0},
            food: {'amount': 25, 'carryover': 0},
            wages: {'amount': 100},
        })
        gui._engine.save_budget(b)

        gui.budget_button.invoke()
        gui.budget_display.edit_button.invoke()
        budget_form = gui.budget_display.budget_form
        self.assertEqual(budget_form.start_date_entry.get(), '2018-01-01')
        self.assertEqual(budget_form.end_date_entry.get(), '2018-12-31')
        budget_form.start_date_entry.delete(0, tkinter.END)
        budget_form.end_date_entry.delete(0, tkinter.END)
        budget_form.start_date_entry.insert(0, '2020-01-01')
        budget_form.end_date_entry.insert(0, '2020-06-30')
        budget_form._widgets['budget_data'][food]['amount'].delete(0, tkinter.END)
        budget_form._widgets['budget_data'][food]['amount'].insert(0, '20')
        budget_form.save_button.invoke()

        budget = gui._engine.get_budgets()[0]
        self.assertEqual(budget.start_date, date(2020, 1, 1))
        self.assertEqual(budget.end_date, date(2020, 6, 30))
        self.assertEqual(budget.get_budget_data()[food]['amount'], 20)

if __name__ == '__main__':
    import sys
    print(f'TkVersion: {tkinter.TkVersion}; TclVersion: {tkinter.TclVersion}')

    unittest.main()
