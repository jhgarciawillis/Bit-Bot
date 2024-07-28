class Currency:
    def __init__(self, symbol, balance=0):
        self.symbol = symbol
        self.balance = balance

class Account:
    def __init__(self, account_type, currencies=None):
        self.account_type = account_type
        self.currencies = currencies or []

    def add_currency(self, currency):
        self.currencies.append(currency)

    def get_currency_balance(self, symbol):
        for currency in self.currencies:
            if currency.symbol == symbol:
                return currency.balance
        return 0

class Wallet:
    def __init__(self, accounts=None):
        self.accounts = accounts or []

    def add_account(self, account):
        self.accounts.append(account)

    def get_account_by_type(self, account_type):
        for account in self.accounts:
            if account.account_type == account_type:
                return account
        return None

