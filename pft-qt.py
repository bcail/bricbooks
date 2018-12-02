import sys
from PySide2 import QtWidgets
import pft


class AccountsDisplayWidget(QtWidgets.QWidget):

    def __init__(self, storage):
        super().__init__()
        layout = QtWidgets.QGridLayout()
        name_label = QtWidgets.QLabel('Name')
        starting_balance_label = QtWidgets.QLabel('Starting Balance')
        layout.addWidget(name_label, 0, 0)
        layout.addWidget(starting_balance_label, 0, 1)
        accounts = storage.get_accounts()
        row = 1
        for acc in accounts:
            nl = QtWidgets.QLabel(acc.name)
            sbl = QtWidgets.QLabel(str(acc.starting_balance))
            layout.addWidget(nl, row, 0)
            layout.addWidget(sbl, row, 1)
            row += 1
        self.setLayout(layout)


class LedgerDisplayWidget(QtWidgets.QWidget):

    def __init__(self, storage):
        super().__init__()
        layout = QtWidgets.QGridLayout()
        layout.addWidget(QtWidgets.QLabel('Txn Type'), 0, 0)
        layout.addWidget(QtWidgets.QLabel('Date'), 0, 1)
        layout.addWidget(QtWidgets.QLabel('Payee'), 0, 2)
        layout.addWidget(QtWidgets.QLabel('Description'), 0, 3)
        layout.addWidget(QtWidgets.QLabel('Categories'), 0, 4)
        layout.addWidget(QtWidgets.QLabel('Status'), 0, 5)
        layout.addWidget(QtWidgets.QLabel('Debit (-)'), 0, 6)
        layout.addWidget(QtWidgets.QLabel('Credit (+)'), 0, 7)
        layout.addWidget(QtWidgets.QLabel('Balance'), 0, 8)
        account = storage.get_accounts()[0]
        self.ledger = pft.Ledger(starting_balance=account.starting_balance)
        storage.load_txns_into_ledger(account.id, self.ledger)
        balance = account.starting_balance
        for index, txn in enumerate(self.ledger.get_sorted_txns()):
            row = index + 1
            tds = txn.get_display_strings()
            type_label = QtWidgets.QLabel(tds['txn_type'])
            date_label = QtWidgets.QLabel(tds['txn_date'])
            payee_label = QtWidgets.QLabel(tds['payee'])
            description_label = QtWidgets.QLabel(tds['description'])
            credit_label = QtWidgets.QLabel(tds['credit'])
            debit_label = QtWidgets.QLabel(tds['debit'])
            balance += txn.amount
            balance_label = QtWidgets.QLabel(str(balance))
            layout.addWidget(type_label, row, 0)
            layout.addWidget(date_label, row, 1)
            layout.addWidget(payee_label, row, 2)
            layout.addWidget(description_label, row, 3)
            layout.addWidget(credit_label, row, 4)
            layout.addWidget(debit_label, row, 5)
            layout.addWidget(balance_label, row, 6)
        self.setLayout(layout)


class CategoriesDisplayWidget(QtWidgets.QWidget):

    def __init__(self, storage, reload_categories):
        super().__init__()
        self._storage = storage
        self._reload = reload_categories
        layout = QtWidgets.QGridLayout()
        layout.addWidget(QtWidgets.QLabel('ID'), 0, 0)
        layout.addWidget(QtWidgets.QLabel('Name'), 0, 1)
        row = 1
        data = {}
        categories = self._storage.get_categories()
        for cat in categories:
            row_data = {'row': row}
            layout.addWidget(QtWidgets.QLabel(str(cat.id)), row, 0)
            layout.addWidget(QtWidgets.QLabel(cat.name), row, 1)
            #row_data['name_label'] = name_label
            def _edit(cat_id=cat.id):
                def _save(cat_id=cat_id):
                    c = Category(id_=cat_id, name=data[cat_id]['name_entry'].get())
                    self._storage.save_category(c)
                    self._reload()
                #data[cat_id]['name_label'].destroy()
                name_entry = QtWidgets.QLineEdit()
                layout.addWidget(name_entry, data[cat_id]['row'], 1)
                data[cat_id]['name_entry'] = name_entry
                data[cat_id]['edit_button']['text'] = 'Save'
                data[cat_id]['edit_button']['command'] = _save
            def _delete(cat_id=cat.id):
                self._storage.delete_category(cat_id)
                self._reload()
            edit_button = QtWidgets.QPushButton('Edit')
            edit_button.clicked.connect(_edit)
            layout.addWidget(edit_button, row, 2)
            row_data['edit_button'] = edit_button
            delete_button = QtWidgets.QPushButton('Delete')
            delete_button.clicked.connect(_delete)
            layout.addWidget(delete_button, row, 3)
            data[cat.id] = row_data
            row += 1
        self.name_entry = QtWidgets.QLineEdit()
        layout.addWidget(self.name_entry, row, 1)
        add_button = QtWidgets.QPushButton('Add New')
        add_button.clicked.connect(self._add)
        layout.addWidget(add_button, row, 2)
        self.setLayout(layout)

    def _add(self):
        c = pft.Category(name=self.name_entry.text())
        self._storage.save_category(c)
        self._reload()


class BudgetDisplayWidget(QtWidgets.QWidget):

    def __init__(self):
        super().__init__()
        layout = QtWidgets.QGridLayout()
        layout.addWidget(QtWidgets.QLabel('Category'), 0, 0)
        layout.addWidget(QtWidgets.QLabel('Amount'), 0, 1)
        layout.addWidget(QtWidgets.QLabel('Income'), 0, 2)
        layout.addWidget(QtWidgets.QLabel('Carryover'), 0, 3)
        layout.addWidget(QtWidgets.QLabel('Total Budget'), 0, 4)
        layout.addWidget(QtWidgets.QLabel('Spent'), 0, 5)
        layout.addWidget(QtWidgets.QLabel('Remaining'), 0, 6)
        layout.addWidget(QtWidgets.QLabel('Percent Available'), 0, 7)
        self.setLayout(layout)


class PFT_GUI_QT(QtWidgets.QWidget):

    def __init__(self, file_name):
        super().__init__()
        self.layout = QtWidgets.QGridLayout()
        self._show_action_buttons(self.layout)
        self.storage = pft.SQLiteStorage(file_name)
        self.main_widget = None
        self.setLayout(self.layout)
        self._show_accounts()

    def _show_action_buttons(self, layout):
        accounts_button = QtWidgets.QPushButton('Accounts')
        accounts_button.clicked.connect(self._show_accounts)
        layout.addWidget(accounts_button, 0, 0)
        ledger_button = QtWidgets.QPushButton('Ledger')
        ledger_button.clicked.connect(self._show_ledger)
        layout.addWidget(ledger_button, 0, 1)
        categories_button = QtWidgets.QPushButton('Categories')
        categories_button.clicked.connect(self._show_categories)
        layout.addWidget(categories_button, 0, 2)
        budget_button = QtWidgets.QPushButton('Budget')
        budget_button.clicked.connect(self._show_budget)
        layout.addWidget(budget_button, 0, 3)

    def _show_accounts(self):
        if self.main_widget:
            self.layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self.main_widget = AccountsDisplayWidget(self.storage)
        self.layout.addWidget(self.main_widget, 1, 0, 1, 4)

    def _show_ledger(self):
        if self.main_widget:
            self.layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self.main_widget = LedgerDisplayWidget(self.storage)
        self.layout.addWidget(self.main_widget, 1, 0, 1, 4)

    def _show_categories(self):
        if self.main_widget:
            self.layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self.main_widget = CategoriesDisplayWidget(self.storage, reload_categories=self._show_categories)
        self.layout.addWidget(self.main_widget, 1, 0, 1, 4)

    def _show_budget(self):
        if self.main_widget:
            self.layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self.main_widget = BudgetDisplayWidget()
        self.layout.addWidget(self.main_widget, 1, 0, 1, 4)


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

