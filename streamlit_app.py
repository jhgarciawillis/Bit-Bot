import streamlit as st
import time
import threading
import logging
from datetime import datetime
from typing import Dict, Any
from trading_bot import TradingBot
from chart_utils import ChartCreator
from trading_loop import initialize_trading_loop, stop_trading_loop
from ui_components import StatusTable, TradeMessages, ErrorMessage, initialize_session_state, SidebarConfig, SymbolSelector, TradingParameters, TradingControls
from config import load_config, initialize_clients, get_available_trading_symbols, verify_live_trading_access

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def initialize_bot(config: Dict[str, Any], is_simulation: bool, simulated_usdt_balance: float = 0) -> TradingBot:
    """
    Initialize the TradingBot with the given configuration.
    
    :param config: Configuration dictionary
    :param is_simulation: Boolean indicating if it's a simulation
    :param simulated_usdt_balance: Simulated USDT balance for simulation mode
    :return: Initialized TradingBot instance
    """
    api_key = config['api_key']
    api_secret = config['api_secret']
    api_passphrase = config['api_passphrase']
    
    bot = TradingBot(api_key, api_secret, api_passphrase, config['bot_config']['update_interval'])
    bot.is_simulation = is_simulation
    
    if is_simulation:
        bot.wallet.update_account_balance("trading", "USDT", simulated_usdt_balance)
    else:
        bot.initialize()
    
    return bot

def main():
    st.set_page_config(layout="wide")
    st.title("Cryptocurrency Trading Bot")

    # Load configuration
    config = load_config()

    # Initialize clients
    initialize_clients()

    # Initialize session state
    initialize_session_state()

    # Sidebar configuration
    sidebar_config = SidebarConfig(config)
    is_simulation, simulated_usdt_balance = sidebar_config.configure()

    if is_simulation is not None:
        try:
            # Live trading access check
            if not is_simulation:
                live_trading_key = st.sidebar.text_input("Enter live trading access key", type="password")
                if not verify_live_trading_access(live_trading_key):
                    st.sidebar.error("Invalid live trading access key. Please try again.")
                    return

            # Initialize bot
            bot = initialize_bot(config, is_simulation, simulated_usdt_balance)

            # Symbol selection
            available_symbols = get_available_trading_symbols()
            symbol_selector = SymbolSelector(available_symbols, config['default_trading_symbols'])
            user_selected_symbols = symbol_selector.display()

            # Trading parameters
            trading_params = TradingParameters(config)
            usdt_liquid_percentage, profit_margin_percentage, num_orders_per_trade = trading_params.display()

            # Update bot parameters
            bot.usdt_liquid_percentage = usdt_liquid_percentage

            if not user_selected_symbols:
                st.warning("Please select at least one symbol to trade.")
                return

            bot.symbol_allocations, tradable_usdt_amount = bot.get_user_allocations(user_selected_symbols, bot.get_account_balance('USDT'))
            if tradable_usdt_amount <= 0:
                st.warning("No USDT available for trading. Please adjust your liquid USDT percentage.")
                return

            # Trading controls
            trading_controls = TradingControls(config)
            start_button, stop_button = trading_controls.display()

            # Main display containers
            chart_container = st.empty()
            table_container = st.empty()
            trade_messages = st.empty()
            error_placeholder = st.empty()

            # Trading loop
            if start_button:
                stop_event, trading_thread = initialize_trading_loop(bot, user_selected_symbols, profit_margin_percentage, num_orders_per_trade)

                chart_creator = ChartCreator(bot)
                start_time = datetime.now()

                while not stop_event.is_set():
                    try:
                        # Create and display the updated charts
                        with chart_container.container():
                            charts = chart_creator.create_charts()
                            st.plotly_chart(charts['price_buy_target'], use_container_width=True)
                            st.plotly_chart(charts['total_profit'], use_container_width=True)

                        # Display the updated table
                        with table_container.container():
                            current_prices = bot.trading_client.get_current_prices(user_selected_symbols)
                            current_status = bot.get_current_status(current_prices)
                            StatusTable(table_container, bot, user_selected_symbols).display(current_status)

                        TradeMessages(trade_messages).display()

                        time.sleep(config['chart_config']['update_interval'])
                    except Exception as e:
                        logger.error(f"An error occurred in the main loop: {e}")
                        st.error(f"An error occurred: {e}")
                        time.sleep(config['error_config']['retry_delay'])

            if stop_button:
                if 'stop_event' in locals() and 'trading_thread' in locals():
                    stop_trading_loop(stop_event, trading_thread)
                st.sidebar.success("Trading stopped.")

        except Exception as e:
            logger.error(f"An error occurred during bot initialization: {e}")
            st.error(f"An error occurred during bot initialization: {e}")

    ErrorMessage(error_placeholder).display()

if __name__ == "__main__":
    main()
