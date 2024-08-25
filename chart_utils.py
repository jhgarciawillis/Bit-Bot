import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from typing import Dict, List
import asyncio
import logging
from config import load_config
from trading_loop import handle_trading_errors

logger = logging.getLogger(__name__)

class ChartCreator:
    def __init__(self, bot):
        self.bot = bot
        self.config = load_config()

    @handle_trading_errors
    async def create_charts_async(self) -> Dict:
        price_buy_target_fig = await self.create_price_buy_target_chart_async()
        total_profit_fig = await self.create_total_profit_chart_async()
        
        return {
            'price_buy_target': price_buy_target_fig,
            'total_profit': total_profit_fig
        }

    @handle_trading_errors
    async def create_price_buy_target_chart_async(self) -> go.Figure:
        fig = make_subplots(rows=len(self.bot.symbol_allocations), cols=1, shared_xaxes=True, vertical_spacing=0.02)

        tasks = [self.create_symbol_trace(symbol, i) for i, symbol in enumerate(self.bot.symbol_allocations, start=1)]
        symbol_traces = await asyncio.gather(*tasks)

        for traces in symbol_traces:
            for trace in traces:
                fig.add_trace(trace[0], row=trace[1], col=1)

        fig.update_layout(
            height=self.config['chart_config']['height'],
            width=self.config['chart_config']['width'],
            title_text="Price and Buy Target Chart",
            xaxis_rangeslider_visible=False
        )
        fig.update_xaxes(title_text="Timestamp", row=len(self.bot.symbol_allocations), col=1)

        return fig

    async def create_symbol_trace(self, symbol: str, row: int) -> List:
        price_data = self.bot.price_history.get(symbol, [])
        timestamps = [entry['timestamp'] for entry in price_data]
        prices = [entry['price'] for entry in price_data]

        price_trace = go.Scatter(x=timestamps, y=prices, mode='lines', name=f'{symbol} Price')

        buy_signals = [entry['price'] for entry in price_data if self.bot.should_buy(symbol, entry['price'])]
        buy_timestamps = [entry['timestamp'] for entry in price_data if self.bot.should_buy(symbol, entry['price'])]

        buy_trace = go.Scatter(
            x=buy_timestamps,
            y=buy_signals,
            mode='markers',
            marker=dict(symbol='triangle-up', size=10),
            name=f'{symbol} Buy Signal'
        )

        return [(price_trace, row), (buy_trace, row)]

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

    def update_bot_data(self, bot):
        """Update the bot instance with fresh data"""
        self.bot = bot
