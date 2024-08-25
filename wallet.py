from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging
import asyncio
from kucoin.client import Market, Trade, User
from kucoin.exceptions import KucoinAPIException
from config import kucoin_client_manager

logger = logging.getLogger(__name__)

class Currency:
    def __init__(self, symbol: str, balance: float = 0):
        self.symbol: str = symbol
        self.balance: float = balance
        self.price_history: List[Tuple[datetime, float]] = []
        self.buy_history: List[Tuple[datetime, float, float]] = []
        self.sell_history: List[Tuple[datetime, float, float]] = []
        self.current_price: Optional[float] = None

    async def update_price(self, price: float, timestamp: Optional[datetime] = None) -> None:
        if timestamp is None:
            timestamp = datetime.now()
        self.price_history.append((timestamp, price))
        self.current_price = price

    async def record_trade(self, amount: float, price: float, trade_type: str, timestamp: Optional[datetime] = None) -> None:
        if timestamp is None:
            timestamp = datetime.now()
        
        if trade_type == 'buy':
            self.buy_history.append((timestamp, amount, price))
            self.balance += amount
        elif trade_type == 'sell':
            self.sell_history.append((timestamp, amount, price))
            self.balance -= amount
        
        logger.info(f"Recorded {trade_type}: {self.symbol} - Amount: {amount}, Price: {price}")

class Account:
    def __init__(self, account_type: str, currencies: Optional[Dict[str, Currency]] = None):
        self.account_type: str = account_type
        self.currencies: Dict[str, Currency] = currencies or {}

    async def add_currency(self, symbol: str, balance: float = 0) -> None:
        if symbol not in self.currencies:
            self.currencies[symbol] = Currency(symbol, balance)
            logger.info(f"Added currency {symbol} to account {self.account_type}")

    def get_currency_balance(self, symbol: str) -> float:
        return self.currencies.get(symbol, Currency(symbol)).balance

    async def update_currency_balance(self, symbol: str, new_balance: float) -> None:
        if symbol not in self.currencies:
            await self.add_currency(symbol, new_balance)
        else:
            self.currencies[symbol].balance = new_balance
        logger.info(f"Updated balance for {symbol} in account {self.account_type}: {new_balance}")

    async def update_currency_price(self, symbol: str, price: float) -> None:
        if symbol in self.currencies:
            await self.currencies[symbol].update_price(price)
            logger.info(f"Updated price for {symbol} in account {self.account_type}: {price}")

class Wallet:
    def __init__(self):
        self.accounts: Dict[str, Account] = {}

    async def add_account(self, account_type: str) -> None:
        if account_type not in self.accounts:
            self.accounts[account_type] = Account(account_type)
            logger.info(f"Added account {account_type} to wallet")

    def get_account(self, account_type: str) -> Optional[Account]:
        return self.accounts.get(account_type)

    async def get_total_balance_in_usdt(self) -> float:
        total_usdt = 0
        try:
            market_client = kucoin_client_manager.get_client(Market)
            for account in self.accounts.values():
                for currency in account.currencies.values():
                    if currency.symbol == 'USDT':
                        total_usdt += currency.balance
                    else:
                        ticker = await asyncio.to_thread(market_client.get_ticker, f"{currency.symbol}-USDT")
                        price = float(ticker['price'])
                        total_usdt += currency.balance * price
        except KucoinAPIException as e:
            logger.error(f"KuCoin API error fetching total balance: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching total balance: {e}")
        return total_usdt

    async def update_account_balance(self, account_type: str, symbol: str, new_balance: float) -> None:
        if account_type not in self.accounts:
            await self.add_account(account_type)
        await self.accounts[account_type].update_currency_balance(symbol, new_balance)

    async def update_currency_price(self, account_type: str, symbol: str, price: float) -> None:
        if account_type in self.accounts:
            await self.accounts[account_type].update_currency_price(symbol, price)

    def get_account_summary(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        summary = {}
        for account_type, account in self.accounts.items():
            summary[account_type] = {
                symbol: {
                    'balance': currency.balance,
                    'current_price': currency.current_price
                } for symbol, currency in account.currencies.items()
            }
        return summary

    async def record_trade(self, account_type: str, symbol: str, amount: float, price: float, trade_type: str) -> None:
        account = self.get_account(account_type)
        if account and symbol in account.currencies:
            currency = account.currencies[symbol]
            await currency.record_trade(amount, price, trade_type)
            
            # Update USDT balance
            usdt_amount = amount * price
            if trade_type == 'buy':
                await self.update_account_balance(account_type, 'USDT', self.get_currency_balance(account_type, 'USDT') - usdt_amount)
            elif trade_type == 'sell':
                await self.update_account_balance(account_type, 'USDT', self.get_currency_balance(account_type, 'USDT') + usdt_amount)
        else:
            logger.warning(f"Failed to record trade: Account {account_type} or currency {symbol} not found")

    def get_currency_balance(self, account_type: str, symbol: str) -> float:
        account = self.get_account(account_type)
        if account:
            return account.get_currency_balance(symbol)
        return 0

    async def sync_with_exchange(self, account_type: str) -> None:
        try:
            user_client = kucoin_client_manager.get_client(User)
            accounts = await asyncio.to_thread(user_client.get_account_list)
            for account in accounts:
                if account['type'] == account_type:
                    symbol = account['currency']
                    balance = float(account['balance'])
                    await self.update_account_balance(account_type, symbol, balance)
            logger.info(f"Wallet synchronized with exchange for account type: {account_type}")
        except KucoinAPIException as e:
            logger.error(f"KuCoin API error synchronizing wallet: {e}")
        except Exception as e:
            logger.error(f"Unexpected error synchronizing wallet: {e}")

    async def update_wallet_state(self, account_type: str, symbol: str, amount: float, price: float, trade_type: str) -> None:
        await self.record_trade(account_type, symbol, amount, price, trade_type)
        await self.update_currency_price(account_type, symbol, price)

async def create_wallet() -> Wallet:
    wallet = Wallet()
    await wallet.add_account("trading")
    await wallet.sync_with_exchange("trade")
    return wallet

if __name__ == "__main__":
    async def run_tests():
        wallet = await create_wallet()
        print("Wallet created and synchronized with exchange")
        
        total_balance = await wallet.get_total_balance_in_usdt()
        print(f"Total balance in USDT: {total_balance}")
        
        account_summary = wallet.get_account_summary()
        print("Account summary:", account_summary)

    asyncio.run(run_tests())
