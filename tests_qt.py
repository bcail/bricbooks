from decimal import Decimal
import unittest
from PySide2 import QtWidgets, QtTest, QtCore
import pft_qt as pft_gui
import pft


class TestQtGUI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication([])

    def test_pft_qt_gui(self):
        pft_qt_gui = pft_gui.PFT_GUI_QT(':memory:')

    def test_account(self):
        storage = pft.SQLiteStorage(':memory:')
        dw = pft_gui.AccountsDisplayWidget(storage)

    def test_ledger(self):
        storage = pft.SQLiteStorage(':memory:')
        acc = pft.Account(name='Savings', starting_balance=Decimal(5000))
        storage.save_account(acc)
        dw = pft_gui.LedgerDisplayWidget(storage)

    def test_categories(self):
        storage = pft.SQLiteStorage(':memory:')
        self.assertEqual(storage.get_categories(), [])
        def reload_categories(): pass
        dw = pft_gui.CategoriesDisplayWidget(storage, reload_categories)
        QtTest.QTest.keyClicks(dw.name_entry, 'Housing')
        QtTest.QTest.mouseClick(dw.add_button, QtCore.Qt.LeftButton)
        self.assertEqual(storage.get_categories()[0].name, 'Housing')

    def test_budget(self):
        storage = pft.SQLiteStorage(':memory:')
        c = pft.Category(name='Housing')
        storage.save_category(c)
        c2 = pft.Category(name='Food')
        storage.save_category(c2)
        b = pft.Budget(year=2018, category_budget_info={
            c: {'amount': Decimal(15), 'carryover': Decimal(0)},
            c2: {'amount': Decimal(25), 'carryover': Decimal(0)},
        })
        storage.save_budget(b)
        budget = storage.get_budgets()[0]
        self.assertEqual(budget.get_budget_data()[c]['amount'], Decimal(15))
        def reload_budget(): pass
        dw = pft_gui.BudgetDisplayWidget(budget=budget, storage=storage, reload_budget=reload_budget)
        QtTest.QTest.mouseClick(dw._edit_button, QtCore.Qt.LeftButton)
        dw.data[c.id]['budget_entry'].setText('30')
        QtTest.QTest.mouseClick(dw._save_button, QtCore.Qt.LeftButton) #now it's the save button
        budgets = storage.get_budgets()
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets[0].get_budget_data()[c]['amount'], Decimal(30))


if __name__ == '__main__':
    unittest.main()

