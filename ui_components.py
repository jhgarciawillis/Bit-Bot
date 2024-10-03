import streamlit as st
import pandas as pd
from typing import Dict, List, Tuple, Any, Optional
import logging
from config import config_manager

logger = logging.getLogger(__name__)

class UIComponent:
    def display(self, *args, **kwargs):
        raise NotImplementedError("Subclasses must implement display method")

class SidebarConfig(UIComponent):
    def display(self) -> Tuple[bool, Optional[float]]:
        logger.info("Displaying sidebar configuration.")
        st.sidebar.header("Configuration")
        is_simulation = st.sidebar.checkbox("Simulation Mode", value=config_manager.get_config('simulation_mode')['enabled'], key='is_simulation')
        if is_simulation:
            logger.info("Simulation mode selected.")
            st.sidebar.write("Running in simulation mode. No real trades will be executed.")
            simulated_usdt_balance = st.sidebar.number_input(
                "Simulated USDT Balance",
                min_value=0.0,
                value=config_manager.get_config('simulation_mode')['initial_balance'],
                step=0.1,
                key='simulated_usdt_balance'
            )
            return is_simulation, simulated_usdt_balance
        else:
            logger.info("Live trading mode selected.")
            st.sidebar.warning("WARNING: This bot will use real funds on the live KuCoin exchange.")
            st.sidebar.warning("Only proceed if you understand the risks and are using funds you can afford to lose.")
            proceed = st.sidebar.checkbox("I understand the risks and want to proceed", key="proceed_checkbox")
            if not proceed:
                logger.info("User did not proceed with live trading.")
                st.sidebar.error("Please check the box to proceed with live trading.")
                return None, None
            return is_simulation, None

class StatusTable(UIComponent):
    def __init__(self, bot):
        self.bot = bot

    def display(self, current_status: Dict[str, Any]) -> None:
        if not current_status:
            logger.warning("No current status available.")
            st.warning("No current status available.")
            return
        logger.info("Displaying status table.")
        status_df = self._create_status_dataframe(current_status)
        st.dataframe(status_df, use_container_width=True)

    def _create_symbol_status_data(self, current_status: Dict[str, Any]) -> Dict[str, List[Any]]:
        logger.info("Creating symbol status data.")
        symbols = list(current_status['prices'].keys())
        return {
            'Symbol': symbols,
            'Current Price': [self._format_price(current_status['prices'].get(symbol)) for symbol in symbols],
            'Buy Price': [self._format_buy_price(current_status['active_trades'], symbol) for symbol in symbols],
            'Target Sell Price': [self._format_target_sell_price(current_status['active_trades'], symbol, self.bot.profit_margin) for symbol in symbols],
            'Current P/L': [self._format_current_pl(current_status['prices'], current_status['active_trades'], symbol) for symbol in symbols],
            'Realized Profit': [self._format_realized_profit(current_status['profits'], symbol) for symbol in symbols],
            'Active Orders': [current_status['active_orders'].get(symbol, 0) for symbol in symbols],
        }

    def _create_status_dataframe(self, current_status: Dict[str, Any]) -> pd.DataFrame:
        logger.info("Creating status dataframe.")
        symbol_data = self._create_symbol_status_data(current_status)
        summary_data = self._create_summary_data(current_status)
        return pd.concat([pd.DataFrame(symbol_data), pd.DataFrame(summary_data)], ignore_index=True)

    def _create_summary_data(self, current_status: Dict[str, Any]) -> Dict[str, List[Any]]:
        logger.info("Creating summary data.")
        total_current_value = current_status['current_total_usdt']
        total_buy_value = sum(
            trade['buy_price'] * trade['amount']
            for trade in current_status['active_trades'].values()
        )
        total_active_orders = sum(current_status['active_orders'].values())
        return {
            'Symbol': ['Total'],
            'Current Price': [f"{total_current_value:.4f} USDT"],
            'Buy Price': [f"{total_buy_value:.4f} USDT"],
            'Target Sell Price': [''],
            'Current P/L': [f"{(total_current_value - total_buy_value) / total_buy_value * 100:.2f}%" if total_buy_value > 0 else 'N/A'],
            'Realized Profit': [f"{current_status['total_profit']:.4f} USDT"],
            'Active Orders': [total_active_orders],
        }

    @staticmethod
    def _format_price(price: Optional[float]) -> str:
        return f"{price:.4f} USDT" if price is not None else "N/A"

    @staticmethod
    def _format_buy_price(active_trades: Dict[str, Dict[str, Any]], symbol: str) -> str:
        buy_order = next((trade for trade in active_trades.values() if trade['symbol'] == symbol), None)
        return f"{buy_order['buy_price']:.4f} USDT" if buy_order else 'N/A'

    @staticmethod
    def _format_target_sell_price(active_trades: Dict[str, Dict[str, Any]], symbol: str, profit_margin: float) -> str:
        buy_order = next((trade for trade in active_trades.values() if trade['symbol'] == symbol), None)
        if buy_order:
            target_sell_price = buy_order['buy_price'] * (1 + profit_margin)
            return f"{target_sell_price:.4f} USDT"
        return 'N/A'

    @staticmethod
    def _format_current_pl(prices: Dict[str, float], active_trades: Dict[str, Dict[str, Any]], symbol: str) -> str:
        current_price = prices.get(symbol)
        buy_order = next((trade for trade in active_trades.values() if trade['symbol'] == symbol), None)
        if current_price is not None and buy_order and buy_order['buy_price'] != 0:
            pl_percentage = (current_price - buy_order['buy_price']) / buy_order['buy_price'] * 100
            return f"{pl_percentage:.2f}%"
        return 'N/A'

    @staticmethod
    def _format_realized_profit(profits: Dict[str, float], symbol: str) -> str:
        return f"{profits.get(symbol, 0):.4f} USDT"

class TradeMessages(UIComponent):
    def display(self) -> None:
        logger.info("Displaying trade messages.")
        st.text("\n".join(st.session_state.trade_messages[-10:]))  # Display last 10 messages

class ErrorMessage(UIComponent):
    def display(self, *args, **kwargs) -> None:
        if 'error_message' in st.session_state and st.session_state.error_message:
            logger.error(f"Displaying error message: {st.session_state.error_message}")
            st.error(st.session_state.error_message)
            st.session_state.error_message = ""  # Clear the error message after displaying

class TradingControls(UIComponent):
    def display(self) -> Tuple[bool, bool]:
        logger.info("Displaying trading controls.")
        col1, col2 = st.sidebar.columns(2)
        start_button = col1.button("Start Trading")
        stop_button = col2.button("Stop Trading")
        return start_button, stop_button

class SymbolSelector(UIComponent):
    def display(self, available_symbols: List[str], default_symbols: List[str]) -> List[str]:
        logger.info("Displaying symbol selector.")
        return st.sidebar.multiselect("Select Symbols to Trade", available_symbols, default=default_symbols, key='selected_symbols')

class TradingParameters(UIComponent):
    def display(self) -> Tuple[float, float, int]:
        logger.info("Displaying trading parameters.")
        usdt_liquid_percentage = st.sidebar.number_input(
            "Enter the percentage of your assets to keep liquid in USDT (0-100%)",
            min_value=0.0,
            max_value=100.0,
            value=config_manager.get_config('usdt_liquid_percentage', 0.5) * 100,
            step=0.0001,
            format="%.4f",
            key='usdt_liquid_percentage'
        ) / 100

        profit_margin_percentage = st.sidebar.number_input(
            "Profit Margin Percentage (0-100%)",
            min_value=0.0001,
            max_value=100.0,
            value=config_manager.get_config('profit_margin', 0.01) * 100,
            step=0.0001,
            format="%.4f",
            key='profit_margin_percentage'
        ) / 100

        max_total_orders = st.sidebar.slider(
            "Maximum Total Orders",
            min_value=1,
            max_value=50,
            value=config_manager.get_config('max_total_orders', 10),
            step=1,
            key='max_total_orders'
        )

        return usdt_liquid_percentage, profit_margin_percentage, max_total_orders

class ChartDisplay(UIComponent):
    def display(self, charts: Dict[str, Any]) -> None:
        logger.info("Displaying charts.")
        for symbol, chart in charts['individual_price_charts'].items():
            st.plotly_chart(chart, use_container_width=True)
        st.plotly_chart(charts['total_profit'], use_container_width=True)

class SimulationIndicator(UIComponent):
    def display(self, is_simulation: bool) -> None:
        logger.info(f"Displaying simulation indicator: {is_simulation}")
        if is_simulation:
            st.sidebar.warning("Running in Simulation Mode")
        else:
            st.sidebar.success("Running in Live Trading Mode")

class WalletBalance(UIComponent):
    def __init__(self, bot):
        self.bot = bot

    def display(self) -> None:
        logger.info("Displaying wallet balance.")
        total_balance = self.bot.wallet.get_total_balance('USDT')
        liquid_usdt = self.bot.wallet.get_liquid_balance('USDT')
        trading_usdt = self.bot.wallet.get_tradable_balance('USDT')
        st.sidebar.info(f"Total Balance: {total_balance:.2f} USDT")
        st.sidebar.info(f"Liquid USDT: {liquid_usdt:.2f}")
        st.sidebar.info(f"Trading USDT: {trading_usdt:.2f}")

class LiveTradingVerification(UIComponent):
    def display(self) -> bool:
        logger.info("Displaying live trading verification.")
        live_trading_key = st.sidebar.text_input("Enter live trading access key", type="password")
        if config_manager.verify_live_trading_access(live_trading_key):
            logger.info("Live trading access key verified.")
            st.sidebar.success("Live trading access key verified.")
            return True
        else:
            logger.info("Invalid live trading access key.")
            st.sidebar.error("Invalid live trading access key. Please try again.")
            return False

class CurrencyAllocationDisplay(UIComponent):
    def display(self, allocations: Dict[str, float]) -> None:
        logger.info("Displaying currency allocations.")
        st.sidebar.subheader("Currency Allocations")
        for symbol, allocation in allocations.items():
            st.sidebar.text(f"{symbol}: {allocation*100:.2f}%")

def initialize_session_state() -> None:
    logger.info("Initializing session state.")
    if 'trade_messages' not in st.session_state:
        st.session_state.trade_messages = []
    if 'error_message' not in st.session_state:
        st.session_state.error_message = ""

class UIManager:
    def __init__(self, bot):
        self.bot = bot
        self.components = {
            'sidebar_config': SidebarConfig(),
            'status_table': StatusTable(bot),
            'trade_messages': TradeMessages(),
            'error_message': ErrorMessage(),
            'trading_controls': TradingControls(),
            'symbol_selector': SymbolSelector(),
            'trading_parameters': TradingParameters(),
            'chart_display': ChartDisplay(),
            'simulation_indicator': SimulationIndicator(),
            'wallet_balance': WalletBalance(bot),
            'live_trading_verification': LiveTradingVerification(),
            'currency_allocation_display': CurrencyAllocationDisplay(),
        }

    def display_component(self, component_name: str, *args, **kwargs):
        if component_name in self.components:
            logger.info(f"Displaying component: {component_name}")
            return self.components[component_name].display(*args, **kwargs)
        else:
            logger.error(f"Component '{component_name}' not found")
            st.error(f"UI component '{component_name}' not found")

    def initialize(self):
        logger.info("Initializing UIManager.")
        initialize_session_state()

    def update_bot(self, bot):
        logger.info("Updating bot in UIManager.")
        self.bot = bot
        self.components['status_table'] = StatusTable(bot)
        self.components['wallet_balance'] = WalletBalance(bot)
