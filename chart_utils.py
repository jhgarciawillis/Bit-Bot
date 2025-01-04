import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional
import logging
from config import config_manager
from utils import handle_errors

logger = logging.getLogger(__name__)

class CustomChart:
    def __init__(self, title: str, x_title: str, y_title: str, chart_type: str):
        self.fig = go.Figure()
        self.chart_type = chart_type
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

    def add_trace(self, x: List[Any], y: List[Any], name: str, mode: str = 'lines', color: str = None, symbol: str = None, size: int = None):
        self.fig.add_trace(go.Scatter(
            x=x, y=y, mode=mode, name=name,
            marker=dict(color=color, symbol=symbol, size=size)
        ))

    def show(self):
        self.fig.show()

    @handle_errors
    def save(self, filename: str):
        self.fig.write_image(filename)
        logger.info(f"Chart saved as {filename}")

class ChartCreator:
    def __init__(self, bot):
        self.bot = bot

    @handle_errors
    def create_charts(self) -> Dict[str, Any]:
        return {
            'individual_price_charts': self.create_individual_price_charts(),
            'total_profit': self.create_total_profit_chart(),
        }

    def create_individual_price_charts(self) -> Dict[str, go.Figure]:
        return {symbol: self.create_single_price_chart(symbol) for symbol in self.bot.symbol_allocations}

    def create_single_price_chart(self, symbol: str) -> go.Figure:
        price_data = self.bot.price_history.get(symbol, [])
        timestamps, prices = self.extract_price_data(price_data)
        
        chart = CustomChart(f'{symbol} Price Chart', 'Timestamp', 'Price (USDT)', 'price')
        chart.add_trace(timestamps, prices, f'{symbol} Price')
        
        buy_timestamps, buy_signals = self.get_buy_signals(symbol, price_data)
        chart.add_trace(buy_timestamps, buy_signals, f'{symbol} Buy Signal', mode='markers', color='green', symbol='triangle-up', size=10)
        
        sell_timestamps, sell_signals = self.get_sell_signals(symbol, price_data)
        chart.add_trace(sell_timestamps, sell_signals, f'{symbol} Sell Signal', mode='markers', color='red', symbol='triangle-down', size=10)
        
        active_trade = self.get_active_trade(symbol)
        if active_trade:
            buy_price = active_trade['buy_price']
            target_sell_price = buy_price * (1 + self.bot.profit_margin)
            chart.add_trace([timestamps[0], timestamps[-1]], [buy_price, buy_price], 'Buy Price', mode='lines', color='blue')
            chart.add_trace([timestamps[0], timestamps[-1]], [target_sell_price, target_sell_price], 'Target Sell Price', mode='lines', color='red')
        
        return chart.fig

    def create_total_profit_chart(self) -> go.Figure:
        timestamps = [status['timestamp'] for status in self.bot.status_history]
        total_profits = [sum(status['profits'].values()) for status in self.bot.status_history]
        
        chart = CustomChart('Total Profit Over Time', 'Timestamp', 'Total Profit (USDT)', 'profit')
        chart.add_trace(timestamps, total_profits, 'Total Profit')
        
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
            if active_trade and entry['price'] >= active_trade['buy_price'] * (1 + self.bot.profit_margin):
                sell_signals.append(entry['price'])
                sell_timestamps.append(entry['timestamp'])
        return sell_timestamps, sell_signals

    def get_active_trade(self, symbol: str) -> Optional[Dict[str, Any]]:
        return next((trade for trade in self.bot.active_trades.values() if trade['symbol'] == symbol), None)

    def update_bot_data(self, bot):
        self.bot = bot

@handle_errors
def save_chart(fig: go.Figure, filename: str) -> None:
    fig.write_image(filename)
    logger.info(f"Chart saved as {filename}")
