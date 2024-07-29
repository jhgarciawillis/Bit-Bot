import streamlit as st
import pandas as pd
from trading_bot import TradingBot

def configure_sidebar():
    st.sidebar.header("Configuration")

    # Simulation mode toggle
    is_simulation = st.sidebar.checkbox("Simulation Mode", value=True)

    if is_simulation:
        st.sidebar.write("Running in simulation mode. No real trades will be executed.")
        api_key = "simulation"
        api_secret = "simulation"
        api_passphrase = "simulation"
        api_url = "https://api.kucoin.com"  # You can use the real URL even for simulation
    else:
        st.sidebar.warning("WARNING: This bot will use real funds on the live KuCoin exchange.")
        st.sidebar.warning("Only proceed if you understand the risks and are using funds you can afford to lose.")
        proceed = st.sidebar.checkbox("I understand the risks and want to proceed")
        if not proceed:
            st.sidebar.error("Please check the box to proceed with live trading.")
            return None, None, None, None, None

        # Use secrets for API credentials in live mode
        api_key = st.secrets["api_credentials"]["api_key"]
        api_secret = st.secrets["api_credentials"]["api_secret"]
        api_passphrase = st.secrets["api_credentials"]["api_passphrase"]
        api_url = "https://api.kucoin.com"

    bot = TradingBot(api_key, api_secret, api_passphrase, api_url)
    bot.print_total_usdt_balance()

    return api_key, api_secret, api_passphrase, api_url, is_simulation

def initialize_session_state():
    if 'trade_messages' not in st.session_state:
        st.session_state.trade_messages = []
    if 'error_message' not in st.session_state:
        st.session_state.error_message = ""

def display_status_table(status_table, current_status, bot, chosen_symbols):
    status_df = pd.DataFrame({
        'Symbol': chosen_symbols,
        'Current Price': [f"{current_status['prices'][symbol]:.4f}" if current_status['prices'][symbol] is not None else "N/A" for symbol in chosen_symbols],
        'Buy Price': [f"{next((trade['buy_price'] for trade in current_status['active_trades'].values() if trade['symbol'] == symbol), None):.4f}" if any(trade['symbol'] == symbol for trade in current_status['active_trades'].values()) else 'N/A' for symbol in chosen_symbols],
        'Target Sell Price': [f"{next((trade['target_sell_price'] for trade in current_status['active_trades'].values() if trade['symbol'] == symbol), None):.4f}" if any(trade['symbol'] == symbol for trade in current_status['active_trades'].values()) else 'N/A' for symbol in chosen_symbols],
        'Current P/L': [f"{(current_status['prices'][symbol] - next((trade['buy_price'] for trade in current_status['active_trades'].values() if trade['symbol'] == symbol), current_status['prices'][symbol])) / next((trade['buy_price'] for trade in current_status['active_trades'].values() if trade['symbol'] == symbol), current_status['prices'][symbol]) * 100:.2f}%" if current_status['prices'][symbol] is not None and any(trade['symbol'] == symbol for trade in current_status['active_trades'].values()) else 'N/A' for symbol in chosen_symbols],
        'Active Trade': ['Yes' if any(trade['symbol'] == symbol for trade in current_status['active_trades'].values()) else 'No' for symbol in chosen_symbols],
        'Realized Profit': [f"{current_status['profits'].get(symbol, 0):.4f}" for symbol in chosen_symbols]
    })
    status_df = pd.concat([status_df, pd.DataFrame({
        'Symbol': ['Total', 'Current Total USDT', 'Tradable USDT', 'Liquid USDT'],
        'Current Price': ['', f"{current_status['current_total_usdt']:.4f}", f"{current_status['tradable_usdt']:.4f}", f"{current_status['liquid_usdt']:.4f}"],
        'Buy Price': ['', '', '', ''],
        'Target Sell Price': ['', '', '', ''],
        'Current P/L': ['', '', '', ''],
        'Active Trade': ['', '', '', ''],
        'Realized Profit': [f"{bot.total_profit:.4f}", '', '', '']
    })], ignore_index=True)

    status_table.table(status_df)

def display_trade_messages(trade_messages):
    trade_messages.text("\n".join(st.session_state.trade_messages[-10:]))  # Display last 10 messages

def display_error_message(error_placeholder):
    if st.session_state.error_message:
        error_placeholder.error(st.session_state.error_message)
        st.session_state.error_message = ""  # Clear the error message after displaying
