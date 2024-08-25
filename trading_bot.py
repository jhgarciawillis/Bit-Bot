import time
import logging
from datetime import datetime
from collections import deque
from statistics import mean, stdev
from typing import Dict, List, Optional, Tuple
from wallet import Wallet
from config import load_config, fetch_real_time_prices, place_spot_order, market_client, trade_client, user_client
import asyncio

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def handle_trading_errors(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            # You might want to add more error handling logic here
    return wrapper

class TradingBot:
    def __init__(self, api_key: str, api_secret: str, api_passphrase: str, update_interval: int):
        self.config = load_config()
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.wallet = Wallet()
        self.wallet.add_account("trading")
        self.is_simulation = self.config['simulation_mode']['enabled']
        self.update_interval = update_interval
        self.profits: Dict[str, float] = {}
        self.total_profit: float = 0
        self.symbol_allocations: Dict[str, float] = {}
        self.usdt_liquid_percentage: float = self.config['default_usdt_liquid_percentage']
        self.price_history: Dict[str, deque] = {}
        self.active_trades: Dict[str, Dict] = {}
        self.PRICE_HISTORY_LENGTH: int = self.config['chart_config']['history_length']
        self.total_trades: int = 0
        self.avg_profit_per_trade: float = 0
        self.status_history: List[Dict] = []

    async def initialize(self) -> None:
        if not self.is_simulation:
            await self.update_wallet_balances()

    @handle_trading_errors
    async def update_wallet_balances(self) -> None:
        if not self.is_simulation:
            try:
                accounts = await asyncio.to_thread(user_client.get_account_list)
                for account in accounts:
                    if account['type'] == 'trade':
                        await self.wallet.update_account_balance("trading", account['currency'], float(account['available']))
                logger.info(f"Updated wallet balances: {self.wallet.get_account_summary()}")
            except Exception as e:
                logger.error(f"Error updating wallet balances: {e}")

    def get_account_balance(self, currency: str = 'USDT') -> float:
        return self.wallet.get_account("trading").get_currency_balance(currency)

    def get_tradable_balance(self, currency: str = 'USDT') -> float:
        return self.wallet.get_account("trading").get_currency_balance(currency)

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
        
        if current_price is not None and current_price < price_mean and (price_mean - current_price) < price_stdev:
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
            return order
        return None

    @handle_trading_errors
    async def place_sell_order(self, symbol: str, amount_crypto: float, target_sell_price: float) -> Optional[Dict]:
        order = await place_spot_order(symbol, 'sell', target_sell_price, amount_crypto, self.is_simulation)
        
        if order:
            return order
        return None

    def get_current_status(self, prices: Dict[str, float]) -> Dict:
        current_total_usdt = self.wallet.get_total_balance_in_usdt(lambda symbol: prices.get(symbol))
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

    @handle_trading_errors
    async def run_trading_iteration(self, symbols: List[str], profit_margin: float, num_orders: int) -> Dict:
        prices = await fetch_real_time_prices(symbols, self.is_simulation)
        await self.update_price_history(symbols, prices)

        current_status = self.get_current_status(prices)
        tradable_usdt = current_status['tradable_usdt']

        for symbol in symbols:
            try:
                current_price = prices.get(symbol, None)
                if current_price is None:
                    logger.warning(f"Skipping {symbol} due to unavailable price data")
                    continue

                allocated_value = self.symbol_allocations.get(symbol, 0) * tradable_usdt
                usdt_balance = self.get_tradable_balance('USDT')

                # Check if we should buy
                limit_buy_price = await self.should_buy(symbol, current_price)
                if limit_buy_price is not None and usdt_balance > 0:
                    buy_amount_usdt = min(allocated_value, usdt_balance)
                    if buy_amount_usdt > 0:
                        order_amount = buy_amount_usdt / num_orders
                        for _ in range(num_orders):
                            order = await self.place_buy_order(symbol, order_amount, limit_buy_price)
                            if order:
                                logger.info(f"Placed buy order for {symbol}: {order_amount:.4f} USDT at {limit_buy_price:.4f}")

                # Check active trades for selling
                for order_id, trade in list(self.active_trades.items()):
                    if trade['symbol'] == symbol:
                        target_sell_price = trade['buy_price'] * (1 + profit_margin)
                        if current_price is not None and current_price >= target_sell_price:
                            sell_amount_crypto = trade['amount']
                            sell_order = await self.place_sell_order(symbol, sell_amount_crypto, target_sell_price)
                            if sell_order:
                                profit = (target_sell_price - trade['buy_price']) * sell_amount_crypto - trade['fee'] - float(sell_order['fee'])
                                self.profits[symbol] = self.profits.get(symbol, 0) + profit
                                self.total_profit += profit
                                self.total_trades += 1
                                self.avg_profit_per_trade = self.total_profit / self.total_trades
                                logger.info(f"Sold {symbol}: {sell_amount_crypto:.8f} at {target_sell_price:.4f}, Profit: {profit:.4f} USDT")
                                del self.active_trades[order_id]

            except KeyError as e:
                logger.error(f"Error accessing key {str(e)} for symbol {symbol}")
            except Exception as e:
                logger.error(f"An error occurred while processing symbol {symbol}: {str(e)}")

        # Update allocations based on new total USDT value
        self.update_allocations(current_status['current_total_usdt'], self.usdt_liquid_percentage)

        return current_status
