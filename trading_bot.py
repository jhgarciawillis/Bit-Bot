import logging
from datetime import datetime
from collections import deque
from statistics import mean, stdev
from typing import Dict, List, Optional, Tuple, Union
from wallet import create_wallet
from config import config_manager
from utils import handle_trading_errors
from kucoin.client import Trade
from simulated_trade_client import SimulatedTradeClient

logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self, update_interval: int, liquid_ratio: float):
        self.wallet = None
        self.update_interval = update_interval
        self.liquid_ratio = liquid_ratio
        self.symbol_allocations: Dict[str, float] = {}
        self.price_history: Dict[str, deque] = {}
        self.active_trades: Dict[str, Dict] = {}
        self.total_trades: int = 0
        self.status_history: List[Dict] = []
        self.is_simulation: bool = False
        self.profit_margin: float = config_manager.get_config('profit_margin')
        self.trade_client: Optional[Union[Trade, SimulatedTradeClient]] = None
        self.max_total_orders: int = config_manager.get_max_total_orders()
        self.currency_allocations: Dict[str, float] = config_manager.get_currency_allocations()
        self.active_orders: Dict[str, List[Dict]] = {}

    def initialize(self) -> None:
        self.is_simulation = config_manager.get_config('simulation_mode')['enabled']
        self.PRICE_HISTORY_LENGTH = config_manager.get_config('chart_config')['history_length']
        self.wallet = create_wallet(self.is_simulation, self.liquid_ratio)
        initial_balance = config_manager.get_config('simulation_mode')['initial_balance']
        self.wallet.initialize_balance(initial_balance)
        self.wallet.set_currency_allocations(self.currency_allocations)
        
        if not self.is_simulation:
            self.trade_client = config_manager.kucoin_client_manager.get_client()
            self.update_wallet_balances()
        else:
            self.trade_client = config_manager.create_simulated_trade_client(
                config_manager.get_config('fees'),
                self.max_total_orders,
                self.currency_allocations
            )
        
        logger.info("Bot initialized successfully.")
        
    @handle_trading_errors
    def update_wallet_balances(self) -> None:
        try:
            self.wallet.sync_with_exchange('trading')
            logger.info(f"Updated wallet balances: {self.wallet.get_account_summary()}")
        except Exception as e:
            logger.error(f"Error updating wallet balances: {e}")

    def get_balance(self, currency: str, balance_type: str) -> float:
        return self.wallet.get_balance('trading', currency, balance_type)

    def get_user_allocations(self, user_selected_symbols: List[str]) -> Dict[str, float]:
        tradable_usdt_amount = self.get_balance('USDT', 'trading')
        
        if tradable_usdt_amount <= 0 or not user_selected_symbols:
            return {}

        return {symbol: tradable_usdt_amount * self.currency_allocations.get(symbol, 0) 
                for symbol in user_selected_symbols}

    def update_price_history(self, symbols: List[str], prices: Dict[str, float]) -> None:
        for symbol in symbols:
            if symbol not in self.price_history:
                self.price_history[symbol] = deque(maxlen=self.PRICE_HISTORY_LENGTH)
            if prices[symbol] is not None:
                self.price_history[symbol].append({
                    'timestamp': datetime.now(),
                    'price': prices[symbol]
                })
                self.wallet.update_currency_price('trading', symbol, prices[symbol])

    def should_buy(self, symbol: str, current_price: float) -> Optional[float]:
        if current_price is None or len(self.price_history[symbol]) < self.PRICE_HISTORY_LENGTH:
            return None
        
        prices = [entry['price'] for entry in self.price_history[symbol]]
        price_mean = mean(prices)
        price_stdev = stdev(prices) if len(set(prices)) > 1 else 0
        
        if current_price < price_mean and (price_mean - current_price) < price_stdev:
            return current_price
        
        return None

    def can_place_order(self, symbol: str) -> bool:
        total_orders = sum(len(orders) for orders in self.active_orders.values())
        return total_orders < self.max_total_orders

    @handle_trading_errors
    def place_buy_order(self, symbol: str, amount_usdt: float, limit_price: float) -> Optional[Dict]:
        if not self.can_place_order(symbol) or amount_usdt > self.get_balance('USDT', 'trading'):
            return None
        
        try:
            order = self.trade_client.create_limit_order(
                symbol=symbol,
                side=Trade.SIDE_BUY,
                price=str(limit_price),
                size=str(amount_usdt / limit_price),
            )
            if order:
                self._process_order_response(order, 'buy', symbol, amount_usdt / limit_price, limit_price)
            return order
        except Exception as e:
            logger.error(f"Error placing buy order: {e}")
            return None

    @handle_trading_errors
    def place_sell_order(self, symbol: str, amount_crypto: float, target_sell_price: float) -> Optional[Dict]:
        if not self.can_place_order(symbol):
            return None
        
        try:
            order = self.trade_client.create_limit_order(
                symbol=symbol,
                side=Trade.SIDE_SELL,
                price=str(target_sell_price),
                size=str(amount_crypto),
            )
            if order:
                self._process_order_response(order, 'sell', symbol, amount_crypto, target_sell_price)
            return order
        except Exception as e:
            logger.error(f"Error placing sell order: {e}")
            return None

    def _process_order_response(self, order: Dict, side: str, symbol: str, amount: float, price: float) -> None:
        if side == Trade.SIDE_BUY:
            self.active_trades[order['orderId']] = {
                'symbol': symbol,
                'buy_price': float(price),
                'amount': float(amount),
                'fee': float(order.get('fee', 0)),
                'buy_time': datetime.now()
            }
        self.wallet.update_account_balance('trading', symbol, float(amount), float(price), float(order.get('fee', 0)), side)
        if symbol not in self.active_orders:
            self.active_orders[symbol] = []
        self.active_orders[symbol].append(order)

    def calculate_target_sell_price(self, buy_price: float) -> float:
        target_sell_price = buy_price * (1 + self.profit_margin)
        return target_sell_price

    def calculate_profit(self, buy_order: Dict, sell_order: Dict) -> float:
        buy_amount_usdt = float(buy_order['dealFunds'])
        sell_amount_usdt = float(sell_order['dealFunds'])
        sell_fee_usdt = float(sell_order['fee'])
        
        profit = (sell_amount_usdt - sell_fee_usdt) - buy_amount_usdt
        return profit

    def update_profit(self, symbol: str, profit: float) -> None:
        self.wallet.update_profits(symbol, profit)
        self.total_trades += 1

    def update_allocations(self, user_selected_symbols: List[str]) -> None:
        self.symbol_allocations = self.get_user_allocations(user_selected_symbols)
        self.currency_allocations = {symbol: 1/len(user_selected_symbols) 
                                   for symbol in user_selected_symbols}
        self.wallet.set_currency_allocations(self.currency_allocations)

    def get_current_status(self, prices: Dict[str, float]) -> Dict:
        current_total_usdt = self.wallet.get_balance('trading', 'USDT', 'liquid') + self.wallet.get_balance('trading', 'USDT', 'trading')
        tradable_usdt = self.get_balance('USDT', 'trading')
        liquid_usdt = self.wallet.get_balance('trading', 'USDT', 'liquid')
        
        status = {
            'timestamp': datetime.now(),
            'prices': prices,
            'active_trades': self.active_trades.copy(),
            'profits': self.wallet.get_profits(),
            'total_profit': sum(self.wallet.get_profits().values()),
            'current_total_usdt': current_total_usdt,
            'tradable_usdt': tradable_usdt,
            'liquid_usdt': liquid_usdt,
            'wallet_summary': self.wallet.get_account_summary(),
            'total_trades': self.total_trades,
            'avg_profit_per_trade': sum(self.wallet.get_profits().values()) / self.total_trades 
                                  if self.total_trades > 0 else 0,
            'active_orders': {symbol: len(orders) for symbol, orders in self.active_orders.items()},
        }
        
        self.status_history.append(status)
        if len(self.status_history) > 120:
            self.status_history.pop(0)
        
        return status
