from functools import partial
import sys
from PySide2 import QtWidgets
import pft


ERROR_STYLE = '''QLineEdit {
    border: 2px solid red;
}'''


def set_widget_error_state(widget):
    widget.setStyleSheet(ERROR_STYLE)


class AccountsDisplayWidget(QtWidgets.QWidget):

    def __init__(self, storage, reload_accounts):
        super().__init__()
        self.storage = storage
        self._reload = reload_accounts
        layout = QtWidgets.QGridLayout()
        name_label = QtWidgets.QLabel('Name')
        starting_balance_label = QtWidgets.QLabel('Starting Balance')
        layout.addWidget(name_label, 0, 0)
        layout.addWidget(starting_balance_label, 0, 1)
        self.accounts_widgets = {}
        accounts = storage.get_accounts()
        row = 1
        for acc in accounts:
            name_label = QtWidgets.QLabel(acc.name)
            starting_balance_label = QtWidgets.QLabel(str(acc.starting_balance))
            layout.addWidget(name_label, row, 0)
            layout.addWidget(starting_balance_label, row, 1)
            def _edit(acc_id):
                orig_name = self.accounts_widgets[acc_id]['labels']['name'].text()
                orig_starting_balance = self.accounts_widgets[acc_id]['labels']['starting_balance'].text()
                for label in self.accounts_widgets[acc_id]['labels'].values():
                    layout.removeWidget(label)
                    label.deleteLater()
                name_entry = QtWidgets.QLineEdit()
                name_entry.setText(orig_name)
                starting_balance_entry = QtWidgets.QLineEdit()
                starting_balance_entry.setText(orig_starting_balance)
                row = self.accounts_widgets[acc_id]['row']
                layout.addWidget(name_entry, row, 0)
                layout.addWidget(starting_balance_entry, row, 1)
                def _save(acc_id):
                    name = self.accounts_widgets[acc_id]['entries']['name'].text()
                    starting_balance = self.accounts_widgets[acc_id]['entries']['starting_balance'].text()
                    try:
                        self.storage.save_account(pft.Account(name=name, starting_balance=starting_balance, id=acc_id))
                        self._reload()
                    except pft.InvalidAccountNameError:
                        set_widget_error_state(self.accounts_widgets[acc_id]['entries']['name'])
                    except pft.InvalidAccountStartingBalanceError:
                        set_widget_error_state(self.accounts_widgets[acc_id]['entries']['starting_balance'])
                save_button = QtWidgets.QPushButton('Save')
                save_button.clicked.connect(partial(_save, acc_id=acc_id))
                layout.addWidget(save_button, row, 2)
                self.accounts_widgets[acc_id]['entries'] = {
                        'name': name_entry,
                        'starting_balance': starting_balance_entry,
                    }
                self.accounts_widgets[acc_id]['buttons'] = {
                        'save': save_button,
                    }
            edit_button = QtWidgets.QPushButton('Edit')
            layout.addWidget(edit_button, row, 2)
            self.accounts_widgets[acc.id] = {
                    'row': row,
                    'labels': {'name': name_label, 'starting_balance': starting_balance_label},
                    'buttons': {'edit': edit_button}
                }
            edit_button.clicked.connect(partial(_edit, acc_id=acc.id))
            row += 1
        add_account_name = QtWidgets.QLineEdit()
        layout.addWidget(add_account_name, row, 0)
        add_account_starting_balance = QtWidgets.QLineEdit()
        layout.addWidget(add_account_starting_balance, row, 1)
        button = QtWidgets.QPushButton('Add New')
        button.clicked.connect(self._save_new_account)
        layout.addWidget(button, row, 2)
        self.add_account_widgets = {
                'entries': {'name': add_account_name, 'starting_balance': add_account_starting_balance},
                'buttons': {'add_new': button},
            }
        self.setLayout(layout)

    def _save_new_account(self):
        name = self.add_account_widgets['entries']['name'].text()
        starting_balance = self.add_account_widgets['entries']['starting_balance'].text()
        try:
            account = pft.Account(name=name, starting_balance=starting_balance)
            self.storage.save_account(account)
            self._reload()
        except pft.InvalidAccountStartingBalanceError:
            set_widget_error_state(self.add_account_widgets['entries']['starting_balance'])
        except pft.InvalidAccountNameError:
            set_widget_error_state(self.add_account_widgets['entries']['name'])


def set_ledger_column_widths(layout):
    layout.setColumnStretch(0, 1)
    layout.setColumnStretch(1, 1)
    layout.setColumnStretch(2, 4)
    layout.setColumnStretch(3, 5)
    layout.setColumnStretch(4, 5)
    layout.setColumnStretch(5, 1)
    layout.setColumnStretch(6, 3)
    layout.setColumnStretch(7, 3)
    layout.setColumnStretch(8, 3)


class LedgerTxnsDisplay:

    def __init__(self, ledger):
        self.ledger = ledger
        self.txn_display_data = {}

    def get_widget(self):
        self.txns_layout = QtWidgets.QGridLayout()
        set_ledger_column_widths(self.txns_layout)
        self._redisplay_txns()
        txns_widget = QtWidgets.QWidget()
        txns_widget.setLayout(self.txns_layout)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(txns_widget)
        return scroll

    def display_new_txn(self, txn):
        self.ledger.add_transaction(txn)
        self._redisplay_txns()

    def _redisplay_txns(self):
        '''draw/redraw txns on the screen as needed'''
        balance = self.ledger._starting_balance
        for index, txn in enumerate(self.ledger.get_sorted_txns()):
            balance += txn.amount
            if txn.id not in self.txn_display_data or self.txn_display_data[txn.id]['row'] != index:
                self._display_txn(txn, row=index, layout=self.txns_layout, balance=balance)

    def _display_txn(self, txn, row, layout, balance):
        if txn.id in self.txn_display_data:
            for widget in self.txn_display_data[txn.id]['widgets']:
                layout.removeWidget(widget)
                widget.deleteLater()
        tds = txn.get_display_strings()
        type_label = QtWidgets.QLabel(tds['txn_type'])
        date_label = QtWidgets.QLabel(tds['txn_date'])
        payee_label = QtWidgets.QLabel(tds['payee'])
        description_label = QtWidgets.QLabel(tds['description'])
        categories_label = QtWidgets.QLabel(tds['categories'])
        status_label = QtWidgets.QLabel(tds['status'])
        credit_label = QtWidgets.QLabel(tds['credit'])
        debit_label = QtWidgets.QLabel(tds['debit'])
        balance_label = QtWidgets.QLabel(str(balance))
        layout.addWidget(type_label, row, 0)
        layout.addWidget(date_label, row, 1)
        layout.addWidget(payee_label, row, 2)
        layout.addWidget(description_label, row, 3)
        layout.addWidget(categories_label, row, 4)
        layout.addWidget(status_label, row, 5)
        layout.addWidget(debit_label, row, 6)
        layout.addWidget(credit_label, row, 7)
        layout.addWidget(balance_label, row, 8)
        self.txn_display_data[txn.id] = {
                'widgets': [type_label, date_label, payee_label, description_label, categories_label, status_label, credit_label, debit_label, balance_label],
                'row': row
            }


class LedgerDisplayWidget(QtWidgets.QWidget):

    def __init__(self, storage):
        super().__init__()
        self.storage = storage
        account = storage.get_accounts()[0]
        layout = QtWidgets.QGridLayout()
        set_ledger_column_widths(layout)
        self._show_headings(layout, row=0)
        self.ledger = pft.Ledger(starting_balance=account.starting_balance)
        storage.load_txns_into_ledger(account.id, self.ledger)
        self.txns_display = LedgerTxnsDisplay(self.ledger)
        layout.addWidget(self.txns_display.get_widget(), 1, 0, 1, 9)
        self.add_txn_widgets = {'entries': {}, 'buttons': {}}
        self._show_add_txn(layout, self.add_txn_widgets, row=2)
        self.setLayout(layout)

    def _show_headings(self, layout, row):
        layout.addWidget(QtWidgets.QLabel('Txn Type'), row, 0)
        layout.addWidget(QtWidgets.QLabel('Date'), row, 1)
        layout.addWidget(QtWidgets.QLabel('Payee'), row, 2)
        layout.addWidget(QtWidgets.QLabel('Description'), row, 3)
        layout.addWidget(QtWidgets.QLabel('Categories'), row, 4)
        layout.addWidget(QtWidgets.QLabel('Status'), row, 5)
        layout.addWidget(QtWidgets.QLabel('Debit (-)'), row, 6)
        layout.addWidget(QtWidgets.QLabel('Credit (+)'), row, 7)
        layout.addWidget(QtWidgets.QLabel('Balance'), row, 8)

    def _show_add_txn(self, layout, add_txn_widgets, row):
        entry_names = ['type', 'date', 'payee', 'description', 'categories', 'status', 'debit', 'credit']
        for index, entry_name in enumerate(entry_names):
            entry = QtWidgets.QLineEdit()
            add_txn_widgets['entries'][entry_name] = entry
            layout.addWidget(entry, row, index)
        add_new_button = QtWidgets.QPushButton('Add New')
        add_new_button.clicked.connect(self._save_new_txn)
        add_txn_widgets['buttons']['add_new'] = add_new_button
        layout.addWidget(add_new_button, row, 8)

    def _save_new_txn(self):
        txn_type = self.add_txn_widgets['entries']['type'].text()
        txn_date = self.add_txn_widgets['entries']['date'].text()
        payee = self.add_txn_widgets['entries']['payee'].text()
        description = self.add_txn_widgets['entries']['description'].text()
        categories = self.add_txn_widgets['entries']['categories'].text()
        status = self.add_txn_widgets['entries']['status'].text()
        credit = self.add_txn_widgets['entries']['credit'].text()
        debit = self.add_txn_widgets['entries']['debit'].text()
        categories = pft.txn_categories_from_string(self.storage, categories)
        txn = pft.Transaction.from_user_strings(
                account=self.storage.get_accounts()[0],
                txn_type=txn_type,
                credit=credit,
                debit=debit,
                txn_date=txn_date,
                payee=payee,
                description=description,
                status=status,
                categories=categories
            )
        self.storage.save_txn(txn)
        self.txns_display.display_new_txn(txn)
        self._clear_add_txn_widgets()

    def _clear_add_txn_widgets(self):
        for w in self.add_txn_widgets['entries'].values():
            w.setText('')


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
        self.add_button = QtWidgets.QPushButton('Add New')
        self.add_button.clicked.connect(self._add)
        layout.addWidget(self.add_button, row, 2)
        self.setLayout(layout)

    def _add(self):
        c = pft.Category(name=self.name_entry.text())
        self._storage.save_category(c)
        self._reload()


class BudgetDisplayWidget(QtWidgets.QWidget):

    def __init__(self, budget, storage, reload_budget):
        super().__init__()
        self.budget = budget
        self.storage = storage
        self.reload_budget = reload_budget
        self.layout = QtWidgets.QGridLayout()
        self.layout.addWidget(QtWidgets.QLabel('Category'), 0, 0)
        self.layout.addWidget(QtWidgets.QLabel('Amount'), 0, 1)
        self.layout.addWidget(QtWidgets.QLabel('Income'), 0, 2)
        self.layout.addWidget(QtWidgets.QLabel('Carryover'), 0, 3)
        self.layout.addWidget(QtWidgets.QLabel('Total Budget'), 0, 4)
        self.layout.addWidget(QtWidgets.QLabel('Spent'), 0, 5)
        self.layout.addWidget(QtWidgets.QLabel('Remaining'), 0, 6)
        self.layout.addWidget(QtWidgets.QLabel('Percent Available'), 0, 7)
        row_index = 1
        self.data = {}
        for cat, info in budget.get_report_display().items():
            self.layout.addWidget(QtWidgets.QLabel(cat.name), row_index, 0)
            budget_label = QtWidgets.QLabel(info['amount'])
            self.layout.addWidget(budget_label, row_index, 1)
            self.layout.addWidget(QtWidgets.QLabel(info['income']), row_index, 2)
            carryover_label = QtWidgets.QLabel(info['carryover'])
            self.layout.addWidget(carryover_label, row_index, 3)
            self.layout.addWidget(QtWidgets.QLabel(info['total_budget']), row_index, 4)
            self.layout.addWidget(QtWidgets.QLabel(info['spent']), row_index, 5)
            self.layout.addWidget(QtWidgets.QLabel(info['remaining']), row_index, 6)
            self.layout.addWidget(QtWidgets.QLabel(info['percent_available']), row_index, 7)
            row_data = {'budget_label': budget_label}
            row_data['carryover_label'] = carryover_label
            row_data['row_index'] = row_index
            row_data['category'] = cat
            self.data[cat.id] = row_data
            row_index += 1
        self.button_row_index = row_index
        self._edit_button = QtWidgets.QPushButton('Edit')
        self._edit_button.clicked.connect(self._edit)
        self.layout.addWidget(self._edit_button, self.button_row_index, 0)
        self.setLayout(self.layout)

    def _save(self):
        category_rows = {}
        for cat_id, info in self.data.items():
            cat = info['category']
            category_rows[cat] = {
                    'amount': info['budget_entry'].text(),
                    'carryover': info['carryover_entry'].text()
                }
        b = pft.Budget(id_=self.budget.id, year=self.budget.year, category_budget_info=category_rows)
        self.storage.save_budget(b)
        self.reload_budget()

    def _edit(self):
        for cat_id, info in self.data.items():
            budget_val = info['budget_label'].text()
            carryover_val = info['carryover_label'].text()
            self.layout.removeWidget(info['budget_label'])
            info['budget_label'].deleteLater()
            self.layout.removeWidget(info['carryover_label'])
            info['carryover_label'].deleteLater()
            budget_entry = QtWidgets.QLineEdit()
            budget_entry.setText(budget_val)
            self.layout.addWidget(budget_entry, info['row_index'], 1)
            info['budget_entry'] = budget_entry
            carryover_entry = QtWidgets.QLineEdit()
            carryover_entry.setText(carryover_val)
            self.layout.addWidget(carryover_entry, info['row_index'], 3)
            info['carryover_entry'] = carryover_entry
        self.layout.removeWidget(self._edit_button)
        self._edit_button.deleteLater()
        self._save_button = QtWidgets.QPushButton('Save')
        self._save_button.clicked.connect(self._save)
        self.layout.addWidget(self._save_button, self.button_row_index, 0)


class PFT_GUI_QT:

    def __init__(self, file_name):
        self.storage = pft.SQLiteStorage(file_name)
        title = 'Python Finance Tracking'
        self.parent_window = QtWidgets.QWidget()
        self.parent_window.setWindowTitle(title)
        self.parent_layout = QtWidgets.QGridLayout()
        self.parent_window.setLayout(self.parent_layout)
        self._show_action_buttons(self.parent_layout)

        self.content_area = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QGridLayout()
        self.content_area.setLayout(self.content_layout)
        self.main_widget = None
        self._show_accounts()
        self.parent_layout.addWidget(self.content_area, 1, 0, 1, 4)
        self.parent_window.showMaximized()

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
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self.main_widget = AccountsDisplayWidget(self.storage, reload_accounts=self._show_accounts)
        self.content_layout.addWidget(self.main_widget, 0, 0)

    def _show_ledger(self):
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self.main_widget = LedgerDisplayWidget(self.storage)
        self.content_layout.addWidget(self.main_widget, 0, 0)

    def _show_categories(self):
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self.main_widget = CategoriesDisplayWidget(self.storage, reload_categories=self._show_categories)
        self.content_layout.addWidget(self.main_widget, 0, 0)

    def _show_budget(self):
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        budgets = self.storage.get_budgets()
        self.main_widget = BudgetDisplayWidget(budgets[0], self.storage, self._show_budget)
        self.content_layout.addWidget(self.main_widget, 0, 0)


if __name__ == '__main__':
    args = pft.parse_args()
    app = QtWidgets.QApplication([])
    if args.file_name:
        gui = PFT_GUI_QT(args.file_name)
    else:
        gui = PFT_GUI_QT(pft.DATA_FILENAME)
    app.exec_()

