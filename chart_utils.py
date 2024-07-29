import plotly.graph_objects as go
import pandas as pd
from trading_bot import TradingBot

class ChartCreator:
    def __init__(self, bot: TradingBot):
        self.bot = bot

    def create_time_series_chart(self, chosen_symbols, chart_type):
        fig = go.Figure()
        
        for symbol in chosen_symbols:
            self.add_symbol_chart_traces(fig, symbol, chart_type)
        
        self.add_total_profits_chart(fig, chart_type)
        
        fig.update_layout(title=f'{chart_type} Over Time', xaxis_title='Time', yaxis_title='Value')
        return fig

    def add_symbol_chart_traces(self, fig, symbol, chart_type):
        history = self.bot.wallet.get_currency_history("trading", symbol.split('-')[0])
        if history and history['price_history']:
            df = pd.DataFrame(history['price_history'], columns=['timestamp', 'price'])
            df.set_index('timestamp', inplace=True)
            
            if chart_type == 'Price':
                fig.add_trace(go.Scatter(x=df.index, y=df['price'], mode='lines', name=f'{symbol} Price'))
            
            if chart_type in ['Buy Prices', 'Target Sell Prices']:
                self.add_buy_sell_price_traces(fig, symbol, chart_type)

    def add_buy_sell_price_traces(self, fig, symbol, chart_type):
        for status in self.bot.status_history:
            for trade in status['active_trades'].values():
                if trade['symbol'] == symbol:
                    if chart_type == 'Buy Prices':
                        fig.add_trace(go.Scatter(x=[trade['buy_time']], y=[trade['buy_price']], 
                                                 mode='markers', name=f'{symbol} Buy', marker_symbol='triangle-up'))
                    else:
                        fig.add_trace(go.Scatter(x=[trade['buy_time']], y=[trade['target_sell_price']], 
                                                 mode='markers', name=f'{symbol} Target Sell', marker_symbol='triangle-down'))

    def add_total_profits_chart(self, fig, chart_type):
        if chart_type == 'Total Profits':
            profit_history = [(status['timestamp'], status['total_profit']) for status in self.bot.status_history]
            df = pd.DataFrame(profit_history, columns=['timestamp', 'total_profit'])
            df.set_index('timestamp', inplace=True)
            fig.add_trace(go.Scatter(x=df.index, y=df['total_profit'], mode='lines', name='Total Profit'))
