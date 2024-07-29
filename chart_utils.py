import plotly.graph_objects as go
import pandas as pd
from trading_bot import TradingBot

def create_time_series_chart(bot: TradingBot, chosen_symbols, chart_type):
    fig = go.Figure()
    
    for symbol in chosen_symbols:
        history = bot.wallet.get_currency_history("trading", symbol.split('-')[0])
        if history and history['price_history']:
            df = pd.DataFrame(history['price_history'], columns=['timestamp', 'price'])
            df.set_index('timestamp', inplace=True)
            
            if chart_type == 'Price':
                fig.add_trace(go.Scatter(x=df.index, y=df['price'], mode='lines', name=f'{symbol} Price'))
            
            if chart_type in ['Buy Prices', 'Target Sell Prices']:
                for trade in bot.active_trades.values():
                    if trade['symbol'] == symbol:
                        if chart_type == 'Buy Prices':
                            fig.add_trace(go.Scatter(x=[trade['buy_time']], y=[trade['buy_price']], 
                                                     mode='markers', name=f'{symbol} Buy', marker_symbol='triangle-up'))
                        else:
                            fig.add_trace(go.Scatter(x=[trade['buy_time']], y=[trade['target_sell_price']], 
                                                     mode='markers', name=f'{symbol} Target Sell', marker_symbol='triangle-down'))
    
    if chart_type == 'Total Profits':
        profit_history = [(status['timestamp'], status['total_profit']) for status in bot.status_history]
        df = pd.DataFrame(profit_history, columns=['timestamp', 'total_profit'])
        df.set_index('timestamp', inplace=True)
        fig.add_trace(go.Scatter(x=df.index, y=df['total_profit'], mode='lines', name='Total Profit'))
    
    fig.update_layout(title=f'{chart_type} Over Time', xaxis_title='Time', yaxis_title='Value')
    return fig
