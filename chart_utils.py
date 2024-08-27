import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional
import logging
from config import config_manager

logger = logging.getLogger(__name__)

def handle_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"An error occurred in {func.__name__}: {str(e)}")
            raise
    return wrapper

class Chart:
    def __init__(self, title: str, x_title: str, y_title: str):
        self.fig = go.Figure()
        self.update_layout(title, x_title, y_title)

    def update_layout(self, title: str, x_title: str, y_title: str):
        self.fig.update_layout(
            title=title,
            xaxis_title=x_title,
            yaxis_title=y_title,
            height=config_manager.get_config('chart_config')['height'],
            width=config_manager.get_config('chart_config')['width'],
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
        )

    def add_line_trace(self, x: List[Any], y: List[Any], name: str):
        self.fig.add_trace(go.Scatter(x=x, y=y, mode='lines', name=name))

    def add_marker_trace(self, x: List[Any], y: List[Any], name: str, marker_symbol: str, marker_size: int, marker_color: str):
        self.fig.add_trace(go.Scatter(
            x=x, y=y, mode='markers', name=name,
            marker=dict(symbol=marker_symbol, size=marker_size, color=marker_color)
        ))

    def add_horizontal_line(self, y: float, line_dash: str, annotation_text: str, line_color: str):
        self.fig.add_hline(y=y, line_dash=line_dash, annotation_text=annotation_text, line_color=line_color)

    @handle_errors
    def save(self, filename: str):
        self.fig.write_image(filename)
        logger.info(f"Chart saved as {filename}")

class PriceChart(Chart):
    def __init__(self, symbol: str):
        super().__init__(f'{symbol} Price Chart', 'Timestamp', 'Price (USDT)')
        self.symbol = symbol

    def add_price_data(self, timestamps: List[datetime], prices: List[float]):
        self.add_line_trace(timestamps, prices, f'{self.symbol} Price')

    def add_buy_signals(self, buy_timestamps: List[datetime], buy_signals: List[float]):
        self.add_marker_trace(buy_timestamps, buy_signals, f'{self.symbol} Buy Signal', 'triangle-up', 10, 'green')

    def add_sell_signals(self, sell_timestamps: List[datetime], sell_signals: List[float]):
        self.add_marker_trace(sell_timestamps, sell_signals, f'{self.symbol} Sell Signal', 'triangle-down', 10, 'red')

    def add_trade_lines(self, buy_price: Optional[float], target_sell_price: Optional[float]):
        if buy_price is not None and target_sell_price is not None:
            self.add_horizontal_line(buy_price, "dash", "Buy Price", "blue")
            self.add_horizontal_line(target_sell_price, "dot", "Target Sell Price", "red")

class ProfitChart(Chart):
    def __init__(self):
        super().__init__('Total Profit Over Time', 'Timestamp', 'Total Profit (USDT)')

    def add_profit_data(self, timestamps: List[datetime], total_profits: List[float]):
        self.add_line_trace(timestamps, total_profits, 'Total Profit')

class BalanceChart(Chart):
    def __init__(self):
        super().__init__('Balance Over Time', 'Timestamp', 'Balance (USDT)')

    def add_balance_data(self, timestamps: List[datetime], liquid_balances: List[float], trading_balances: List[float]):
        self.add_line_trace(timestamps, liquid_balances, 'Liquid Balance')
        self.add_line_trace(timestamps, trading_balances, 'Trading Balance')

class ChartCreator:
    def __init__(self, bot):
        self.bot = bot

    @handle_errors
    def create_charts(self) -> Dict[str, Any]:
        return {
            'individual_price_charts': self.create_individual_price_charts(),
            'total_profit': self.create_total_profit_chart(),
            'balance': self.create_balance_chart()
        }

    def create_individual_price_charts(self) -> Dict[str, go.Figure]:
        return {symbol: self.create_single_price_chart(symbol) for symbol in self.bot.symbol_allocations}

    def create_single_price_chart(self, symbol: str) -> go.Figure:
        price_data = self.bot.price_history.get(symbol, [])
        timestamps, prices = self.extract_price_data(price_data)
        
        chart = PriceChart(symbol)
        chart.add_price_data(timestamps, prices)
        
        buy_timestamps, buy_signals = self.get_buy_signals(symbol, price_data)
        chart.add_buy_signals(buy_timestamps, buy_signals)
        
        sell_timestamps, sell_signals = self.get_sell_signals(symbol, price_data)
        chart.add_sell_signals(sell_timestamps, sell_signals)
        
        active_trade = self.get_active_trade(symbol)
        if active_trade:
            buy_price = active_trade['buy_price']
            target_sell_price = buy_price * (1 + self.bot.profits.get(symbol, 0) if self.bot.profits.get(symbol, 0) is not None else 0)
            chart.add_trade_lines(buy_price, target_sell_price)
        
        return chart.fig

    def create_total_profit_chart(self) -> go.Figure:
        timestamps = [status['timestamp'] for status in self.bot.status_history]
        total_profits = [status['total_profit'] for status in self.bot.status_history]
        
        chart = ProfitChart()
        chart.add_profit_data(timestamps, total_profits)
        
        return chart.fig

    def create_balance_chart(self) -> go.Figure:
        timestamps = [status['timestamp'] for status in self.bot.status_history]
        liquid_balances = [status['liquid_usdt'] for status in self.bot.status_history]
        trading_balances = [status['tradable_usdt'] for status in self.bot.status_history]
        
        chart = BalanceChart()
        chart.add_balance_data(timestamps, liquid_balances, trading_balances)
        
        return chart.fig

    @staticmethod
    def extract_price_data(price_data: List[Dict[str, Any]]) -> Tuple[List[datetime], List[float]]:
        return [entry['timestamp'] for entry in price_data], [entry['price'] for entry in price_data]

    def get_buy_signals(self, symbol: str, price_data: List[Dict[str, Any]]) -> Tuple[List[datetime], List[float]]:
        buy_signals = []
        buy_timestamps = []
        for entry in price_data:
            if self.bot.should_buy(symbol, entry['price']) is not None:
                buy_signals.append(entry['price'])
                buy_timestamps.append(entry['timestamp'])
        return buy_timestamps, buy_signals

    def get_sell_signals(self, symbol: str, price_data: List[Dict[str, Any]]) -> Tuple[List[datetime], List[float]]:
        sell_signals = []
        sell_timestamps = []
        for entry in price_data:
            active_trade = self.get_active_trade(symbol)
            if active_trade and entry['price'] >= active_trade['buy_price'] * (1 + self.bot.profits.get(symbol, 0) if self.bot.profits.get(symbol, 0) is not None else 0):
                sell_signals.append(entry['price'])
                sell_timestamps.append(entry['timestamp'])
        return sell_timestamps, sell_signals

    def get_active_trade(self, symbol: str) -> Optional[Dict[str, Any]]:
        return next((trade for trade in self.bot.active_trades.values() if trade['symbol'] == symbol), None)

    def update_bot_data(self, bot):
        """Update the bot instance with fresh data"""
        self.bot = bot

@handle_errors
def save_chart(fig: go.Figure, filename: str) -> None:
    fig.write_image(filename)
    logger.info(f"Chart saved as {filename}")
