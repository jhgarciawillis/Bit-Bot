import streamlit as st
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from config import config_manager
from trading_bot import TradingBot, create_trading_bot
from chart_utils import ChartCreator
from trading_loop import initialize_trading_loop, stop_trading_loop
from ui_components import UIManager
from wallet import create_wallet

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def initialize_bot(is_simulation: bool, liquid_ratio: float, initial_balance: float) -> TradingBot:
    logger.info("Initializing bot...")
    bot = st.session_state.get('bot')
    if bot is None:
        logger.info("Creating a new bot instance.")
        bot = create_trading_bot(config_manager.get_config('bot_config')['update_interval'], liquid_ratio)
        st.session_state['bot'] = bot
    else:
        logger.info("Using existing bot instance.")
    
    bot.is_simulation = is_simulation
    bot.wallet = create_wallet(is_simulation, liquid_ratio)
    bot.wallet.initialize_balance(initial_balance)
    
    bot.initialize()
    
    logger.info("Bot initialized successfully.")
    return bot

def save_chart(fig, filename):
    logger.info(f"Saving chart as {filename}...")
    fig.write_image(filename)
    logger.info(f"Chart saved as {filename}")
    st.success(f"Chart saved as {filename}")

def main():
    logger.info("Starting main function...")
    st.set_page_config(layout="wide")
    st.title("Cryptocurrency Trading Bot")

    error_container = st.empty()
    ui_manager = UIManager(None)  # Initialize UI manager at the beginning

    try:
        logger.info("Initializing KuCoin client...")
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

        # Sidebar
        st.sidebar.header("Configuration")

        # Mode selection
        is_simulation = st.sidebar.checkbox("Simulation Mode", value=config_manager.get_config('simulation_mode')['enabled'])
        
        if is_simulation:
            st.sidebar.write("Running in simulation mode. No real trades will be executed.")
            initial_balance = st.sidebar.number_input(
                "Simulated USDT Balance",
                min_value=0.0,
                value=config_manager.get_config('simulation_mode')['initial_balance'],
                step=0.1
            )
        else:
            st.sidebar.warning("WARNING: This bot will use real funds on the live KuCoin exchange.")
            st.sidebar.warning("Only proceed if you understand the risks and are using funds you can afford to lose.")
            proceed = st.sidebar.checkbox("I understand the risks and want to proceed")
            if not proceed:
                st.sidebar.error("Please check the box to proceed with live trading.")
                return
            
            if not ui_manager.display_component('live_trading_verification'):
                return
            
            initial_balance = config_manager.get_config('simulation_mode')['initial_balance']

        # Trading parameters
        st.sidebar.header("Trading Parameters")
        usdt_liquid_percentage = st.sidebar.slider(
            "Percentage of assets to keep liquid (0-100%)",
            min_value=0.0,
            max_value=100.0,
            value=config_manager.get_config('usdt_liquid_percentage', 0.5) * 100,
            step=0.1
        ) / 100

        profit_margin_percentage = st.sidebar.number_input(
            "Profit Margin Percentage",
            min_value=0.0001,
            value=config_manager.get_config('profit_margin', 0.0001) * 100,
            step=0.0001,
            format="%.4f"
        ) / 100

        max_total_orders = st.sidebar.slider(
            "Maximum Total Orders",
            min_value=1,
            max_value=50,
            value=config_manager.get_config('max_total_orders', 10)
        )

        # Initialize bot
        bot = initialize_bot(is_simulation, usdt_liquid_percentage, initial_balance)
        ui_manager.update_bot(bot)

        # Display wallet balance
        ui_manager.display_component('wallet_balance')

        # Symbol selector
        available_symbols = config_manager.get_available_trading_symbols()
        if not available_symbols:
            st.warning("No available trading symbols found. Please check your KuCoin API connection.")
            return
        
        user_selected_symbols = st.sidebar.multiselect(
            "Select Symbols to Trade",
            available_symbols,
            default=config_manager.get_config('trading_symbols')
        )

        if not user_selected_symbols:
            st.warning("Please select at least one symbol to trade.")
            return

        # Currency allocations
        st.sidebar.subheader("Currency Allocations")
        currency_allocations = {}
        for symbol in user_selected_symbols:
            allocation = st.sidebar.slider(
                f"Allocation for {symbol} (%)",
                min_value=0.0,
                max_value=100.0,
                value=100.0 / len(user_selected_symbols),
                step=0.1
            )
            currency_allocations[symbol] = allocation / 100.0

        # Normalize allocations
        total_allocation = sum(currency_allocations.values())
        if total_allocation != 0:
            currency_allocations = {symbol: alloc / total_allocation for symbol, alloc in currency_allocations.items()}

        # Save user inputs
        st.session_state.user_inputs = {
            'user_selected_symbols': user_selected_symbols,
            'profit_margin_percentage': profit_margin_percentage,
            'max_total_orders': max_total_orders,
            'usdt_liquid_percentage': usdt_liquid_percentage,
            'currency_allocations': currency_allocations,
        }

        # Update bot configuration
        bot.max_total_orders = max_total_orders
        bot.update_allocations(user_selected_symbols)
        bot.wallet.set_currency_allocations(currency_allocations)

        # Trading controls
        start_button = st.sidebar.button("Start Trading")
        stop_button = st.sidebar.button("Stop Trading")

        if start_button and not st.session_state.is_trading:
            st.session_state.is_trading = True
            bot.profit_margin = profit_margin_percentage
            st.session_state.stop_event, st.session_state.trading_task = initialize_trading_loop(
                bot, user_selected_symbols, profit_margin_percentage
            )

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

    except Exception as e:
        logger.error(f"An error occurred in the main function: {e}")
        ui_manager.display_component('error_message', error_message=str(e), container=error_container)

if __name__ == "__main__":
    main()
