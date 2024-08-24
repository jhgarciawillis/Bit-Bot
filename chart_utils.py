import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import pandas as pd
from typing import Dict, Any
from trading_bot import TradingBot

class ChartConfig:
    COLORS = {
        'current_price': 'blue',
        'buy_price': 'green',
        'target_sell_price': 'red',
        'total_profit': 'purple'
    }
    CHART_HEIGHT = 600
    CHART_TITLE = "Price, Buy Prices, and Target Sell Prices (Last 120 Minutes)"

class PriceBuyTargetProfitChart:
    def __init__(self, bot: TradingBot, start_time: datetime, duration_minutes: int = 120, config: ChartConfig = ChartConfig()):
        self.bot = bot
        self.start_time = start_time
        self.end_time = start_time + timedelta(minutes=duration_minutes)
        self.duration_minutes = duration_minutes
        self.config = config
        self.cache = {}

    def create_chart(self) -> go.Figure:
        fig = go.Figure()

        for symbol in self.bot.symbol_allocations.keys():
            self._add_price_data(fig, symbol)
            self._add_buy_price_data(fig, symbol)
            self._add_target_sell_price_data(fig, symbol)

        fig.update_layout(
            title_text=self.config.CHART_TITLE,
            height=self.config.CHART_HEIGHT,
            xaxis_title="Time",
            yaxis_title="Price (USDT)",
            legend_title="Legend",
            hovermode="x unified"
        )

        return fig

    def _add_price_data(self, fig: go.Figure, symbol: str) -> None:
        price_data = self._get_price_data(symbol)
        fig.add_trace(go.Scatter(
            x=price_data['timestamp'],
            y=price_data['current_price'],
            mode='lines',
            name=f'{symbol}_current_price',
            line=dict(color=self.config.COLORS['current_price'])
        ))

    def _add_buy_price_data(self, fig: go.Figure, symbol: str) -> None:
        buy_data = self._get_buy_price_data(symbol)
        fig.add_trace(go.Scatter(
            x=buy_data['timestamp'],
            y=buy_data['buy_price'],
            mode='markers',
            name=f'{symbol}_buy_price',
            marker=dict(color=self.config.COLORS['buy_price'], symbol='triangle-up', size=10)
        ))

    def _add_target_sell_price_data(self, fig: go.Figure, symbol: str) -> None:
        target_sell_data = self._get_target_sell_price_data(symbol)
        fig.add_trace(go.Scatter(
            x=target_sell_data['timestamp'],
            y=target_sell_data['target_sell_price'],
            mode='markers',
            name=f'{symbol}_target_sell_price',
            marker=dict(color=self.config.COLORS['target_sell_price'], symbol='triangle-down', size=10)
        ))

    def _get_price_data(self, symbol: str) -> pd.DataFrame:
        cache_key = f'price_data_{symbol}'
        if cache_key not in self.cache:
            try:
                price_history = self.bot.price_history.get(symbol, [])
                self.cache[cache_key] = pd.DataFrame({
                    'timestamp': [entry['timestamp'] for entry in price_history if self.start_time <= entry['timestamp'] <= self.end_time],
                    'current_price': [entry['price'] for entry in price_history if self.start_time <= entry['timestamp'] <= self.end_time]
                })
            except Exception as e:
                print(f"Error getting price data for {symbol}: {str(e)}")
                self.cache[cache_key] = pd.DataFrame(columns=['timestamp', 'current_price'])
        return self.cache[cache_key]

    def _get_buy_price_data(self, symbol: str) -> pd.DataFrame:
        cache_key = f'buy_price_data_{symbol}'
        if cache_key not in self.cache:
            try:
                buy_history = [trade for trade in self.bot.active_trades.values() if trade['symbol'] == symbol]
                self.cache[cache_key] = pd.DataFrame({
                    'timestamp': [trade['buy_time'] for trade in buy_history if self.start_time <= trade['buy_time'] <= self.end_time],
                    'buy_price': [trade['buy_price'] for trade in buy_history if self.start_time <= trade['buy_time'] <= self.end_time]
                })
            except Exception as e:
                print(f"Error getting buy price data for {symbol}: {str(e)}")
                self.cache[cache_key] = pd.DataFrame(columns=['timestamp', 'buy_price'])
        return self.cache[cache_key]

    def _get_target_sell_price_data(self, symbol: str) -> pd.DataFrame:
        cache_key = f'target_sell_price_data_{symbol}'
        if cache_key not in self.cache:
            try:
                target_sell_history = [trade for trade in self.bot.active_trades.values() if trade['symbol'] == symbol]
                self.cache[cache_key] = pd.DataFrame({
                    'timestamp': [trade['buy_time'] for trade in target_sell_history if self.start_time <= trade['buy_time'] <= self.end_time],
                    'target_sell_price': [trade['target_sell_price'] for trade in target_sell_history if self.start_time <= trade['buy_time'] <= self.end_time]
                })
            except Exception as e:
                print(f"Error getting target sell price data for {symbol}: {str(e)}")
                self.cache[cache_key] = pd.DataFrame(columns=['timestamp', 'target_sell_price'])
        return self.cache[cache_key]

class TotalProfitChart:
    def __init__(self, bot: TradingBot, start_time: datetime, duration_minutes: int = 120, config: ChartConfig = ChartConfig()):
        self.bot = bot
        self.start_time = start_time
        self.end_time = start_time + timedelta(minutes=duration_minutes)
        self.duration_minutes = duration_minutes
        self.config = config
        self.cache = {}

    def create_chart(self) -> go.Figure:
        fig = go.Figure()

        self._add_total_profit_data(fig)

        fig.update_layout(
            title_text="Total Profit (Last 120 Minutes)",
            height=300,
            xaxis_title="Time",
            yaxis_title="Total Profit (USDT)",
            legend_title="Legend",
            hovermode="x unified"
        )

        return fig

    def _add_total_profit_data(self, fig: go.Figure) -> None:
        profit_data = self._get_total_profit_data()
        fig.add_trace(go.Scatter(
            x=profit_data['timestamp'],
            y=profit_data['total_profit'],
            mode='lines',
            name='total_profit',
            line=dict(color=self.config.COLORS['total_profit'])
        ))

    def _get_total_profit_data(self) -> pd.DataFrame:
        cache_key = 'total_profit_data'
        if cache_key not in self.cache:
            try:
                profit_history = self.bot.status_history
                self.cache[cache_key] = pd.DataFrame({
                    'timestamp': [status['timestamp'] for status in profit_history if self.start_time <= status['timestamp'] <= self.end_time],
                    'total_profit': [status['total_profit'] for status in profit_history if self.start_time <= status['timestamp'] <= self.end_time]
                })
            except Exception as e:
                print(f"Error getting total profit data: {str(e)}")
                self.cache[cache_key] = pd.DataFrame(columns=['timestamp', 'total_profit'])
        return self.cache[cache_key]

class ChartCreator:
    def __init__(self, bot: TradingBot):
        self.bot = bot

    def create_charts(self) -> Dict[str, go.Figure]:
        start_time = datetime.now() - timedelta(minutes=120)
        price_buy_target_chart = PriceBuyTargetProfitChart(self.bot, start_time)
        total_profit_chart = TotalProfitChart(self.bot, start_time)
        return {
            'price_buy_target': price_buy_target_chart.create_chart(),
            'total_profit': total_profit_chart.create_chart()
        }
