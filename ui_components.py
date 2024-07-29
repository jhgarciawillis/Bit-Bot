import streamlit as st
from trading_bot import TradingBot
import pandas as pd

class SidebarConfig:
    def __init__(self):
        self.is_simulation = None
        self.simulated_usdt_balance = None

    def configure(self):
        st.sidebar.header("Configuration")

        # Simulation mode toggle
        self.is_simulation = st.sidebar.checkbox("Simulation Mode", value=True)

        if self.is_simulation:
            self.configure_simulation_mode()
        else:
            self.configure_live_mode()

        return (
            self.is_simulation,
            self.simulated_usdt_balance,
        )

    def configure_simulation_mode(self):
        st.sidebar.write("Running in simulation mode. No real trades will be executed.")
        self.simulated_usdt_balance = st.sidebar.number_input(
            f"Simulated USDT Balance",
            key=f"simulated_usdt_balance",
            min_value=0.0,
            value=1000.0,
            step=0.1
        )

    def configure_live_mode(self):
        st.sidebar.warning("WARNING: This bot will use real funds on the live KuCoin exchange.")
        st.sidebar.warning("Only proceed if you understand the risks and are using funds you can afford to lose.")
        proceed = st.sidebar.checkbox("I understand the risks and want to proceed")
        if not proceed:
            st.sidebar.error("Please check the box to proceed with live trading.")
            self.is_simulation = True
            self.simulated_usdt_balance = None

class StatusTable:
    def __init__(self, status_table, bot: TradingBot, chosen_symbols):
        self.status_table = status_table
        self.bot = bot
        self.chosen_symbols = chosen_symbols

    def display(self, current_status):
        status_df = self.create_status_dataframe(current_status)
        self.status_table.table(status_df)

    def create_status_dataframe(self, current_status):
        status_df = self.create_symbol_status_dataframe(current_status)
        status_df = self.add_summary_rows(status_df, current_status)
        return status_df

    def create_symbol_status_dataframe(self, current_status):
        data = {
            'Symbol': self.chosen_symbols,
            'Current Price': [self.format_price(current_status['prices'][symbol]) for symbol in self.chosen_symbols],
            'Buy Price': [self.format_buy_price(current_status['active_trades'], symbol) for symbol in self.chosen_symbols],
            'Target Sell Price': [self.format_target_sell_price(current_status['active_trades'], symbol) for symbol in self.chosen_symbols],
            'Current P/L': [self.format_current_pl(current_status['prices'], current_status['active_trades'], symbol) for symbol in self.chosen_symbols],
            'Active Trade': [self.format_active_trade(current_status['active_trades'], symbol) for symbol in self.chosen_symbols],
            'Realized Profit': [self.format_realized_profit(current_status['profits'], symbol) for symbol in self.chosen_symbols],
        }
        return pd.DataFrame(data)

    def add_summary_rows(self, status_df, current_status):
        summary_data = {
            'Symbol': ['Total', 'Current Total USDT', 'Tradable USDT', 'Liquid USDT'],
            'Current Price': ['', f"{current_status['current_total_usdt']:.4f}", f"{current_status['tradable_usdt']:.4f}", f"{current_status['liquid_usdt']:.4f}"],
            'Buy Price': ['', '', '', ''],
            'Target Sell Price': ['', '', '', ''],
            'Current P/L': ['', '', '', ''],
            'Active Trade': ['', '', '', ''],
            'Realized Profit': [f"{self.bot.total_profit:.4f}", '', '', ''],
        }
        summary_df = pd.DataFrame(summary_data)
        return pd.concat([status_df, summary_df], ignore_index=True)

    def format_price(self, price):
        return f"{price:.4f} USDT" if price is not None else "N/A"

    def format_buy_price(self, active_trades, symbol):
        buy_order = next((trade for trade in active_trades.values() if trade['symbol'] == symbol), None)
        return f"{buy_order['buy_price']:.4f} USDT" if buy_order else 'N/A'

    def format_target_sell_price(self, active_trades, symbol):
        buy_order = next((trade for trade in active_trades.values() if trade['symbol'] == symbol), None)
        return f"{buy_order['target_sell_price']:.4f} USDT" if buy_order else 'N/A'

    def format_current_pl(self, prices, active_trades, symbol):
        current_price = prices[symbol]
        buy_order = next((trade for trade in active_trades.values() if trade['symbol'] == symbol), current_price)
        if current_price is not None and buy_order:
            return f"{(current_price - buy_order['buy_price']) / buy_order['buy_price'] * 100:.2f}%"
        else:
            return 'N/A'

    def format_active_trade(self, active_trades, symbol):
        return 'Yes' if any(trade['symbol'] == symbol for trade in active_trades.values()) else 'No'

    def format_realized_profit(self, profits, symbol):
        return f"{profits.get(symbol, 0):.4f}"

class TradeMessages:
    def __init__(self, trade_messages):
        self.trade_messages = trade_messages

    def display(self):
        self.trade_messages.text("\n".join(st.session_state.trade_messages[-10:]))  # Display last 10 messages

class ErrorMessage:
    def __init__(self, error_placeholder):
        self.error_placeholder = error_placeholder

    def display(self):
        if st.session_state.error_message:
            self.error_placeholder.error(st.session_state.error_message)
            st.session_state.error_message = ""  # Clear the error message after displaying

def initialize_session_state():
    if 'trade_messages' not in st.session_state:
        st.session_state.trade_messages = []
    if 'error_message' not in st.session_state:
        st.session_state.error_message = ""
