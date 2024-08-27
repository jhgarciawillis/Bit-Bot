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

def initialize_bot(is_simulation: bool, liquid_ratio: float) -> TradingBot:
    logger.info("Initializing bot...")
    bot = st.session_state.get('bot')
    if bot is None:
        logger.info("Creating a new bot instance.")
        bot = create_trading_bot(config_manager.get_config('bot_config')['update_interval'])
        st.session_state['bot'] = bot
    else:
        logger.info("Using existing bot instance.")
    
    bot.is_simulation = is_simulation
    bot.wallet = create_wallet(is_simulation, liquid_ratio)
    
    if not is_simulation:
        logger.info("Live trading mode, initializing bot.")
        bot.initialize()
    else:
        logger.info("Simulation mode, no need to initialize bot.")
    
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
            logger.info("Initializing 'is_trading' in session state.")
            st.session_state.is_trading = False
        if 'stop_event' not in st.session_state:
            logger.info("Initializing 'stop_event' in session state.")
            st.session_state.stop_event = None
        if 'trading_task' not in st.session_state:
            logger.info("Initializing 'trading_task' in session state.")
            st.session_state.trading_task = None
        if 'user_inputs' not in st.session_state:
            logger.info("Initializing 'user_inputs' in session state.")
            st.session_state.user_inputs = {}

        logger.info("Configuring sidebar...")
        is_simulation, liquid_ratio = ui_manager.display_component('sidebar_config')

        if is_simulation is not None:
            logger.info(f"Simulation mode: {is_simulation}")
            if not is_simulation:
                logger.info("Live trading mode, verifying access key...")
                if not ui_manager.display_component('live_trading_verification'):
                    return
            
            logger.info("Initializing bot...")
            bot = initialize_bot(is_simulation, liquid_ratio)
            ui_manager.update_bot(bot)  # Update the bot in UIManager

            logger.info("Displaying wallet balance...")
            ui_manager.display_component('wallet_balance')

            logger.info("Displaying simulation indicator...")
            ui_manager.display_component('simulation_indicator', is_simulation=is_simulation)

            logger.info("Fetching available trading symbols...")
            available_symbols = config_manager.get_available_trading_symbols()
            if not available_symbols:
                logger.warning("No available trading symbols found. Please check your KuCoin API connection.")
                st.warning("No available trading symbols found. Please check your KuCoin API connection.")
                return
            
            logger.info("Displaying symbol selector...")
            user_selected_symbols = ui_manager.display_component('symbol_selector', available_symbols=available_symbols, default_symbols=config_manager.get_config('trading_symbols'))

            if not user_selected_symbols:
                logger.warning("No symbols selected for trading.")
                st.warning("Please select at least one symbol to trade.")
                return

            logger.info("Displaying trading parameters...")
            logger.info("Calling ui_manager.display_component('trading_parameters')")
            usdt_liquid_percentage, profit_margin_percentage, num_orders_per_trade = ui_manager.display_component('trading_parameters')
            logger.info(f"Received usdt_liquid_percentage: {usdt_liquid_percentage}, profit_margin_percentage: {profit_margin_percentage}, num_orders_per_trade: {num_orders_per_trade}")

            # Check if the returned values are valid
            if profit_margin_percentage is None or num_orders_per_trade is None or usdt_liquid_percentage is None:
                logger.error("Invalid trading parameters. Please check your configuration.")
                st.error("Invalid trading parameters. Please check your configuration.")
                return

            logger.info("Informing users about total fees and suggested profit margin.")
            st.sidebar.info("Please note that the total fees for buying and selling are 0.2%. It is recommended to set a profit margin higher than 0.2% to cover the fees.")

            logger.info("Saving user inputs to session state...")
            st.session_state.user_inputs = {
                'user_selected_symbols': user_selected_symbols,
                'profit_margin_percentage': profit_margin_percentage,
                'num_orders_per_trade': num_orders_per_trade,
                'usdt_liquid_percentage': usdt_liquid_percentage,
            }

            logger.info("Updating symbol allocations...")
            bot.update_allocations(user_selected_symbols)

            logger.info("Displaying trading controls...")
            start_button, stop_button = ui_manager.display_component('trading_controls')

            if start_button and not st.session_state.is_trading:
                logger.info("Starting trading...")
                st.session_state.is_trading = True
                st.session_state.stop_event, st.session_state.trading_task = initialize_trading_loop(
                    bot, user_selected_symbols, profit_margin_percentage, num_orders_per_trade
                )

            if st.session_state.is_trading:
                logger.info("Trading is in progress, updating charts and status...")
                chart_creator = ChartCreator(bot)
                chart_container = st.container()
                status_container = st.container()
                trade_messages_container = st.container()
                last_update_time = datetime.now() - timedelta(seconds=31)  # Ensure first update happens immediately

                try:
                    current_time = datetime.now()
                    if (current_time - last_update_time).total_seconds() >= 30:
                        logger.info("Updating charts and status...")
                        charts = chart_creator.create_charts()
                        ui_manager.display_component('chart_display', charts=charts, container=chart_container)

                        logger.info("Fetching current prices and updating status table...")
                        current_prices = config_manager.fetch_real_time_prices(user_selected_symbols)
                        current_status = bot.get_current_status(current_prices)
                        ui_manager.display_component('status_table', current_status=current_status, container=status_container)

                        logger.info("Displaying trade messages...")
                        ui_manager.display_component('trade_messages', container=trade_messages_container)

                        last_update_time = current_time

                except Exception as e:
                    logger.error(f"An error occurred in the main loop: {e}")
                    ui_manager.display_component('error_message', error_message=str(e), container=error_container)

            if stop_button or (not st.session_state.is_trading and st.session_state.stop_event):
                logger.info("Stopping trading...")
                st.session_state.is_trading = False
                if st.session_state.stop_event and st.session_state.trading_task:
                    stop_trading_loop(st.session_state.stop_event, st.session_state.trading_task)
                    st.session_state.stop_event = None
                    st.session_state.trading_task = None
                st.sidebar.success("Trading stopped.")
                chart_container.empty()

    except Exception as e:
        logger.error(f"An error occurred in the main function: {e}")
        ui_manager.display_component('error_message', error_message=str(e), container=error_container)

if __name__ == "__main__":
    main()
