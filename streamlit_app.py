import streamlit as st
import time
import requests
from kucoin.client import Market, Trade, User
import config
from collections import deque
from statistics import mean, stdev
from datetime import datetime, timedelta

# Global variables
profits = {}
total_profit = 0
symbol_allocations = {}
usdt_liquid_percentage = 0
price_history = {}
active_trades = {}
PRICE_HISTORY_LENGTH = 30
simulated_balance = {}
is_simulation = False
num_orders = 1  # Default to 1, will be updated in simulation mode
market_client, trade_client, user_client = None, None, None
FEE_RATE = 0.001  # 0.1% fee rate, adjust if needed

def initialize_clients():
    global market_client, trade_client, user_client
    API_KEY = config.API_KEY
    API_SECRET = config.API_SECRET
    API_PASSPHRASE = config.API_PASSPHRASE
    API_URL = 'https://api.kucoin.com'

    market_client = Market(url=API_URL)
    trade_client = Trade(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE, url=API_URL)
    user_client = User(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE, url=API_URL)

def get_user_symbol_choices():
    symbols = st.sidebar.multiselect("Select Symbols to Trade", config.AVAILABLE_SYMBOLS)
    return symbols

def get_float_input(min_value, max_value):
    while True:
        try:
            value = st.sidebar.number_input("Enter the percentage of your assets to keep liquid in USDT (0-100%)", min_value=float(min_value), max_value=float(max_value), value=50.0, step=0.1) / 100
            if min_value <= value <= max_value:
                return value
            else:
                st.sidebar.error(f"Please enter a value between {min_value} and {max_value}.")
        except ValueError:
            st.sidebar.error("Please enter a valid number.")

def get_user_allocations(symbols, total_usdt):
    global usdt_liquid_percentage
    st.sidebar.write(f"Your current USDT balance in trading account: {total_usdt:.2f} USDT")
    
    usdt_liquid_percentage = get_float_input(0, 100)
    liquid_usdt = total_usdt * usdt_liquid_percentage
    st.sidebar.write(f"Amount to keep liquid in USDT: {liquid_usdt:.2f} USDT")

    tradable_usdt = total_usdt - liquid_usdt
    st.sidebar.write(f"USDT available for trading: {tradable_usdt:.2f} USDT")

    allocations = {}
    for symbol in symbols:
        allocations[symbol] = 1 / len(symbols)

    return allocations, tradable_usdt

def get_account_balance(currency='USDT'):
    if is_simulation:
        return simulated_balance.get(currency, 0)
    try:
        accounts = user_client.get_account_list(currency=currency, account_type='trade')
        if accounts:
            return float(accounts[0]['available'])
        else:
            st.sidebar.error(f"No account found for {currency}")
            return 0
    except Exception as e:
        st.sidebar.error(f"Error fetching account balance for {currency}: {e}")
        return 0

def get_current_prices(symbols):
    prices = {}
    for symbol in symbols:
        try:
            ticker = market_client.get_ticker(symbol)
            prices[symbol] = float(ticker['price'])
        except Exception as e:
            st.error(f"Error fetching price for {symbol}: {e}")
            prices[symbol] = None
    return prices

def place_market_buy_order(symbol, amount_usdt):
    current_price = get_current_prices([symbol])[symbol]
    if current_price is None:
        st.error(f"Unable to place buy order for {symbol} due to price fetch error")
        return None
    
    amount_usdt_with_fee = amount_usdt / (1 + FEE_RATE)
    amount_crypto = amount_usdt_with_fee / current_price
    fee_usdt = amount_usdt - amount_usdt_with_fee

    if is_simulation:
        order_id = f"sim_buy_{symbol}_{time.time()}"
        simulated_balance['USDT'] -= amount_usdt
        if symbol not in simulated_balance:
            simulated_balance[symbol] = 0
        simulated_balance[symbol] += amount_crypto
    else:
        try:
            order = trade_client.create_market_order(symbol, 'buy', funds=amount_usdt)
            order_id = order['orderId']
            # Fetch the actual execution price
            order_details = trade_client.get_order_details(order_id)
            current_price = float(order_details['dealFunds']) / float(order_details['dealSize'])
            amount_crypto = float(order_details['dealSize'])
            fee_usdt = float(order_details['fee'])
        except Exception as e:
            st.error(f"Error placing buy order for {symbol}: {e}")
            return None
    return {'orderId': order_id, 'price': current_price, 'amount': amount_crypto, 'fee_usdt': fee_usdt}

def place_market_sell_order(symbol, amount_crypto):
    current_price = get_current_prices([symbol])[symbol]
    if current_price is None:
        st.error(f"Unable to place sell order for {symbol} due to price fetch error")
        return None
    
    amount_usdt = amount_crypto * current_price
    fee_usdt = amount_usdt * FEE_RATE
    amount_usdt_after_fee = amount_usdt - fee_usdt

    if is_simulation:
        order_id = f"sim_sell_{symbol}_{time.time()}"
        simulated_balance['USDT'] += amount_usdt_after_fee
        simulated_balance[symbol] -= amount_crypto
    else:
        try:
            order = trade_client.create_market_order(symbol, 'sell', size=amount_crypto)
            order_id = order['orderId']
            # Fetch the actual execution price
            order_details = trade_client.get_order_details(order_id)
            current_price = float(order_details['dealFunds']) / float(order_details['dealSize'])
            amount_usdt_after_fee = float(order_details['dealFunds'])
            fee_usdt = float(order_details['fee'])
        except Exception as e:
            st.error(f"Error placing sell order for {symbol}: {e}")
            return None
    return {'orderId': order_id, 'price': current_price, 'amount_usdt': amount_usdt_after_fee, 'fee_usdt': fee_usdt}

def update_price_history(symbols, prices):
    for symbol in symbols:
        if symbol not in price_history:
            price_history[symbol] = deque(maxlen=PRICE_HISTORY_LENGTH)
        if prices[symbol] is not None:
            price_history[symbol].append(prices[symbol])

def should_buy(symbol, current_price):
    if current_price is None or len(price_history[symbol]) < PRICE_HISTORY_LENGTH:
        return False
    
    price_mean = mean(price_history[symbol])
    price_stdev = stdev(price_history[symbol]) if len(set(price_history[symbol])) > 1 else 0

    # Buy if the price is below the mean and within 1 standard deviation
    return current_price < price_mean and (price_mean - current_price) < price_stdev

def update_allocations(total_usdt):
    global symbol_allocations
    liquid_usdt = total_usdt * usdt_liquid_percentage
    tradable_usdt = max(total_usdt - liquid_usdt, 0)  # Ensure non-negative
    if tradable_usdt == 0:
        # Set all allocations to 0 if there's no tradable USDT
        symbol_allocations = {symbol: 0 for symbol in symbol_allocations}
    else:
        for symbol in symbol_allocations:
            symbol_allocations[symbol] = (symbol_allocations[symbol] * tradable_usdt) / total_usdt

def get_current_status(prices, active_trades, profits, total_profit, simulated_balance):
    if is_simulation:
        current_total_usdt = simulated_balance.get('USDT', 0)
    else:
        current_total_usdt = get_account_balance('USDT')
        for symbol in prices:
            crypto_currency = symbol.split('-')[0]
            current_total_usdt += get_account_balance(crypto_currency) * prices[symbol]

    liquid_usdt = current_total_usdt * usdt_liquid_percentage
    tradable_usdt = max(current_total_usdt - liquid_usdt, 0)
    return {
        'prices': prices,
        'active_trades': active_trades,
        'profits': profits.copy(),
        'total_profit': total_profit,
        'current_total_usdt': current_total_usdt,
        'tradable_usdt': tradable_usdt,
        'liquid_usdt': liquid_usdt,
        'simulated_balance': simulated_balance.copy() if is_simulation else {}
    }

def get_profit_margin():
    total_fee_percentage = FEE_RATE * 2 * 100  # Convert to percentage and account for both buy and sell
    st.sidebar.write(f"Note: The total trading fee is approximately {total_fee_percentage:.2f}% (buy + sell).")
    st.sidebar.write("Your profit margin should be higher than this to ensure profitability.")
    
    profit_margin = st.sidebar.slider("Profit Margin (%)", min_value=0.1, max_value=10.0, value=1.0, step=0.1) / 100

    if profit_margin <= total_fee_percentage / 100:
        st.sidebar.warning(f"Warning: Your chosen profit margin ({profit_margin*100:.2f}%) is lower than or equal to the total fee ({total_fee_percentage:.2f}%).")
        st.sidebar.warning("This may result in losses.")

    return profit_margin

def main():
    global total_profit, symbol_allocations, usdt_liquid_percentage, active_trades, market_client, trade_client, user_client, is_simulation, simulated_balance, num_orders

    st.title("Cryptocurrency Trading Bot")

    is_simulation = st.sidebar.checkbox("Simulation Mode", value=True)

    if is_simulation:
        st.sidebar.write("Running in simulation mode. No real trades will be executed.")
        simulated_balance['USDT'] = st.sidebar.number_input("Simulated USDT Balance", min_value=0.0, value=1000.0, step=0.1)
    else:
        st.sidebar.warning("WARNING: This bot will use real funds on the live KuCoin exchange.")
        st.sidebar.warning("Only proceed if you understand the risks and are using funds you can afford to lose.")
        proceed = st.sidebar.checkbox("I understand the risks and want to proceed")
        if not proceed:
            st.sidebar.error("Please check the box to proceed with live trading.")
            return

    initialize_clients()

    chosen_symbols = get_user_symbol_choices()

    total_usdt = get_account_balance('USDT')
    st.sidebar.write(f"Confirmed USDT Balance: {total_usdt:.2f}")

    symbol_allocations, tradable_usdt = get_user_allocations(chosen_symbols, total_usdt)
    profit_margin = get_profit_margin()
    num_orders = st.sidebar.slider("Number of Orders", min_value=1, max_value=10, value=1, step=1)

    profits = {symbol: 0 for symbol in chosen_symbols}
    previous_status = None

    if st.sidebar.button("Start Trading"):
        st.empty()
        while True:
            try:
                prices = get_current_prices(chosen_symbols)
                update_price_history(chosen_symbols, prices)

                for symbol in chosen_symbols:
                    current_price = prices[symbol]
                    if current_price is None:
                        st.warning(f"Skipping {symbol} due to unavailable price data")
                        continue

                    allocated_value = tradable_usdt * symbol_allocations[symbol]
                    base_currency = symbol.split('-')[1]
                    base_balance = get_account_balance(base_currency)

                    # Check if we should buy
                    if base_balance > 0 and should_buy(symbol, current_price):
                        buy_amount_usdt = min(allocated_value, base_balance)
                        if buy_amount_usdt > 0:
                            order_amount = buy_amount_usdt / num_orders
                            for _ in range(num_orders):
                                order = place_market_buy_order(symbol, order_amount)
                                if order:
                                    target_sell_price = order['price'] * (1 + profit_margin + 2*FEE_RATE)  # Account for buy and sell fees
                                    active_trades[order['orderId']] = {
                                        'symbol': symbol,
                                        'buy_price': order['price'],
                                        'amount': order['amount'],
                                        'target_sell_price': target_sell_price,
                                        'fee_usdt': order['fee_usdt']
                                    }
                                    st.write(f"Placed buy order for {symbol}: {order_amount:.2f} USDT at {order['price']}, Order ID: {order['orderId']}")

                    # Check active trades for selling
                    for order_id, trade in list(active_trades.items()):
                        if trade['symbol'] == symbol and current_price >= trade['target_sell_price']:
                            sell_amount_crypto = trade['amount']
                            sell_order = place_market_sell_order(symbol, sell_amount_crypto)
                            if sell_order:
                                sell_amount_usdt = sell_order['amount_usdt']
                                total_fee = trade['fee_usdt'] + sell_order['fee_usdt']
                                profit = sell_amount_usdt - (trade['amount'] * trade['buy_price']) - total_fee
                                profits[symbol] += profit
                                total_profit += profit
                                st.write(f"Placed sell order for {symbol}: {sell_amount_usdt:.2f} USDT at {sell_order['price']}, Profit: {profit:.2f} USDT, Total Fee: {total_fee:.2f} USDT, Order ID: {sell_order['orderId']}")
                                del active_trades[order_id]

                current_status = get_current_status(prices, active_trades, profits, total_profit, simulated_balance)

                if current_status != previous_status:
                    st.empty()
                    st.write("### Current Status")
                    st.write(f"Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    st.write("Current Prices, Buy Prices, and Target Sell Prices:")
                    for symbol, price in current_status['prices'].items():
                        st.write(f"- {symbol}:")
                        st.write(f"  - Current Price: {price:.2f} USDT")
                        buy_orders = [trade for trade in current_status['active_trades'].values() if trade['symbol'] == symbol]
                        if buy_orders:
                            for order in buy_orders:
                                st.write(f"  - Buy Price: {order['buy_price']:.2f} USDT")
                                st.write(f"  - Target Sell Price: {order['target_sell_price']:.2f} USDT")
                        else:
                            st.write("  - No Active Trades")
                    st.write(f"Active Trades: {len(current_status['active_trades'])}")
                    st.write("Active Trade Details:")
                    for order_id in current_status['active_trades']:
                        st.write(f"- {order_id}")
                    st.write(f"Profits per Trade: {current_status['profits']}")
                    st.write(f"Total Profit: {current_status['total_profit']:.2f} USDT")
                    st.write(f"Current Total USDT: {current_status['current_total_usdt']:.2f}")
                    st.write(f"Tradable USDT: {current_status['tradable_usdt']:.2f}")
                    st.write(f"Liquid USDT (not to be traded): {current_status['liquid_usdt']:.2f}")
                    if is_simulation:
                        st.write("Simulated Balances:")
                        for currency, balance in current_status['simulated_balance'].items():
                            st.write(f"- {currency}: {balance:.8f}")

                    previous_status = current_status

                time.sleep(1)  # Check every second
            except Exception as e:
                st.error(f"An error occurred: {e}")
                st.write("Continuing with the next iteration...")
                time.sleep(1)

if __name__ == "__main__":
    main()