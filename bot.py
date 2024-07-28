import streamlit as st
import time
from kucoin.client import Market, Trade, User
from collections import deque
from statistics import mean, stdev
from datetime import datetime, timedelta
import pandas as pd
from wallet import Wallet, Account, Currency
from config import PRICE_HISTORY_LENGTH, FEE_RATE

class TradingBot:
    def __init__(self, wallet, market_client, trade_client, user_client):
        self.wallet = wallet
        self.market_client = market_client
        self.trade_client = trade_client
        self.user_client = user_client
        self.profits = {}
        self.total_profit = 0
        self.symbol_allocations = {}
        self.usdt_liquid_percentage = 0
        self.price_history = {}
        self.active_trades = {}
        self.PRICE_HISTORY_LENGTH = 30
        self.is_simulation = False
        self.num_orders = 1
        self.FEE_RATE = 0.001
        self.status_history = []
        self.entry_prices = {}
        self.profit_margin = 0

    def initialize_clients(self, api_key, api_secret, api_passphrase, api_url):
        self.market_client = Market(url=api_url)
        self.trade_client = Trade(key=api_key, secret=api_secret, passphrase=api_passphrase, url=api_url)
        self.user_client = User(key=api_key, secret=api_secret, passphrase=api_passphrase, url=api_url)

    def get_user_symbol_choices(self):
        symbols = st.sidebar.multiselect("Select Symbols to Trade", config.AVAILABLE_SYMBOLS)
        return symbols

    def get_float_input(self, label, min_value, max_value, default_value, step):
        while True:
            try:
                value = st.sidebar.number_input(label, min_value=float(min_value), max_value=float(max_value), value=float(default_value), step=float(step))
                if min_value <= value <= max_value:
                    return value
                else:
                    st.sidebar.error(f"Please enter a value between {min_value} and {max_value}.")
            except ValueError:
                st.sidebar.error("Please enter a valid number.")

    def get_user_allocations(self, symbols, total_usdt):
        st.sidebar.write(f"Your current USDT balance in trading account: {total_usdt:.4f} USDT")
        
        self.usdt_liquid_percentage = self.get_float_input("Enter the percentage of your assets to keep liquid in USDT (0-100%)", 0, 100, 50.0, 0.0001) / 100
        liquid_usdt = total_usdt * self.usdt_liquid_percentage
        st.sidebar.write(f"Amount to keep liquid in USDT: {liquid_usdt:.4f} USDT")

        tradable_usdt = total_usdt - liquid_usdt
        st.sidebar.write(f"USDT available for trading: {tradable_usdt:.4f} USDT")

        allocations = {}
        for symbol in symbols:
            allocations[symbol] = 1 / len(symbols)

        return allocations, tradable_usdt

    def get_entry_prices(self, symbols):
        entry_prices = {}
        for symbol in symbols:
            entry_price = self.get_float_input(f"Enter the entry price for {symbol}", 0, float('inf'), 0, 0.0001)
            entry_prices[symbol] = entry_price
        return entry_prices

    def get_account_balance(self, currency_symbol):
        trading_account = self.wallet.get_account_by_type("trading")
        if trading_account:
            return trading_account.get_currency_balance(currency_symbol)
        return 0

    def get_current_prices(self, symbols):
        prices = {}
        for symbol in symbols:
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
            trading_account = self.wallet.get_account_by_type("trading")
            if trading_account:
                usdt_currency = trading_account.get_currency_balance("USDT")
                usdt_currency.balance -= amount_usdt
                crypto_currency = trading_account.get_currency_balance(symbol)
                if crypto_currency:
                    crypto_currency.balance += amount_crypto
                else:
                    trading_account.add_currency(Currency(symbol, amount_crypto))
        else:
            try:
                order = self.trade_client.create_market_order(symbol, 'buy', funds=amount_usdt)
                order_id = order['orderId']
                # Fetch the actual execution price
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
            trading_account = self.wallet.get_account_by_type("trading")
            if trading_account:
                usdt_currency = trading_account.get_currency_balance("USDT")
                usdt_currency.balance += amount_usdt_after_fee
                crypto_currency = trading_account.get_currency_balance(symbol)
                crypto_currency.balance -= amount_crypto
        else:
            try:
                order = self.trade_client.create_market_order(symbol, 'sell', size=amount_crypto)
                order_id = order['orderId']
                # Fetch the actual execution price
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

        # Buy if the price is below the mean and within 1 standard deviation
        return current_price < price_mean and (price_mean - current_price) < price_stdev

    def update_allocations(self, total_usdt):
        liquid_usdt = total_usdt * self.usdt_liquid_percentage
        tradable_usdt = max(total_usdt - liquid_usdt, 0)  # Ensure non-negative
        if tradable_usdt == 0:
            # Set all allocations to 0 if there's no tradable USDT
            self.symbol_allocations = {symbol: 0 for symbol in self.symbol_allocations}
        else:
            for symbol in self.symbol_allocations:
                self.symbol_allocations[symbol] = (self.symbol_allocations[symbol] * tradable_usdt) / total_usdt

    def get_current_status(self, prices, active_trades, profits, total_profit):
        if self.is_simulation:
            trading_account = self.wallet.get_account_by_type("trading")
            current_total_usdt = trading_account.get_currency_balance("USDT")
            for symbol in prices:
                current_total_usdt += trading_account.get_currency_balance(symbol) * prices[symbol]
        else:
            current_total_usdt = self.get_account_balance('USDT')
            for symbol in prices:
                crypto_currency = symbol.split('-')[0]
                current_total_usdt += self.get_account_balance(crypto_currency) * prices[symbol]

        liquid_usdt = current_total_usdt * self.usdt_liquid_percentage
        tradable_usdt = max(current_total_usdt - liquid_usdt, 0)

        status = {
            'timestamp': datetime.now(),
            'prices': prices,
            'active_trades': active_trades,
            'profits': profits.copy(),
            'total_profit': total_profit,
            'current_total_usdt': current_total_usdt,
            'tradable_usdt': tradable_usdt,
            'liquid_usdt': liquid_usdt,
            'usdt_liquid_percentage': self.usdt_liquid_percentage,
            'profit_margin': self.profit_margin
        }

        self.status_history.append(status)

        return status

    def get_profit_margin(self):
        total_fee_percentage = self.FEE_RATE * 2 * 100  # Convert to percentage and account for both buy and sell
        st.sidebar.write(f"Note: The total trading fee is approximately {total_fee_percentage:.4f}% (buy + sell).")
        st.sidebar.write("Your profit margin should be higher than this to ensure profitability.")
        
        self.profit_margin = self.get_float_input("Enter the desired profit margin percentage (0-100%)", 0, 100, 1.0, 0.0001) / 100

        if self.profit_margin <= total_fee_percentage / 100:
            st.sidebar.warning(f"Warning: Your chosen profit margin ({self.profit_margin*100:.4f}%) is lower than or equal to the total fee ({total_fee_percentage:.4f}%).")
            st.sidebar.warning("This may result in losses.")

        return self.profit_margin

    def display_currency_status(self):
        st.subheader("Currency Status")

        if len(self.status_history) > 0:
            latest_status = self.status_history[-1]

            st.write(f"Current Time: {latest_status['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
            st.write(f"Total Profit: {latest_status['total_profit']:.4f} USDT")
            st.write(f"Current Total USDT: {latest_status['current_total_usdt']:.4f}")
            st.write(f"Tradable USDT: {latest_status['tradable_usdt']:.4f}")
            st.write(f"Liquid USDT (not to be traded): {latest_status['liquid_usdt']:.4f}")
            st.write(f"USDT Liquid Percentage: {latest_status['usdt_liquid_percentage']:.4%}")
            st.write(f"Profit Margin: {latest_status['profit_margin']:.4%}")

            # Display currency balances in the wallet
            st.write("Wallet Balances:")
            trading_account = self.wallet.get_account_by_type("trading")
            if trading_account:
                for currency in trading_account.currencies:
                    st.write(f"- {currency.symbol}: {currency.balance:.8f}")

            # Display current prices and profits for each symbol
            st.write("Current Prices and Profits:")
            for symbol, price in latest_status['prices'].items():
                st.write(f"- {symbol}: Price: {price:.4f} USDT, Profit: {latest_status['profits'][symbol]:.4f} USDT")

            # Display status history in a table
            status_df = pd.DataFrame(self.status_history)
            status_df['timestamp'] = status_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
            st.write("Status History:")
            st.dataframe(status_df)
        else:
            st.write("No data available yet.")