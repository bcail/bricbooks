from decimal import Decimal
import unittest
from PySide2 import QtWidgets, QtTest, QtCore
import pft_qt as pft_gui
import pft


class TestQtGUI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication([])

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


if __name__ == '__main__':
    unittest.main()

