from datetime import date
from fractions import Fraction
from functools import partial

import bricbooks as bb


PYSIDE2_VERSION = '5.15.2'
PYSIDE6_VERSION = '6.2.1'


def _do_qt_install():
    if sys.version_info[1] > 9:
        pyside = f'PySide6=={PYSIDE6_VERSION}'
    else:
        pyside = f'PySide2=={PYSIDE2_VERSION}'
    cmd = [sys.executable, '-m', 'pip', 'install', pyside]
    print(f'installing Qt for Python ({pyside}): %s' % ' '.join(cmd))
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(result.stdout.decode('utf8'))
    except subprocess.CalledProcessError as e:
        print('Error installing Qt for Python')
        if e.stdout:
            print(e.stdout.decode('utf8'))
        if e.stderr:
            print(e.stderr.decode('utf8'))
        sys.exit(1)


def install_qt_for_python():
    install = input("couldn't import Qt for Python module - OK to download & install it (Y/n)?")
    if install.lower() != 'n':
        _do_qt_install()
        print('Please restart %s now.' % bb.TITLE)
        sys.exit(0)
    else:
        print('Exiting.')
        sys.exit(0)


try:
    from PySide2 import QtWidgets, QtGui, QtCore
except ImportError:
    try:
        from PySide6 import QtWidgets, QtGui, QtCore
    except ImportError:
        pass


def show_error(msg):
    msgbox = QtWidgets.QMessageBox()
    msgbox.setText(msg)
    msgbox.exec_()


ACCOUNTS_GUI_FIELDS = {
        'type': {'column_number': 0, 'column_stretch': 2, 'label': 'Type'},
        'number': {'column_number': 1, 'column_stretch': 1, 'label': 'Number'},
        'name': {'column_number': 2, 'column_stretch': 3, 'label': 'Name'},
        'parent': {'column_number': 3, 'column_stretch': 3, 'label': 'Parent'},
        'buttons': {'column_number': 4, 'column_stretch': 3},
    }


GUI_FIELDS = {
        'txn_type': {'column_number': 0, 'add_edit_column_number': 0, 'column_stretch': 1, 'label': 'Txn Type'},
        'txn_date': {'column_number': 1, 'add_edit_column_number': 1, 'column_stretch': 2, 'label': 'Date'},
        'payee': {'column_number': 2, 'add_edit_column_number': 2, 'column_stretch': 2, 'label': 'Payee'},
        'description': {'column_number': 3, 'add_edit_column_number': 3, 'column_stretch': 2, 'label': 'Description'},
        'status': {'column_number': 4, 'add_edit_column_number': 4, 'column_stretch': 1, 'label': 'Status'},
        'withdrawal': {'column_number': 5, 'add_edit_column_number': 5, 'column_stretch': 2, 'label': 'Withdrawal'},
        'deposit': {'column_number': 6, 'add_edit_column_number': 6, 'column_stretch': 2, 'label': 'Deposit'},
        'balance': {'column_number': 7, 'add_edit_column_number': -1, 'column_stretch': 2, 'label': 'Balance'},
        'categories': {'column_number': 8, 'add_edit_column_number': 7, 'column_stretch': 3, 'label': 'Categories'},
        'buttons': {'column_number': -1, 'add_edit_column_number': 8, 'column_stretch': 2, 'label': ''},
    }


class AccountForm:
    '''display widgets for Account data, and create a new
        Account when user finishes entering data'''

    def __init__(self, all_accounts, account=None, save_account=None):
        self._all_accounts = all_accounts
        self._account = account
        self._save_account = save_account
        self._widgets = {}

    def show_form(self):
        self._display = QtWidgets.QDialog()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self._show_widgets(layout, self._widgets)
        self._display.setLayout(layout)
        self._display.open()

    def _show_widgets(self, layout, widgets):
        row = 0
        for index, f in enumerate(['type', 'number', 'name', 'parent']):
            layout.addWidget(QtWidgets.QLabel(ACCOUNTS_GUI_FIELDS[f]['label']), row, index)
        row += 1
        account_type = QtWidgets.QComboBox()
        for index, type_ in enumerate(bb.AccountType):
            account_type.addItem(type_.name, type_)
            if self._account and self._account.type == type_:
                account_type.setCurrentIndex(index)
        layout.addWidget(account_type, row, ACCOUNTS_GUI_FIELDS['type']['column_number'])
        number = QtWidgets.QLineEdit()
        if self._account:
            number.setText(self._account.number)
        layout.addWidget(number, row, ACCOUNTS_GUI_FIELDS['number']['column_number'])
        name = QtWidgets.QLineEdit()
        if self._account:
            name.setText(self._account.name)
        layout.addWidget(name, row, ACCOUNTS_GUI_FIELDS['name']['column_number'])
        parent_combo = QtWidgets.QComboBox()
        parent_combo.addItem('---------', None)
        for index, acc in enumerate(self._all_accounts):
            parent_combo.addItem(acc.name, acc.id)
            if self._account and self._account.parent == acc:
                parent_combo.setCurrentIndex(index+1)
        layout.addWidget(parent_combo, row, ACCOUNTS_GUI_FIELDS['parent']['column_number'])
        button = QtWidgets.QPushButton('Save')
        button.clicked.connect(self._save_new_account)
        layout.addWidget(button, row, ACCOUNTS_GUI_FIELDS['buttons']['column_number'])
        widgets['type'] = account_type
        widgets['number'] = number
        widgets['name'] = name
        widgets['parent'] = parent_combo
        widgets['save_btn'] = button

    def _save_new_account(self):
        type_ = self._widgets['type'].currentData()
        number = self._widgets['number'].text()
        name = self._widgets['name'].text()
        parent_id = self._widgets['parent'].currentData()
        if self._account:
            id_ = self._account.id
            commodity_id = self._account.commodity.id
        else:
            id_ = None
            commodity_id = None
        try:
            self._save_account(id_=id_, type_=type_, commodity_id=commodity_id, number=number, name=name, parent_id=parent_id)
            self._display.accept()
        except bb.InvalidAccountNameError as e:
            show_error(msg=str(e))


def get_accounts_model_class():

    class Model(QtCore.QAbstractTableModel):

        def __init__(self, accounts):
            self._accounts = accounts
            super().__init__()

        def rowCount(self, parent):
            return len(self._accounts)

        def columnCount(self, parent):
            return 4

        def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
            if role == QtCore.Qt.DisplayRole:
                if orientation == QtCore.Qt.Horizontal:
                    if section == 0:
                        return 'Type'
                    elif section == 1:
                        return 'Number'
                    elif section == 2:
                        return 'Name'
                    elif section == 3:
                        return 'Parent'
            elif role == QtCore.Qt.TextAlignmentRole:
                return QtCore.Qt.AlignCenter

        def data(self, index, role=QtCore.Qt.DisplayRole):
            if role == QtCore.Qt.DisplayRole:
                if index.column() == 0:
                    return self._accounts[index.row()].type.name
                if index.column() == 1:
                    return self._accounts[index.row()].number
                if index.column() == 2:
                    return self._accounts[index.row()].name
                if index.column() == 3:
                    if self._accounts[index.row()].parent:
                        return str(self._accounts[index.row()].parent)
            elif role == QtCore.Qt.TextAlignmentRole:
                return QtCore.Qt.AlignCenter

        def get_account(self, index):
            return self._accounts[index.row()]

    return Model


class AccountsDisplay:

    def __init__(self, accounts, save_account, reload_accounts, model_class):
        self._accounts = accounts
        self._save_account = save_account
        self._reload = reload_accounts
        self._model_class = model_class
        self._accounts_model = self._get_accounts_model(self._accounts)
        self._accounts_widget = self._get_accounts_widget(self._accounts_model)

    def get_widget(self):
        main_widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        row = 0
        self.add_button = QtWidgets.QPushButton('New Account')
        self.add_button.clicked.connect(self._open_new_account_form)
        layout.addWidget(self.add_button, row, 0)
        row += 1
        layout.addWidget(self._accounts_widget, row, 0, 1, 5)
        main_widget.setLayout(layout)
        return main_widget

    def _get_accounts_model(self, accounts):
        return self._model_class(accounts)

    def _get_accounts_widget(self, model):
        widget = QtWidgets.QTableView()
        widget.setModel(model)
        widget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        widget.resizeColumnsToContents()
        widget.resizeRowsToContents()
        widget.clicked.connect(self._edit)
        return widget

    def _open_new_account_form(self):
        self.add_account_display = AccountForm(self._accounts, save_account=self._handle_new_account)
        self.add_account_display.show_form()

    def _handle_new_account(self, id_, type_, commodity_id, number, name, parent_id):
        self._save_account(id_=id_, type_=type_, commodity_id=commodity_id, number=number, name=name, parent_id=parent_id)
        self._reload()

    def _edit(self, index):
        account = self._accounts_model.get_account(index)
        self.edit_account_display = AccountForm(self._accounts, account=account, save_account=self._handle_new_account)
        self.edit_account_display.show_form()


def set_ledger_column_widths(layout):
    for field_info in GUI_FIELDS.values():
        if field_info['column_number'] >= 0:
            layout.setColumnStretch(field_info['column_number'], field_info['column_stretch'])


class SplitTransactionEditor:

    def __init__(self, all_accounts, initial_txn_splits):
        self._all_accounts = all_accounts
        self._initial_txn_splits = initial_txn_splits
        self._final_txn_splits = {}
        self._entries = {}

    def _get_txn_splits(self, split_editor):
        for value in self._entries.values():
            #value is amount_entry, account
            text = value[0].text()
            if text:
                self._final_txn_splits[value[1]] = {'amount': text}
        split_editor.accept()

    def _show_split_editor(self):
        split_editor = QtWidgets.QDialog()
        main_layout = QtWidgets.QGridLayout()
        main_widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        row = 0
        for account in self._all_accounts:
            layout.addWidget(QtWidgets.QLabel(str(account)), row, 0)
            amount_entry = QtWidgets.QLineEdit()
            for acc, split_info in self._initial_txn_splits.items():
                amt = split_info['amount']
                if acc == account:
                    amount_entry.setText(bb.amount_display(amt))
            self._entries[account.id] = (amount_entry, account)
            layout.addWidget(amount_entry, row, 1)
            row += 1
        ok_button = QtWidgets.QPushButton('Done')
        ok_button.clicked.connect(partial(self._get_txn_splits, split_editor=split_editor))
        cancel_button = QtWidgets.QPushButton('Cancel')
        cancel_button.clicked.connect(split_editor.reject)
        layout.addWidget(ok_button, row, 0)
        layout.addWidget(cancel_button, row, 1)
        main_widget.setLayout(layout)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(main_widget)
        main_layout.addWidget(scroll, 0, 0)
        split_editor.setLayout(main_layout)
        split_editor.exec_()

    def get_txn_splits(self):
        self._show_split_editor()
        return self._final_txn_splits


def get_txns_model_class():

    class Model(QtCore.QAbstractTableModel):

        def __init__(self, account, txns, scheduled_txns_due):
            self._account = account
            self._txns = txns
            self._scheduled_txns_due = scheduled_txns_due
            super().__init__()

        def rowCount(self, parent=None):
            return len(self._txns) + len(self._scheduled_txns_due)

        def columnCount(self, parent=None):
            return 9

        def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
            if role == QtCore.Qt.DisplayRole:
                if orientation == QtCore.Qt.Horizontal:
                    if section == 0:
                        return 'Type'
                    elif section == 1:
                        return 'Date'
                    elif section == 2:
                        return 'Payee'
                    elif section == 3:
                        return 'Description'
                    elif section == 4:
                        return 'Status'
                    elif section == 5:
                        return 'Withdrawal'
                    elif section == 6:
                        return 'Deposit'
                    elif section == 7:
                        return 'Balance'
                    elif section == 8:
                        return 'Transfer Account'
            if role == QtCore.Qt.TextAlignmentRole:
                return QtCore.Qt.AlignCenter

        def data(self, index, role=QtCore.Qt.DisplayRole):
            column = index.column()
            if role == QtCore.Qt.DisplayRole:
                row = index.row()
                is_scheduled_txn = False
                if row >= len(self._txns):
                    txn = self._scheduled_txns_due[row-len(self._txns)]
                    is_scheduled_txn = True
                else:
                    txn = self._txns[index.row()]
                tds = bb.get_display_strings_for_ledger(self._account, txn)
                if column == 0:
                    return tds['txn_type']
                if column == 1:
                    return tds['txn_date']
                if column == 2:
                    return tds['payee']
                if column == 3:
                    return tds['description']
                if column == 4:
                    if not is_scheduled_txn:
                        return tds['status']
                if column == 5:
                    return tds['withdrawal']
                if column == 6:
                    return tds['deposit']
                if column == 7:
                    return tds.get('balance', None)
                if column == 8:
                    return tds['categories']
            elif role == QtCore.Qt.BackgroundRole:
                row = index.row()
                is_scheduled_txn = False
                if row >= len(self._txns):
                    txn = self._scheduled_txns_due[row-len(self._txns)]
                    is_scheduled_txn = True
                else:
                    txn = self._txns[index.row()]
                if is_scheduled_txn:
                    return QtGui.QBrush(QtCore.Qt.gray)
            elif role == QtCore.Qt.TextAlignmentRole:
                if column != 3: #Description should be aligned left
                    return QtCore.Qt.AlignCenter

        def get_txn(self, index):
            row = index.row()
            if row >= len(self._txns):
                return self._scheduled_txns_due[row-len(self._txns)]
            else:
                return self._txns[row]

        def get_bottom_right_index(self):
            return self.createIndex(self.rowCount(), self.columnCount()-1)

        def add_txn(self, txn, new_txns, new_scheduled_txns_due):
            self._txns = new_txns
            self._scheduled_txns_due = new_scheduled_txns_due
            self.layoutChanged.emit()

        def update_txn(self, txn, new_txns, new_scheduled_txns_due):
            #txn edited:
            #   date could have changed, and moved this row up or down in the table
            #   amount could have changed, and affected all the subsequence balances
            #   any of the fields of this txn could have changed
            #initial_row_index = -1
            #for index, t in enumerate(self._txns):
            #    if t == txn:
            #        initial_row_index = index
            #        break
            self._txns = new_txns
            self._scheduled_txns_due = new_scheduled_txns_due
            #final_row_index = -1
            #for index, t in enumerate(self._txns):
            #    if t == txn:
            #        final_row_index = index
            #        break
            #if initial_row_index > final_row_index:
            #    topLeft = self.createIndex(final_row_index, 0)
            #    bottomRight = self.createIndex(initial_row_index, self.columnCount())
            #else:
            #    topLeft = self.createIndex(initial_row_index, 0)
            #    bottomRight = self.createIndex(final_row_index, self.columnCount())
            #this updates everything - we should add checks so we only update what needs to be changed
            self.layoutChanged.emit()

        def update_txn_status(self, txn, new_txns, new_scheduled_txns_due):
            row_index = -1
            for index, t in enumerate(self._txns):
                if t == txn:
                    row_index = index
                    break
            self._txns = new_txns
            self._scheduled_txns_due = new_scheduled_txns_due
            status_index = self.createIndex(row_index, 4)
            self.dataChanged.emit(status_index, status_index)

        def remove_txn(self, txn, new_txns, new_scheduled_txns_due):
            self._txns = new_txns
            self._scheduled_txns_due = new_scheduled_txns_due
            self.layoutChanged.emit()

    return Model


class LedgerTxnsDisplay:

    def __init__(self, engine, account, filter_text, filter_account_id, post_update_function, model_class, display_ledger):
        self.engine = engine
        self.account = account
        self._status = ''
        self._filter_text = ''
        filter_parts = filter_text.split()
        for fp in filter_parts:
            if fp.startswith('status:'):
                self._status = fp.replace('status:', '')
            else:
                self._filter_text += f' {fp}'
        self._filter_account_id = filter_account_id
        self._scheduled_txn_widgets = []
        #post_update_function is for updating the balances widgets
        self._post_update_function = post_update_function
        self._display_ledger = display_ledger
        self._model_class = model_class
        self._txns_model = self._model_class(
                self.account,
                self._get_txns(),
                self.engine.get_scheduled_transactions_due(accounts=[self.account])
            )
        self._txns_widget = self._get_txns_widget(self._txns_model)

    def get_widget(self):
        self.main_widget = QtWidgets.QScrollArea()
        self.main_widget.setWidgetResizable(True)
        self.main_widget.setWidget(self._txns_widget)
        return self.main_widget

    def _get_txns_widget(self, txns_model):
        widget = QtWidgets.QTableView()
        widget.setModel(txns_model)
        widget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        widget.resizeColumnsToContents()
        widget.resizeRowsToContents()
        widget.clicked.connect(self._edit)
        return widget

    def handle_new_txn(self, txn):
        self.engine.save_transaction(txn)
        self._txns_model.add_txn(
                txn,
                self._get_txns(),
                self.engine.get_scheduled_transactions_due()
            )
        self._post_update_function()

    def _get_txns(self):
        accounts = [self.account]
        if self._filter_account_id:
            accounts.append(self.engine.get_account(id_=self._filter_account_id))
        return self.engine.get_transactions(accounts=accounts, status=self._status.strip(), query=self._filter_text.strip())

    def _delete(self, txn):
        self.engine.delete_transaction(txn.id)
        self._txns_model.remove_txn(
                txn,
                self._get_txns(),
                self.engine.get_scheduled_transactions_due()
            )
        self._post_update_function()

    def _save_edit(self, txn):
        self.engine.save_transaction(txn)
        self._txns_model.update_txn(
                txn,
                self._get_txns(),
                self.engine.get_scheduled_transactions_due()
            )
        self._post_update_function()

    def _edit(self, index):
        txn = self._txns_model.get_txn(index)
        if isinstance(txn, bb.ScheduledTransaction):
            self._show_scheduled_txn_form(txn)
        #if status column was clicked, just update status instead of opening edit form
        elif index.column() == 4:
            txn.update_reconciled_state(account=self.account)
            self.engine.save_transaction(txn)
            self._txns_model.update_txn_status(
                    txn,
                    self._get_txns(),
                    self.engine.get_scheduled_transactions_due()
                )
            self._post_update_function()
        else:
            self.edit_txn_display = TxnForm(
                    accounts=self.engine.get_accounts(types=[bb.AccountType.EXPENSE, bb.AccountType.INCOME, bb.AccountType.ASSET, bb.AccountType.LIABILITY, bb.AccountType.EQUITY]),
                    payees=self.engine.get_payees(),
                    save_txn=self._save_edit,
                    current_account=self.account,
                    txn=txn,
                    delete_txn=self._delete
                )
            self.edit_txn_display.show_form()

    def _enter_scheduled_txn(self, new_txn, scheduled_txn):
        scheduled_txn.advance_to_next_due_date()
        self.engine.save_scheduled_transaction(scheduled_txn)
        self.engine.save_transaction(new_txn)
        self._display_ledger()
        self._post_update_function()

    def _skip_scheduled_txn(self, scheduled_txn_id):
        self.engine.skip_scheduled_transaction(scheduled_txn_id)
        self._display_ledger()

    def _show_scheduled_txn_form(self, scheduled_txn):
        save_txn = partial(self._enter_scheduled_txn, scheduled_txn=scheduled_txn)
        self.scheduled_txn_display = TxnForm(
                accounts=self.engine.get_accounts(types=[bb.AccountType.EXPENSE, bb.AccountType.INCOME, bb.AccountType.ASSET, bb.AccountType.LIABILITY, bb.AccountType.EQUITY]),
                payees=self.engine.get_payees(),
                save_txn=save_txn,
                current_account=self.account,
                txn=scheduled_txn,
                skip_txn=partial(self._skip_scheduled_txn, scheduled_txn_id=scheduled_txn.id)
            )
        self.scheduled_txn_display.show_form()


def get_new_txn_splits(accounts, initial_txn_splits):
    editor = SplitTransactionEditor(accounts, initial_txn_splits)
    return editor.get_txn_splits()


class TxnAccountsDisplay:

    def __init__(self, accounts=None, main_account=None, txn=None):
        self._accounts = accounts
        self._main_account = main_account
        self._txn = txn
        layout = QtWidgets.QGridLayout()
        self._categories_combo = QtWidgets.QComboBox()
        self._categories_combo.addItem('---------', None)
        current_index = 0
        index = 0
        for account in self._accounts:
            if account != self._main_account:
                #find correct account in the list if txn has just two splits
                if txn and len(txn.splits.keys()) == 2:
                    if account in txn.splits:
                        current_index = index + 1
                self._categories_combo.addItem(str(account), account)
                index += 1
        self._multiple_entry_index = index + 1
        current_categories = []
        if txn and len(txn.splits.keys()) > 2:
            current_categories = txn.splits
            current_index = self._multiple_entry_index
        self._categories_combo.addItem('multiple', current_categories)
        self._categories_combo.setCurrentIndex(current_index)
        layout.addWidget(self._categories_combo, 0, 0)
        self.split_button = QtWidgets.QPushButton('Split')
        txn_id = None
        if txn:
            txn_id = txn.id
        self.split_button.clicked.connect(self._split_transactions)
        layout.addWidget(self.split_button)
        self._widget = QtWidgets.QWidget()
        self._widget.setLayout(layout)

    def _split_transactions(self):
        initial_txn_splits = {}
        if self._txn:
            initial_txn_splits = self._txn.splits
        new_txn_splits = get_new_txn_splits(self._accounts, initial_txn_splits)
        if new_txn_splits and new_txn_splits != initial_txn_splits:
            self._categories_combo.setCurrentIndex(self._multiple_entry_index)
            self._categories_combo.setItemData(self._multiple_entry_index, new_txn_splits)

    def get_categories(self):
        splits = self._categories_combo.currentData()
        #remove main account split (if present), because that comes from withdrawal/deposit fields
        if isinstance(splits, dict):
            splits.pop(self._main_account, None)
        return splits

    def get_widget(self):
        return self._widget


class TxnForm:
    '''Display widgets for Transaction data, and create a new
    Transaction when user finishes entering data.
    Displays ScheduledTransaction actions if txn is a ScheduledTxn.'''

    def __init__(self, accounts, payees, save_txn, current_account, txn=None, delete_txn=None, skip_txn=None):
        self._accounts = accounts
        self._payees = payees
        self._save_txn = save_txn
        self._current_account = current_account
        self._txn = txn
        self._delete_txn = delete_txn
        self._skip_txn = skip_txn
        self._widgets = {}

    def show_form(self):
        self._txn_display = QtWidgets.QDialog()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        set_ledger_column_widths(layout)
        self._show_widgets(layout, payees=self._payees, txn=self._txn, current_account=self._current_account)
        self._txn_display.setLayout(layout)
        self._txn_display.open()

    def _show_widgets(self, layout, payees, txn, current_account):
        tds = {}
        if txn:
            tds = bb.get_display_strings_for_ledger(current_account, txn)
        labels = [None, None, None, None, None, None, None, None, None]
        widgets = [None, None, None, None, None, None, None, None, None]
        for name in ['txn_type', 'txn_date', 'description', 'withdrawal', 'deposit']:
            entry = QtWidgets.QLineEdit()
            if self._txn:
                entry.setText(tds[name])
            else:
                if name == 'txn_date':
                    entry.setText(str(date.today()))
            self._widgets[name] = entry
            widgets[GUI_FIELDS[name]['add_edit_column_number']] = entry
            labels[GUI_FIELDS[name]['add_edit_column_number']] = QtWidgets.QLabel(GUI_FIELDS[name]['label'])
        status_entry = QtWidgets.QComboBox()
        for index, status in enumerate(['', bb.Transaction.CLEARED, bb.Transaction.RECONCILED]):
            status_entry.addItem(status)
            try:
                if self._txn and self._txn.splits[self._current_account].get('status') == status:
                    status_entry.setCurrentIndex(index)
            except AttributeError: #ScheduledTxn doesn't have a status
                pass
        self._widgets['status'] = status_entry
        widgets[GUI_FIELDS['status']['add_edit_column_number']] = status_entry
        labels[GUI_FIELDS['status']['add_edit_column_number']] = QtWidgets.QLabel(GUI_FIELDS['status']['label'])
        payee_entry = QtWidgets.QComboBox()
        payee_entry.setEditable(True)
        payee_entry.addItem('')
        payee_index = 0
        for index, payee in enumerate(payees):
            payee_entry.addItem(payee.name, payee)
            if self._txn and payee.name == tds['payee']:
                payee_index = index + 1 #because of first empty item
        if self._txn:
            payee_entry.setCurrentIndex(payee_index)
        self._widgets['payee'] = payee_entry
        widgets[GUI_FIELDS['payee']['add_edit_column_number']] = payee_entry
        labels[GUI_FIELDS['payee']['add_edit_column_number']] = QtWidgets.QLabel(GUI_FIELDS['payee']['label'])
        txn_accounts_display = TxnAccountsDisplay(
                accounts=self._accounts,
                main_account=self._current_account,
                txn=self._txn
            )
        widgets[GUI_FIELDS['categories']['add_edit_column_number']] = txn_accounts_display.get_widget()
        labels[GUI_FIELDS['categories']['add_edit_column_number']] = QtWidgets.QLabel(GUI_FIELDS['categories']['label'])
        self._widgets['accounts_display'] = txn_accounts_display
        if isinstance(self._txn, bb.ScheduledTransaction):
            button = QtWidgets.QPushButton('Enter New Txn')
        elif self._txn:
            button = QtWidgets.QPushButton('Save Edit')
        else:
            button = QtWidgets.QPushButton('Add New')
        self._widgets['save_btn'] = button
        button.clicked.connect(self._save)
        widgets[GUI_FIELDS['buttons']['add_edit_column_number']] = button
        for index, label in enumerate(labels):
            if label:
                layout.addWidget(label, 0, index)
        for index, widget in enumerate(widgets):
            layout.addWidget(widget, 1, index)
        if self._txn:
            delete_button = QtWidgets.QPushButton('Delete Txn')
            delete_button.clicked.connect(self.delete)
            self._widgets['delete_btn'] = delete_button
            layout.addWidget(delete_button, 2, 0)
            if isinstance(self._txn, bb.ScheduledTransaction):
                button = QtWidgets.QPushButton('Skip Next Txn')
                button.clicked.connect(self._skip)
                self._widgets['skip_btn'] = button
                layout.addWidget(button, 2, GUI_FIELDS['buttons']['add_edit_column_number'])

    def _save(self):
        txn_type = self._widgets['txn_type'].text()
        txn_date = self._widgets['txn_date'].text()
        payee = self._widgets['payee'].currentData()
        if not payee:
            payee = self._widgets['payee'].currentText()
        description = self._widgets['description'].text()
        categories = self._widgets['accounts_display'].get_categories()
        status = self._widgets['status'].currentText()
        deposit = self._widgets['deposit'].text()
        withdrawal = self._widgets['withdrawal'].text()
        kwargs = {
            'account': self._current_account,
            'txn_type': txn_type,
            'deposit': deposit,
            'withdrawal': withdrawal,
            'txn_date': txn_date,
            'payee': payee,
            'description': description,
            'status': status,
            'categories': categories,
        }
        if self._txn and not isinstance(self._txn, bb.ScheduledTransaction):
            kwargs['id_'] = self._txn.id
        try:
            txn = bb.Transaction.from_user_info(**kwargs)
            self._save_txn(txn)
            self._txn_display.accept()
        except Exception as e:
            show_error(msg=str(e))

    def delete(self):
        self._delete_txn(self._txn)
        self._txn_display.accept()

    def _skip(self):
        self._skip_txn()
        self._txn_display.accept()


class ScheduledTxnForm:

    def __init__(self, accounts, payees, save_scheduled_txn, scheduled_txn=None):
        self._accounts = accounts
        self._payees = payees
        self._scheduled_txn = scheduled_txn
        self._save_scheduled_txn = save_scheduled_txn
        self._widgets = {}

    def show_form(self):
        self._display = QtWidgets.QDialog()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        set_ledger_column_widths(layout)
        self._show_widgets(layout)
        self._display.setLayout(layout)
        self._display.open()

    def _show_widgets(self, layout):
        layout.addWidget(QtWidgets.QLabel('Name'), 0, 0)
        name_entry = QtWidgets.QLineEdit()
        if self._scheduled_txn:
            name_entry.setText(self._scheduled_txn.name)
        self._widgets['name'] = name_entry
        layout.addWidget(name_entry, 0, 1)
        layout.addWidget(QtWidgets.QLabel('Frequency'), 1, 0)
        frequency_entry = QtWidgets.QComboBox()
        frequency_index = 0
        for index, frequency in enumerate(bb.ScheduledTransactionFrequency):
            frequency_entry.addItem(frequency.name, frequency)
            if self._scheduled_txn and frequency == self._scheduled_txn.frequency:
                frequency_index = index
        if self._scheduled_txn:
            frequency_entry.setCurrentIndex(frequency_index)
        self._widgets['frequency'] = frequency_entry
        layout.addWidget(frequency_entry, 1, 1)
        layout.addWidget(QtWidgets.QLabel('Next Due Date'), 2, 0)
        next_due_date_entry = QtWidgets.QLineEdit()
        if self._scheduled_txn:
            next_due_date_entry.setText(str(self._scheduled_txn.next_due_date))
        self._widgets['next_due_date'] = next_due_date_entry
        layout.addWidget(next_due_date_entry, 2, 1)

        layout.addWidget(QtWidgets.QLabel('Payee'), 3, 0)
        payee_entry = QtWidgets.QComboBox()
        payee_entry.setEditable(True)
        payee_entry.addItem('')
        payee_index = 0
        for index, payee in enumerate(self._payees):
            payee_entry.addItem(payee.name, payee)
            if self._scheduled_txn and self._scheduled_txn.payee and self._scheduled_txn.payee.name == payee.name:
                payee_index = index + 1 #because of first empty item
        if self._scheduled_txn:
            payee_entry.setCurrentIndex(payee_index)
        self._widgets['payee'] = payee_entry
        layout.addWidget(payee_entry, 3, 1)

        account = deposit = withdrawal = None
        if self._scheduled_txn:
            account = list(self._scheduled_txn.splits.keys())[0]
            amount = self._scheduled_txn.splits[account]['amount']
            if amount > 0:
                deposit = bb.amount_display(amount)
            else:
                withdrawal = bb.amount_display(amount * Fraction(-1))

        layout.addWidget(QtWidgets.QLabel('Account'), 4, 0)
        account_entry = QtWidgets.QComboBox()
        account_index = -1
        for index, acct in enumerate(self._accounts):
            account_entry.addItem(acct.name, acct)
            if account and account == acct:
                account_index = index
        if account:
            account_entry.setCurrentIndex(account_index)
        self._widgets['account'] = account_entry
        layout.addWidget(account_entry, 4, 1)
        layout.addWidget(QtWidgets.QLabel('Withdrawal'), 5, 0)
        withdrawal_entry = QtWidgets.QLineEdit()
        if withdrawal:
            withdrawal_entry.setText(withdrawal)
        self._widgets['withdrawal'] = withdrawal_entry
        layout.addWidget(withdrawal_entry, 5, 1)
        layout.addWidget(QtWidgets.QLabel('Deposit'), 6, 0)
        deposit_entry = QtWidgets.QLineEdit()
        if deposit:
            deposit_entry.setText(deposit)
        self._widgets['deposit'] = deposit_entry
        layout.addWidget(deposit_entry, 6, 1)
        layout.addWidget(QtWidgets.QLabel('Categories'), 7, 0)
        txn_accounts_display = TxnAccountsDisplay(
                accounts=self._accounts,
                txn=self._scheduled_txn,
                main_account=account
            )
        self._widgets['accounts_display'] = txn_accounts_display
        layout.addWidget(txn_accounts_display.get_widget(), 7, 1)
        save_button = QtWidgets.QPushButton('Save')
        save_button.clicked.connect(self._save)
        self._widgets['save_btn'] = save_button
        layout.addWidget(save_button, 8, 0)

    def _save(self):
        payee = self._widgets['payee'].currentData()
        if not payee:
            payee = self._widgets['payee'].currentText()
        account = self._widgets['account'].currentData()
        deposit = self._widgets['deposit'].text()
        withdrawal = self._widgets['withdrawal'].text()
        categories = self._widgets['accounts_display'].get_categories()
        splits = bb.Transaction.splits_from_user_info(
                account=account,
                deposit=deposit,
                withdrawal=withdrawal,
                input_categories=categories
            )
        if self._scheduled_txn:
            id_ = self._scheduled_txn.id
        else:
            id_ = None
        st = bb.ScheduledTransaction(
                name=self._widgets['name'].text(),
                frequency=self._widgets['frequency'].currentData(),
                next_due_date=self._widgets['next_due_date'].text(),
                splits=splits,
                payee=payee,
                id_=id_,
            )
        self._save_scheduled_txn(scheduled_txn=st)
        self._display.accept()


class LedgerDisplay:

    def __init__(self, engine, txns_model_class, current_account=None):
        self._engine = engine
        self._txns_model_class = txns_model_class
        #choose an account if there is one
        if not current_account:
            accounts = self._engine.get_accounts(types=[bb.AccountType.ASSET])
            if accounts:
                current_account = accounts[0]
        self._current_account = current_account
        self.txns_display_widget = None
        self.balances_widget = None

    def get_widget(self):
        self.widget, self.layout = self._setup_main()
        if self._current_account:
            self._display_ledger(self.layout, self._current_account)
        else:
            self.layout.addWidget(QtWidgets.QLabel(''), self._ledger_txns_row_index, 0, 1, 9)
            self.layout.setRowStretch(self._ledger_txns_row_index, 1)
        return self.widget

    def _setup_main(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        new_row = self._show_headings(layout, row=0)
        self._ledger_txns_row_index = new_row
        widget.setLayout(layout)
        return widget, layout

    def _display_ledger(self, layout, account, filter_text='', filter_account_id=None):
        self.txns_display = LedgerTxnsDisplay(self._engine, account, filter_text, filter_account_id,
                post_update_function=partial(self._display_balances_widget, layout=layout),
                model_class=self._txns_model_class,
                display_ledger=partial(self._display_ledger, layout=layout, account=account))
        if self.txns_display_widget:
            layout.removeWidget(self.txns_display_widget)
            self.txns_display_widget.deleteLater()
        self.txns_display_widget = self.txns_display.get_widget()
        layout.addWidget(self.txns_display_widget, self._ledger_txns_row_index, 0, 1, 9)
        self._display_balances_widget(layout)

    def _display_balances_widget(self, layout):
        if self.balances_widget:
            layout.removeWidget(self.balances_widget)
            self.balances_widget.deleteLater()
        self.balances_widget = self._get_balances_widget()
        layout.addWidget(self.balances_widget, self._ledger_txns_row_index+1, 0, 1, 9)

    def _get_balances_widget(self):
        #this is a row below the list of txns
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        balances = self._engine.get_current_balances_for_display(account=self._current_account)
        balance_text = f'Current Balance: {balances.current}'
        cleared_text = f'Cleared: {balances.current_cleared}'
        layout.addWidget(QtWidgets.QLabel(cleared_text), 0, 0)
        layout.addWidget(QtWidgets.QLabel(balance_text), 0, 1)
        widget.setLayout(layout)
        return widget

    def _update_account(self, index):
        self._current_account = self._engine.get_accounts()[index]
        self._display_ledger(layout=self.layout, account=self._current_account)

    def _filter_txns(self):
        self._display_ledger(layout=self.layout, account=self._current_account, filter_text=self._filter_box.text(), filter_account_id=self.filter_account_combo.currentData())

    def _show_all_txns(self):
        self._filter_box.setText('')
        self._display_ledger(layout=self.layout, account=self._current_account)

    def _show_headings(self, layout, row):
        self.action_combo = QtWidgets.QComboBox()
        current_index = 0
        accounts = self._engine.get_ledger_accounts()
        for index, a in enumerate(accounts):
            if a.id == self._current_account.id:
                current_index = index
            self.action_combo.addItem(a.name)
        self.action_combo.setCurrentIndex(current_index)
        self.action_combo.currentIndexChanged.connect(self._update_account)
        layout.addWidget(self.action_combo, row, 0)
        self.add_button = QtWidgets.QPushButton('New Txn')
        self.add_button.clicked.connect(self._open_new_txn_form)
        layout.addWidget(self.add_button, row, 1)
        self._filter_box = QtWidgets.QLineEdit()
        layout.addWidget(self._filter_box, row, 2)
        self.filter_account_combo = QtWidgets.QComboBox()
        self.filter_account_combo.addItem('All Transfer Accounts', None)
        accounts = self._engine.get_accounts(types=[bb.AccountType.EXPENSE, bb.AccountType.INCOME, bb.AccountType.ASSET, bb.AccountType.LIABILITY, bb.AccountType.EQUITY, bb.AccountType.SECURITY])
        for a in accounts:
            if a != self._current_account:
                self.filter_account_combo.addItem(a.name, a.id)
        layout.addWidget(self.filter_account_combo, row, 3)
        self._filter_btn = QtWidgets.QPushButton('Filter')
        self._filter_btn.clicked.connect(self._filter_txns)
        layout.addWidget(self._filter_btn, row, 4)
        clear_btn = QtWidgets.QPushButton('Show all')
        clear_btn.clicked.connect(self._show_all_txns)
        layout.addWidget(clear_btn, row, 5)
        return row + 1

    def _open_new_txn_form(self):
        self.add_txn_display = TxnForm(
                accounts=self._engine.get_accounts(types=[bb.AccountType.EXPENSE, bb.AccountType.INCOME, bb.AccountType.ASSET, bb.AccountType.LIABILITY, bb.AccountType.EQUITY]),
                payees=self._engine.get_payees(),
                save_txn=self.txns_display.handle_new_txn,
                current_account=self._current_account
            )
        self.add_txn_display.show_form()


class BudgetForm:
    '''Handle editing an existing budget or creating a new one'''

    def __init__(self, budget=None, accounts=None, save_budget=None):
        if budget and accounts:
            raise BudgetError('pass budget or accounts, not both')
        self._budget = budget
        self._widgets = {'budget_data': {}}
        self._save_budget = save_budget
        self._accounts = accounts
        if self._budget:
            self._budget_data = self._budget.get_budget_data()
        else:
            self._budget_data = {}
            for account in self._accounts:
                self._budget_data[account] = {}

    def show_form(self):
        layout = QtWidgets.QGridLayout()
        self._show_widgets(layout, self._widgets)
        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        top_layout = QtWidgets.QGridLayout()
        top_layout.addWidget(scroll, 0, 0)
        self._display = QtWidgets.QDialog()
        self._display.setLayout(top_layout)
        self._display.open()

    def _show_widgets(self, layout, widgets):
        row = 0
        for index, label in enumerate(['Start Date', 'End Date']):
            layout.addWidget(QtWidgets.QLabel(label), row, index)
        row += 1
        start_date = QtWidgets.QLineEdit()
        end_date = QtWidgets.QLineEdit()
        if self._budget:
            start_date.setText(str(self._budget.start_date))
            end_date.setText(str(self._budget.end_date))
        layout.addWidget(start_date, row, 0)
        layout.addWidget(end_date, row, 1)
        widgets['start_date'] = start_date
        widgets['end_date'] = end_date
        row += 1
        layout.addWidget(QtWidgets.QLabel('Amount'), row, 1)
        layout.addWidget(QtWidgets.QLabel('Carryover'), row, 2)
        row += 1
        for account, info in self._budget_data.items():
            layout.addWidget(QtWidgets.QLabel(str(account)), row, 0)
            amount = QtWidgets.QLineEdit()
            carryover = QtWidgets.QLineEdit()
            amount.setText(str(info.get('amount', '')))
            carryover.setText(str(info.get('carryover', '')))
            widgets['budget_data'][account] = {
                    'amount': amount,
                    'carryover': carryover,
                }
            layout.addWidget(amount, row, 1)
            layout.addWidget(carryover, row, 2)
            row += 1
        save_button = QtWidgets.QPushButton('Save')
        save_button.clicked.connect(self._save)
        layout.addWidget(save_button, row, 0)

    def _save(self):
        start_date = self._widgets['start_date'].text()
        end_date = self._widgets['end_date'].text()
        account_budget_info = {}
        for account, widgets in self._widgets['budget_data'].items():
            account_budget_info[account] = {'amount': widgets['amount'].text(), 'carryover': widgets['carryover'].text()}
        if self._budget:
            b = bb.Budget(start_date=start_date, end_date=end_date, id_=self._budget.id, account_budget_info=account_budget_info)
        else:
            b = bb.Budget(start_date=start_date, end_date=end_date, account_budget_info=account_budget_info)
        self._save_budget(b)
        self._display.accept()


def get_budget_model_class():

    class Model(QtCore.QAbstractTableModel):

        def __init__(self, budget):
            self._budget_report = budget.get_report_display(current_date=date.today())
            self._report_data = []
            for info in self._budget_report['income']:
                self._report_data.append(info)
            for info in self._budget_report['expense']:
                self._report_data.append(info)
            super().__init__()

        def rowCount(self, parent):
            return len(self._report_data)

        def columnCount(self, parent):
            return 9

        def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
            if role == QtCore.Qt.DisplayRole:
                if orientation == QtCore.Qt.Horizontal:
                    if section == 0:
                        return 'Account'
                    elif section == 1:
                        return 'Amount'
                    elif section == 2:
                        return 'Income'
                    elif section == 3:
                        return 'Carryover'
                    elif section == 4:
                        return 'Total Budget'
                    elif section == 5:
                        return 'Spent'
                    elif section == 6:
                        return 'Remaining'
                    elif section == 7:
                        return 'Remaining Percent'
                    elif section == 8:
                        return 'Current Status'
            elif role == QtCore.Qt.TextAlignmentRole:
                return QtCore.Qt.AlignCenter

        def data(self, index, role=QtCore.Qt.DisplayRole):
            if role == QtCore.Qt.DisplayRole:
                if index.column() == 0:
                    return self._report_data[index.row()].get('name', '')
                if index.column() == 1:
                    return self._report_data[index.row()].get('amount', '')
                if index.column() == 2:
                    return self._report_data[index.row()].get('income', '')
                if index.column() == 3:
                    return self._report_data[index.row()].get('carryover', '')
                if index.column() == 4:
                    return self._report_data[index.row()].get('total_budget', '')
                if index.column() == 5:
                    return self._report_data[index.row()].get('spent', '')
                if index.column() == 6:
                    return self._report_data[index.row()].get('remaining', '')
                if index.column() == 7:
                    return self._report_data[index.row()].get('remaining_percent', '')
                if index.column() == 8:
                    return self._report_data[index.row()].get('current_status', '')
            elif role == QtCore.Qt.TextAlignmentRole:
                return QtCore.Qt.AlignCenter

    return Model


class BudgetDataDisplay:
    '''Just for displaying budget values and income/expense data.'''

    def __init__(self, budget, save_budget, budget_model_class):
        self._budget = budget
        self._save_budget = save_budget
        self._budget_model_class = budget_model_class

    def _get_model(self):
        return self._budget_model_class(self._budget)

    def get_widget(self):
        model = self._get_model()
        self.main_widget = QtWidgets.QTableView()
        self.main_widget.setModel(model)
        self.main_widget.resizeColumnsToContents()
        return self.main_widget


class BudgetDisplay:

    def __init__(self, engine, budget_model_class, current_budget=None):
        self._engine = engine
        self._budget_model_class = budget_model_class
        if not current_budget:
            budgets = self._engine.get_budgets()
            if budgets:
                current_budget = budgets[0]
        self._current_budget = current_budget
        self._budget_select_combo = None
        self._budget_data_display_widget = None

    def get_widget(self):
        self.widget, self.layout, self._row_index = self._setup_main()
        if self._current_budget:
            self._display_budget(self.layout, self._current_budget, self._row_index)
        else:
            self.layout.addWidget(QtWidgets.QLabel(''), self._row_index, 0, 1, 6)
            self.layout.setRowStretch(self._row_index, 1)
        return self.widget

    def _setup_main(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        row_index = self._show_headings(layout, row=0)
        widget.setLayout(layout)
        return widget, layout, row_index

    def _display_budget(self, layout, budget, row):
        self.budget_data_display = BudgetDataDisplay(budget, save_budget=self._save_budget_and_reload, budget_model_class=self._budget_model_class)
        if self._budget_data_display_widget:
            layout.removeWidget(self._budget_data_display_widget)
            self._budget_data_display_widget.deleteLater()
        self._budget_data_display_widget = self.budget_data_display.get_widget()
        layout.addWidget(self._budget_data_display_widget, row, 0, 1, 9)
        row += 1
        self._edit_button = QtWidgets.QPushButton('Edit')
        self._edit_button.clicked.connect(partial(self._open_form, budget=budget))
        layout.addWidget(self._edit_button, row, 0)

    def _update_budget(self, index=0):
        self._current_budget = self._engine.get_budgets()[index]
        self._budget_select_combo.setCurrentIndex(index)
        self._display_budget(layout=self.layout, budget=self._current_budget, row=self._row_index)

    def _show_headings(self, layout, row):
        self._budget_select_combo = QtWidgets.QComboBox()
        current_index = 0
        budgets = self._engine.get_budgets()
        for index, budget in enumerate(budgets):
            if budget == self._current_budget:
                current_index = index
            self._budget_select_combo.addItem(budget.display(show_id=False), budget)
        self._budget_select_combo.setCurrentIndex(current_index)
        self._budget_select_combo.currentIndexChanged.connect(self._update_budget)
        layout.addWidget(self._budget_select_combo, row, 0)
        self.add_button = QtWidgets.QPushButton('New Budget')
        self.add_button.clicked.connect(partial(self._open_form, budget=None))
        layout.addWidget(self.add_button, row, 1)
        return row + 1

    def _save_budget_and_reload(self, budget, new_budget=False):
        self._engine.save_budget(budget)
        #need to reload budget from storage here, so txn info is picked up
        self._current_budget = self._engine.get_budget(id_=budget.id)
        if new_budget:
            #need to add new budget to select combo and select it
            num_items = self._budget_select_combo.count()
            self._budget_select_combo.addItem(self._current_budget.display(show_id=False), self._current_budget)
            self._budget_select_combo.setCurrentIndex(num_items)
        self._display_budget(layout=self.layout, budget=self._current_budget, row=self._row_index)

    def _open_form(self, budget):
        if budget:
            self.budget_form = BudgetForm(budget=budget, save_budget=self._save_budget_and_reload)
        else:
            income_and_expense_accounts = self._engine.get_accounts(types=[bb.AccountType.INCOME, bb.AccountType.EXPENSE])
            self.budget_form = BudgetForm(accounts=income_and_expense_accounts, save_budget=partial(self._save_budget_and_reload, new_budget=True))
        self.budget_form.show_form()


def get_scheduled_txns_model_class():

    class Model(QtCore.QAbstractTableModel):

        def __init__(self, scheduled_txns):
            self._scheduled_txns = scheduled_txns
            super().__init__()

        def rowCount(self, parent):
            return len(self._scheduled_txns)

        def columnCount(self, parent):
            return 5

        def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
            if role == QtCore.Qt.DisplayRole:
                if orientation == QtCore.Qt.Horizontal:
                    if section == 0:
                        return 'Name'
                    elif section == 1:
                        return 'Frequency'
                    elif section == 2:
                        return 'Next Due Date'
                    elif section == 3:
                        return 'Payee'
                    elif section == 4:
                        return 'Splits'
            elif role == QtCore.Qt.TextAlignmentRole:
                return QtCore.Qt.AlignCenter

        def data(self, index, role=QtCore.Qt.DisplayRole):
            if role == QtCore.Qt.DisplayRole:
                column = index.column()
                row = index.row()
                if column == 0:
                    return self._scheduled_txns[row].name
                elif column == 1:
                    return self._scheduled_txns[row].frequency.value
                elif column == 2:
                    return str(self._scheduled_txns[row].next_due_date)
                elif column == 3:
                    payee = self._scheduled_txns[row].payee
                    if payee:
                        return payee.name
                elif column == 4:
                    return bb.splits_display(self._scheduled_txns[row].splits)
            elif role == QtCore.Qt.TextAlignmentRole:
                return QtCore.Qt.AlignCenter

        def get_scheduled_txn_id(self, index):
            return self._scheduled_txns[index.row()].id

    return Model


class ScheduledTxnsDataDisplay:
    '''for displaying the list of scheduled transactions'''

    def __init__(self, scheduled_txns, engine, model_class, reload_function):
        self.scheduled_txns = scheduled_txns
        self._engine = engine
        self._model_class = model_class
        self._reload = reload_function
        self._model = model_class(self.scheduled_txns)
        self.widgets = {}

    def get_widget(self):
        self.main_widget = QtWidgets.QTableView()
        self.main_widget.setModel(self._model)
        self.main_widget.resizeColumnsToContents()
        self.main_widget.clicked.connect(self._edit)
        return self.main_widget

    def _edit(self, index):
        st_id = self._model.get_scheduled_txn_id(index)
        scheduled_txn = self._engine.get_scheduled_transaction(st_id)
        self.edit_form = ScheduledTxnForm(
                accounts=self._engine.get_accounts(),
                payees=self._engine.get_payees(),
                save_scheduled_txn=self._save_scheduled_txn_and_reload,
                scheduled_txn=scheduled_txn
            )
        self.edit_form.show_form()

    def _save_scheduled_txn_and_reload(self, scheduled_txn):
        self._engine.save_scheduled_transaction(scheduled_txn)
        self._reload()


class ScheduledTxnsDisplay:

    def __init__(self, engine, model_class):
        self._engine = engine
        self._model_class = model_class
        self._data_display_widget = None

    def get_widget(self):
        self.widget, self.layout, self._row_index = self._setup_main()
        self._display_scheduled_txns(self.layout)
        return self.widget

    def _setup_main(self):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        row_index = self._show_headings(layout, row=0)
        widget.setLayout(layout)
        return widget, layout, row_index

    def _show_headings(self, layout, row):
        current_index = 0
        self.add_button = QtWidgets.QPushButton('New Scheduled Transaction')
        self.add_button.clicked.connect(partial(self._open_form, scheduled_txn=None))
        layout.addWidget(self.add_button, row, 0)
        return row + 1

    def _display_scheduled_txns(self, layout):
        scheduled_txns = self._engine.get_scheduled_transactions()
        if self._data_display_widget:
            layout.removeWidget(self._data_display_widget)
            self._data_display_widget.deleteLater()
        if scheduled_txns:
            self.data_display = ScheduledTxnsDataDisplay(scheduled_txns, engine=self._engine, model_class=self._model_class,
                    reload_function=partial(self._display_scheduled_txns, layout=layout))
            self._data_display_widget = self.data_display.get_widget()
            layout.addWidget(self._data_display_widget, self._row_index, 0, 1, 5)
            self._row_index += 1

    def _open_form(self, scheduled_txn):
        if scheduled_txn:
            self.form = ScheduledTxnForm(
                    accounts=self._engine.get_accounts(),
                    payees=self._engine.get_payees(),
                    save_scheduled_txn=self._save_scheduled_txn_and_reload,
                    scheduled_txn=scheduled_txn
                )
        else:
            self.form = ScheduledTxnForm(
                    accounts=self._engine.get_accounts(),
                    payees=self._engine.get_payees(),
                    save_scheduled_txn=self._save_scheduled_txn_and_reload,
                    scheduled_txn=scheduled_txn
                )
        self.form.show_form()

    def _save_scheduled_txn_and_reload(self, scheduled_txn):
        self._engine.save_scheduled_transaction(scheduled_txn)
        self._display_scheduled_txns(layout=self.layout)


class GUI_QT:

    def __init__(self, file_name=None):
        self.parent_window = QtWidgets.QWidget()
        self.parent_window.setWindowTitle(bb.TITLE)
        self.parent_layout = QtWidgets.QGridLayout()
        self.parent_layout.setContentsMargins(4, 4, 4, 4)
        self.parent_window.setLayout(self.parent_layout)
        self.content_area = None
        self._accounts_model_class = get_accounts_model_class()
        self._txns_model_class = get_txns_model_class()
        self._budget_model_class = get_budget_model_class()
        self._scheduled_txns_model_class = get_scheduled_txns_model_class()

        if file_name:
            self._load_db(file_name)
        else:
            self._show_splash()
        self.parent_window.showMaximized()

    def _show_splash(self):
        #show screen for creating new db or opening existing one
        self.content_area = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QGridLayout()
        new_button = QtWidgets.QPushButton('New')
        new_button.clicked.connect(self._new_file)
        self.content_layout.addWidget(new_button, 0, 0)
        open_button = QtWidgets.QPushButton('Open')
        open_button.clicked.connect(self._open_file)
        self.content_layout.addWidget(open_button, 1, 0)
        files = bb.get_files(bb.CUR_DIR)
        for index, f in enumerate(files):
            button = QtWidgets.QPushButton(f.name)
            button.clicked.connect(partial(self._load_db, file_name=str(f)))
            self.content_layout.addWidget(button, index+2, 0)
        self.content_area.setLayout(self.content_layout)
        self.parent_layout.addWidget(self.content_area, 1, 0, 1, 2)

    def _load_db(self, file_name):
        try:
            self._engine = bb.Engine(file_name)
        except bb.InvalidStorageFile as e:
            if 'file is not a database' in str(e):
                show_error(msg='File %s is not a database' % file_name)
                return
            raise
        if self.content_area:
            self.parent_layout.removeWidget(self.content_area)
            self.content_area.deleteLater()
        self.content_area = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QGridLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_area.setLayout(self.content_layout)
        self.parent_layout.addWidget(self.content_area, 1, 0, 1, 6)
        self.main_widget = None
        self._show_action_buttons(self.parent_layout)
        accounts = self._engine.get_accounts()
        if accounts:
            self._show_ledger()
        else:
            self._show_accounts()

    def _new_file(self):
        file_name = QtWidgets.QFileDialog.getSaveFileName()[0]
        if file_name:
            self._load_db(file_name)

    def _open_file(self):
        file_name = QtWidgets.QFileDialog.getOpenFileName()[0]
        if file_name:
            self._load_db(file_name)

    def _show_action_buttons(self, layout):
        self.accounts_button = QtWidgets.QPushButton('Accounts')
        self.accounts_button.clicked.connect(self._show_accounts)
        layout.addWidget(self.accounts_button, 0, 0)
        self.ledger_button = QtWidgets.QPushButton('Ledger')
        self.ledger_button.clicked.connect(self._show_ledger)
        layout.addWidget(self.ledger_button, 0, 1)
        self.budget_button = QtWidgets.QPushButton('Budget')
        self.budget_button.clicked.connect(self._show_budget)
        layout.addWidget(self.budget_button, 0, 2)
        self.scheduled_txns_button = QtWidgets.QPushButton('Scheduled Transactions')
        self.scheduled_txns_button.clicked.connect(self._show_scheduled_txns)
        layout.addWidget(self.scheduled_txns_button, 0, 3)

    def _show_accounts(self):
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        accounts = self._engine.get_accounts()
        self.accounts_display = AccountsDisplay(accounts, save_account=self._engine.save_account, reload_accounts=self._show_accounts, model_class=self._accounts_model_class)
        self.main_widget = self.accounts_display.get_widget()
        self.content_layout.addWidget(self.main_widget, 0, 0)

    def _show_ledger(self):
        accounts = self._engine.get_accounts(types=[bb.AccountType.ASSET])
        if not accounts:
            show_error('Enter an asset account first.')
            return
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self.ledger_display = LedgerDisplay(engine=self._engine, txns_model_class=self._txns_model_class)
        self.main_widget = self.ledger_display.get_widget()
        self.content_layout.addWidget(self.main_widget, 0, 0)

    def _show_budget(self, current_budget=None):
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self.budget_display = BudgetDisplay(self._engine, budget_model_class=self._budget_model_class, current_budget=current_budget)
        self.main_widget = self.budget_display.get_widget()
        self.content_layout.addWidget(self.main_widget, 0, 0)

    def _show_scheduled_txns(self):
        if self.main_widget:
            self.content_layout.removeWidget(self.main_widget)
            self.main_widget.deleteLater()
        self.scheduled_txns_display = ScheduledTxnsDisplay(self._engine, model_class=self._scheduled_txns_model_class)
        self.main_widget = self.scheduled_txns_display.get_widget()
        self.content_layout.addWidget(self.main_widget, 0, 0)


def parse_args():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--install_qt', dest='install_qt', action='store_true')
    parser.add_argument('-f', '--file_name', dest='file_name')
    parser.add_argument('--cli', dest='cli', action='store_true')
    parser.add_argument('-i', '--import', dest='file_to_import')
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    args = parse_args()

    if args.install_qt:
        _do_qt_install()
        sys.exit(0)

    if args.file_name and not os.path.exists(args.file_name):
        raise Exception('no such file: "%s"' % args.file_name)

    try:
        from PySide2 import QtWidgets, QtGui, QtCore
    except ImportError as e:
        try:
            from PySide6 import QtWidgets, QtGui, QtCore
        except ImportError as e:
            install_qt_for_python()

    app = QtWidgets.QApplication([])
    if args.file_name:
        gui = GUI_QT(args.file_name)
    else:
        gui = GUI_QT()
    try:
        app.exec_()
    except Exception:
        import traceback
        bb.log(traceback.format_exc())
        raise
