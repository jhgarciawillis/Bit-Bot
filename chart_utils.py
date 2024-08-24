import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import pandas as pd
from trading_bot import TradingBot

class PriceBuyTargetProfitChart:
    def __init__(self, bot: TradingBot, start_time: datetime, duration_minutes: int = 120):
        self.bot = bot
        self.start_time = start_time
        self.end_time = start_time + timedelta(minutes=duration_minutes)
        self.duration_minutes = duration_minutes

    def create_chart(self):
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                            subplot_titles=("Price, Buy, and Target Sell", "Total Profit"))

        for symbol in self.bot.symbol_allocations.keys():
            self._add_price_data(fig, symbol)
            self._add_buy_price_data(fig, symbol)
            self._add_target_sell_price_data(fig, symbol)

        self._add_total_profit_data(fig)

        fig.update_layout(
            title_text="Price, Buy Prices, Target Sell Prices, and Total Profit (Last 120 Minutes)",
            height=800,
            xaxis_title="Time",
            yaxis_title="Price (USDT)",
            yaxis2_title="Total Profit (USDT)",
            legend_title="Legend",
            hovermode="x unified"
        )

        return fig

    def _add_price_data(self, fig, symbol):
        price_data = self._get_price_data(symbol)
        fig.add_trace(go.Scatter(
            x=price_data['timestamp'],
            y=price_data['current_price'],
            mode='lines',
            name=f'{symbol}_current_price',
            line=dict(color='blue')
        ), row=1, col=1)

    def _add_buy_price_data(self, fig, symbol):
        buy_data = self._get_buy_price_data(symbol)
        fig.add_trace(go.Scatter(
            x=buy_data['timestamp'],
            y=buy_data['buy_price'],
            mode='markers',
            name=f'{symbol}_buy_price',
            marker=dict(color='green', symbol='triangle-up', size=10)
        ), row=1, col=1)

    def _add_target_sell_price_data(self, fig, symbol):
        target_sell_data = self._get_target_sell_price_data(symbol)
        fig.add_trace(go.Scatter(
            x=target_sell_data['timestamp'],
            y=target_sell_data['target_sell_price'],
            mode='markers',
            name=f'{symbol}_target_sell_price',
            marker=dict(color='red', symbol='triangle-down', size=10)
        ), row=1, col=1)

    def _add_total_profit_data(self, fig):
        profit_data = self._get_total_profit_data()
        fig.add_trace(go.Scatter(
            x=profit_data['timestamp'],
            y=profit_data['total_profit'],
            mode='lines',
            name='total_profit',
            line=dict(color='purple')
        ), row=2, col=1)

    def _get_price_data(self, symbol):
        price_history = self.bot.price_history.get(symbol, [])
        return pd.DataFrame({
            'timestamp': [entry['timestamp'] for entry in price_history if self.start_time <= entry['timestamp'] <= self.end_time],
            'current_price': [entry['price'] for entry in price_history if self.start_time <= entry['timestamp'] <= self.end_time]
        })

    def _get_buy_price_data(self, symbol):
        buy_history = [trade for trade in self.bot.active_trades.values() if trade['symbol'] == symbol]
        return pd.DataFrame({
            'timestamp': [trade['buy_time'] for trade in buy_history if self.start_time <= trade['buy_time'] <= self.end_time],
            'buy_price': [trade['buy_price'] for trade in buy_history if self.start_time <= trade['buy_time'] <= self.end_time]
        })

    def _get_target_sell_price_data(self, symbol):
        target_sell_history = [trade for trade in self.bot.active_trades.values() if trade['symbol'] == symbol]
        return pd.DataFrame({
            'timestamp': [trade['buy_time'] for trade in target_sell_history if self.start_time <= trade['buy_time'] <= self.end_time],
            'target_sell_price': [trade['target_sell_price'] for trade in target_sell_history if self.start_time <= trade['buy_time'] <= self.end_time]
        })

    def _get_total_profit_data(self):
        profit_history = self.bot.status_history
        return pd.DataFrame({
            'timestamp': [status['timestamp'] for status in profit_history if self.start_time <= status['timestamp'] <= self.end_time],
            'total_profit': [status['total_profit'] for status in profit_history if self.start_time <= status['timestamp'] <= self.end_time]
        })

class ChartCreator:
    def __init__(self, bot: TradingBot):
        self.bot = bot

    def create_charts(self):
        start_time = datetime.now() - timedelta(minutes=120)
        price_buy_target_profit_chart = PriceBuyTargetProfitChart(self.bot, start_time)
        return price_buy_target_profit_chart.create_chart()
