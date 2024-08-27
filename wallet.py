from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging
from config import config_manager
from kucoin.client import User

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
    def __init__(self, account_type: str, initial_balance: float = 0):
        self.account_type: str = account_type
        self.currencies: Dict[str, Currency] = {}
        self.add_currency('USDT', initial_balance)

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
        self.accounts: Dict[str, Account] = {
            'trading': Account('trading', config_manager.get_config('simulation_mode')['initial_balance']),
            'simulation': Account('simulation', config_manager.get_config('simulation_mode')['initial_balance'])
        }
        self.is_simulation = config_manager.get_config('simulation_mode')['enabled']

    def update_account_balance(self, account_type: str, currency: str, balance: float, balance_type: str = 'trading') -> None:
        if account_type in self.accounts:
            account = self.accounts[account_type]
            if balance_type == 'liquid':
                account.update_currency_balance(currency, balance)
            elif balance_type == 'trading':
                account.update_currency_balance(currency, balance)
            logger.info(f"Updated {account_type} account {balance_type} balance for {currency}: {balance}")
        else:
            logger.warning(f"Invalid account type: {account_type}")

    def get_currency_balance(self, account_type: str, currency: str, balance_type: str = 'trading') -> float:
        if account_type in self.accounts:
            account = self.accounts[account_type]
            if balance_type == 'liquid':
                return account.get_currency_balance(currency)
            elif balance_type == 'trading':
                return account.get_currency_balance(currency)
        else:
            logger.warning(f"No {balance_type} balance found for {currency} in {account_type} account")
            return 0.0

    def get_total_balance_in_usdt(self, account_type: str = 'trading') -> float:
        if self.is_simulation:
            return self._get_simulated_total_balance_in_usdt(account_type)
        else:
            return self._get_live_total_balance_in_usdt()

    def _get_simulated_total_balance_in_usdt(self, account_type: str) -> float:
        total_usdt = 0
        if account_type in self.accounts:
            account = self.accounts[account_type]
            for currency in account.currencies.values():
                if currency.symbol == 'USDT':
                    total_usdt += currency.balance
                elif currency.current_price is not None:
                    total_usdt += currency.balance * currency.current_price
        logger.info(f"Total simulated {account_type} account balance: {total_usdt:.2f} USDT")
        return total_usdt

    def _get_live_total_balance_in_usdt(self) -> float:
        try:
            user_client = config_manager.kucoin_client_manager.get_client(User)
            accounts = user_client.get_account_list()
            total_usdt = sum(float(account['balance']) for account in accounts if account['currency'] == 'USDT')
            logger.info(f"Total live trading account balance: {total_usdt:.2f} USDT")
            return total_usdt
        except Exception as e:
            logger.error(f"Failed to fetch live total balance: {e}")
            return 0.0

    def get_account_summary(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        return {
            account_type: {
                currency.symbol: {
                    'liquid': currency.balance if account_type == 'trading' else 0,
                    'trading': currency.balance,
                    'price': currency.current_price or 0
                } for currency in account.currencies.values()
            } for account_type, account in self.accounts.items()
        }

    def update_wallet_state(self, account_type: str, currency: str, amount: float, price: float, side: str) -> None:
        account = self.accounts.get(account_type)
        if account:
            if currency in account.currencies:
                account.currencies[currency].record_trade(amount, price, side)
                if side == 'buy':
                    self.update_account_balance(account_type, 'USDT', account.get_currency_balance('USDT') - amount * price, 'trading')
                elif side == 'sell':
                    self.update_account_balance(account_type, 'USDT', account.get_currency_balance('USDT') + amount * price, 'trading')
            else:
                logger.warning(f"Currency {currency} not found in {account_type} account")
        else:
            logger.warning(f"Invalid account type: {account_type}")

    def update_currency_price(self, account_type: str, currency: str, price: float) -> None:
        if account_type in self.accounts:
            account = self.accounts[account_type]
            account.update_currency_price(currency, price)
        else:
            logger.warning(f"Invalid account type: {account_type}")

    def get_currency_price(self, account_type: str, currency: str) -> float:
        if account_type in self.accounts:
            account = self.accounts[account_type]
            if currency in account.currencies:
                return account.currencies[currency].current_price or 0
        logger.warning(f"No price found for {currency} in {account_type} account")
        return 0.0

    def sync_with_exchange(self, account_type: str, liquid_ratio: float) -> None:
        if self.is_simulation:
            logger.warning("Syncing wallet with exchange is not applicable in simulation mode")
            return

        try:
            user_client = config_manager.kucoin_client_manager.get_client(User)
            accounts = user_client.get_account_list()
            for account in accounts:
                if account['type'] == 'trade':
                    symbol = account['currency']
                    total_balance = float(account['balance'])
                    trading_balance = total_balance * (1 - liquid_ratio)
                    liquid_balance = total_balance - trading_balance
                    self.update_account_balance(account_type, symbol, liquid_balance, 'liquid')
                    self.update_account_balance(account_type, symbol, trading_balance, 'trading')
            logger.info(f"Wallet synchronized with exchange for account type: {account_type}")
        except Exception as e:
            logger.error(f"Unexpected error synchronizing wallet: {e}")

def create_wallet(is_simulation: bool, liquid_ratio: float = 0.5) -> Wallet:
    wallet = Wallet()
    wallet.is_simulation = is_simulation
    if not is_simulation:
        wallet.sync_with_exchange('trading', liquid_ratio)
    return wallet
