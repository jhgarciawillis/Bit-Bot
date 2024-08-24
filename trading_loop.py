import time
import threading
import streamlit as st
from typing import List, Tuple
from trading_bot import TradingBot
import logging
from config import load_config

logger = logging.getLogger(__name__)

def trading_loop(bot: TradingBot, chosen_symbols: List[str], profit_margin: float, num_orders: int, stop_event: threading.Event) -> None:
    """
    Main trading loop that runs continuously until stopped.

    :param bot: TradingBot instance
    :param chosen_symbols: List of trading symbols
    :param profit_margin: Profit margin for trades
    :param num_orders: Number of orders to place
    :param stop_event: Threading event to signal stopping the loop
    """
    config = load_config()
    
    while not stop_event.is_set():
        try:
            current_status = bot.run_trading_iteration(chosen_symbols, profit_margin, num_orders)
            
            # Update session state with new trade messages
            for symbol, profit in current_status['profits'].items():
                if profit > 0:
                    st.session_state.trade_messages.append(f"Profit realized for {symbol}: {profit:.4f} USDT")
            
            # Keep only the last 10 trade messages
            st.session_state.trade_messages = st.session_state.trade_messages[-10:]
            
            # Sleep for the configured update interval
            time.sleep(config['bot_config']['update_interval'])
            
        except Exception as e:
            logger.error(f"An error occurred in the trading loop: {str(e)}")
            st.session_state.error_message = f"An error occurred: {str(e)}"
            
            # Sleep for the configured retry delay before next iteration
            time.sleep(config['error_config']['retry_delay'])

def initialize_trading_loop(bot: TradingBot, chosen_symbols: List[str], profit_margin: float, num_orders: int) -> Tuple[threading.Event, threading.Thread]:
    """
    Initialize and start the trading loop in a separate thread.

    :param bot: TradingBot instance
    :param chosen_symbols: List of trading symbols
    :param profit_margin: Profit margin for trades
    :param num_orders: Number of orders to place
    :return: Tuple containing the stop event and the trading thread
    """
    stop_event = threading.Event()
    trading_thread = threading.Thread(
        target=trading_loop,
        args=(bot, chosen_symbols, profit_margin, num_orders, stop_event)
    )
    trading_thread.start()
    return stop_event, trading_thread

def stop_trading_loop(stop_event: threading.Event, trading_thread: threading.Thread) -> None:
    """
    Stop the trading loop and wait for the thread to finish.

    :param stop_event: Threading event to signal stopping the loop
    :param trading_thread: The trading thread to stop
    """
    stop_event.set()
    trading_thread.join()
    logger.info("Trading loop stopped")

def handle_trading_errors(func):
    """
    Decorator to handle errors in trading functions.

    :param func: Function to decorate
    :return: Wrapped function
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            st.session_state.error_message = f"An error occurred in {func.__name__}: {str(e)}"
    return wrapper

@handle_trading_errors
def update_trading_status(bot: TradingBot, chosen_symbols: List[str]) -> None:
    """
    Update and display the current trading status.

    :param bot: TradingBot instance
    :param chosen_symbols: List of trading symbols
    """
    current_prices = bot.trading_client.get_current_prices(chosen_symbols)
    current_status = bot.get_current_status(current_prices)
    
    # Update Streamlit display with current status
    st.write("Current Trading Status:")
    st.write(f"Total Profit: {current_status['total_profit']:.4f} USDT")
    st.write(f"Active Trades: {len(current_status['active_trades'])}")
    st.write(f"Total Trades: {current_status['total_trades']}")
    
    # Display current prices
    st.write("Current Prices:")
    for symbol, price in current_prices.items():
        st.write(f"{symbol}: {price:.4f} USDT")

def main_trading_loop(bot: TradingBot, chosen_symbols: List[str], profit_margin: float, num_orders: int) -> None:
    """
    Main function to run the trading loop and update status.

    :param bot: TradingBot instance
    :param chosen_symbols: List of trading symbols
    :param profit_margin: Profit margin for trades
    :param num_orders: Number of orders to place
    """
    stop_event, trading_thread = initialize_trading_loop(bot, chosen_symbols, profit_margin, num_orders)
    
    try:
        while not stop_event.is_set():
            update_trading_status(bot, chosen_symbols)
            time.sleep(5)  # Update status every 5 seconds
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Stopping trading loop.")
    finally:
        stop_trading_loop(stop_event, trading_thread)

if __name__ == "__main__":
    # This block allows running the trading loop independently for testing
    config = load_config()
    bot = TradingBot(config['api_key'], config['api_secret'], config['api_passphrase'], config['bot_config']['update_interval'])
    chosen_symbols = config['default_trading_symbols']
    profit_margin = config['default_profit_margin']
    num_orders = config['default_num_orders']
    
    main_trading_loop(bot, chosen_symbols, profit_margin, num_orders)
