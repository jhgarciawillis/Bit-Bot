import streamlit as st
import time
from collections import deque
from statistics import mean, stdev
from datetime import datetime
import pandas as pd

try:
    from kucoin.client import Market, Trade, User
except ImportError:
    st.warning("KuCoin client not available. Running in simulation mode only.")
    Market, Trade, User = None, None, None

class TradingBot:
    def __init__(self, api_key, api_secret, api_passphrase, api_url):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.api_url = api_url
        self.market_client = None
        self.trade_client = None
        self.user_client = None
        self.profits = {}
        self.total_profit = 0
        self.symbol_allocations = {}
        self.usdt_liquid_percentage = 0
        self.price_history = {}
        self.active_trades = {}
        self.PRICE_HISTORY_LENGTH = 30
        self.simulated_balance = {}
        self.is_simulation = False
        self.num_orders = 1
        self.FEE_RATE = 0.001
        self.status_history = []

    def initialize_clients(self):
        if not self.is_simulation and Market and Trade and User:
            self.market_client = Market(url=self.api_url)
            self.trade_client = Trade(key=self.api_key, secret=self.api_secret, passphrase=self.api_passphrase, url=self.api_url)
            self.user_client = User(key=self.api_key, secret=self.api_secret, passphrase=self.api_passphrase, url=self.api_url)
        else:
            st.warning("Running in simulation mode or KuCoin client not available.")

    def get_user_symbol_choices(self, available_symbols):
        return st.sidebar.multiselect("Select Symbols to Trade", available_symbols)

    def get_float_input(self, label, min_value, max_value, default_value, step):
        while True:
            try:
                value = st.sidebar.number_input(label, min_value=float(min_value), max_value=float(max_value), value=float(default_value), step=float(step)) / 100
                if min_value <= value <= max_value:
                    return value
                else:
                    st.sidebar.error(f"Please enter a value between {min_value} and {max_value}.")
            except ValueError:
                st.sidebar.error("Please enter a valid number.")

    def get_user_allocations(self, symbols, total_usdt):
        st.sidebar.write(f"Your current USDT balance in trading account: {total_usdt:.2f} USDT")
        
        self.usdt_liquid_percentage = self.get_float_input("Enter the percentage of your assets to keep liquid in USDT (0-100%)", 0, 100, 50.0, 0.1)
        liquid_usdt = total_usdt * self.usdt_liquid_percentage
        st.sidebar.write(f"Amount to keep liquid in USDT: {liquid_usdt:.2f} USDT")

        tradable_usdt = total_usdt - liquid_usdt
        st.sidebar.write(f"USDT available for trading: {tradable_usdt:.2f} USDT")

        allocations = {}
        for symbol in symbols:
            allocations[symbol] = 1 / len(symbols)

        return allocations, tradable_usdt

    def get_account_balance(self, currency='USDT'):
        if self.is_simulation:
            return self.simulated_balance.get(currency, 0)
        try:
            accounts = self.user_client.get_account_list(currency=currency, account_type='trade')
            if accounts:
                return float(accounts[0]['available'])
            else:
                st.sidebar.error(f"No account found for {currency}")
                return 0
        except Exception as e:
            st.sidebar.error(f"Error fetching account balance for {currency}: {e}")
            return 0

    def get_current_prices(self, symbols):
        prices = {}
        for symbol in symbols:
            if self.is_simulation:
                # Simulate price movement
                last_price = self.price_history[symbol][-1] if symbol in self.price_history and self.price_history[symbol] else 100
                change = (random.random() - 0.5) * 2  # Random price change between -1% and 1%
                prices[symbol] = last_price * (1 + change / 100)
            else:
                try:
                    ticker = self.market_client.get_ticker(symbol)
                    prices[symbol] = float(ticker['price'])
                except Exception as e:
                    st.error(f"Error fetching price for {symbol}: {e}")
                    prices[symbol] = None
        return prices

    def place_market_buy_order(self, symbol, amount_usdt):
        current_price = self.get_current_prices([symbol])[symbol]
        if current_price is None:
            st.error(f"Unable to place buy order for {symbol} due to price fetch error")
            return None
        
        amount_usdt_with_fee = amount_usdt / (1 + self.FEE_RATE)
        amount_crypto = amount_usdt_with_fee / current_price
        fee_usdt = amount_usdt - amount_usdt_with_fee

        if self.is_simulation:
            order_id = f"sim_buy_{symbol}_{time.time()}"
            self.simulated_balance['USDT'] -= amount_usdt
            if symbol not in self.simulated_balance:
                self.simulated_balance[symbol] = 0
            self.simulated_balance[symbol] += amount_crypto
        else:
            try:
                order = self.trade_client.create_market_order(symbol, 'buy', funds=amount_usdt)
                order_id = order['orderId']
                order_details = self.trade_client.get_order_details(order_id)
                current_price = float(order_details['dealFunds']) / float(order_details['dealSize'])
                amount_crypto = float(order_details['dealSize'])
                fee_usdt = float(order_details['fee'])
            except Exception as e:
                st.error(f"Error placing buy order for {symbol}: {e}")
                return None
        return {'orderId': order_id, 'price': current_price, 'amount': amount_crypto, 'fee_usdt': fee_usdt}

    def place_market_sell_order(self, symbol, amount_crypto):
        current_price = self.get_current_prices([symbol])[symbol]
        if current_price is None:
            st.error(f"Unable to place sell order for {symbol} due to price fetch error")
            return None
        
        amount_usdt = amount_crypto * current_price
        fee_usdt = amount_usdt * self.FEE_RATE
        amount_usdt_after_fee = amount_usdt - fee_usdt

        if self.is_simulation:
            order_id = f"sim_sell_{symbol}_{time.time()}"
            self.simulated_balance['USDT'] += amount_usdt_after_fee
            self.simulated_balance[symbol] -= amount_crypto
        else:
            try:
                order = self.trade_client.create_market_order(symbol, 'sell', size=amount_crypto)
                order_id = order['orderId']
                order_details = self.trade_client.get_order_details(order_id)
                current_price = float(order_details['dealFunds']) / float(order_details['dealSize'])
                amount_usdt_after_fee = float(order_details['dealFunds'])
                fee_usdt = float(order_details['fee'])
            except Exception as e:
                st.error(f"Error placing sell order for {symbol}: {e}")
                return None
        return {'orderId': order_id, 'price': current_price, 'amount_usdt': amount_usdt_after_fee, 'fee_usdt': fee_usdt}

    def update_price_history(self, symbols, prices):
        for symbol in symbols:
            if symbol not in self.price_history:
                self.price_history[symbol] = deque(maxlen=self.PRICE_HISTORY_LENGTH)
            if prices[symbol] is not None:
                self.price_history[symbol].append(prices[symbol])

    def should_buy(self, symbol, current_price):
        if current_price is None or len(self.price_history[symbol]) < self.PRICE_HISTORY_LENGTH:
            return False
        
        price_mean = mean(self.price_history[symbol])
        price_stdev = stdev(self.price_history[symbol]) if len(set(self.price_history[symbol])) > 1 else 0

        return current_price < price_mean and (price_mean - current_price) < price_stdev

    def update_allocations(self, total_usdt):
        liquid_usdt = total_usdt * self.usdt_liquid_percentage
        tradable_usdt = max(total_usdt - liquid_usdt, 0)
        if tradable_usdt == 0:
            self.symbol_allocations = {symbol: 0 for symbol in self.symbol_allocations}
        else:
            for symbol in self.symbol_allocations:
                self.symbol_allocations[symbol] = (self.symbol_allocations[symbol] * tradable_usdt) / total_usdt

    def get_current_status(self, prices):
        if self.is_simulation:
            current_total_usdt = self.simulated_balance.get('USDT', 0)
            for symbol, price in prices.items():
                current_total_usdt += self.simulated_balance.get(symbol, 0) * price
        else:
            current_total_usdt = self.get_account_balance('USDT')
            for symbol, price in prices.items():
                crypto_currency = symbol.split('-')[0]
                current_total_usdt += self.get_account_balance(crypto_currency) * price

        liquid_usdt = current_total_usdt * self.usdt_liquid_percentage
        tradable_usdt = max(current_total_usdt - liquid_usdt, 0)
        
        status = {
            'timestamp': datetime.now(),
            'prices': prices,
            'active_trades': self.active_trades,
            'profits': self.profits.copy(),
            'total_profit': self.total_profit,
            'current_total_usdt': current_total_usdt,
            'tradable_usdt': tradable_usdt,
            'liquid_usdt': liquid_usdt,
            'simulated_balance': self.simulated_balance.copy() if self.is_simulation else {}
        }
        
        self.status_history.append(status)
        return status

    def get_profit_margin(self):
        total_fee_percentage = self.FEE_RATE * 2 * 100
        st.sidebar.write(f"Note: The total trading fee is approximately {total_fee_percentage:.2f}% (buy + sell).")
        st.sidebar.write("Your profit margin should be higher than this to ensure profitability.")
        
        profit_margin = st.sidebar.slider("Profit Margin (%)", min_value=0.1, max_value=10.0, value=1.0, step=0.1) / 100

        if profit_margin <= total_fee_percentage / 100:
            st.sidebar.warning(f"Warning: Your chosen profit margin ({profit_margin*100:.2f}%) is lower than or equal to the total fee ({total_fee_percentage:.2f}%).")
            st.sidebar.warning("This may result in losses.")

        return profit_margin

    def display_current_status(self, current_status):
        st.write("### Current Status")
        st.write(f"Current Time: {current_status['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        st.write("Current Prices, Buy Prices, and Target Sell Prices:")
        for symbol, price in current_status['prices'].items():
            st.write(f"- {symbol}:")
            st.write(f"  - Current Price: {price:.4f} USDT")
            buy_orders = [trade for trade in current_status['active_trades'].values() if trade['symbol'] == symbol]
            if buy_orders:
                for order in buy_orders:
                    st.write(f"  - Buy Price: {order['buy_price']:.4f} USDT")
                    st.write(f"  - Target Sell Price: {order['target_sell_price']:.4f} USDT")
            else:
                st.write("  - No Active Trades")
        st.write(f"Active Trades: {len(current_status['active_trades'])}")
        st.write("Active Trade Details:")
        for order_id, trade in current_status['active_trades'].items():
            st.write(f"- Order ID: {order_id}")
            st.write(f"  Symbol: {trade['symbol']}")
            st.write(f"  Buy Price: {trade['buy_price']:.4f} USDT")
            st.write(f"  Amount: {trade['amount']:.8f}")
            st.write(f"  Target Sell Price: {trade['target_sell_price']:.4f} USDT")
        st.write(f"Profits per Symbol: {current_status['profits']}")
        st.write(f"Total Profit: {current_status['total_profit']:.4f} USDT")
        st.write(f"Current Total USDT: {current_status['current_total_usdt']:.4f}")
        st.write(f"Tradable USDT: {current_status['tradable_usdt']:.4f}")
        st.write(f"Liquid USDT (not to be traded): {current_status['liquid_usdt']:.4f}")
        if self.is_simulation:
            st.write("Simulated Balances:")
            for currency, balance in current_status['simulated_balance'].items():
                st.write(f"- {currency}: {balance:.8f}")

        # Display status history in a table
        if len(self.status_history) > 1:  # Only show if there's more than one status update
            status_df = pd.DataFrame(self.status_history)
            status_df['timestamp'] = status_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
            st.write("Status History:")
            st.dataframe(status_df)
