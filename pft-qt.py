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
            tds = txn.get_display_strings()
            type_label = QtWidgets.QLabel(tds['txn_type'])
            date_label = QtWidgets.QLabel(tds['txn_date'])
            payee_label = QtWidgets.QLabel(tds['payee'])
            description_label = QtWidgets.QLabel(tds['description'])
            credit_label = QtWidgets.QLabel(tds['credit'])
            debit_label = QtWidgets.QLabel(tds['debit'])
            balance += txn.amount
            balance_label = QtWidgets.QLabel(str(balance))
            layout.addWidget(type_label, index, 0)
            layout.addWidget(date_label, index, 1)
            layout.addWidget(payee_label, index, 2)
            layout.addWidget(description_label, index, 3)
            layout.addWidget(credit_label, index, 4)
            layout.addWidget(debit_label, index, 5)
            layout.addWidget(balance_label, index, 6)
        self.setLayout(layout)


if __name__ == '__main__':
    args = pft.parse_args()
    app = QtWidgets.QApplication([])
    if args.file_name:
        main_window = PFT_GUI_QT(args.file_name)
    else:
        main_window = PFT_GUI_QT(pft.DATA_FILENAME)
    scroll = QtWidgets.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(main_window)
    scroll.show()
    title = 'Python Finance Tracking'
    scroll.setWindowTitle(title)
    app.exec_()

