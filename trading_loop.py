import asyncio
import streamlit as st
from typing import List, Tuple, Dict, Any
from trading_bot import TradingBot
import logging
from config import load_config, fetch_real_time_prices, kucoin_client_manager
from kucoin.exceptions import KucoinAPIException

logger = logging.getLogger(__name__)

def handle_trading_errors(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except KucoinAPIException as e:
            logger.error(f"KuCoin API error in {func.__name__}: {str(e)}")
            if 'error_message' in st.session_state:
                st.session_state.error_message = f"KuCoin API error: {str(e)}"
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            if 'error_message' in st.session_state:
                st.session_state.error_message = f"An error occurred: {str(e)}"
    return wrapper

class TradingLoop:
    def __init__(self, bot: TradingBot, chosen_symbols: List[str], profit_margin: float, num_orders: int):
        self.bot = bot
        self.chosen_symbols = chosen_symbols
        self.profit_margin = profit_margin
        self.num_orders = num_orders
        self.config = asyncio.run(load_config())

    @handle_trading_errors
    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await self.trading_iteration()
                await asyncio.sleep(self.config['bot_config']['update_interval'])
            except asyncio.CancelledError:
                logger.info("Trading loop cancelled")
                break
            except Exception as e:
                logger.error(f"An error occurred in the trading loop: {str(e)}")
                await asyncio.sleep(self.config['error_config']['retry_delay'])

    @handle_trading_errors
    async def trading_iteration(self) -> None:
        current_prices = await fetch_real_time_prices(self.chosen_symbols, self.bot.is_simulation)
        
        for symbol in self.chosen_symbols:
            await self.process_symbol(symbol, current_prices[symbol])

        await self.update_trading_status(current_prices)

    @handle_trading_errors
    async def process_symbol(self, symbol: str, current_price: float) -> None:
        if current_price is None:
            logger.warning(f"No price data available for {symbol}")
            return

        await self.bot.update_price_history(symbol, current_price)

        if symbol not in self.bot.active_trades:
            await self.check_buy_condition(symbol, current_price)
        else:
            await self.check_sell_condition(symbol, current_price)

    @handle_trading_errors
    async def check_buy_condition(self, symbol: str, current_price: float) -> None:
        should_buy = await self.bot.should_buy(symbol, current_price)
        if should_buy is not None:
            usdt_balance = await self.bot.get_tradable_balance('USDT')
            allocated_value = self.bot.symbol_allocations.get(symbol, 0) * usdt_balance
            if allocated_value > 0:
                order_amount = allocated_value / self.num_orders
                for _ in range(self.num_orders):
                    order = await self.bot.place_buy_order(symbol, order_amount, should_buy)
                    if order:
                        logger.info(f"Placed buy order for {symbol}: {order_amount:.4f} USDT at {should_buy:.4f}")

    @handle_trading_errors
    async def check_sell_condition(self, symbol: str, current_price: float) -> None:
        active_trade = self.bot.active_trades[symbol]
        target_sell_price = active_trade['buy_price'] * (1 + self.profit_margin)
        if current_price >= target_sell_price:
            sell_amount = active_trade['amount']
            sell_order = await self.bot.place_sell_order(symbol, sell_amount, current_price)
            if sell_order:
                profit = (current_price - active_trade['buy_price']) * sell_amount - active_trade['fee'] - float(sell_order['fee'])
                self.bot.profits[symbol] = self.bot.profits.get(symbol, 0) + profit
                self.bot.total_profit += profit
                self.bot.total_trades += 1
                self.bot.avg_profit_per_trade = self.bot.total_profit / self.bot.total_trades
                logger.info(f"Sold {symbol}: {sell_amount:.8f} at {current_price:.4f}, Profit: {profit:.4f} USDT")
                del self.bot.active_trades[symbol]

    @handle_trading_errors
    async def update_trading_status(self, current_prices: Dict[str, float]) -> None:
        current_status = await self.bot.get_current_status(current_prices)
        
        if 'trade_messages' in st.session_state:
            for symbol, profit in current_status['profits'].items():
                if profit > 0:
                    st.session_state.trade_messages.append(f"Profit realized for {symbol}: {profit:.4f} USDT")
            
            st.session_state.trade_messages = st.session_state.trade_messages[-10:]

        self.bot.update_allocations(current_status['current_total_usdt'], self.bot.usdt_liquid_percentage)

async def initialize_trading_loop(bot: TradingBot, chosen_symbols: List[str], profit_margin: float, num_orders: int) -> Tuple[asyncio.Event, asyncio.Task]:
    stop_event = asyncio.Event()
    trading_loop = TradingLoop(bot, chosen_symbols, profit_margin, num_orders)
    trading_task = asyncio.create_task(trading_loop.run(stop_event))
    return stop_event, trading_task

async def stop_trading_loop(stop_event: asyncio.Event, trading_task: asyncio.Task) -> None:
    stop_event.set()
    try:
        await asyncio.wait_for(trading_task, timeout=10)
    except asyncio.TimeoutError:
        logger.warning("Trading task did not stop within the timeout period.")
    else:
        logger.info("Trading loop stopped successfully.")

if __name__ == "__main__":
    async def run_test():
        config = await load_config()
        bot = await TradingBot.create(config['bot_config']['update_interval'])
        chosen_symbols = config['default_trading_symbols']
        profit_margin = config['default_profit_margin']
        num_orders = config['default_num_orders']
        
        stop_event, trading_task = await initialize_trading_loop(bot, chosen_symbols, profit_margin, num_orders)
        
        # Run for 5 minutes
        await asyncio.sleep(300)
        
        await stop_trading_loop(stop_event, trading_task)

    asyncio.run(run_test())
