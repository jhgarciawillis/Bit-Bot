import streamlit as st
from bot import TradingBot
from wallet import Wallet, Account, Currency
from kucoin.client import Market, Trade, User
from config import AVAILABLE_SYMBOLS

def main():
    global total_profit, symbol_allocations, usdt_liquid_percentage, active_trades, num_orders

    st.title("Cryptocurrency Trading Bot")

    is_simulation = st.sidebar.checkbox("Simulation Mode", value=True)

    if is_simulation:
        st.sidebar.write("Running in simulation mode. No real trades will be executed.")
        simulated_usdt_balance = st.sidebar.number_input("Simulated USDT Balance", min_value=0.0, value=1000.0, step=0.0001)
        trading_account = Account("trading", [Currency("USDT", simulated_usdt_balance)])
        wallet = Wallet([trading_account])
    else:
        st.sidebar.warning("WARNING: This bot will use real funds on the live KuCoin exchange.")
        st.sidebar.warning("Only proceed if you understand the risks and are using funds you can afford to lose.")
        proceed = st.sidebar.checkbox("I understand the risks and want to proceed")
        if not proceed:
            st.sidebar.error("Please check the box to proceed with live trading.")
            return

        # Initialize the wallet and account with real balances
        trading_account = Account("trading")
        wallet = Wallet([trading_account])

    # Initialize the KuCoin clients
    market_client = Market(url=st.secrets["API_URL"])
    trade_client = Trade(key=st.secrets["API_KEY"], secret=st.secrets["API_SECRET"], passphrase=st.secrets["API_PASSPHRASE"], url=st.secrets["API_URL"])
    user_client = User(key=st.secrets["API_KEY"], secret=st.secrets["API_SECRET"], passphrase=st.secrets["API_PASSPHRASE"], url=st.secrets["API_URL"])

    # Initialize the trading bot
    bot = TradingBot(wallet, market_client, trade_client, user_client)
    bot.initialize_clients(st.secrets["API_KEY"], st.secrets["API_SECRET"], st.secrets["API_PASSPHRASE"], st.secrets["API_URL"])
    bot.is_simulation = is_simulation

    chosen_symbols = bot.get_user_symbol_choices(AVAILABLE_SYMBOLS)
    entry_prices = bot.get_entry_prices(chosen_symbols)

    total_usdt = bot.get_account_balance('USDT')
    st.sidebar.write(f"Confirmed USDT Balance: {total_usdt:.4f}")

    symbol_allocations, tradable_usdt = bot.get_user_allocations(chosen_symbols, total_usdt)
    profit_margin = bot.get_profit_margin()
    num_orders = st.sidebar.slider("Number of Orders", min_value=1, max_value=10, value=1, step=1)

    profits = {symbol: 0 for symbol in chosen_symbols}
    previous_status = None

    if st.sidebar.button("Start Trading"):
        st.empty()
        while True:
            try:
                prices = bot.get_current_prices(chosen_symbols)
                bot.update_price_history(chosen_symbols, prices)

                for symbol in chosen_symbols:
                    current_price = prices[symbol]
                    if current_price is None:
                        st.warning(f"Skipping {symbol} due to unavailable price data")
                        continue

                    if current_price < entry_prices[symbol]:
                        allocated_value = tradable_usdt * symbol_allocations[symbol]
                        base_currency = symbol.split('-')[1]
                        base_balance = bot.get_account_balance(base_currency)

                        # Check if we should buy
                        if base_balance > 0 and bot.should_buy(symbol, current_price):
                            buy_amount_usdt = min(allocated_value, base_balance)
                            if buy_amount_usdt > 0:
                                order_amount = buy_amount_usdt / num_orders
                                for _ in range(num_orders):
                                    order = bot.place_market_buy_order(symbol, order_amount)
                                    if order:
                                        target_sell_price = order['price'] * (1 + profit_margin + 2*bot.FEE_RATE)  # Account for buy and sell fees
                                        bot.active_trades[order['orderId']] = {
                                            'symbol': symbol,
                                            'buy_price': order['price'],
                                            'amount': order['amount'],
                                            'target_sell_price': target_sell_price,
                                            'fee_usdt': order['fee_usdt']
                                        }
                                        st.write(f"Placed buy order for {symbol}: {order_amount:.4f} USDT at {order['price']:.4f}, Order ID: {order['orderId']}")

                    # Check active trades for selling
                    for order_id, trade in list(bot.active_trades.items()):
                        if trade['symbol'] == symbol and current_price >= trade['target_sell_price']:
                            sell_amount_crypto = trade['amount']
                            sell_order = bot.place_market_sell_order(symbol, sell_amount_crypto)
                            if sell_order:
                                sell_amount_usdt = sell_order['amount_usdt']
                                total_fee = trade['fee_usdt'] + sell_order['fee_usdt']
                                profit = sell_amount_usdt - (trade['amount'] * trade['buy_price']) - total_fee
                                profits[symbol] += profit
                                total_profit += profit
                                st.write(f"Placed sell order for {symbol}: {sell_amount_usdt:.4f} USDT at {sell_order['price']:.4f}, Profit: {profit:.4f} USDT, Total Fee: {total_fee:.4f} USDT, Order ID: {sell_order['orderId']}")
                                del bot.active_trades[order_id]

                current_status = bot.get_current_status(prices, bot.active_trades, profits, total_profit)

                if current_status != previous_status:
                    st.empty()
                    bot.display_currency_status()
                    previous_status = current_status

                time.sleep(1)  # Check every second
            except Exception as e:
                st.error(f"An error occurred: {e}")
                st.write("Continuing with the next iteration...")
                time.sleep(1)

if __name__ == "__main__":
    main()