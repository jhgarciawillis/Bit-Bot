import streamlit as st
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from config import config_manager
from trading_bot import TradingBot
from chart_utils import ChartCreator
from trading_loop import initialize_trading_loop, stop_trading_loop
from ui_components import UIManager

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def initialize_bot(is_simulation: bool, liquid_ratio: float, initial_balance: float) -> TradingBot:
    logger.info("Initializing bot...")
    bot = st.session_state.get('bot')
    if bot is None:
        logger.info("Creating a new bot instance.")
        bot = TradingBot(config_manager.get_config('bot_config')['update_interval'], liquid_ratio)
        st.session_state['bot'] = bot
    else:
        logger.info("Using existing bot instance.")
    
    bot.is_simulation = is_simulation
    bot.initialize()
    
    logger.info("Bot initialized successfully.")
    return bot

def main():
    logger.info("Starting main function...")
    st.set_page_config(layout="wide")
    st.title("Cryptocurrency Trading Bot")

    error_container = st.empty()
    ui_manager = UIManager(None)  # Initialize UI manager at the beginning

    try:
        logger.info("Initializing KuCoin client...")
        if not config_manager.get_config('simulation_mode')['enabled']:
            config_manager.initialize_kucoin_client()
        logger.info("Initializing session state...")
        ui_manager.initialize()

        if 'is_trading' not in st.session_state:
            st.session_state.is_trading = False
        if 'stop_event' not in st.session_state:
            st.session_state.stop_event = None
        if 'trading_task' not in st.session_state:
            st.session_state.trading_task = None
        if 'user_inputs' not in st.session_state:
            st.session_state.user_inputs = {}

        # Sidebar controls
        is_simulation, initial_balance, liquid_ratio, profit_margin_percentage, max_total_orders = ui_manager.display_component('sidebar_controls')
        
        if is_simulation is None:
            return

        # Initialize bot
        bot = initialize_bot(is_simulation, liquid_ratio, initial_balance)
        ui_manager.bot = bot  # Update UI manager with the initialized bot

        # Symbol selector
        available_symbols = config_manager.get_available_trading_symbols()
        if not available_symbols:
            st.warning("No available trading symbols found. Please check your KuCoin API connection.")
            return
        
        user_selected_symbols = ui_manager.display_component('symbol_selector', available_symbols=available_symbols, default_symbols=config_manager.get_config('trading_symbols'))

        if not user_selected_symbols:
            st.warning("Please select at least one symbol to trade.")
            return

        # Save user inputs
        st.session_state.user_inputs = {
            'user_selected_symbols': user_selected_symbols,
            'profit_margin_percentage': profit_margin_percentage,
            'max_total_orders': max_total_orders,
            'liquid_ratio': liquid_ratio,
        }

        # Update bot configuration
        bot.max_total_orders = max_total_orders
        bot.update_allocations(user_selected_symbols)
        bot.wallet.set_currency_allocations({symbol: 1/len(user_selected_symbols) for symbol in user_selected_symbols})

        # Trading controls
        start_button, stop_button = ui_manager.display_component('trading_controls')

        if start_button and not st.session_state.is_trading:
            st.session_state.is_trading = True
            bot.profit_margin = profit_margin_percentage
            st.session_state.stop_event, st.session_state.trading_task = initialize_trading_loop(
                bot, user_selected_symbols, profit_margin_percentage
            )
            st.sidebar.success("Trading started.")

            # Update charts and status
            chart_creator = ChartCreator(bot)
            charts = chart_creator.create_charts()
            ui_manager.display_component('chart_display', charts=charts)

            current_prices = config_manager.fetch_real_time_prices(user_selected_symbols)
            current_status = bot.get_current_status(current_prices)
            ui_manager.display_component('status_table', current_status=current_status)

            ui_manager.display_component('trade_messages')

        if stop_button or (not st.session_state.is_trading and st.session_state.stop_event):
            st.session_state.is_trading = False
            if st.session_state.stop_event and st.session_state.trading_task:
                stop_trading_loop(st.session_state.stop_event, st.session_state.trading_task)
                st.session_state.stop_event = None
                st.session_state.trading_task = None
            st.sidebar.success("Trading stopped.")
            ui_manager.display_component('chart_display', charts={})
            ui_manager.display_component('status_table', current_status={})

        # Main area
        if st.session_state.is_trading:
            st.subheader("Trading Status")
            current_prices = config_manager.fetch_real_time_prices(user_selected_symbols)
            current_status = bot.get_current_status(current_prices)
            ui_manager.display_component('status_table', current_status=current_status)

            st.subheader("Trade Messages")
            ui_manager.display_component('trade_messages')

            st.subheader("Trading Charts")
            chart_creator = ChartCreator(bot)
            charts = chart_creator.create_charts()
            ui_manager.display_component('chart_display', charts=charts)
        else:
            st.info("Click 'Start Trading' to begin trading.")

        # Display simulation indicator
        ui_manager.display_component('simulation_indicator', is_simulation=is_simulation)

    except Exception as e:
        logger.error(f"An error occurred in the main function: {e}")
        ui_manager.display_component('error_message', error_message=str(e), container=error_container)

if __name__ == "__main__":
    main()
