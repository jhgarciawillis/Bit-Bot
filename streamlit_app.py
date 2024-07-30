import streamlit as st
import time
import threading
import signal
from trading_bot import TradingBot
from chart_utils import ChartCreator
from trading_loop import trading_loop
from ui_components import StatusTable, TradeMessages, ErrorMessage, initialize_session_state

# Hardcoded variables
DEFAULT_TRADING_SYMBOLS = ['BTC-USDT', 'ETH-USDT', 'XRP-USDT', 'ADA-USDT', 'DOT-USDT']
API_URL = "https://api.kucoin.com"

# Global flag to control the trading loop
stop_trading = threading.Event()

def get_available_trading_symbols(market_client):
    try:
        symbol_list = market_client.get_symbol_list()
        return [item['symbol'] for item in symbol_list if isinstance(item, dict) and 'symbol' in item and item['symbol'].endswith('-USDT')]
    except Exception as e:
        st.error(f"Error fetching symbol list: {e}")
        return DEFAULT_TRADING_SYMBOLS

def simulation_sidebar():
    st.sidebar.header("Simulation Mode")
    simulated_usdt_balance = st.sidebar.number_input(
        "Simulated USDT Balance",
        min_value=0.0,
        value=1000.0,
        step=0.1
    )
    return simulated_usdt_balance

def live_trading_sidebar():
    st.sidebar.header("Live Trading Mode")
    personal_key = st.sidebar.text_input("Enter your personal key:", type="password")
    
    if personal_key == "":
        st.sidebar.error("Personal key cannot be empty. Please enter your personal key to proceed.")
        return None, False
    
    correct_key = st.secrets.get("perso_key", "")
    if personal_key != correct_key or correct_key == "":
        st.sidebar.error("Invalid personal key. Please enter the correct key to proceed.")
        return None, False

    st.sidebar.success("Personal key verified. You can now configure live trading.")
    st.sidebar.warning("WARNING: This bot will use real funds on the live KuCoin exchange.")
    st.sidebar.warning("Only proceed if you understand the risks and are using funds you can afford to lose.")
    
    proceed = st.sidebar.checkbox("I understand the risks and want to proceed", key="proceed_checkbox")
    
    return personal_key, proceed

def common_sidebar_config(bot, available_trading_symbols):
    user_selected_symbols = st.sidebar.multiselect("Select Symbols to Trade", available_trading_symbols)
    
    bot.usdt_liquid_percentage = st.sidebar.number_input(
        "Enter the percentage of your assets to keep liquid in USDT (0-100%)",
        min_value=0.0,
        max_value=100.0,
        value=50.0,
        step=0.0001,
        format="%.4f"
    ) / 100

    profit_margin_percentage = st.sidebar.number_input(
        "Profit Margin Percentage (0-100%)",
        min_value=0.0001,
        max_value=100.0,
        value=1.0,
        step=0.0001,
        format="%.4f"
    ) / 100

    num_orders_per_trade = st.sidebar.slider("Number of Orders", min_value=1, max_value=10, value=1, step=1)

    return user_selected_symbols, profit_margin_percentage, num_orders_per_trade

def signal_handler(signum, frame):
    stop_trading.set()

def main():
    st.set_page_config(layout="wide")
    st.title("Cryptocurrency Trading Bot")

    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    mode = st.radio("Select Mode", ["Simulation", "Live Trading"])

    chart_container = st.empty()
    table_container = st.empty()
    trade_messages = st.empty()
    error_placeholder = st.empty()

    initialize_session_state()

    if mode == "Simulation":
        simulated_usdt_balance = simulation_sidebar()
        api_key = st.secrets["api_credentials"]["api_key"]
        api_secret = st.secrets["api_credentials"]["api_secret"]
        api_passphrase = st.secrets["api_credentials"]["api_passphrase"]
        bot = TradingBot(api_key, api_secret, api_passphrase, API_URL)
        bot.is_simulation = True
        bot.wallet.update_account_balance("trading", "USDT", simulated_usdt_balance)
        total_usdt_balance = simulated_usdt_balance
        proceed = True
    else:
        personal_key, proceed = live_trading_sidebar()
        if not proceed:
            return

        api_key = st.secrets["api_credentials"]["api_key"]
        api_secret = st.secrets["api_credentials"]["api_secret"]
        api_passphrase = st.secrets["api_credentials"]["api_passphrase"]
        bot = TradingBot(api_key, api_secret, api_passphrase, API_URL)
        bot.initialize()
        total_usdt_balance = bot.get_account_balance('USDT')

    if 'bot' not in st.session_state:
        st.session_state.bot = bot

    if proceed:
        st.sidebar.write(f"{'Simulated' if mode == 'Simulation' else 'Confirmed'} USDT Balance: {total_usdt_balance:.4f}")

        available_trading_symbols = get_available_trading_symbols(bot.trading_client.market_client) if bot.trading_client.market_client else DEFAULT_TRADING_SYMBOLS
        user_selected_symbols, profit_margin_percentage, num_orders_per_trade = common_sidebar_config(bot, available_trading_symbols)

        if not user_selected_symbols:
            st.warning("Please select at least one symbol to trade.")
            return

        bot.symbol_allocations, tradable_usdt_amount = bot.get_user_allocations(user_selected_symbols, total_usdt_balance)
        if tradable_usdt_amount <= 0:
            st.warning("No USDT available for trading. Please adjust your liquid USDT percentage.")
            return

        col1, col2 = st.sidebar.columns(2)
        start_button = col1.button("Start Trading")
        stop_button = col2.button("Stop Trading")

        if start_button:
            stop_trading.clear()
            trading_thread = threading.Thread(target=trading_loop, args=(bot, user_selected_symbols, profit_margin_percentage, num_orders_per_trade, stop_trading))
            trading_thread.start()

            chart_creator = ChartCreator(bot)
            charts = chart_creator.create_charts()

            while not stop_trading.is_set():
                try:
                    # Display the updated charts
                    with chart_container.container():
                        st.plotly_chart(charts, use_container_width=True)

                    # Display the updated table
                    with table_container.container():
                        current_prices = bot.trading_client.get_current_prices(user_selected_symbols)
                        current_status = bot.get_current_status(current_prices)
                        StatusTable(table_container, bot, user_selected_symbols).display(current_status)

                    TradeMessages(trade_messages).display()

                    time.sleep(1)
                except Exception as e:
                    st.error(f"An error occurred in the main loop: {e}")
                    time.sleep(5)

        if stop_button:
            stop_trading.set()
            st.sidebar.success("Trading stopped.")

    else:
        st.sidebar.warning("Please enter the correct personal key and check the checkbox to proceed with live trading.")
        st.sidebar.button("Start Trading", disabled=True)

    ErrorMessage(error_placeholder).display()  # Display error message outside the loop

if __name__ == "__main__":
    main()
