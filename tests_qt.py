from datetime import date
import unittest
from unittest.mock import patch, MagicMock
import bricbooks as bb
import bricbooks_qt as bb_qt
from tests import get_test_account
from load_test_data import CHECKING


class TestQtGUI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication([])

    def test_bb_qt_gui(self):
        bb_qt_gui = bb_qt.GUI_QT(':memory:')

    def test_account(self):
        gui = bb_qt.GUI_QT(':memory:')
        engine = gui._engine
        a = get_test_account()
        engine.save_account(account=a)
        #go to ledger page, and back to accounts, so the test account we added gets picked up in gui
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(gui.accounts_button, QtCore.Qt.LeftButton)
        accounts_display = gui.accounts_display
        QtTest.QTest.mouseClick(accounts_display.add_button, QtCore.Qt.LeftButton)
        accounts_display.add_account_display._widgets['number'].setText('400')
        accounts_display.add_account_display._widgets['name'].setText('Savings')
        accounts_display.add_account_display._widgets['parent'].setCurrentIndex(1)
        QtTest.QTest.mouseClick(accounts_display.add_account_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        accounts = engine.get_accounts()
        self.assertEqual(len(accounts), 2)
        self.assertEqual(accounts[1].type.name, 'ASSET')
        self.assertEqual(accounts[1].number, '400')
        self.assertEqual(accounts[1].name, 'Savings')
        self.assertEqual(accounts[1].parent.name, CHECKING)

    def test_account_edit(self):
        gui = bb_qt.GUI_QT(':memory:')
        engine = gui._engine
        checking = get_test_account(type_=bb.AccountType.ASSET, name='Checking')
        engine.save_account(account=checking)
        savings = get_test_account(type_=bb.AccountType.ASSET, name='Savings')
        engine.save_account(account=savings)
        #go to ledger page, and back to accounts, so the test account we added gets picked up in gui
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(gui.accounts_button, QtCore.Qt.LeftButton)
        accounts_display = gui.accounts_display
        #https://stackoverflow.com/a/12604740
        secondRowXPos = accounts_display._accounts_widget.columnViewportPosition(0) + 5
        secondRowYPos = accounts_display._accounts_widget.rowViewportPosition(1) + 10
        viewport = accounts_display._accounts_widget.viewport()
        QtTest.QTest.mouseClick(viewport, QtCore.Qt.LeftButton, QtCore.Qt.KeyboardModifiers(), QtCore.QPoint(secondRowXPos, secondRowYPos))
        accounts_display.edit_account_display._widgets['name'].setText('New Savings')
        accounts_display.edit_account_display._widgets['parent'].setCurrentIndex(1)
        QtTest.QTest.mouseClick(accounts_display.edit_account_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        self.assertEqual(len(engine.get_accounts()), 2)
        self.assertEqual(engine.get_accounts()[1].name, 'New Savings')
        self.assertEqual(engine.get_accounts()[1].parent.name, 'Checking')

    def test_expense_account_edit(self):
        gui = bb_qt.GUI_QT(':memory:')
        engine = gui._engine
        checking = get_test_account(type_=bb.AccountType.ASSET, name='Checking')
        engine.save_account(account=checking)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        engine.save_account(account=food)
        #go to ledger page, and back to accounts, so the test account we added gets picked up in gui
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(gui.accounts_button, QtCore.Qt.LeftButton)
        accounts_display = gui.accounts_display
        secondRowXPos = accounts_display._accounts_widget.columnViewportPosition(0) + 5
        secondRowYPos = accounts_display._accounts_widget.rowViewportPosition(1) + 10
        viewport = accounts_display._accounts_widget.viewport()
        QtTest.QTest.mouseClick(viewport, QtCore.Qt.LeftButton, QtCore.Qt.KeyboardModifiers(), QtCore.QPoint(secondRowXPos, secondRowYPos))
        accounts_display.edit_account_display._widgets['name'].setText('New Food')
        QtTest.QTest.mouseClick(accounts_display.edit_account_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        self.assertEqual(len(engine.get_accounts()), 2)
        self.assertEqual(engine.get_accounts()[1].name, 'New Food')

    @patch('bricbooks_qt.show_error')
    def test_account_exception(self, mock_method):
        gui = bb_qt.GUI_QT(':memory:')
        accounts_display = gui.accounts_display
        QtTest.QTest.mouseClick(accounts_display.add_button, QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(accounts_display.add_account_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        mock_method.assert_called_once_with(msg='Account must have a name')

    def test_empty_ledger(self):
        engine = bb.Engine(':memory:')
        ledger_display = bb_qt.LedgerDisplay(engine, txns_model_class=bb_qt.get_txns_model_class())

    def test_ledger_add(self):
        gui = bb_qt.GUI_QT(':memory:')
        engine = gui._engine
        checking = get_test_account()
        engine.save_account(account=checking)
        savings = get_test_account(name='Savings')
        engine.save_account(account=savings)
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        engine.save_account(account=housing)
        txn = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date.today())
        txn2 = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date(2017, 1, 2))
        engine.save_transaction(txn)
        engine.save_transaction(txn2)
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton) #go to ledger page
        ledger_display = gui.ledger_display
        QtTest.QTest.mouseClick(ledger_display.add_button, QtCore.Qt.LeftButton)
        self.assertEqual(ledger_display.add_txn_display._widgets['accounts_display']._categories_combo.count(), 4)
        self.assertEqual(ledger_display.add_txn_display._widgets['txn_date'].text(), str(date.today()))
        ledger_display.add_txn_display._widgets['txn_date'].setText('2017-01-05')
        ledger_display.add_txn_display._widgets['withdrawal'].setText('18')
        ledger_display.add_txn_display._widgets['payee'].setCurrentText('Burgers')
        ledger_display.add_txn_display._widgets['accounts_display']._categories_combo.setCurrentIndex(1)
        QtTest.QTest.mouseClick(ledger_display.add_txn_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        #make sure new txn was saved
        txns = engine.get_transactions(accounts=[checking])
        self.assertEqual(len(txns), 3)
        self.assertEqual(txns[1].splits[checking], {'amount': -18, 'quantity': -18})
        self.assertEqual(txns[1].payee.name, 'Burgers')

    @patch('bricbooks_qt.show_error')
    def test_ledger_add_txn_error(self, mock_method):
        gui = bb_qt.GUI_QT(':memory:')
        checking = get_test_account()
        gui._engine.save_account(account=checking)
        savings = get_test_account(name='Savings')
        gui._engine.save_account(account=savings)
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton) #go to ledger page
        QtTest.QTest.mouseClick(gui.ledger_display.add_button, QtCore.Qt.LeftButton)
        gui.ledger_display.add_txn_display._widgets['txn_date'].setText('')
        gui.ledger_display.add_txn_display._widgets['withdrawal'].setText('18')
        gui.ledger_display.add_txn_display._widgets['payee'].setCurrentText('Burgers')
        gui.ledger_display.add_txn_display._widgets['accounts_display']._categories_combo.setCurrentIndex(1)
        QtTest.QTest.mouseClick(gui.ledger_display.add_txn_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        mock_method.assert_called_once_with(msg='transaction must have a txn_date')

    def test_ledger_add_not_first_account(self):
        #test that correct accounts are set for the new txn (not just first account in the list)
        gui = bb_qt.GUI_QT(':memory:')
        engine = gui._engine
        checking = get_test_account()
        engine.save_account(account=checking)
        savings = get_test_account(name='Savings')
        engine.save_account(account=savings)
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        engine.save_account(account=housing)
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton) #go to ledger page
        ledger_display = gui.ledger_display
        ledger_display.action_combo.setCurrentIndex(1)
        QtTest.QTest.mouseClick(ledger_display.add_button, QtCore.Qt.LeftButton)
        ledger_display.add_txn_display._widgets['txn_date'].setText('2017-01-05')
        ledger_display.add_txn_display._widgets['withdrawal'].setText('18')
        ledger_display.add_txn_display._widgets['accounts_display']._categories_combo.setCurrentIndex(1)
        QtTest.QTest.mouseClick(ledger_display.add_txn_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        #make sure new txn was saved correctly
        txns = engine.get_transactions(accounts=[savings])
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].splits,
                {
                    savings: {'amount': -18, 'quantity': -18},
                    housing: {'amount': 18, 'quantity': 18},
                }
            )

    def test_add_txn_multiple_splits(self):
        gui = bb_qt.GUI_QT(':memory:')
        engine = gui._engine
        checking = get_test_account()
        engine.save_account(account=checking)
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        engine.save_account(account=housing)
        rent = get_test_account(type_=bb.AccountType.EXPENSE, name='Rent')
        engine.save_account(account=rent)
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton) #go to ledger page
        ledger_display = gui.ledger_display
        QtTest.QTest.mouseClick(ledger_display.add_button, QtCore.Qt.LeftButton)
        txn_accounts_display_splits = {rent: {'amount': 3}, housing: {'amount': 7}}
        ledger_display.add_txn_display._widgets['txn_date'].setText('2017-01-05')
        ledger_display.add_txn_display._widgets['withdrawal'].setText('10')
        bb_qt.get_new_txn_splits = MagicMock(return_value=txn_accounts_display_splits)
        QtTest.QTest.mouseClick(ledger_display.add_txn_display._widgets['accounts_display'].split_button, QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(ledger_display.add_txn_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        #make sure new txn was saved
        txns = engine.get_transactions(accounts=[checking])
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].splits[checking], {'amount': -10, 'quantity': -10})

    def test_ledger_switch_account(self):
        gui = bb_qt.GUI_QT(':memory:')
        engine = gui._engine
        checking = get_test_account(type_=bb.AccountType.ASSET, name='Checking')
        savings = get_test_account(type_=bb.AccountType.ASSET, name='Savings')
        restaurant = get_test_account(type_=bb.AccountType.EXPENSE, name='Restaurants')
        engine.save_account(account=checking)
        engine.save_account(account=savings)
        engine.save_account(account=restaurant)
        txn = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date.today())
        txn2 = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date(2017, 1, 2))
        txn3 = bb.Transaction(splits={savings: {'amount': 5}, checking: {'amount': -5}}, txn_date=date(2018, 1, 2))
        engine.save_transaction(txn)
        engine.save_transaction(txn2)
        engine.save_transaction(txn3)
        st = bb.ScheduledTransaction(
                name='weekly 1',
                frequency=bb.ScheduledTransactionFrequency.WEEKLY,
                next_due_date='2019-01-02',
                splits={restaurant: {'amount': 5}, checking: {'amount': -5}},
                txn_type='a',
                payee=bb.Payee('Wendys'),
                description='something',
            )
        engine.save_scheduled_transaction(st)
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton) #go to ledger page
        ledger_display = gui.ledger_display
        self.assertEqual(ledger_display._current_account, checking)
        self.assertEqual(ledger_display.action_combo.currentIndex(), 0)
        self.assertEqual(ledger_display.action_combo.currentText(), 'Checking')
        ledger_display.action_combo.setCurrentIndex(1)
        self.assertEqual(ledger_display._current_account, savings)
        self.assertEqual(ledger_display.action_combo.currentText(), 'Savings')

    def test_ledger_filter(self):
        gui = bb_qt.GUI_QT(':memory:')
        engine = gui._engine
        checking = get_test_account(type_=bb.AccountType.ASSET, name='Checking')
        savings = get_test_account(type_=bb.AccountType.ASSET, name='Savings')
        engine.save_account(account=checking)
        engine.save_account(account=savings)
        txn = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date.today(), description='something')
        txn2 = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date(2017, 1, 2))
        txn3 = bb.Transaction(splits={savings: {'amount': 5}, checking: {'amount': -5}}, txn_date=date(2018, 1, 2))
        engine.save_transaction(txn)
        engine.save_transaction(txn2)
        engine.save_transaction(txn3)
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton) #go to ledger page
        gui.ledger_display._filter_box.setText('something')
        QtTest.QTest.mouseClick(gui.ledger_display._filter_btn, QtCore.Qt.LeftButton)
        self.assertEqual(len(gui.ledger_display.txns_display._txns_model._txns), 1)

    def test_ledger_status(self):
        gui = bb_qt.GUI_QT(':memory:')
        engine = gui._engine
        checking = get_test_account(type_=bb.AccountType.ASSET, name='Checking')
        savings = get_test_account(type_=bb.AccountType.ASSET, name='Savings')
        engine.save_account(account=checking)
        engine.save_account(account=savings)
        txn = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date.today())
        txn2 = bb.Transaction(splits={checking: {'amount': 5, 'status': bb.Transaction.CLEARED}, savings: {'amount': -5}}, txn_date=date(2017, 1, 2))
        txn3 = bb.Transaction(splits={savings: {'amount': 5}, checking: {'amount': -5}}, txn_date=date(2018, 1, 2))
        engine.save_transaction(txn)
        engine.save_transaction(txn2)
        engine.save_transaction(txn3)
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton) #go to ledger page
        gui.ledger_display._filter_box.setText('status:C')
        QtTest.QTest.mouseClick(gui.ledger_display._filter_btn, QtCore.Qt.LeftButton)
        self.assertEqual(len(gui.ledger_display.txns_display._txns_model._txns), 1)
        self.assertEqual(gui.ledger_display.txns_display._txns_model._txns[0].txn_date, date(2017, 1, 2))

    def test_ledger_txn_edit(self):
        gui = bb_qt.GUI_QT(':memory:')
        engine = gui._engine
        checking = get_test_account()
        engine.save_account(account=checking)
        savings = get_test_account(name='Savings')
        engine.save_account(account=savings)
        payee = bb.Payee('some payee')
        engine.save_payee(payee)
        txn = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date(2017, 1, 3))
        txn2 = bb.Transaction(splits={checking: {'amount': 17}, savings: {'amount': -17}}, txn_date=date(2017, 5, 2), payee=payee)
        txn3 = bb.Transaction(splits={checking: {'amount': 25}, savings: {'amount': -25}}, txn_date=date(2017, 10, 18))
        txn4 = bb.Transaction(splits={checking: {'amount': 10}, savings: {'amount': -10}}, txn_date=date(2018, 6, 6))
        engine.save_transaction(txn)
        engine.save_transaction(txn2)
        engine.save_transaction(txn3)
        engine.save_transaction(txn4)
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton) #go to ledger page
        ledger_display = gui.ledger_display

        secondRowXPos = ledger_display.txns_display._txns_widget.columnViewportPosition(0) + 5
        secondRowYPos = ledger_display.txns_display._txns_widget.rowViewportPosition(1) + 10
        viewport = ledger_display.txns_display._txns_widget.viewport()
        QtTest.QTest.mouseClick(viewport, QtCore.Qt.LeftButton, QtCore.Qt.KeyboardModifiers(), QtCore.QPoint(secondRowXPos, secondRowYPos))

        self.assertEqual(ledger_display.txns_display.edit_txn_display._widgets['txn_date'].text(), '2017-05-02')
        self.assertEqual(ledger_display.txns_display.edit_txn_display._widgets['payee'].currentText(), 'some payee')

        ledger_display.txns_display.edit_txn_display._widgets['txn_date'].setText('2017-12-31')
        ledger_display.txns_display.edit_txn_display._widgets['deposit'].setText('20')
        QtTest.QTest.mouseClick(ledger_display.txns_display.edit_txn_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        #make sure edit was saved
        txns = engine.get_transactions(accounts=[checking])
        self.assertEqual(len(txns), 4)
        self.assertEqual(txns[2].txn_date, date(2017, 12, 31))
        self.assertEqual(txns[2].splits[checking], {'amount': 20, 'quantity': 20})
        self.assertEqual(txns[2].splits[savings], {'amount': -20, 'quantity': -20})

    def test_ledger_txn_edit_expense_account(self):
        gui = bb_qt.GUI_QT(':memory:')
        checking = get_test_account()
        gui._engine.save_account(account=checking)
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        gui._engine.save_account(account=housing)
        restaurants = get_test_account(type_=bb.AccountType.EXPENSE, name='Restaurants')
        gui._engine.save_account(account=restaurants)
        txn = bb.Transaction(splits={checking: {'amount': 5}, housing: {'amount': -5}}, txn_date=date(2017, 1, 3))
        txn2 = bb.Transaction(splits={checking: {'amount': 17}, housing: {'amount': -17}}, txn_date=date(2017, 5, 2))
        gui._engine.save_transaction(txn)
        gui._engine.save_transaction(txn2)
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton) #go to ledger page
        ledger_display = gui.ledger_display
        #activate editing
        secondRowXPos = ledger_display.txns_display._txns_widget.columnViewportPosition(0) + 5
        secondRowYPos = ledger_display.txns_display._txns_widget.rowViewportPosition(1) + 10
        viewport = ledger_display.txns_display._txns_widget.viewport()
        QtTest.QTest.mouseClick(viewport, QtCore.Qt.LeftButton, QtCore.Qt.KeyboardModifiers(), QtCore.QPoint(secondRowXPos, secondRowYPos))

        #change expense account
        ledger_display.txns_display.edit_txn_display._widgets['accounts_display']._categories_combo.setCurrentIndex(2)
        #save the change
        QtTest.QTest.mouseClick(ledger_display.txns_display.edit_txn_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        #make sure new category was saved
        txns = gui._engine.get_transactions(accounts=[checking])
        self.assertEqual(txns[1].splits[restaurants], {'amount': -17, 'quantity': -17})

    def test_ledger_txn_edit_multiple_splits(self):
        gui = bb_qt.GUI_QT(':memory:')
        checking = get_test_account()
        gui._engine.save_account(account=checking)
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        gui._engine.save_account(account=housing)
        restaurants = get_test_account(type_=bb.AccountType.EXPENSE, name='Restaurants')
        gui._engine.save_account(account=restaurants)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        gui._engine.save_account(account=food)
        initial_splits = {checking: {'amount': -25}, housing: {'amount': 20}, restaurants: {'amount': 5}}
        txn_account_display_splits = {housing: {'amount': 15}, restaurants: {'amount': 10}}
        final_splits = {checking: {'amount': -25, 'quantity': -25}, housing: {'amount': 15, 'quantity': 15}, restaurants: {'amount': 10, 'quantity': 10}}
        txn = bb.Transaction(splits=initial_splits, txn_date=date(2017, 1, 3))
        gui._engine.save_transaction(txn)
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton) #go to ledger page
        #activate editing
        firstRowXPos = gui.ledger_display.txns_display._txns_widget.columnViewportPosition(0) + 5
        firstRowYPos = gui.ledger_display.txns_display._txns_widget.rowViewportPosition(0) + 10
        viewport = gui.ledger_display.txns_display._txns_widget.viewport()
        QtTest.QTest.mouseClick(viewport, QtCore.Qt.LeftButton, QtCore.Qt.KeyboardModifiers(), QtCore.QPoint(firstRowXPos, firstRowYPos))
        self.assertEqual(gui.ledger_display.txns_display.edit_txn_display._widgets['accounts_display']._categories_combo.currentText(), 'multiple')
        self.assertEqual(gui.ledger_display.txns_display.edit_txn_display._widgets['accounts_display']._categories_combo.currentData(), initial_splits)
        bb_qt.get_new_txn_splits = MagicMock(return_value=txn_account_display_splits)
        QtTest.QTest.mouseClick(gui.ledger_display.txns_display.edit_txn_display._widgets['accounts_display'].split_button, QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(gui.ledger_display.txns_display.edit_txn_display._widgets['save_btn'], QtCore.Qt.LeftButton)
        updated_txn = gui._engine.get_transaction(txn.id)
        self.assertDictEqual(updated_txn.splits, final_splits)

    def test_ledger_txn_delete(self):
        gui = bb_qt.GUI_QT(':memory:')
        engine = gui._engine
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        engine.save_account(account=checking)
        engine.save_account(account=savings)
        txn = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date.today())
        txn2 = bb.Transaction(splits={checking: {'amount': 23}, savings: {'amount': -23}}, txn_date=date(2017, 1, 2))
        engine.save_transaction(txn)
        engine.save_transaction(txn2)
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton) #go to ledger page
        ledger_display = gui.ledger_display
        secondRowXPos = ledger_display.txns_display._txns_widget.columnViewportPosition(0) + 5
        secondRowYPos = ledger_display.txns_display._txns_widget.rowViewportPosition(1) + 10
        viewport = ledger_display.txns_display._txns_widget.viewport()
        QtTest.QTest.mouseClick(viewport, QtCore.Qt.LeftButton, QtCore.Qt.KeyboardModifiers(), QtCore.QPoint(secondRowXPos, secondRowYPos))
        QtTest.QTest.mouseClick(ledger_display.txns_display.edit_txn_display._widgets['delete_btn'], QtCore.Qt.LeftButton)
        #make sure txn was deleted
        txns = engine.get_transactions(accounts=[checking])
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0].splits[checking], {'amount': 23, 'quantity': 23})

    def test_ledger_enter_scheduled_txn(self):
        gui = bb_qt.GUI_QT(':memory:') #goes to accounts page, b/c no accounts yet
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        housing = get_test_account(name='Housing', type_=bb.AccountType.EXPENSE)
        gui._engine.save_account(account=checking)
        gui._engine.save_account(account=savings)
        gui._engine.save_account(account=housing)
        gui._engine.save_transaction(
                bb.Transaction(
                    txn_date=date(2018, 1, 11),
                    splits={checking: {'amount': 150}, savings: {'amount': -150}},
                    description='some txn',
                )
            )
        splits = {checking: {'amount': -100}, housing: {'amount': 100}}
        scheduled_txn = bb.ScheduledTransaction(
            name='weekly',
            frequency=bb.ScheduledTransactionFrequency.WEEKLY,
            splits=splits,
            next_due_date=date(2018, 1, 13),
        )
        gui._engine.save_scheduled_transaction(scheduled_txn)
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton) #go to ledger page
        secondRowXPos = gui.ledger_display.txns_display._txns_widget.columnViewportPosition(0) + 5
        secondRowYPos = gui.ledger_display.txns_display._txns_widget.rowViewportPosition(1) + 10
        viewport = gui.ledger_display.txns_display._txns_widget.viewport()
        QtTest.QTest.mouseClick(viewport, QtCore.Qt.LeftButton, QtCore.Qt.KeyboardModifiers(), QtCore.QPoint(secondRowXPos, secondRowYPos))
        QtTest.QTest.mouseClick(gui.ledger_display.txns_display.scheduled_txn_display._widgets['save_btn'], QtCore.Qt.LeftButton) #click to skip next txn
        scheduled_txns = gui._engine.get_scheduled_transactions()
        self.assertEqual(len(scheduled_txns), 1)
        self.assertEqual(scheduled_txns[0].next_due_date, date(2018, 1, 20))
        txns = gui._engine.get_transactions(accounts=[checking])
        self.assertEqual(len(txns), 2)
        self.assertEqual(txns[0].splits[checking]['amount'], 150)
        self.assertEqual(txns[1].splits[checking]['amount'], -100)

    def test_ledger_skip_scheduled_txn(self):
        gui = bb_qt.GUI_QT(':memory:') #goes to accounts page, b/c no accounts yet
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        housing = get_test_account(name='Housing', type_=bb.AccountType.EXPENSE)
        gui._engine.save_account(account=checking)
        gui._engine.save_account(account=savings)
        gui._engine.save_account(account=housing)
        splits = {checking: {'amount': -100}, housing: {'amount': 100}}
        scheduled_txn = bb.ScheduledTransaction(
            name='weekly',
            frequency=bb.ScheduledTransactionFrequency.WEEKLY,
            splits=splits,
            next_due_date=date(2018, 1, 13),
        )
        gui._engine.save_scheduled_transaction(scheduled_txn)
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton) #go to ledger page
        firstRowXPos = gui.ledger_display.txns_display._txns_widget.columnViewportPosition(0) + 5
        firstRowYPos = gui.ledger_display.txns_display._txns_widget.rowViewportPosition(0) + 10
        viewport = gui.ledger_display.txns_display._txns_widget.viewport()
        QtTest.QTest.mouseClick(viewport, QtCore.Qt.LeftButton, QtCore.Qt.KeyboardModifiers(), QtCore.QPoint(firstRowXPos, firstRowYPos))
        QtTest.QTest.mouseClick(gui.ledger_display.txns_display.scheduled_txn_display._widgets['skip_btn'], QtCore.Qt.LeftButton) #click to skip next txn
        scheduled_txns = gui._engine.get_scheduled_transactions()
        self.assertEqual(len(scheduled_txns), 1)
        self.assertEqual(scheduled_txns[0].next_due_date, date(2018, 1, 20))

    def test_ledger_update_reconciled_state(self):
        gui = bb_qt.GUI_QT(':memory:') #goes to accounts page, b/c no accounts yet
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        gui._engine.save_account(account=checking)
        gui._engine.save_account(account=savings)
        txn = bb.Transaction(splits={checking: {'amount': 5}, savings: {'amount': -5}}, txn_date=date.today())
        gui._engine.save_transaction(txn)
        QtTest.QTest.mouseClick(gui.ledger_button, QtCore.Qt.LeftButton) #go to ledger page
        firstRowXPos = gui.ledger_display.txns_display._txns_widget.columnViewportPosition(4) + 5
        firstRowYPos = gui.ledger_display.txns_display._txns_widget.rowViewportPosition(0) + 10
        viewport = gui.ledger_display.txns_display._txns_widget.viewport()
        QtTest.QTest.mouseClick(viewport, QtCore.Qt.LeftButton, QtCore.Qt.KeyboardModifiers(), QtCore.QPoint(firstRowXPos, firstRowYPos))
        txns = gui._engine.get_transactions(accounts=[checking])
        self.assertEqual(txns[0].splits[checking]['status'], bb.Transaction.CLEARED)

    def test_budget_display(self):
        gui = bb_qt.GUI_QT(':memory:')
        engine = gui._engine
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        engine.save_account(account=housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        engine.save_account(account=food)
        wages = get_test_account(type_=bb.AccountType.INCOME, name='Wages')
        engine.save_account(account=wages)
        b = bb.Budget(year=2018, account_budget_info={
            housing: {'amount': 15, 'carryover': 0},
            food: {'amount': 25, 'carryover': 0},
            wages: {'amount': 100},
        })
        engine.save_budget(b)
        budget = engine.get_budgets()[0]
        QtTest.QTest.mouseClick(gui.budget_button, QtCore.Qt.LeftButton) #go to budget page
        budget_display = gui.budget_display
        widget = budget_display.get_widget()

    def test_budget_create(self):
        gui = bb_qt.GUI_QT(':memory:')
        engine = gui._engine
        housing = get_test_account(type_=bb.AccountType.EXPENSE, name='Housing')
        engine.save_account(account=housing)
        food = get_test_account(type_=bb.AccountType.EXPENSE, name='Food')
        engine.save_account(account=food)
        QtTest.QTest.mouseClick(gui.budget_button, QtCore.Qt.LeftButton) #go to budget page
        self.assertFalse(gui.budget_display._current_budget)
        self.assertEqual(gui.budget_display._budget_select_combo.currentText(), '')
        self.assertEqual(gui.budget_display._budget_select_combo.currentData(), None)
        QtTest.QTest.mouseClick(gui.budget_display.add_button, QtCore.Qt.LeftButton)
        gui.budget_display.budget_form._widgets['start_date'].setText('2020-01-01')
        gui.budget_display.budget_form._widgets['end_date'].setText('2020-12-31')
        gui.budget_display.budget_form._widgets['budget_data'][housing]['amount'].setText('500')
        gui.budget_display.budget_form._save()
        #verify budget saved in storage
        budget = engine.get_budgets()[0]
        self.assertEqual(budget.start_date, date(2020, 1, 1))
        self.assertEqual(budget.get_budget_data()[housing]['amount'], 500)
        #verify BudgetDisplay updated
        self.assertEqual(gui.budget_display._current_budget, budget)
        self.assertEqual(gui.budget_display._budget_select_combo.currentText(), '2020-01-01 - 2020-12-31')
        self.assertEqual(gui.budget_display._budget_select_combo.currentData(), budget)

    def test_add_scheduled_txn(self):
        gui = bb_qt.GUI_QT(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        gui._engine.save_account(account=checking)
        gui._engine.save_account(account=savings)
        QtTest.QTest.mouseClick(gui.scheduled_txns_button, QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(gui.scheduled_txns_display.add_button, QtCore.Qt.LeftButton)
        gui.scheduled_txns_display.form._widgets['name'].setText('test st')
        gui.scheduled_txns_display.form._widgets['next_due_date'].setText('2020-01-15')
        gui.scheduled_txns_display.form._widgets['account'].setCurrentIndex(0)
        gui.scheduled_txns_display.form._widgets['payee'].setCurrentText('Someone')
        gui.scheduled_txns_display.form._widgets['withdrawal'].setText('37')
        gui.scheduled_txns_display.form._widgets['accounts_display']._categories_combo.setCurrentIndex(2)
        QtTest.QTest.mouseClick(gui.scheduled_txns_display.form._widgets['save_btn'], QtCore.Qt.LeftButton)
        scheduled_txns = gui._engine.get_scheduled_transactions()
        self.assertEqual(scheduled_txns[0].name, 'test st')
        self.assertEqual(scheduled_txns[0].splits[checking], {'amount': -37, 'quantity': -37})
        self.assertEqual(scheduled_txns[0].splits[savings], {'amount': 37, 'quantity': 37})
        self.assertEqual(scheduled_txns[0].payee.name, 'Someone')

    def test_edit_scheduled_txn(self):
        gui = bb_qt.GUI_QT(':memory:')
        checking = get_test_account()
        savings = get_test_account(name='Savings')
        housing = get_test_account(name='Housing', type_=bb.AccountType.EXPENSE)
        gui._engine.save_account(account=checking)
        gui._engine.save_account(account=savings)
        gui._engine.save_account(account=housing)
        splits = {checking: {'amount': -100}, housing: {'amount': 100}}
        scheduled_txn = bb.ScheduledTransaction(
            name='weekly',
            frequency=bb.ScheduledTransactionFrequency.WEEKLY,
            splits=splits,
            next_due_date=date.today()
        )
        gui._engine.save_scheduled_transaction(scheduled_txn)
        #go to scheduled txns, click on one to activate edit form, update values, & save it
        QtTest.QTest.mouseClick(gui.scheduled_txns_button, QtCore.Qt.LeftButton)
        firstRowXPos = gui.scheduled_txns_display.data_display.main_widget.columnViewportPosition(2) + 5
        firstRowYPos = gui.scheduled_txns_display.data_display.main_widget.rowViewportPosition(0) + 10
        viewport = gui.scheduled_txns_display.data_display.main_widget.viewport()
        QtTest.QTest.mouseClick(viewport, QtCore.Qt.LeftButton, QtCore.Qt.KeyboardModifiers(), QtCore.QPoint(firstRowXPos, firstRowYPos))
        gui.scheduled_txns_display.data_display.edit_form._widgets['name'].setText('updated')
        gui.scheduled_txns_display.data_display.edit_form._widgets['withdrawal'].setText('15')
        self.assertEqual(gui.scheduled_txns_display.data_display.edit_form._widgets['accounts_display']._categories_combo.currentData(), housing)
        QtTest.QTest.mouseClick(gui.scheduled_txns_display.data_display.edit_form._widgets['save_btn'], QtCore.Qt.LeftButton)
        scheduled_txns = gui._engine.get_scheduled_transactions()
        self.assertEqual(len(scheduled_txns), 1)
        self.assertEqual(scheduled_txns[0].name, 'updated')
        self.assertEqual(scheduled_txns[0].splits[checking], {'amount': -15, 'quantity': -15})
        self.assertEqual(scheduled_txns[0].splits[housing], {'amount': 15, 'quantity': 15})


if __name__ == '__main__':
    try:
        from PySide2 import QtWidgets, QtTest, QtCore
    except ImportError:
        from PySide6 import QtWidgets, QtTest, QtCore
    unittest.main()
