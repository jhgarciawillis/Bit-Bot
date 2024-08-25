import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from typing import Dict, List, Any
import asyncio
import logging
from config import load_config
from trading_loop import handle_trading_errors

logger = logging.getLogger(__name__)

class ChartCreator:
    def __init__(self, bot):
        self.bot = bot
        self.config = asyncio.run(load_config())

    @handle_trading_errors
    async def create_charts_async(self) -> Dict[str, Any]:
        individual_price_charts = await self.create_individual_price_charts_async()
        total_profit_fig = await self.create_total_profit_chart_async()
        
        return {
            'individual_price_charts': individual_price_charts,
            'total_profit': total_profit_fig
        }

    @handle_trading_errors
    async def create_individual_price_charts_async(self) -> Dict[str, go.Figure]:
        charts = {}
        tasks = [self.create_single_price_chart_async(symbol) for symbol in self.bot.symbol_allocations]
        results = await asyncio.gather(*tasks)
        for symbol, chart in zip(self.bot.symbol_allocations, results):
            charts[symbol] = chart
        return charts

    async def create_single_price_chart_async(self, symbol: str) -> go.Figure:
        fig = go.Figure()

        price_data = self.bot.price_history.get(symbol, [])
        timestamps = [entry['timestamp'] for entry in price_data]
        prices = [entry['price'] for entry in price_data]

        fig.add_trace(go.Scatter(x=timestamps, y=prices, mode='lines', name=f'{symbol} Price'))

        buy_signals = []
        buy_timestamps = []
        for entry in price_data:
            should_buy = await self.bot.should_buy(symbol, entry['price'])
            if should_buy is not None:
                buy_signals.append(entry['price'])
                buy_timestamps.append(entry['timestamp'])

        fig.add_trace(go.Scatter(
            x=buy_timestamps,
            y=buy_signals,
            mode='markers',
            marker=dict(symbol='triangle-up', size=10, color='green'),
            name=f'{symbol} Buy Signal'
        ))

        active_trade = next((trade for trade in self.bot.active_trades.values() if trade['symbol'] == symbol), None)
        if active_trade:
            buy_price = active_trade['buy_price']
            target_sell_price = buy_price * (1 + self.bot.profits.get(symbol, 0))
            fig.add_hline(y=buy_price, line_dash="dash", annotation_text="Buy Price", line_color="blue")
            fig.add_hline(y=target_sell_price, line_dash="dot", annotation_text="Target Sell Price", line_color="red")

        fig.update_layout(
            title=f'{symbol} Price Chart',
            xaxis_title='Timestamp',
            yaxis_title='Price (USDT)',
            height=self.config['chart_config']['height'],
            width=self.config['chart_config']['width'],
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
        )

        return fig

    @handle_trading_errors
    async def create_total_profit_chart_async(self) -> go.Figure:
        timestamps = [status['timestamp'] for status in self.bot.status_history]
        total_profits = [status['total_profit'] for status in self.bot.status_history]

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=timestamps, y=total_profits, mode='lines', name='Total Profit'))

        fig.update_layout(
            title='Total Profit Over Time',
            xaxis_title='Timestamp',
            yaxis_title='Total Profit (USDT)',
            height=self.config['chart_config']['height'],
            width=self.config['chart_config']['width']
        )

        return fig
    
    @handle_trading_errors
    async def save_chart_async(self, fig: go.Figure, filename: str) -> None:
        try:
            await asyncio.to_thread(fig.write_image, filename)
            logger.info(f"Chart saved as {filename}")
        except Exception as e:
            logger.error(f"Error saving chart: {e}")
            raise

    async def update_bot_data(self, bot):
        """Update the bot instance with fresh data asynchronously"""
        self.bot = bot
        # Refresh config in case it has changed
        self.config = await load_config()
