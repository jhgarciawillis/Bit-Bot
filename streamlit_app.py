import streamlit as st
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from trading_bot import TradingBot
from chart_utils import ChartCreator
from trading_loop import initialize_trading_loop, stop_trading_loop
from ui_components import StatusTable, TradeMessages, ErrorMessage, initialize_session_state, SidebarConfig, SymbolSelector, TradingParameters, TradingControls
from config import load_config, initialize_clients, get_available_trading_symbols, verify_live_trading_access
from wallet import Wallet

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def initialize_bot(config: Dict[str, Any], is_simulation: bool, simulated_usdt_balance: float = 0) -> TradingBot:
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

def save_chart(fig, filename):
    fig.write_image(filename)
    st.success(f"Chart saved as {filename}")

def display_trading_account_balance(bot: TradingBot):
    trading_account_balance = bot.get_account_balance('USDT')
    st.sidebar.info(f"Trading Account Balance: {trading_account_balance:.2f} USDT")

def main():
    st.set_page_config(layout="wide")
    st.title("Cryptocurrency Trading Bot")

    config = load_config()
    initialize_clients()
    initialize_session_state()

    if 'is_trading' not in st.session_state:
        st.session_state.is_trading = False
    if 'stop_event' not in st.session_state:
        st.session_state.stop_event = None
    if 'trading_thread' not in st.session_state:
        st.session_state.trading_thread = None
    if 'user_inputs' not in st.session_state:
        st.session_state.user_inputs = {}

    sidebar_config = SidebarConfig(config)
    is_simulation, simulated_usdt_balance = sidebar_config.configure()

    if is_simulation is not None:
        try:
            if not is_simulation:
                live_trading_key = st.sidebar.text_input("Enter live trading access key", type="password")
                if not verify_live_trading_access(live_trading_key):
                    st.sidebar.error("Invalid live trading access key. Please try again.")
                    return
                else:
                    bot = initialize_bot(config, is_simulation, simulated_usdt_balance)
                    display_trading_account_balance(bot)
            else:
                bot = initialize_bot(config, is_simulation, simulated_usdt_balance)
                display_trading_account_balance(bot)

            available_symbols = get_available_trading_symbols()
            if not available_symbols:
                st.warning("No available trading symbols found. Please check your KuCoin API connection.")
                return
            
            symbol_selector = SymbolSelector(available_symbols, config['default_trading_symbols'])
            user_selected_symbols = symbol_selector.display()

            trading_params = TradingParameters(config)
            usdt_liquid_percentage, profit_margin_percentage, num_orders_per_trade = trading_params.display()

            # Inform users about the total fees and suggest a higher profit margin
            st.sidebar.info("Please note that the total fees for buying and selling are 0.2%. It is recommended to set a profit margin higher than 0.2% to cover the fees.")

            # Save user inputs
            st.session_state.user_inputs = {
                'user_selected_symbols': user_selected_symbols,
                'usdt_liquid_percentage': usdt_liquid_percentage,
                'profit_margin_percentage': profit_margin_percentage,
                'num_orders_per_trade': num_orders_per_trade
            }

            bot.usdt_liquid_percentage = usdt_liquid_percentage

            if not user_selected_symbols:
                st.warning("Please select at least one symbol to trade.")
                return

            bot.symbol_allocations, tradable_usdt_amount = bot.get_user_allocations(user_selected_symbols, bot.get_account_balance('USDT'))
            if tradable_usdt_amount <= 0:
                st.warning("No USDT available for trading. Please adjust your liquid USDT percentage.")
                return

            st.sidebar.info(f"Tradable USDT Amount: {tradable_usdt_amount:.2f}")

            trading_controls = TradingControls(config)
            start_button, stop_button = trading_controls.display()

            chart_container = st.empty()
            table_container = st.empty()
            trade_messages = st.empty()
            error_placeholder = st.empty()

            if start_button and not st.session_state.is_trading:
                st.session_state.is_trading = True
                st.session_state.stop_event, st.session_state.trading_thread = initialize_trading_loop(
                    bot, user_selected_symbols, profit_margin_percentage, num_orders_per_trade
                )

            if st.session_state.is_trading:
                chart_creator = ChartCreator(bot)
                last_update_time = datetime.now() - timedelta(seconds=31)  # Ensure first update happens immediately

                try:
                    current_time = datetime.now()
                    if (current_time - last_update_time).total_seconds() >= 30:
                        with chart_container.container():
                            charts = chart_creator.create_charts()
                            price_chart = st.plotly_chart(charts['price_buy_target'], use_container_width=True)
                            profit_chart = st.plotly_chart(charts['total_profit'], use_container_width=True)

                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button('Save Price Chart'):
                                    save_chart(charts['price_buy_target'], 'price_chart.png')
                            with col2:
                                if st.button('Save Profit Chart'):
                                    save_chart(charts['total_profit'], 'profit_chart.png')

                        with table_container.container():
                            current_prices = bot.trading_client.get_current_prices(user_selected_symbols)
                            current_status = bot.get_current_status(current_prices)
                            StatusTable(table_container, bot, user_selected_symbols).display(current_status)

                        TradeMessages(trade_messages).display()

                        last_update_time = current_time

                except Exception as e:
                    logger.error(f"An error occurred in the main loop: {e}")
                    st.error(f"An error occurred: {e}")

            if stop_button or (not st.session_state.is_trading and st.session_state.stop_event):
                st.session_state.is_trading = False
                if st.session_state.stop_event and st.session_state.trading_thread:
                    stop_trading_loop(st.session_state.stop_event, st.session_state.trading_thread)
                    st.session_state.stop_event = None
                    st.session_state.trading_thread = None
                st.sidebar.success("Trading stopped.")
                chart_container.empty()
                table_container.empty()

        except Exception as e:
            logger.error(f"An error occurred during bot initialization: {e}")
            st.error(f"An error occurred during bot initialization: {e}")

    ErrorMessage(error_placeholder).display()

if __name__ == "__main__":
    main()
