import plotly.graph_objects as go
import plotly.subplots as sp
import pandas as pd
from trading_bot import TradingBot

class ChartCreator:
    def __init__(self, bot: TradingBot):
        self.bot = bot

    def create_charts(self):
        fig = sp.make_subplots(rows=2, cols=2, subplot_titles=("Price", "Buy Prices", "Target Sell Prices", "Total Profits"),
                               horizontal_spacing=0.1, vertical_spacing=0.1)  # Adjust spacing between subplots

        self.add_price_chart(fig, 1, 1)
        self.add_buy_prices_chart(fig, 1, 2)
        self.add_target_sell_prices_chart(fig, 2, 1)
        self.add_total_profits_chart(fig, 2, 2)

        fig.update_layout(height=400, width=400, showlegend=False, margin=dict(l=20, r=20, t=40, b=20))  # Updated chart size and margins
        return fig

    def add_price_chart(self, fig, row, col):
        for symbol in self.bot.symbol_allocations:
            history = self.bot.wallet.get_currency_history("trading", symbol.split('-')[0])
            if history and history['price_history']:
                df = pd.DataFrame(history['price_history'], columns=['timestamp', 'price'])
                df.set_index('timestamp', inplace=True)
                fig.add_trace(go.Scatter(x=df.index, y=df['price'], mode='lines', name=f'{symbol} Price'), row=row, col=col)

    def add_buy_prices_chart(self, fig, row, col):
        for status in self.bot.status_history:
            for trade in status['active_trades'].values():
                fig.add_trace(go.Scatter(x=[trade['buy_time']], y=[trade['buy_price']], mode='markers', name=f"{trade['symbol']} Buy", marker_symbol='triangle-up'), row=row, col=col)

    def add_target_sell_prices_chart(self, fig, row, col):
        for status in self.bot.status_history:
            for trade in status['active_trades'].values():
                fig.add_trace(go.Scatter(x=[trade['buy_time']], y=[trade['target_sell_price']], mode='markers', name=f"{trade['symbol']} Target Sell", marker_symbol='triangle-down'), row=row, col=col)

    def add_total_profits_chart(self, fig, row, col):
        profit_history = [(status['timestamp'], status['total_profit']) for status in self.bot.status_history]
        df = pd.DataFrame(profit_history, columns=['timestamp', 'total_profit'])
        df.set_index('timestamp', inplace=True)
        fig.add_trace(go.Scatter(x=df.index, y=df['total_profit'], mode='lines', name='Total Profit'), row=row, col=col)
