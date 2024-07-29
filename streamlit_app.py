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

def main():
    st.set_page_config(layout="wide")
    st.title("Cryptocurrency Trading Bot")

    sidebar_config = SidebarConfig()
    config_result = sidebar_config.configure()
    
    if config_result is None:
        return  # Exit if the user didn't confirm for live trading
    
    is_simulation, simulated_usdt_balance = config_result

    api_key = st.secrets["api_credentials"]["api_key"]
    api_secret = st.secrets["api_credentials"]["api_secret"]
    api_passphrase = st.secrets["api_credentials"]["api_passphrase"]
    api_url = "https://api.kucoin.com"

    if 'bot' not in st.session_state:
        st.session_state.bot = TradingBot(api_key, api_secret, api_passphrase, api_url)

    bot = st.session_state.bot
    bot.is_simulation = is_simulation

    if is_simulation:
        bot.wallet.update_account_balance("trading", "USDT", simulated_usdt_balance)
    
    bot.initialize()
    total_usdt_balance = bot.get_account_balance('USDT')
    st.sidebar.write(f"{'Simulated' if is_simulation else 'Confirmed'} USDT Balance: {total_usdt_balance:.4f}")

    # Get user inputs
    if bot.trading_client.market_client is not None:
        try:
            symbol_list = bot.trading_client.market_client.get_symbol_list()
            available_trading_symbols = [item['symbol'] for item in symbol_list if isinstance(item, dict) and 'symbol' in item]
        except Exception as e:
            st.error(f"Error fetching symbol list: {e}")
            available_trading_symbols = ['BTC-USDT', 'ETH-USDT', 'XRP-USDT', 'ADA-USDT', 'DOT-USDT']
    else:
        available_trading_symbols = ['BTC-USDT', 'ETH-USDT', 'XRP-USDT', 'ADA-USDT', 'DOT-USDT']

    # Filter out non-USDT trading pairs
    available_trading_symbols = [symbol for symbol in available_trading_symbols if symbol.endswith('-USDT')]
    
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

    # Get user input for profit margin and number of orders
    profit_margin_percentage = st.sidebar.number_input(
        "Profit Margin Percentage (0-100%)",
        min_value=0.0001,
        max_value=100.0,
        value=1.0,
        step=0.0001,
        format="%.4f"
    ) / 100
    num_orders_per_trade = st.sidebar.slider("Number of Orders", min_value=1, max_value=10, value=1, step=1)

    # Chart type selection
    selected_chart_type = st.selectbox("Select chart type", ['Price', 'Buy Prices', 'Target Sell Prices', 'Total Profits'])

    # Create placeholders for chart, status table, and error messages
    chart_placeholder = st.empty()
    status_table = st.empty()
    trade_messages = st.empty()
    error_placeholder = st.empty()

    initialize_session_state()

    # Main trading loop
    if st.sidebar.button("Start Trading"):
        trading_thread = threading.Thread(target=trading_loop, args=(bot, user_selected_symbols, profit_margin_percentage, num_orders_per_trade))
        trading_thread.start()

        chart_creator = ChartCreator(bot)
        while True:
            try:
                # Update chart
                fig = chart_creator.create_time_series_chart(user_selected_symbols, selected_chart_type)
                chart_placeholder.plotly_chart(fig, use_container_width=True)

                # Update status table
                current_prices = bot.trading_client.get_current_prices(user_selected_symbols)
                current_status = bot.get_current_status(current_prices)
                status_table_component = StatusTable(status_table, bot, user_selected_symbols)
                status_table_component.display(current_status)

                # Display trade messages
                trade_messages_component = TradeMessages(trade_messages)
                trade_messages_component.display()

                # Display error message if any
                error_message_component = ErrorMessage(error_placeholder)
                error_message_component.display()

                time.sleep(1)  # Update every second
            except Exception as e:
                st.error(f"An error occurred in the main loop: {e}")
                time.sleep(5)  # Wait for 5 seconds before retrying

if __name__ == "__main__":
    main()
