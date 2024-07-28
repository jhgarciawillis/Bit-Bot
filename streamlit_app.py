import streamlit as st
import time
from trading_bot import TradingBot
import config
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import traceback

def safe_divide(numerator, denominator):
    return numerator / denominator if denominator != 0 else 0

def create_time_series_chart(bot, chosen_symbols, chart_type):
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

def main():
    st.title("Cryptocurrency Trading Bot")

    # Sidebar for configuration
    st.sidebar.header("Configuration")

    # Simulation mode toggle
    is_simulation = st.sidebar.checkbox("Simulation Mode", value=True)

    if is_simulation:
        st.sidebar.write("Running in simulation mode. No real trades will be executed.")
        api_key = "simulation"
        api_secret = "simulation"
        api_passphrase = "simulation"
        api_url = "https://api.kucoin.com"  # You can use the real URL even for simulation
    else:
        st.sidebar.warning("WARNING: This bot will use real funds on the live KuCoin exchange.")
        st.sidebar.warning("Only proceed if you understand the risks and are using funds you can afford to lose.")
        proceed = st.sidebar.checkbox("I understand the risks and want to proceed")
        if not proceed:
            st.sidebar.error("Please check the box to proceed with live trading.")
            return

        # Use secrets for API credentials in live mode
        api_key = st.secrets["API_KEY"]
        api_secret = st.secrets["API_SECRET"]
        api_passphrase = st.secrets["API_PASSPHRASE"]
        api_url = st.secrets["API_URL"]

    # Initialize the trading bot
    bot = TradingBot(api_key, api_secret, api_passphrase, api_url)
    bot.is_simulation = is_simulation
    bot.initialize_clients()

    if is_simulation:
        simulated_usdt_balance = st.sidebar.number_input("Simulated USDT Balance", min_value=0.0, value=1000.0, step=0.1)
        bot.wallet.update_account_balance("trading", "USDT", simulated_usdt_balance)

    # Get user inputs
    available_symbols = bot.market_client.get_symbol_list()
    chosen_symbols = bot.get_user_symbol_choices(available_symbols)

    if not chosen_symbols:
        st.warning("Please select at least one symbol to trade.")
        return

    total_usdt = bot.get_account_balance('USDT')
    st.sidebar.write(f"Confirmed USDT Balance: {total_usdt:.4f}")

    bot.symbol_allocations, tradable_usdt = bot.get_user_allocations(chosen_symbols, total_usdt)
    if tradable_usdt <= 0:
        st.warning("No USDT available for trading. Please adjust your liquid USDT percentage.")
        return

    profit_margin = bot.get_profit_margin()
    bot.num_orders = st.sidebar.slider("Number of Orders", min_value=1, max_value=10, value=1, step=1)

    # Initialize profits dictionary
    bot.profits = {symbol: 0 for symbol in chosen_symbols}

    # Create placeholders for status table, chart, and error messages
    status_table = st.empty()
    chart_placeholder = st.empty()
    error_placeholder = st.empty()

    # Chart type selection
    chart_type = st.selectbox("Select chart type", ['Price', 'Buy Prices', 'Target Sell Prices', 'Total Profits'])

    # Main trading loop
    if st.sidebar.button("Start Trading"):
        while True:
            try:
                # Clear previous error messages
                error_placeholder.empty()

                # Fetch current prices
                prices = bot.get_current_prices(chosen_symbols)
                if not prices:
                    raise ValueError("Failed to fetch current prices")

                bot.update_price_history(chosen_symbols, prices)

                current_status = bot.get_current_status(prices)
                if current_status['tradable_usdt'] <= 0:
                    st.warning("No USDT available for trading. Please adjust your liquid USDT percentage.")
                    time.sleep(5)  # Wait for 5 seconds before checking again
                    continue

                for symbol in chosen_symbols:
                    current_price = prices[symbol]
                    if current_price is None:
                        st.warning(f"Skipping {symbol} due to unavailable price data")
                        continue

                    allocated_value = safe_divide(current_status['tradable_usdt'] * bot.symbol_allocations[symbol], 1)
                    base_currency = symbol.split('-')[1]
                    base_balance = bot.get_account_balance(base_currency)

                    # Check if we should buy
                    if base_balance > 0 and bot.should_buy(symbol, current_price):
                        buy_amount_usdt = min(allocated_value, base_balance)
                        if buy_amount_usdt > 0:
                            order_amount = safe_divide(buy_amount_usdt, bot.num_orders)
                            for _ in range(bot.num_orders):
                                order = bot.place_market_buy_order(symbol, order_amount)
                                if order:
                                    target_sell_price = order['price'] * (1 + profit_margin + 2*bot.FEE_RATE)
                                    bot.active_trades[order['orderId']] = {
                                        'symbol': symbol,
                                        'buy_price': order['price'],
                                        'amount': order['amount'],
                                        'target_sell_price': target_sell_price,
                                        'fee_usdt': order['fee_usdt'],
                                        'buy_time': datetime.now()
                                    }
                                    st.write(f"Placed buy order for {symbol}: {order_amount:.4f} USDT at {order['price']:.4f}, Order ID: {order['orderId']}")

                    # Check active trades for selling
                    for order_id, trade in list(bot.active_trades.items()):
                        if trade['symbol'] == symbol and current_price >= trade['target_sell_price']:
                            sell_amount_crypto = trade['amount']
                            sell_order = bot.place_market_sell_order(symbol, sell_amount_crypto)
                            if sell_order:
                                sell_amount_usdt = sell_order['amount']
                                total_fee = trade['fee_usdt'] + sell_order['fee_usdt']
                                profit = sell_amount_usdt - (trade['amount'] * trade['buy_price']) - total_fee
                                bot.profits[symbol] += profit
                                bot.total_profit += profit
                                st.write(f"Placed sell order for {symbol}: {sell_amount_usdt:.4f} USDT at {sell_order['price']:.4f}, Profit: {profit:.4f} USDT, Total Fee: {total_fee:.4f} USDT, Order ID: {sell_order['orderId']}")
                                del bot.active_trades[order_id]

                # Update status table
                status_df = pd.DataFrame({
                    'Symbol': chosen_symbols,
                    'Current Price': [f"{prices[symbol]:.4f}" if prices[symbol] is not None else "N/A" for symbol in chosen_symbols],
                    'Buy Price': [f"{bot.active_trades[list(bot.active_trades.keys())[0]]['buy_price']:.4f}" if bot.active_trades else 'N/A' for _ in chosen_symbols],
                    'Target Sell Price': [f"{bot.active_trades[list(bot.active_trades.keys())[0]]['target_sell_price']:.4f}" if bot.active_trades else 'N/A' for _ in chosen_symbols],
                    'Active Trade': ['Yes' if bot.active_trades else 'No' for _ in chosen_symbols],
                    'Profit': [f"{bot.profits[symbol]:.4f}" for symbol in chosen_symbols]
                })
                status_df = pd.concat([status_df, pd.DataFrame({
                    'Symbol': ['Total', 'Current Total USDT', 'Tradable USDT', 'Liquid USDT'],
                    'Current Price': ['', f"{current_status['current_total_usdt']:.4f}", f"{current_status['tradable_usdt']:.4f}", f"{current_status['liquid_usdt']:.4f}"],
                    'Buy Price': ['', '', '', ''],
                    'Target Sell Price': ['', '', '', ''],
                    'Active Trade': ['', '', '', ''],
                    'Profit': [f"{bot.total_profit:.4f}", '', '', '']
                })], ignore_index=True)

                status_table.table(status_df)

                # Update chart
                fig = create_time_series_chart(bot, chosen_symbols, chart_type)
                chart_placeholder.plotly_chart(fig)

                # Update allocations based on new total USDT value
                bot.update_allocations(current_status['current_total_usdt'])

                # Sleep for a short duration before the next iteration
                time.sleep(1)

            except Exception as e:
                error_message = f"An error occurred: {str(e)}\n"
                error_message += f"Error location:\n{traceback.format_exc()}"
                error_placeholder.error(error_message)
                time.sleep(5)  # Wait for 5 seconds before the next iteration

if __name__ == "__main__":
    main()
