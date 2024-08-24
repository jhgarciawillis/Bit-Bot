import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from typing import Dict, List

class ChartCreator:
    def __init__(self, bot):
        self.bot = bot

    def create_charts(self) -> Dict:
        price_buy_target_fig = self.create_price_buy_target_chart()
        total_profit_fig = self.create_total_profit_chart()
        
        return {
            'price_buy_target': price_buy_target_fig,
            'total_profit': total_profit_fig
        }

    def create_price_buy_target_chart(self) -> go.Figure:
        fig = make_subplots(rows=len(self.bot.symbol_allocations), cols=1, shared_xaxes=True, vertical_spacing=0.02)

        for i, symbol in enumerate(self.bot.symbol_allocations, start=1):
            price_data = self.bot.price_history[symbol]
            timestamps = [entry['timestamp'] for entry in price_data]
            prices = [entry['price'] for entry in price_data]

            fig.add_trace(go.Scatter(x=timestamps, y=prices, mode='lines', name=f'{symbol} Price'), row=i, col=1)

            buy_signals = [entry['price'] for entry in price_data if entry['price'] <= self.bot.should_buy(symbol, entry['price'])]
            buy_timestamps = [entry['timestamp'] for entry in price_data if entry['price'] <= self.bot.should_buy(symbol, entry['price'])]

            fig.add_trace(go.Scatter(x=buy_timestamps, y=buy_signals, mode='markers', marker=dict(symbol='triangle-up', size=10), name=f'{symbol} Buy Signal'), row=i, col=1)

            fig.update_yaxes(title_text=f'{symbol} Price', row=i, col=1)

        fig.update_layout(height=600, width=800, title_text="Price and Buy Target Chart", xaxis_rangeslider_visible=False)
        fig.update_xaxes(title_text="Timestamp", row=len(self.bot.symbol_allocations), col=1)

        return fig

    def create_total_profit_chart(self) -> go.Figure:
        timestamps = [status['timestamp'] for status in self.bot.status_history]
        total_profits = [status['total_profit'] for status in self.bot.status_history]

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=timestamps, y=total_profits, mode='lines', name='Total Profit'))

        fig.update_layout(title='Total Profit Over Time', xaxis_title='Timestamp', yaxis_title='Total Profit (USDT)', height=400, width=800)

        return fig
    
    def save_chart(self, fig: go.Figure, filename: str) -> None:
        fig.write_image(filename)
