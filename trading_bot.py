import time
import logging
from datetime import datetime
from collections import deque
from statistics import mean, stdev
import random
from typing import Dict, List, Optional, Tuple
from wallet import Wallet, Account, Currency
from config import load_config

try:
    from kucoin.client import Market, Trade, User
except ImportError as e:
    logging.warning(f"KuCoin client import error: {type(e).__name__}")
    Market, Trade, User = None, None, None

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TradingClient:
    def __init__(self, api_key: str, api_secret: str, api_passphrase: str, api_url: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.api_url = api_url
        self.market_client: Optional[Market] = None
        self.trade_client: Optional[Trade] = None
        self.user_client: Optional[User] = None
        self.is_simulation: bool = False

    def initialize(self) -> None:
        logger.info("Initializing clients")
        if Market and Trade and User:
            try:
                self.market_client = Market(url=self.api_url)
                self.trade_client = Trade(key=self.api_key, secret=self.api_secret, passphrase=self.api_passphrase, url=self.api_url)
                self.user_client = User(key=self.api_key, secret=self.api_secret, passphrase=self.api_passphrase, url=self.api_url)
                logger.info("Clients initialized successfully")
            except Exception as e:
                logger.error(f"Error initializing clients: {type(e).__name__}")
                self.market_client = None
                self.trade_client = None
                self.user_client = None
        else:
            logger.warning("Running in simulation mode or KuCoin client not available.")
            self.is_simulation = True

    def get_current_prices(self, symbols: List[str]) -> Dict[str, float]:
        prices = {}
        for symbol in symbols:
            try:
                if self.market_client and not self.is_simulation:
                    ticker = self.market_client.get_ticker(symbol)
                    prices[symbol] = float(ticker['price'])
                else:
                    # Simulation mode: generate random price movements
                    last_price = prices.get(symbol, 100)  # Default to 100 if no previous price
                    price_change = random.uniform(-0.001, 0.001)  # -0.1% to 0.1% change
                    new_price = last_price * (1 + price_change)
                    prices[symbol] = round(new_price, 2)
            except Exception as e:
                logger.error(f"Error fetching price for {symbol}: {type(e).__name__}")
                prices[symbol] = None
        
        logger.info(f"Current prices: {prices}")
        return prices

    def place_order(self, symbol: str, side: str, amount: float, price: Optional[float] = None) -> Optional[Dict]:
        if self.trade_client and not self.is_simulation:
            try:
                if price:
                    order = self.trade_client.create_limit_order(symbol, side, amount, price)
                else:
                    order = self.trade_client.create_market_order(symbol, side, amount)
                return order
            except Exception as e:
                logger.error(f"Error placing {side} order for {symbol}: {type(e).__name__}")
                return None
        else:
            # Simulation mode
            return {
                'orderId': f'sim_{side}_{symbol}_{time.time()}',
                'price': price or self.get_current_prices([symbol])[symbol],
                'amount': amount,
                'fee': amount * 0.001  # Simulated 0.1% fee
            }

class TradingBot:
    def __init__(self, api_key: str, api_secret: str, api_passphrase: str, update_interval: int):
        config = load_config()
        self.trading_client = TradingClient(api_key, api_secret, api_passphrase, config['api_url'])
        self.wallet = Wallet()
        self.wallet.add_account("trading")
        self.is_simulation = config['simulation_mode']['enabled']
        self.update_interval = update_interval
        self.profits: Dict[str, float] = {}
        self.total_profit: float = 0
        self.symbol_allocations: Dict[str, float] = {}
        self.usdt_liquid_percentage: float = config['default_usdt_liquid_percentage']
        self.price_history: Dict[str, deque] = {}
        self.active_trades: Dict[str, Dict] = {}
        self.PRICE_HISTORY_LENGTH: int = config['chart_config']['history_length']
        self.total_trades: int = 0
        self.avg_profit_per_trade: float = 0
        self.status_history: List[Dict] = []

    def initialize(self) -> None:
        self.trading_client.initialize()
        if not self.is_simulation:
            self.update_wallet_balances()

    def update_wallet_balances(self) -> None:
        if self.trading_client.user_client:
            try:
                accounts = self.trading_client.user_client.get_account_list()
                for account in accounts:
                    if account['type'] == 'trade':
                        self.wallet.update_account_balance("trading", account['currency'], float(account['available']))
                logger.info(f"Updated wallet balances: {self.wallet.get_account_summary()}")
            except Exception as e:
                logger.error(f"Error updating wallet balances: {e}")

    def get_account_balance(self, currency: str = 'USDT') -> float:
        return self.wallet.get_account("trading").get_currency_balance(currency)

    def get_tradable_balance(self, currency: str = 'USDT') -> float:
        return self.wallet.get_account("trading").get_currency_balance(currency)

    def get_user_allocations(self, user_selected_symbols: List[str], total_usdt_balance: float) -> Tuple[Dict[str, float], float]:
        tradable_usdt_amount = total_usdt_balance * (1 - self.usdt_liquid_percentage)
        
        if tradable_usdt_amount <= 0 or not user_selected_symbols:
            return {}, 0

        symbol_allocations = {symbol: 1 / len(user_selected_symbols) for symbol in user_selected_symbols}
        for symbol in user_selected_symbols:
            if symbol not in self.profits:
                self.profits[symbol] = 0
        
        return symbol_allocations, tradable_usdt_amount

    def update_price_history(self, symbols: List[str], prices: Dict[str, float]) -> None:
        for symbol in symbols:
            if symbol not in self.price_history:
                self.price_history[symbol] = deque(maxlen=self.PRICE_HISTORY_LENGTH)
            if prices[symbol] is not None:
                self.price_history[symbol].append({
                    'timestamp': datetime.now(),
                    'price': prices[symbol]
                })
                self.wallet.update_currency_price("trading", symbol.split('-')[0], prices[symbol])

    def should_buy(self, symbol: str, current_price: float) -> Optional[float]:
        if current_price is None or len(self.price_history[symbol]) < self.PRICE_HISTORY_LENGTH:
            return None
        
        prices = [entry['price'] for entry in self.price_history[symbol]]
        price_mean = mean(prices)
        price_stdev = stdev(prices) if len(set(prices)) > 1 else 0
        
        if current_price is not None and current_price < price_mean and (price_mean - current_price) < price_stdev:
            return price_mean
        
        return None

    def place_buy_order(self, symbol: str, amount_usdt: float, limit_price: float) -> Optional[Dict]:
        amount_crypto = amount_usdt / limit_price
        order = self.trading_client.place_order(symbol, 'buy', amount_crypto, limit_price)
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

    def place_sell_order(self, symbol: str, amount_crypto: float, target_sell_price: float) -> Optional[Dict]:
        order = self.trading_client.place_order(symbol, 'sell', amount_crypto, target_sell_price)
        if order:
            return order
        return None

    def get_current_status(self, prices: Dict[str, float]) -> Dict:
        current_total_usdt = self.wallet.get_total_balance_in_usdt(lambda symbol: prices.get(symbol.split('-')[0] + '-USDT'))
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

    def run_trading_iteration(self, symbols: List[str], profit_margin: float, num_orders: int) -> Dict:
        prices = self.trading_client.get_current_prices(symbols)
        self.update_price_history(symbols, prices)

        current_status = self.get_current_status(prices)
        tradable_usdt = current_status['tradable_usdt']

        for symbol in symbols:
            try:
                current_price = prices[symbol]
                if current_price is None:
                    logger.warning(f"Skipping {symbol} due to unavailable price data")
                    continue

                allocated_value = self.symbol_allocations.get(symbol, 0) * tradable_usdt
                usdt_balance = self.get_tradable_balance('USDT')

                # Check if we should buy
                limit_buy_price = self.should_buy(symbol, current_price)
                if usdt_balance > 0 and limit_buy_price is not None:
                    buy_amount_usdt = min(allocated_value, usdt_balance)
                    if buy_amount_usdt > 0:
                        order_amount = buy_amount_usdt / num_orders
                        for _ in range(num_orders):
                            order = self.place_buy_order(symbol, order_amount, limit_buy_price)
                            if order:
                                logger.info(f"Placed buy order for {symbol}: {order_amount:.4f} USDT at {limit_buy_price:.4f}")

                # Check active trades for selling
                for order_id, trade in list(self.active_trades.items()):
                    if trade['symbol'] == symbol:
                        target_sell_price = trade['buy_price'] * (1 + profit_margin)
                        if current_price >= target_sell_price:
                            sell_amount_crypto = trade['amount']
                            sell_order = self.place_sell_order(symbol, sell_amount_crypto, target_sell_price)
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
