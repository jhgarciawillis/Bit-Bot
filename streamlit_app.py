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
    (
        is_simulation,
        simulated_usdt_balance,
    ) = sidebar_config.configure()

    api_key = st.secrets["api_credentials"]["api_key"]
    api_secret = st.secrets["api_credentials"]["api_secret"]
    api_passphrase = st.secrets["api_credentials"]["api_passphrase"]
    api_url = "https://api.kucoin.com"

    bot = TradingBot(api_key, api_secret, api_passphrase, api_url)
    if is_simulation:
        bot.is_simulation = True
        bot.simulated_usdt_balance = {'USDT': simulated_usdt_balance}

    if 'bot' not in st.session_state:
        st.session_state.bot = bot

    if not is_simulation:
        total_usdt = bot.get_account_balance('USDT')
        st.sidebar.write(f"Confirmed USDT Balance: {total_usdt:.2f}")
    else:
        total_usdt = bot.simulated_usdt_balance['USDT']

    # Get user inputs
    if bot.trading_client.market_client is not None:
        available_symbols = bot.trading_client.market_client.get_symbol_list()
    else:
        available_symbols = ['BTC-USDT', 'ETH-USDT', 'XRP-USDT', 'ADA-USDT', 'DOT-USDT']
    
    chosen_symbols = st.sidebar.multiselect("Select Symbols to Trade", available_symbols)

    if not chosen_symbols:
        st.warning("Please select at least one symbol to trade.")
        return
    
    bot.symbol_allocations, tradable_usdt = bot.get_user_allocations(chosen_symbols, total_usdt)
    if tradable_usdt <= 0:
        st.warning("No USDT available for trading. Please adjust your liquid USDT percentage.")
        return

    # Get user input for profit margin and number of orders
    profit_margin = st.sidebar.number_input(
        "Profit Margin Percentage (0-100%)",
        min_value=0.0001,
        max_value=100.0,
        value=1.0,
        step=0.0001,
        format="%.4f"
    ) / 100
    num_orders = st.sidebar.slider("Number of Orders", min_value=1, max_value=10, value=1, step=1)

    # Chart type selection
    chart_type = st.selectbox("Select chart type", ['Price', 'Buy Prices', 'Target Sell Prices', 'Total Profits'])

    # Create placeholders for chart, status table, and error messages
    chart_placeholder = st.empty()
    status_table = st.empty()
    trade_messages = st.empty()
    error_placeholder = st.empty()

    initialize_session_state()

    # Main trading loop
    if st.sidebar.button("Start Trading"):
        trading_thread = threading.Thread(target=trading_loop, args=(bot, chosen_symbols, profit_margin, num_orders))
        trading_thread.start()

        chart_creator = ChartCreator(bot)
        while True:
            # Update chart
            fig = chart_creator.create_time_series_chart(chosen_symbols, chart_type)
            chart_placeholder.plotly_chart(fig, use_container_width=True)

            # Update status table
            current_status = bot.get_current_status(bot.get_current_prices(chosen_symbols))
            status_table_component = StatusTable(status_table, bot, chosen_symbols)
            status_table_component.display(current_status)

            # Display trade messages
            trade_messages_component = TradeMessages(trade_messages)
            trade_messages_component.display()

            # Display error message if any
            error_message_component = ErrorMessage(error_placeholder)
            error_message_component.display()

            time.sleep(1)  # Update every second

if __name__ == "__main__":
    main()
