import streamlit as st
import time
from bot import TradingBot
import config

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
        bot.simulated_balance['USDT'] = st.sidebar.number_input("Simulated USDT Balance", min_value=0.0, value=1000.0, step=0.1)

    # Get user inputs
    chosen_symbols = bot.get_user_symbol_choices(config.AVAILABLE_SYMBOLS)

    if not chosen_symbols:
        st.warning("Please select at least one symbol to trade.")
        return

    total_usdt = bot.get_account_balance('USDT')
    st.sidebar.write(f"Confirmed USDT Balance: {total_usdt:.2f}")

    bot.symbol_allocations, tradable_usdt = bot.get_user_allocations(chosen_symbols, total_usdt)
    profit_margin = bot.get_profit_margin()
    bot.num_orders = st.sidebar.slider("Number of Orders", min_value=1, max_value=10, value=1, step=1)

    # Initialize profits dictionary
    bot.profits = {symbol: 0 for symbol in chosen_symbols}

    # Main trading loop
    if st.sidebar.button("Start Trading"):
        status_placeholder = st.empty()
        while True:
            try:
                # Fetch current prices
                prices = bot.get_current_prices(chosen_symbols)
                bot.update_price_history(chosen_symbols, prices)

                for symbol in chosen_symbols:
                    current_price = prices[symbol]
                    if current_price is None:
                        st.warning(f"Skipping {symbol} due to unavailable price data")
                        continue

                    allocated_value = tradable_usdt * bot.symbol_allocations[symbol]
                    base_currency = symbol.split('-')[1]
                    base_balance = bot.get_account_balance(base_currency)

                    # Check if we should buy
                    if base_balance > 0 and bot.should_buy(symbol, current_price):
                        buy_amount_usdt = min(allocated_value, base_balance)
                        if buy_amount_usdt > 0:
                            order_amount = buy_amount_usdt / bot.num_orders
                            for _ in range(bot.num_orders):
                                order = bot.place_market_buy_order(symbol, order_amount)
                                if order:
                                    target_sell_price = order['price'] * (1 + profit_margin + 2*bot.FEE_RATE)
                                    bot.active_trades[order['orderId']] = {
                                        'symbol': symbol,
                                        'buy_price': order['price'],
                                        'amount': order['amount'],
                                        'target_sell_price': target_sell_price,
                                        'fee_usdt': order['fee_usdt']
                                    }
                                    st.write(f"Placed buy order for {symbol}: {order_amount:.2f} USDT at {order['price']}, Order ID: {order['orderId']}")

                    # Check active trades for selling
                    for order_id, trade in list(bot.active_trades.items()):
                        if trade['symbol'] == symbol and current_price >= trade['target_sell_price']:
                            sell_amount_crypto = trade['amount']
                            sell_order = bot.place_market_sell_order(symbol, sell_amount_crypto)
                            if sell_order:
                                sell_amount_usdt = sell_order['amount_usdt']
                                total_fee = trade['fee_usdt'] + sell_order['fee_usdt']
                                profit = sell_amount_usdt - (trade['amount'] * trade['buy_price']) - total_fee
                                bot.profits[symbol] += profit
                                bot.total_profit += profit
                                st.write(f"Placed sell order for {symbol}: {sell_amount_usdt:.2f} USDT at {sell_order['price']}, Profit: {profit:.2f} USDT, Total Fee: {total_fee:.2f} USDT, Order ID: {sell_order['orderId']}")
                                del bot.active_trades[order_id]

                # Update and display status
                current_status = bot.get_current_status(prices)
                status_placeholder.empty()
                with status_placeholder.container():
                    bot.display_current_status(current_status)

                # Update allocations based on new total USDT value
                bot.update_allocations(current_status['current_total_usdt'])

                # Sleep for a short duration before the next iteration
                time.sleep(1)

            except Exception as e:
                st.error(f"An error occurred: {e}")
                st.write("Continuing with the next iteration...")
                time.sleep(1)

if __name__ == "__main__":
    main()
