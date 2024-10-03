import time
import threading
import streamlit as st
from typing import List, Tuple, Dict, Any
from trading_bot import TradingBot
import logging
from config import config_manager

logger = logging.getLogger(__name__)

def handle_trading_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"An error occurred in {func.__name__}: {str(e)}")
            if 'error_message' in st.session_state:
                st.session_state.error_message = f"An error occurred: {str(e)}"
    return wrapper

class TradingLoop:
    def __init__(self, bot: TradingBot, chosen_symbols: List[str], profit_margin: float):
        self.bot = bot
        self.chosen_symbols = chosen_symbols
        self.profit_margin = profit_margin if profit_margin is not None else config_manager.get_config('profit_margin', 0)

    @handle_trading_errors
    def run(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            try:
                self.trading_iteration()
                time.sleep(config_manager.get_config('bot_config')['update_interval'])
            except Exception as e:
                logger.error(f"An error occurred in the trading loop: {str(e)}")
                time.sleep(config_manager.get_config('error_config')['retry_delay'])

    @handle_trading_errors
    def trading_iteration(self) -> None:
        current_prices = config_manager.fetch_real_time_prices(self.chosen_symbols)
        
        for symbol in self.chosen_symbols:
            self.process_symbol(symbol, current_prices[symbol])

        self.update_trading_status(current_prices)

    @handle_trading_errors
    def process_symbol(self, symbol: str, current_price: float) -> None:
        if current_price is None:
            logger.warning(f"No price data available for {symbol}")
            return

        self.bot.update_price_history([symbol], {symbol: current_price})

        if self.bot.can_place_order(symbol):
            self.check_buy_condition(symbol, current_price)
        
        self.check_sell_condition(symbol, current_price)

    @handle_trading_errors
    def check_buy_condition(self, symbol: str, current_price: float) -> None:
        should_buy = self.bot.should_buy(symbol, current_price)
        if should_buy is not None:
            available_balance = self.bot.get_available_balance(symbol)
            if available_balance > 0:
                order_amount = min(available_balance, self.bot.symbol_allocations.get(symbol, 0))
                if order_amount > 0:
                    order = self.bot.place_buy_order(symbol, order_amount, should_buy)
                    if order:
                        logger.info(f"Placed buy order for {symbol}: {order['dealSize']:.8f} {symbol} at {should_buy:.4f} USDT")

    @handle_trading_errors
    def check_sell_condition(self, symbol: str, current_price: float) -> None:
        active_trades = [trade for trade in self.bot.active_trades.values() if trade['symbol'] == symbol]
        for active_trade in active_trades:
            target_sell_price = active_trade['buy_price'] * (1 + self.profit_margin)
            if current_price >= target_sell_price:
                sell_amount = active_trade['amount']
                sell_order = self.bot.place_sell_order(symbol, sell_amount, current_price)
                if sell_order:
                    profit = self.bot.calculate_profit(active_trade, sell_order)
                    self.bot.update_profit(symbol, profit)
                    logger.info(f"Sold {symbol}: {sell_order['dealSize']:.8f} at {current_price:.4f}, Profit: {profit:.4f} USDT")
                    del self.bot.active_trades[active_trade['orderId']]

    @handle_trading_errors
    def update_trading_status(self, current_prices: Dict[str, float]) -> None:
        current_status = self.bot.get_current_status(current_prices)
        
        if 'trade_messages' in st.session_state:
            for symbol, profit in current_status['profits'].items():
                if profit > 0:
                    st.session_state.trade_messages.append(f"Profit realized for {symbol}: {profit:.4f} USDT")
            
            st.session_state.trade_messages = st.session_state.trade_messages[-10:]

        self.bot.update_allocations(self.chosen_symbols)

def initialize_trading_loop(bot: TradingBot, chosen_symbols: List[str], profit_margin: float) -> Tuple[threading.Event, threading.Thread]:
    stop_event = threading.Event()
    trading_loop = TradingLoop(bot, chosen_symbols, profit_margin)
    trading_thread = threading.Thread(target=trading_loop.run, args=(stop_event,))
    trading_thread.start()
    return stop_event, trading_thread

def stop_trading_loop(stop_event: threading.Event, trading_thread: threading.Thread) -> None:
    stop_event.set()
    try:
        trading_thread.join(timeout=10)
    except TimeoutError:
        logger.warning("Trading thread did not stop within the timeout period.")
    else:
        logger.info("Trading loop stopped successfully.")

if __name__ == "__main__":
    bot = TradingBot(config_manager.get_config('bot_config')['update_interval'], config_manager.get_config('liquid_ratio'))
    bot.initialize()
    chosen_symbols = config_manager.get_config('trading_symbols')
    profit_margin = config_manager.get_config('profit_margin')
    
    stop_event, trading_thread = initialize_trading_loop(bot, chosen_symbols, profit_margin)
    
    # Run for 5 minutes
    time.sleep(300)
    
    stop_trading_loop(stop_event, trading_thread)
