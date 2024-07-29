from datetime import datetime

class Currency:
    def __init__(self, symbol, balance=0):
        self.symbol = symbol
        self.balance = balance
        self.price_history = []
        self.buy_history = []
        self.sell_history = []
        self.current_price = None

    def update_price(self, price, timestamp=None):
        if timestamp is None:
            timestamp = datetime.now()
        self.price_history.append((timestamp, price))
        self.current_price = price

    def record_buy(self, amount, price, timestamp=None):
        if timestamp is None:
            timestamp = datetime.now()
        self.buy_history.append((timestamp, amount, price))

    def record_sell(self, amount, price, timestamp=None):
        if timestamp is None:
            timestamp = datetime.now()
        self.sell_history.append((timestamp, amount, price))

class Account:
    def __init__(self, account_type, currencies=None):
        self.account_type = account_type
        self.currencies = currencies or {}

    def add_currency(self, symbol, balance=0):
        if symbol not in self.currencies:
            self.currencies[symbol] = Currency(symbol, balance)

    def get_currency_balance(self, symbol):
        return self.currencies.get(symbol, Currency(symbol)).balance

    def update_currency_balance(self, symbol, new_balance):
        if symbol not in self.currencies:
            self.add_currency(symbol, new_balance)
        else:
            self.currencies[symbol].balance = new_balance

    def update_currency_price(self, symbol, price):
        if symbol in self.currencies:
            self.currencies[symbol].update_price(price)

class Wallet:
    def __init__(self, accounts=None):
        self.accounts = accounts or {}

    def add_account(self, account_type):
        if account_type not in self.accounts:
            self.accounts[account_type] = Account(account_type)

    def get_account(self, account_type):
        return self.accounts.get(account_type)

    def get_total_balance_in_usdt(self, price_fetcher):
        total_usdt = 0
        for account in self.accounts.values():
            for currency in account.currencies.values():
                if currency.symbol == 'USDT':
                    total_usdt += currency.balance
                else:
                    price = price_fetcher(currency.symbol + '-USDT')
                    if price is not None:
                        total_usdt += currency.balance * price
        return total_usdt

    def update_account_balance(self, account_type, symbol, new_balance):
        if account_type not in self.accounts:
            self.add_account(account_type)
        self.accounts[account_type].update_currency_balance(symbol, new_balance)

    def update_currency_price(self, account_type, symbol, price):
        if account_type in self.accounts:
            self.accounts[account_type].update_currency_price(symbol, price)

    def get_account_summary(self):
        summary = {}
        for account_type, account in self.accounts.items():
            summary[account_type] = {
                symbol: {
                    'balance': currency.balance,
                    'current_price': currency.current_price,
                    'buy_history': currency.buy_history,
                    'sell_history': currency.sell_history
                } for symbol, currency in account.currencies.items()
            }
        return summary

    def get_currency_history(self, account_type, symbol):
        account = self.get_account(account_type)
        if account and symbol in account.currencies:
            currency = account.currencies[symbol]
            return {
                'price_history': currency.price_history,
                'buy_history': currency.buy_history,
                'sell_history': currency.sell_history
            }
        return None
