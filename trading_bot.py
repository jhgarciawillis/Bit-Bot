import logging
from datetime import datetime
from collections import deque
from statistics import mean, stdev
from typing import Dict, List, Optional, Tuple
from wallet import create_wallet
from config import load_config, fetch_real_time_prices, place_spot_order, kucoin_client_manager
from kucoin.client import User
import asyncio

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def handle_trading_errors(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"An error occurred in {func.__name__}: {str(e)}")
    return wrapper

class TradingBot:
    def __init__(self, update_interval: int):
        self.wallet = None
        self.update_interval = update_interval
        self.profits: Dict[str, float] = {}
        self.total_profit: float = 0
        self.symbol_allocations: Dict[str, float] = {}
        self.price_history: Dict[str, deque] = {}
        self.active_trades: Dict[str, Dict] = {}
        self.total_trades: int = 0
        self.avg_profit_per_trade: float = 0
        self.status_history: List[Dict] = []

    async def initialize(self) -> None:
        self.config = await load_config()
        self.is_simulation = self.config['simulation_mode']['enabled']
        self.usdt_liquid_percentage = self.config['default_usdt_liquid_percentage']
        self.PRICE_HISTORY_LENGTH = self.config['chart_config']['history_length']
        self.wallet = await create_wallet()
        if not self.is_simulation:
            await self.update_wallet_balances()

    @handle_trading_errors
    async def update_wallet_balances(self) -> None:
        try:
            user_client = kucoin_client_manager.get_client(User)
            accounts = await asyncio.to_thread(user_client.get_account_list)
            for account in accounts:
                if account['type'] == 'trade':
                    await self.wallet.update_account_balance("trading", account['currency'], float(account['available']))
            logger.info(f"Updated wallet balances: {self.wallet.get_account_summary()}")
        except Exception as e:
            logger.error(f"Error updating wallet balances: {e}")

    def get_account_balance(self, currency: str = 'USDT') -> float:
        return self.wallet.get_currency_balance("trading", currency)

    def get_tradable_balance(self, currency: str = 'USDT') -> float:
        return self.wallet.get_currency_balance("trading", currency)

    async def get_user_allocations(self, user_selected_symbols: List[str], total_usdt_balance: float) -> Tuple[Dict[str, float], float]:
        tradable_usdt_amount = total_usdt_balance * (1 - self.usdt_liquid_percentage)
        
        if tradable_usdt_amount <= 0 or not user_selected_symbols:
            return {}, 0

        symbol_allocations = {symbol: 1 / len(user_selected_symbols) for symbol in user_selected_symbols}
        for symbol in user_selected_symbols:
            if symbol not in self.profits:
                self.profits[symbol] = 0
        
        return symbol_allocations, tradable_usdt_amount

    async def update_price_history(self, symbols: List[str], prices: Dict[str, float]) -> None:
        for symbol in symbols:
            if symbol not in self.price_history:
                self.price_history[symbol] = deque(maxlen=self.PRICE_HISTORY_LENGTH)
            if prices[symbol] is not None:
                self.price_history[symbol].append({
                    'timestamp': datetime.now(),
                    'price': prices[symbol]
                })
                await self.wallet.update_currency_price("trading", symbol, prices[symbol])

    async def should_buy(self, symbol: str, current_price: float) -> Optional[float]:
        if current_price is None or len(self.price_history[symbol]) < self.PRICE_HISTORY_LENGTH:
            return None
        
        prices = [entry['price'] for entry in self.price_history[symbol]]
        price_mean = mean(prices)
        price_stdev = stdev(prices) if len(set(prices)) > 1 else 0
        
        if current_price < price_mean and (price_mean - current_price) < price_stdev:
            return price_mean
        
        return None

    @handle_trading_errors
    async def place_buy_order(self, symbol: str, amount_usdt: float, limit_price: float) -> Optional[Dict]:
        amount_crypto = amount_usdt / limit_price
        order = await place_spot_order(symbol, 'buy', limit_price, amount_crypto, self.is_simulation)
        
        if order:
            self.active_trades[order['orderId']] = {
                'symbol': symbol,
                'buy_price': float(order['price']),
                'amount': float(order['amount']),
                'fee': float(order['fee']),
                'buy_time': datetime.now()
            }
            await self.wallet.update_wallet_state("trading", symbol, float(order['amount']), float(order['price']), 'buy')
            return order
        return None

    @handle_trading_errors
    async def place_sell_order(self, symbol: str, amount_crypto: float, target_sell_price: float) -> Optional[Dict]:
        order = await place_spot_order(symbol, 'sell', target_sell_price, amount_crypto, self.is_simulation)
        
        if order:
            await self.wallet.update_wallet_state("trading", symbol, float(order['amount']), float(order['price']), 'sell')
            return order
        return None

    async def get_current_status(self, prices: Dict[str, float]) -> Dict:
        current_total_usdt = await self.wallet.get_total_balance_in_usdt()
        liquid_usdt = current_total_usdt * self.usdt_liquid_percentage
        tradable_usdt = max(current_total_usdt - liquid_usdt, 0)
        
        status = {
            'timestamp': datetime.now(),
            'prices': prices,
            'active_trades': self.active_trades.copy(),
            'profits': self.profits.copy(),
            'total_profit': self.total_profit,
            'current_total_usdt': current_total_usdt,
            'tradable_usdt': tradable_usdt,
            'liquid_usdt': liquid_usdt,
            'wallet_summary': self.wallet.get_account_summary(),
            'total_trades': self.total_trades,
            'avg_profit_per_trade': self.avg_profit_per_trade,
        }
        
        self.status_history.append(status)
        
        # Keep only the last 120 status updates (for 2 hours of history with 1-minute updates)
        if len(self.status_history) > 120:
            self.status_history.pop(0)
        
        return status

    def update_allocations(self, total_usdt: float, liquid_usdt_percentage: float) -> None:
        liquid_usdt = total_usdt * liquid_usdt_percentage
        tradable_usdt = max(total_usdt - liquid_usdt, 0)
        if tradable_usdt == 0:
            self.symbol_allocations = {symbol: 0 for symbol in self.symbol_allocations}
        else:
            total_allocation = sum(self.symbol_allocations.values())
            if total_allocation > 0:
                for symbol in self.symbol_allocations:
                    self.symbol_allocations[symbol] = (self.symbol_allocations[symbol] / total_allocation) * tradable_usdt
            else:
                equal_allocation = tradable_usdt / len(self.symbol_allocations)
                self.symbol_allocations = {symbol: equal_allocation for symbol in self.symbol_allocations}

async def create_trading_bot(update_interval: int) -> TradingBot:
    bot = TradingBot(update_interval)
    await bot.initialize()
    return bot
