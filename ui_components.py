import streamlit as st
from trading_bot import TradingBot
import pandas as pd
from typing import Dict, List, Tuple, Any, Optional
import logging
from config import verify_live_trading_access

logger = logging.getLogger(__name__)

class SidebarConfig:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def configure(self) -> Tuple[bool, Optional[float]]:
        st.sidebar.header("Configuration")

        is_simulation = st.sidebar.checkbox("Simulation Mode", value=self.config['simulation_mode']['enabled'])
        if is_simulation:
            st.sidebar.write("Running in simulation mode. No real trades will be executed.")
            simulated_usdt_balance = st.sidebar.number_input(
                "Simulated USDT Balance",
                min_value=0.0,
                value=self.config['simulation_mode']['initial_balance'],
                step=0.1
            )
            return is_simulation, simulated_usdt_balance
        else:
            st.sidebar.warning("WARNING: This bot will use real funds on the live KuCoin exchange.")
            st.sidebar.warning("Only proceed if you understand the risks and are using funds you can afford to lose.")
            proceed = st.sidebar.checkbox("I understand the risks and want to proceed", key="proceed_checkbox")
            if not proceed:
                st.sidebar.error("Please check the box to proceed with live trading.")
                return None, None
            return is_simulation, None

class StatusTable:
    def __init__(self, status_container: st.container, bot: TradingBot, chosen_symbols: List[str]):
        self.status_container = status_container
        self.bot = bot
        self.chosen_symbols = chosen_symbols

    def display(self, current_status: Dict[str, Any]) -> None:
        status_df = self.create_status_dataframe(current_status)
        with self.status_container:
            st.dataframe(status_df, use_container_width=True)

    def create_status_dataframe(self, current_status: Dict[str, Any]) -> pd.DataFrame:
        status_df = self.create_symbol_status_dataframe(current_status)
        status_df = self.add_summary_rows(status_df, current_status)
        return status_df

    def create_symbol_status_dataframe(self, current_status: Dict[str, Any]) -> pd.DataFrame:
        data = {
            'Symbol': self.chosen_symbols,
            'Current Price': [self.format_price(current_status['prices'].get(symbol, None)) for symbol in self.chosen_symbols],
            'Buy Price': [self.format_buy_price(current_status['active_trades'], symbol) for symbol in self.chosen_symbols],
            'Target Sell Price': [self.format_target_sell_price(current_status['active_trades'], symbol) for symbol in self.chosen_symbols],
            'Current P/L': [self.format_current_pl(current_status['prices'], current_status['active_trades'], symbol) for symbol in self.chosen_symbols],
            'Active Trade': [self.format_active_trade(current_status['active_trades'], symbol) for symbol in self.chosen_symbols],
            'Realized Profit': [self.format_realized_profit(current_status['profits'], symbol) for symbol in self.chosen_symbols],
        }
        return pd.DataFrame(data)

    def add_summary_rows(self, status_df: pd.DataFrame, current_status: Dict[str, Any]) -> pd.DataFrame:
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

    @staticmethod
    def format_price(price: Optional[float]) -> str:
        return f"{price:.4f} USDT" if price is not None else "N/A"

    @staticmethod
    def format_buy_price(active_trades: Dict[str, Dict[str, Any]], symbol: str) -> str:
        buy_order = next((trade for trade in active_trades.values() if trade['symbol'] == symbol), None)
        return f"{buy_order['buy_price']:.4f} USDT" if buy_order else 'N/A'

    def format_target_sell_price(self, active_trades: Dict[str, Dict[str, Any]], symbol: str) -> str:
        buy_order = next((trade for trade in active_trades.values() if trade['symbol'] == symbol), None)
        return f"{buy_order['buy_price'] * (1 + self.bot.profits[symbol]):.4f} USDT" if buy_order else 'N/A'

    @staticmethod
    def format_current_pl(prices: Dict[str, float], active_trades: Dict[str, Dict[str, Any]], symbol: str) -> str:
        current_price = prices.get(symbol, None)
        buy_order = next((trade for trade in active_trades.values() if trade['symbol'] == symbol), None)
        if current_price is not None and buy_order and buy_order['buy_price'] != 0:
            return f"{(current_price - buy_order['buy_price']) / buy_order['buy_price'] * 100:.2f}%"
        else:
            return 'N/A'

    @staticmethod
    def format_active_trade(active_trades: Dict[str, Dict[str, Any]], symbol: str) -> str:
        return 'Yes' if any(trade['symbol'] == symbol for trade in active_trades.values()) else 'No'

    @staticmethod
    def format_realized_profit(profits: Dict[str, float], symbol: str) -> str:
        return f"{profits.get(symbol, 0):.4f}"

class TradeMessages:
    def __init__(self, trade_messages_container: st.container):
        self.trade_messages_container = trade_messages_container

    def display(self) -> None:
        with self.trade_messages_container:
            st.text("\n".join(st.session_state.trade_messages[-10:]))  # Display last 10 messages

class ErrorMessage:
    def __init__(self, error_container: st.container):
        self.error_container = error_container

    def display(self) -> None:
        with self.error_container:
            if 'error_message' in st.session_state and st.session_state.error_message:
                st.error(st.session_state.error_message)
                st.session_state.error_message = ""  # Clear the error message after displaying

def initialize_session_state() -> None:
    if 'trade_messages' not in st.session_state:
        st.session_state.trade_messages = []
    if 'error_message' not in st.session_state:
        st.session_state.error_message = ""

class TradingControls:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def display(self) -> Tuple[bool, bool]:
        col1, col2 = st.sidebar.columns(2)
        start_button = col1.button("Start Trading")
        stop_button = col2.button("Stop Trading")
        return start_button, stop_button

class SymbolSelector:
    def __init__(self, available_symbols: List[str], default_symbols: List[str]):
        self.available_symbols = available_symbols
        self.default_symbols = default_symbols

    def display(self) -> List[str]:
        return st.sidebar.multiselect("Select Symbols to Trade", self.available_symbols, default=self.default_symbols)

class TradingParameters:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def display(self) -> Tuple[float, float, int]:
        usdt_liquid_percentage = st.sidebar.number_input(
            "Enter the percentage of your assets to keep liquid in USDT (0-100%)",
            min_value=0.0,
            max_value=100.0,
            value=self.config['default_usdt_liquid_percentage'] * 100,
            step=0.0001,
            format="%.4f"
        ) / 100

        profit_margin_percentage = st.sidebar.number_input(
            "Profit Margin Percentage (0-100%)",
            min_value=0.0001,
            max_value=100.0,
            value=self.config['default_profit_margin'] * 100,
            step=0.0001,
            format="%.4f"
        ) / 100

        num_orders_per_trade = st.sidebar.slider(
            "Number of Orders",
            min_value=1,
            max_value=10,
            value=self.config['default_num_orders'],
            step=1
        )

        return usdt_liquid_percentage, profit_margin_percentage, num_orders_per_trade

class ChartDisplay:
    def __init__(self, chart_container: st.container):
        self.chart_container = chart_container

    def display(self, charts: Dict[str, Any]) -> None:
        with self.chart_container:
            for symbol, chart in charts['individual_price_charts'].items():
                st.plotly_chart(chart, use_container_width=True)
            st.plotly_chart(charts['total_profit'], use_container_width=True)

class SimulationIndicator:
    def __init__(self, is_simulation: bool):
        self.is_simulation = is_simulation

    def display(self) -> None:
        if self.is_simulation:
            st.sidebar.warning("Running in Simulation Mode")
        else:
            st.sidebar.success("Running in Live Trading Mode")

class WalletBalance:
    def __init__(self, bot: TradingBot):
        self.bot = bot

    def display(self) -> None:
        trading_account_balance = self.bot.get_account_balance('USDT')
        st.sidebar.info(f"Trading Account Balance: {trading_account_balance:.2f} USDT")

class LiveTradingVerification:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def verify(self) -> bool:
        live_trading_key = st.sidebar.text_input("Enter live trading access key", type="password")
        if verify_live_trading_access(live_trading_key):
            st.sidebar.success("Live trading access key verified.")
            return True
        else:
            st.sidebar.error("Invalid live trading access key. Please try again.")
            return False
