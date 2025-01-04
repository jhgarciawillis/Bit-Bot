from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging
from config import config_manager
from kucoin.client import Client

logger = logging.getLogger(__name__)

class Trade:
    def __init__(self, timestamp: datetime, amount: float, price: float, fee: float):
        self.timestamp = timestamp
        self.amount = amount
        self.price = price
        self.fee = fee

class Currency:
    def __init__(self, symbol: str):
        self.symbol: str = symbol
        self.balance: Dict[str, float] = {'liquid': 0, 'trading': 0}
        self.price_history: List[Tuple[datetime, float]] = []
        self.buy_history: List[Trade] = []
        self.sell_history: List[Trade] = []
        self.current_price: Optional[float] = None

    def update_price(self, price: float, timestamp: Optional[datetime] = None) -> None:
        timestamp = timestamp or datetime.now()
        self.price_history.append((timestamp, price))
        self.current_price = price

    def record_trade(self, amount: float, price: float, fee: float, trade_type: str, timestamp: Optional[datetime] = None) -> None:
        timestamp = timestamp or datetime.now()
        trade = Trade(timestamp, amount, price, fee)
        
        if trade_type == Client.SIDE_BUY:
            self.buy_history.append(trade)
            self.balance['trading'] += amount
        elif trade_type == Client.SIDE_SELL:
            self.sell_history.append(trade)
            self.balance['trading'] -= amount
        
        logger.info(f"Recorded {trade_type}: {self.symbol} - Amount: {amount:.8f}, Price: {price:.4f}, Fee: {fee:.8f}")

class Account:
    def __init__(self, account_type: str):
        self.account_type: str = account_type
        self.currencies: Dict[str, Currency] = {}
        self.currency_allocations: Dict[str, float] = {}

    def add_currency(self, symbol: str) -> None:
        if symbol not in self.currencies:
            self.currencies[symbol] = Currency(symbol)
            logger.info(f"Added currency {symbol} to account {self.account_type}")

    def get_balance(self, symbol: str, balance_type: str) -> float:
        if symbol in self.currencies:
            return self.currencies[symbol].balance[balance_type]
        return 0.0

    def update_balance(self, symbol: str, new_balance: float, balance_type: str) -> None:
        if symbol not in self.currencies:
            self.add_currency(symbol)
        self.currencies[symbol].balance[balance_type] = new_balance
        logger.info(f"Updated {balance_type} balance for {symbol} in account {self.account_type}: {new_balance:.8f}")

    def update_currency_price(self, symbol: str, price: float) -> None:
        if symbol in self.currencies:
            self.currencies[symbol].update_price(price)
            logger.info(f"Updated price for {symbol} in account {self.account_type}: {price:.8f}")

    def set_currency_allocations(self, allocations: Dict[str, float]) -> None:
        self.currency_allocations = allocations
        logger.info(f"Updated currency allocations for account {self.account_type}: {allocations}")

    def get_available_balance(self, symbol: str) -> float:
        if symbol in self.currencies:
            if symbol == 'USDT':
                return self.currencies[symbol].balance['trading']
            return self.currencies[symbol].balance['trading'] * self.currency_allocations.get(symbol, 0)
        return 0.0

class Wallet:
    def __init__(self, is_simulation: bool, liquid_ratio: float):
        self.is_simulation = is_simulation
        self.liquid_ratio = liquid_ratio
        self.accounts: Dict[str, Account] = {
            'trading': Account('trading'),
            'simulation': Account('simulation')
        }
        self.profits: Dict[str, float] = {}

    def initialize_balance(self, total_balance: float) -> None:
        liquid_balance = total_balance * self.liquid_ratio
        tradable_balance = total_balance - liquid_balance
        self.update_account_balance('trading', 'USDT', liquid_balance, 'liquid')
        self.update_account_balance('trading', 'USDT', tradable_balance, 'trading')

    def update_account_balance(self, account_type: str, currency: str, balance: float, balance_type: str) -> None:
        if account_type in self.accounts:
            account = self.accounts[account_type]
            account.update_balance(currency, balance, balance_type)
        else:
            logger.warning(f"Invalid account type: {account_type}")

    def get_balance(self, account_type: str, currency: str, balance_type: str) -> float:
        if account_type in self.accounts:
            return self.accounts[account_type].get_balance(currency, balance_type)
        logger.warning(f"No {balance_type} balance found for {currency} in {account_type} account")
        return 0.0

    def update_currency_price(self, account_type: str, currency: str, price: float) -> None:
        if account_type in self.accounts:
            account = self.accounts[account_type]
            account.update_currency_price(currency, price)
        else:
            logger.warning(f"Invalid account type: {account_type}")

    def sync_with_exchange(self, account_type: str) -> None:
        # Implement syncing wallet balances with the exchange
        pass

    def update_profits(self, symbol: str, profit: float) -> None:
        if symbol not in self.profits:
            self.profits[symbol] = 0
        self.profits[symbol] += profit
        logger.info(f"Updated profit for {symbol}: {self.profits[symbol]:.8f} USDT")

    def get_profits(self) -> Dict[str, float]:
        return self.profits

    def set_currency_allocations(self, allocations: Dict[str, float]) -> None:
        for account in self.accounts.values():
            account.set_currency_allocations(allocations)

    def get_available_balance(self, symbol: str) -> float:
        return self.accounts['trading'].get_available_balance(symbol)

    def get_account_summary(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        return {
            account_type: {
                currency.symbol: {
                    'liquid': currency.balance['liquid'],
                    'trading': currency.balance['trading'],
                    'price': currency.current_price or 0
                } for currency in account.currencies.values()
            } for account_type, account in self.accounts.items()
        }

def create_wallet(is_simulation: bool, liquid_ratio: float = 0.5) -> Wallet:
    return Wallet(is_simulation, liquid_ratio)
