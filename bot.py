import streamlit as st
import time
from collections import deque
from statistics import mean, stdev
from datetime import datetime
import pandas as pd
import random
from wallet import Wallet, Account, Currency

try:
    from kucoin.client import Market, Trade, User
except ImportError as e:
    if "pkg_resources" in str(e):
        st.warning("pkg_resources not found. Please install setuptools or update your environment.")
    else:
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
        self.wallet = Wallet()
        self.wallet.add_account("trading")
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
                value = st.sidebar.number_input(
                    label,
                    min_value=float(min_value),
                    max_value=float(max_value),
                    value=float(default_value),
                    step=float(step),
                    format="%.4f"
                )
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

    def get_account_balance(self, currency='USDT'):
        return self.wallet.get_account("trading").get_currency_balance(currency)

    def get_current_prices(self, symbols):
        prices = {}
        for symbol in symbols:
            if self.is_simulation:
                last_price = self.wallet.get_currency_history("trading", symbol.split('-')[0])['price_history'][-1][1] if self.wallet.get_currency_history("trading", symbol.split('-')[0])['price_history'] else 100
                change = (random.random() - 0.5) * 2  # Random price change between -1% and 1%
                price = last_price * (1 + change / 100)
            else:
                try:
                    ticker = self.market_client.get_ticker(symbol)
                    price = float(ticker['price'])
                except Exception as e:
                    st.error(f"Error fetching price for {symbol}: {e}")
                    price = None
            
            prices[symbol] = price
            if price is not None:
                self.wallet.update_currency_price("trading", symbol.split('-')[0], price)
        
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
            success = self.wallet.simulate_market_buy("trading", symbol.split('-')[0], amount_usdt, current_price)
            if not success:
                st.error(f"Insufficient funds to place buy order for {symbol}")
                return None
            order_id = f"sim_buy_{symbol}_{time.time()}"
        else:
            try:
                order = self.trade_client.create_market_order(symbol, 'buy', funds=amount_usdt)
                order_id = order['orderId']
                order_details = self.trade_client.get_order_details(order_id)
                current_price = float(order_details['dealFunds']) / float(order_details['dealSize'])
                amount_crypto = float(order_details['dealSize'])
                fee_usdt = float(order_details['fee'])
                self.wallet.update_account_balance("trading", "USDT", self.get_account_balance("USDT") - amount_usdt)
                self.wallet.update_account_balance("trading", symbol.split('-')[0], self.get_account_balance(symbol.split('-')[0]) + amount_crypto)
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
            success = self.wallet.simulate_market_sell("trading", symbol.split('-')[0], amount_crypto, current_price)
            if not success:
                st.error(f"Insufficient {symbol.split('-')[0]} to place sell order")
                return None
            order_id = f"sim_sell_{symbol}_{time.time()}"
        else:
            try:
                order = self.trade_client.create_market_order(symbol, 'sell', size=amount_crypto)
                order_id = order['orderId']
                order_details = self.trade_client.get_order_details(order_id)
                current_price = float(order_details['dealFunds']) / float(order_details['dealSize'])
                amount_usdt_after_fee = float(order_details['dealFunds'])
                fee_usdt = float(order_details['fee'])
                self.wallet.update_account_balance("trading", symbol.split('-')[0], self.get_account_balance(symbol.split('-')[0]) - amount_crypto)
                self.wallet.update_account_balance("trading", "USDT", self.get_account_balance("USDT") + amount_usdt_after_fee)
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
            'wallet_summary': self.wallet.get_account_summary()
        }
        
        self.status_history.append(status)
        return status

    def get_profit_margin(self):
        total_fee_percentage = self.FEE_RATE * 2 * 100
        st.sidebar.write(f"Note: The total trading fee is approximately {total_fee_percentage:.4f}% (buy + sell).")
        st.sidebar.write("Your profit margin should be higher than this to ensure profitability.")
        
        profit_margin = self.get_float_input(
            "Enter the desired profit margin percentage (0-100%)",
            0,
            100,
            1.0,
            0.0001
        )

        if profit_margin <= total_fee_percentage:
            st.sidebar.warning(f"Warning: Your chosen profit margin ({profit_margin:.4f}%) is lower than or equal to the total fee ({total_fee_percentage:.4f}%).")
            st.sidebar.warning("This may result in losses.")

        return profit_margin / 100  # Convert percentage to decimal

    def display_current_status(self, current_status):
        st.write("### Current Status")
        st.write(f"Current Time: {current_status['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Display current prices, buy prices, and target sell prices
        price_data = []
        for symbol, price in current_status['prices'].items():
            row = {"Symbol": symbol, "Current Price": f"{price:.4f} USDT"}
            buy_orders = [trade for trade in current_status['active_trades'].values() if trade['symbol'] == symbol]
            if buy_orders:
                row["Buy Price"] = f"{buy_orders[0]['buy_price']:.4f} USDT"
                row["Target Sell Price"] = f"{buy_orders[0]['target_sell_price']:.4f} USDT"
            else:
                row["Buy Price"] = "N/A"
                row["Target Sell Price"] = "N/A"
            price_data.append(row)
        
        st.table(pd.DataFrame(price_data))

        # Display active trades
        st.write(f"Active Trades: {len(current_status['active_trades'])}")
        if current_status['active_trades']:
            active_trades_data = [
                {
                    "Order ID": order_id,
                    "Symbol": trade['symbol'],
                    "Buy Price": f"{trade['buy_price']:.4f} USDT",
                    "Amount": f"{trade['amount']:.8f}",
                    "Target Sell Price": f"{trade['target_sell_price']:.4f} USDT"
                }
                for order_id, trade in current_status['active_trades'].items()
            ]
            st.table(pd.DataFrame(active_trades_data))

        # Display profits
        st.write(f"Profits per Symbol: {current_status['profits']}")
        st.write(f"Total Profit: {current_status['total_profit']:.4f} USDT")

        # Display account balances
        st.write(f"Current Total USDT: {current_status['current_total_usdt']:.4f}")
        st.write(f"Tradable USDT: {current_status['tradable_usdt']:.4f}")
        st.write(f"Liquid USDT (not to be traded): {current_status['liquid_usdt']:.4f}")

        # Display wallet summary
        st.write("### Wallet Summary")
        for account_type, account_data in current_status['wallet_summary'].items():
            st.write(f"Account: {account_type}")
            wallet_data = []
            for symbol, currency_data in account_data.items():
                wallet_data.append({
                    "Symbol": symbol,
                    "Balance": f"{currency_data['balance']:.8f}",
                    "Current Price": f"{currency_data['current_price']:.4f} USDT" if currency_data['current_price'] else "N/A"
                })
            st.table(pd.DataFrame(wallet_data))

    def display_current_status(self, current_status):
        # Display historical data as line charts
        st.write("### Historical Data")
        for symbol in current_status['prices'].keys():
            crypto_symbol = symbol.split('-')[0]
            history = self.wallet.get_currency_history("trading", crypto_symbol)
            if history and history['price_history']:
                df = pd.DataFrame(history['price_history'], columns=['timestamp', 'price'])
                df.set_index('timestamp', inplace=True)
                st.write(f"{symbol} Price History")
                st.line_chart(df)

                if history['buy_history'] or history['sell_history']:
                    trades_df = pd.DataFrame(
                        history['buy_history'] + history['sell_history'],
                        columns=['timestamp', 'amount', 'price', 'type']
                    )
                    trades_df['type'] = ['buy'] * len(history['buy_history']) + ['sell'] * len(history['sell_history'])
                    trades_df.set_index('timestamp', inplace=True)
                    st.write(f"{symbol} Trade History")
                    st.scatter_chart(trades_df, x='timestamp', y='price', color='type', size='amount')

        # Display status history as a line chart
        if len(self.status_history) > 1:
            status_df = pd.DataFrame([(s['timestamp'], s['current_total_usdt']) for s in self.status_history],
                                     columns=['timestamp', 'total_usdt'])
            status_df.set_index('timestamp', inplace=True)
            st.write("Total USDT Value Over Time")
            st.line_chart(status_df)
