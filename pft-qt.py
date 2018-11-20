import sys
from PySide2 import QtWidgets
import pft


class PFT_GUI_QT(QtWidgets.QWidget):

    def __init__(self, file_name):
        super().__init__()
        self.storage = pft.SQLiteStorage(file_name)
        account = self.storage.get_accounts()[0]
        self.ledger = pft.Ledger(starting_balance=account.starting_balance)
        self.storage.load_txns_into_ledger(account.id, self.ledger)
        balance = account.starting_balance
        layout = QtWidgets.QGridLayout()
        for index, txn in enumerate(self.ledger.get_sorted_txns()):
            date_label = QtWidgets.QLabel(str(txn.txn_date))
            amount_label = QtWidgets.QLabel(str(txn.amount))
            balance += txn.amount
            balance_label = QtWidgets.QLabel(str(balance))
            balance_label.show()
            layout.addWidget(date_label, index, 0)
            layout.addWidget(amount_label, index, 1)
            layout.addWidget(balance_label, index, 2)
        self.setLayout(layout)


if __name__ == '__main__':
    args = pft.parse_args()
    app = QtWidgets.QApplication([])
    if args.file_name:
        main_window = PFT_GUI_QT(args.file_name)
    else:
        main_window = PFT_GUI_QT(pft.DATA_FILENAME)
    main_window.show()
    app.exec_()

