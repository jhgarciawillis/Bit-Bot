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

    def update_currency_balance(self, symbol, new_balance):
        for currency in self.currencies:
            if currency.symbol == symbol:
                currency.balance = new_balance
                return
        # If the currency doesn't exist, add it
        self.add_currency(Currency(symbol, new_balance))

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

    def get_total_balance_in_usdt(self, price_fetcher):
        total_usdt = 0
        for account in self.accounts:
            for currency in account.currencies:
                if currency.symbol == 'USDT':
                    total_usdt += currency.balance
                else:
                    price = price_fetcher(currency.symbol + '-USDT')
                    if price is not None:
                        total_usdt += currency.balance * price
        return total_usdt

    def update_account_balance(self, account_type, symbol, new_balance):
        account = self.get_account_by_type(account_type)
        if account:
            account.update_currency_balance(symbol, new_balance)
        else:
            new_account = Account(account_type)
            new_account.add_currency(Currency(symbol, new_balance))
            self.add_account(new_account)
