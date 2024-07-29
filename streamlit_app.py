import streamlit as st
import time
import threading
from trading_bot import TradingBot
from chart_utils import ChartCreator
from trading_loop import trading_loop
from ui_components import (
    SidebarConfig,
    StatusTable,
    TradeMessages,
    ErrorMessage,
    initialize_session_state
)

# Hardcoded variables
DEFAULT_TRADING_SYMBOLS = ['BTC-USDT', 'ETH-USDT', 'XRP-USDT', 'ADA-USDT', 'DOT-USDT']
API_URL = "https://api.kucoin.com"

def get_available_trading_symbols(market_client):
    try:
        symbol_list = market_client.get_symbol_list()
        return [item['symbol'] for item in symbol_list if isinstance(item, dict) and 'symbol' in item and item['symbol'].endswith('-USDT')]
    except Exception as e:
        st.error(f"Error fetching symbol list: {e}")
        return DEFAULT_TRADING_SYMBOLS

def main():
    st.set_page_config(layout="wide")
    st.sidebar.title("Cryptocurrency Trading Bot")

    sidebar_config = SidebarConfig()
    config_result = sidebar_config.configure()
    if config_result is None:
        return
    is_simulation, simulated_usdt_balance = config_result

    chart_container = st.empty()
    table_container = st.empty()
    trade_messages = st.empty()
    error_placeholder = st.empty()

    initialize_session_state()

    if is_simulation:
        api_key = st.secrets["api_credentials"]["api_key"]
        api_secret = st.secrets["api_credentials"]["api_secret"]
        api_passphrase = st.secrets["api_credentials"]["api_passphrase"]
        bot = TradingBot(api_key, api_secret, api_passphrase, API_URL)
        bot.is_simulation = True
        bot.wallet.update_account_balance("trading", "USDT", simulated_usdt_balance)
        total_usdt_balance = simulated_usdt_balance
    else:
        user_api_key = st.sidebar.text_input("Enter your personal API key:", type="password")
        if user_api_key != st.secrets.get("perso_key", ""):
            st.sidebar.warning("Invalid API key. Please enter the correct key to proceed.")
            st.sidebar.markdown("**Start Trading** button is disabled until the correct API key is provided.")
            st.sidebar.button("Start Trading", disabled=True)
            api_key, api_secret, api_passphrase = None, None, None
            total_usdt_balance = 0.0
        else:
            st.sidebar.success("API key verified. You can now start trading.")
            api_key = st.secrets["api_credentials"]["api_key"]
            api_secret = st.secrets["api_credentials"]["api_secret"]
            api_passphrase = st.secrets["api_credentials"]["api_passphrase"]
            bot = TradingBot(api_key, api_secret, api_passphrase, API_URL)
            bot.initialize()
            total_usdt_balance = bot.get_account_balance('USDT')

    if 'bot' not in st.session_state:
        st.session_state.bot = bot

    st.sidebar.write(f"{'Simulated' if is_simulation else 'Confirmed'} USDT Balance: {total_usdt_balance:.4f}")

    available_trading_symbols = get_available_trading_symbols(bot.trading_client.market_client) if bot.trading_client.market_client else DEFAULT_TRADING_SYMBOLS
    user_selected_symbols = st.sidebar.multiselect("Select Symbols to Trade", available_trading_symbols)
    if not user_selected_symbols:
        st.warning("Please select at least one symbol to trade.")
        return
    
    bot.usdt_liquid_percentage = st.sidebar.number_input(
        "Enter the percentage of your assets to keep liquid in USDT (0-100%)",
        min_value=0.0,
        max_value=100.0,
        value=50.0,
        step=0.0001,
        format="%.4f"
    ) / 100

    bot.symbol_allocations, tradable_usdt_amount = bot.get_user_allocations(user_selected_symbols, total_usdt_balance)
    if tradable_usdt_amount <= 0:
        st.warning("No USDT available for trading. Please adjust your liquid USDT percentage.")
        return

    profit_margin_percentage = st.sidebar.number_input(
        "Profit Margin Percentage (0-100%)",
        min_value=0.0001,
        max_value=100.0,
        value=1.0,
        step=0.0001,
        format="%.4f"
    ) / 100
    num_orders_per_trade = st.sidebar.slider("Number of Orders", min_value=1, max_value=10, value=1, step=1)

    understand_checkbox = st.sidebar.checkbox("I understand the risks and want to proceed")

    if (user_api_key == st.secrets.get("perso_key", "") and understand_checkbox and api_key and api_secret and api_passphrase) or is_simulation:
        if st.sidebar.button("Start Trading"):
            trading_thread = threading.Thread(target=trading_loop, args=(bot, user_selected_symbols, profit_margin_percentage, num_orders_per_trade))
            trading_thread.start()

            chart_creator = ChartCreator(bot)
            charts = chart_creator.create_charts()

            while True:
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
    else:
        st.sidebar.warning("Invalid API key or checkbox not checked. Please enter the correct API key and check the checkbox to proceed.")
        st.sidebar.markdown("**Start Trading** button is disabled until the correct API key is provided and the checkbox is checked.")
        st.sidebar.button("Start Trading", disabled=True)

    ErrorMessage(error_placeholder).display()  # Display error message outside the loop

if __name__ == "__main__":
    main()
