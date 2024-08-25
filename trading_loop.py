import asyncio
import streamlit as st
from typing import List, Tuple
from trading_bot import TradingBot
import logging
from config import load_config

logger = logging.getLogger(__name__)

async def trading_loop(bot: TradingBot, chosen_symbols: List[str], profit_margin: float, num_orders: int, stop_event: asyncio.Event) -> None:
    """
    Main trading loop that runs continuously until stopped.

    :param bot: TradingBot instance
    :param chosen_symbols: List of trading symbols
    :param profit_margin: Profit margin for trades
    :param num_orders: Number of orders to place
    :param stop_event: Asyncio event to signal stopping the loop
    """
    config = await load_config()
    
    while not stop_event.is_set():
        try:
            current_status = await bot.run_trading_iteration(chosen_symbols, profit_margin, num_orders)
            
            # Update session state with new trade messages
            if 'trade_messages' in st.session_state:
                for symbol, profit in current_status['profits'].items():
                    if profit > 0:
                        st.session_state.trade_messages.append(f"Profit realized for {symbol}: {profit:.4f} USDT")
                
                # Keep only the last 10 trade messages
                st.session_state.trade_messages = st.session_state.trade_messages[-10:]
            
            # Sleep for the configured update interval
            await asyncio.sleep(config['bot_config']['update_interval'])
            
        except Exception as e:
            logger.error(f"An error occurred in the trading loop: {str(e)}")
            if 'error_message' in st.session_state:
                st.session_state.error_message = f"An error occurred: {str(e)}"
            
            # Sleep for the configured retry delay before next iteration
            await asyncio.sleep(config['error_config']['retry_delay'])

async def initialize_trading_loop(bot: TradingBot, chosen_symbols: List[str], profit_margin: float, num_orders: int) -> Tuple[asyncio.Event, asyncio.Task]:
    """
    Initialize and start the trading loop as an asyncio task.

    :param bot: TradingBot instance
    :param chosen_symbols: List of trading symbols
    :param profit_margin: Profit margin for trades
    :param num_orders: Number of orders to place
    :return: Tuple containing the stop event and the trading task
    """
    stop_event = asyncio.Event()
    trading_task = asyncio.create_task(
        trading_loop(bot, chosen_symbols, profit_margin, num_orders, stop_event)
    )
    return stop_event, trading_task

async def stop_trading_loop(stop_event: asyncio.Event, trading_task: asyncio.Task) -> None:
    """
    Stop the trading loop and wait for the task to finish.

    :param stop_event: Asyncio event to signal stopping the loop
    :param trading_task: The trading task to stop
    """
    stop_event.set()
    try:
        await asyncio.wait_for(trading_task, timeout=10)  # Wait for up to 10 seconds for the task to finish
    except asyncio.TimeoutError:
        logger.warning("Trading task did not stop within the timeout period.")
    else:
        logger.info("Trading loop stopped successfully.")

def handle_trading_errors(func):
    """
    Decorator to handle errors in trading functions.

    :param func: Function to decorate
    :return: Wrapped function
    """
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            if 'error_message' in st.session_state:
                st.session_state.error_message = f"An error occurred in {func.__name__}: {str(e)}"
    return wrapper

@handle_trading_errors
async def update_trading_status(bot: TradingBot, chosen_symbols: List[str]) -> None:
    """
    Update and display the current trading status.

    :param bot: TradingBot instance
    :param chosen_symbols: List of trading symbols
    """
    current_prices = await bot.get_current_prices(chosen_symbols)
    current_status = bot.get_current_status(current_prices)

    # Update Streamlit display with current status
    st.write("Current Trading Status:")
    st.write(f"Total Profit: {current_status['total_profit']:.4f} USDT")
    st.write(f"Active Trades: {len(current_status['active_trades'])}")
    st.write(f"Total Trades: {current_status['total_trades']}")
    
    # Display current prices in a table
    price_data = [[symbol, f"{price:.4f} USDT"] for symbol, price in current_prices.items()]
    st.table(price_data)

async def main_trading_loop(bot: TradingBot, chosen_symbols: List[str], profit_margin: float, num_orders: int) -> None:
    """
    Main function to run the trading loop and update status.

    :param bot: TradingBot instance
    :param chosen_symbols: List of trading symbols
    :param profit_margin: Profit margin for trades
    :param num_orders: Number of orders to place
    """
    stop_event, trading_task = await initialize_trading_loop(bot, chosen_symbols, profit_margin, num_orders)
    
    try:
        while not stop_event.is_set():
            await update_trading_status(bot, chosen_symbols)
            await asyncio.sleep(5)  # Update status every 5 seconds
    except asyncio.CancelledError:
        logger.info("Trading loop cancelled. Stopping trading loop.")
    finally:
        await stop_trading_loop(stop_event, trading_task)

if __name__ == "__main__":
    # This block allows running the trading loop independently for testing
    async def run():
        config = await load_config()
        bot = TradingBot(config['api_key'], config['api_secret'], config['api_passphrase'], config['bot_config']['update_interval'])
        await bot.initialize()
        chosen_symbols = config['default_trading_symbols']
        profit_margin = config['default_profit_margin']
        num_orders = config['default_num_orders']
        
        await main_trading_loop(bot, chosen_symbols, profit_margin, num_orders)

    asyncio.run(run())
