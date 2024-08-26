from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging
from config import config_manager

logger = logging.getLogger(__name__)

class Trade:
    def __init__(self, timestamp: datetime, amount: float, price: float):
        self.timestamp = timestamp
        self.amount = amount
        self.price = price

class Currency:
    def __init__(self, symbol: str, balance: float = 0):
        self.symbol: str = symbol
        self.balance: float = balance
        self.price_history: List[Tuple[datetime, float]] = []
        self.buy_history: List[Trade] = []
        self.sell_history: List[Trade] = []
        self.current_price: Optional[float] = None

    def update_price(self, price: float, timestamp: Optional[datetime] = None) -> None:
        timestamp = timestamp or datetime.now()
        self.price_history.append((timestamp, price))
        self.current_price = price

    def record_trade(self, amount: float, price: float, trade_type: str, timestamp: Optional[datetime] = None) -> None:
        timestamp = timestamp or datetime.now()
        trade = Trade(timestamp, amount, price)
        
        if trade_type == 'buy':
            self.buy_history.append(trade)
            self.balance += amount
        elif trade_type == 'sell':
            self.sell_history.append(trade)
            self.balance -= amount
        
        logger.info(f"Recorded {trade_type}: {self.symbol} - Amount: {amount}, Price: {price}")

class Account:
    def __init__(self, account_type: str):
        self.account_type: str = account_type
        self.currencies: Dict[str, Currency] = {}

    def add_currency(self, symbol: str, balance: float = 0) -> None:
        if symbol not in self.currencies:
            self.currencies[symbol] = Currency(symbol, balance)
            logger.info(f"Added currency {symbol} to account {self.account_type}")

    def get_currency_balance(self, symbol: str) -> float:
        return self.currencies.get(symbol, Currency(symbol)).balance

    def update_currency_balance(self, symbol: str, new_balance: float) -> None:
        if symbol not in self.currencies:
            self.add_currency(symbol, new_balance)
        else:
            self.currencies[symbol].balance = new_balance
        logger.info(f"Updated balance for {symbol} in account {self.account_type}: {new_balance}")

    def update_currency_price(self, symbol: str, price: float) -> None:
        if symbol in self.currencies:
            self.currencies[symbol].update_price(price)
            logger.info(f"Updated price for {symbol} in account {self.account_type}: {price}")

class Wallet:
    def __init__(self):
        self.accounts: Dict[str, Account] = {}

    def add_account(self, account_type: str) -> None:
        if account_type not in self.accounts:
            self.accounts[account_type] = Account(account_type)
            logger.info(f"Added account {account_type} to wallet")

    def get_account(self, account_type: str) -> Optional[Account]:
        return self.accounts.get(account_type)

    def get_total_balance_in_usdt(self) -> float:
        total_usdt = 0
        try:
            for account in self.accounts.values():
                for currency in account.currencies.values():
                    if currency.symbol == 'USDT':
                        total_usdt += currency.balance
                    elif currency.current_price is not None:
                        total_usdt += currency.balance * currency.current_price
        except Exception as e:
            logger.error(f"Unexpected error calculating total balance: {e}")
        return total_usdt

    def update_account_balance(self, account_type: str, symbol: str, new_balance: float) -> None:
        if account_type not in self.accounts:
            self.add_account(account_type)
        self.accounts[account_type].update_currency_balance(symbol, new_balance)

    def update_currency_price(self, account_type: str, symbol: str, price: float) -> None:
        if account_type in self.accounts:
            self.accounts[account_type].update_currency_price(symbol, price)

    def get_account_summary(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        return {
            account_type: {
                symbol: {
                    'balance': currency.balance,
                    'current_price': currency.current_price
                } for symbol, currency in account.currencies.items()
            } for account_type, account in self.accounts.items()
        }

    def record_trade(self, account_type: str, symbol: str, amount: float, price: float, trade_type: str) -> None:
        account = self.get_account(account_type)
        if account and symbol in account.currencies:
            currency = account.currencies[symbol]
            currency.record_trade(amount, price, trade_type)
            
            # Update USDT balance
            usdt_amount = amount * price
            usdt_balance = self.get_currency_balance(account_type, 'USDT')
            if trade_type == 'buy':
                self.update_account_balance(account_type, 'USDT', usdt_balance - usdt_amount)
            elif trade_type == 'sell':
                self.update_account_balance(account_type, 'USDT', usdt_balance + usdt_amount)
        else:
            logger.warning(f"Failed to record trade: Account {account_type} or currency {symbol} not found")

    def get_currency_balance(self, account_type: str, symbol: str) -> float:
        account = self.get_account(account_type)
        return account.get_currency_balance(symbol) if account else 0

    def sync_with_exchange(self, account_type: str) -> None:
        try:
            accounts = config_manager.get_account_list()
            for account in accounts:
                if account['type'] == account_type:
                    symbol = account['currency']
                    balance = float(account['balance'])
                    self.update_account_balance(account_type, symbol, balance)
            logger.info(f"Wallet synchronized with exchange for account type: {account_type}")
        except Exception as e:
            logger.error(f"Unexpected error synchronizing wallet: {e}")

    def update_wallet_state(self, account_type: str, symbol: str, amount: float, price: float, trade_type: str) -> None:
        self.record_trade(account_type, symbol, amount, price, trade_type)
        self.update_currency_price(account_type, symbol, price)

def create_wallet() -> Wallet:
    wallet = Wallet()
    wallet.add_account("trading")
    wallet.sync_with_exchange("trade")
    return wallet

if __name__ == "__main__":
    wallet = create_wallet()
    print("Wallet created and synchronized with exchange")
    
    total_balance = wallet.get_total_balance_in_usdt()
    print(f"Total balance in USDT: {total_balance}")
    
    account_summary = wallet.get_account_summary()
    print("Account summary:", account_summary)
