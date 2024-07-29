import time
import streamlit as st
import requests
from collections import deque
from statistics import mean, stdev
from datetime import datetime, timedelta
import pandas as pd
import random
import logging
from wallet import Wallet, Account, Currency

try:
    from kucoin.client import Market, Trade, User
except ImportError as e:
    logging.warning(f"KuCoin client import error: {type(e).__name__}")
    Market, Trade, User = None, None, None

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TradingClient:
    def __init__(self, api_key, api_secret, api_passphrase, api_url):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.api_url = api_url
        self.market_client = None
        self.trade_client = None
        self.user_client = None

    def initialize(self):
        logger.info("Initializing clients")
        if Market and Trade and User:
            try:
                self.market_client = Market(url=self.api_url)
                self.trade_client = Trade(key=self.api_key, secret=self.api_secret, passphrase=self.api_passphrase, url=self.api_url)
                self.user_client = User(key=self.api_key, secret=self.api_secret, passphrase=self.api_passphrase, url=self.api_url)
                logger.info("Clients initialized successfully")
            except Exception as e:
                logger.error(f"Error initializing clients: {type(e).__name__}")
                self.market_client = None
                self.trade_client = None
                self.user_client = None
        else:
            logger.warning("Running in simulation mode or KuCoin client not available.")

    def get_current_prices(self, symbols):
        prices = {}
        for symbol in symbols:
            try:
                if self.market_client:
                    ticker = self.market_client.get_ticker(symbol)
                    prices[symbol] = float(ticker['price'])
                else:
                    # Fallback to REST API if market_client is not available
                    response = requests.get(f"{self.api_url}/api/v1/market/orderbook/level1?symbol={symbol}")
                    response.raise_for_status()
                    prices[symbol] = float(response.json()['data']['price'])
            except Exception as e:
                logger.error(f"Error fetching price for {symbol}: {type(e).__name__}")
                prices[symbol] = None
        
        logger.info(f"Current prices: {prices}")
        return prices

    def place_market_order(self, symbol, amount, order_type):
        logger.debug(f"Placing {order_type} order for {symbol}")
        current_price = self.get_current_prices([symbol])[symbol]
        if current_price is None:
            logger.error(f"Unable to place {order_type} order for {symbol} due to price fetch error")
            st.error(f"Unable to place {order_type} order for {symbol} due to price fetch error")
            return None

        if order_type == 'buy':
            amount_usdt_with_fee = amount / (1 + TradingBot.FEE_RATE)
            amount_crypto = amount_usdt_with_fee / current_price
            fee_usdt = amount - amount_usdt_with_fee
        else:  # sell
            amount_usdt = amount * current_price
            fee_usdt = amount_usdt * TradingBot.FEE_RATE
            amount_usdt_after_fee = amount_usdt - fee_usdt

        if TradingBot.is_simulation:
            order_id = f"sim_{order_type}_{symbol}_{time.time()}"
        else:
            try:
                if order_type == 'buy':
                    order = self.trade_client.create_market_order(symbol, 'buy', funds=amount)
                else:
                    order = self.trade_client.create_market_order(symbol, 'sell', size=amount)
                order_id = order['orderId']
                order_details = self.trade_client.get_order_details(order_id)
                current_price = float(order_details['dealFunds']) / float(order_details['dealSize'])
                amount_crypto = float(order_details['dealSize'])
                fee_usdt = float(order_details['fee'])
            except Exception as e:
                logger.error(f"Error placing {order_type} order for {symbol}: {type(e).__name__}")
                st.error(f"Error placing {order_type} order for {symbol}: {type(e).__name__}")
                return None

        logger.info(f"Successfully placed {order_type} order for {symbol}")
        return {
            'orderId': order_id,
            'price': current_price,
            'amount': amount_crypto if order_type == 'buy' else amount_usdt_after_fee,
            'fee_usdt': fee_usdt
        }

class TradingBot:
    def __init__(self, api_key, api_secret, api_passphrase, api_url):
        self.trading_client = TradingClient(api_key, api_secret, api_passphrase, api_url)
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
        self.simulated_usdt_balance = 0
        self.num_orders = 1
        self.FEE_RATE = 0.001
        self.status_history = []

    def initialize(self):
        self.trading_client.initialize()

    def get_user_symbol_choices(self, available_symbols):
        logger.debug("Getting user symbol choices")
        return st.sidebar.multiselect("Select Symbols to Trade", available_symbols)

    def get_account_balance(self, currency='USDT'):
        logger.debug(f"Getting account balance for {currency}")
        if not self.is_simulation:
            try:
                account_balance = self.trading_client.user_client.get_account(currency, account_type='trade')
                return float(account_balance['available'])
            except Exception as e:
                logger.error(f"Error fetching account balance for {currency}: {type(e).__name__}")
                return 0
        else:
            return self.simulated_usdt_balance

    def print_total_usdt_balance(self):
        if self.is_simulation:
            total_usdt = self.simulated_usdt_balance
        else:
            total_usdt = self.get_account_balance('USDT')
        st.sidebar.write(f"Total USDT Balance: {total_usdt:.4f}")

    def get_user_allocations(self, symbols, total_usdt):
        logger.debug("Getting user allocations")
        
        st.sidebar.write(f"Your current USDT balance in trading account: {total_usdt:.4f} USDT")
        
        self.usdt_liquid_percentage = st.sidebar.number_input(
            "Enter the percentage of your assets to keep liquid in USDT (0-100%)",
            min_value=0.0,
            max_value=100.0,
            value=50.0,
            step=0.0001,
            format="%.4f"
        ) / 100
        
        liquid_usdt = total_usdt * self.usdt_liquid_percentage
        st.sidebar.write(f"Amount to keep liquid in USDT: {liquid_usdt:.4f} USDT")

        tradable_usdt = total_usdt - liquid_usdt
        st.sidebar.write(f"USDT available for trading: {tradable_usdt:.4f} USDT")

        if tradable_usdt <= 0:
            logger.warning("No USDT available for trading")
            return {}, 0

        allocations = {symbol: 1 / len(symbols) for symbol in symbols}
        
        # Initialize profits for new symbols
        for symbol in symbols:
            if symbol not in self.profits:
                self.profits[symbol] = 0
        
        return allocations, tradable_usdt

    def update_price_history(self, symbols, prices):
        logger.debug("Updating price history")
        for symbol in symbols:
            if symbol not in self.price_history:
                self.price_history[symbol] = deque(maxlen=self.PRICE_HISTORY_LENGTH)
            if prices[symbol] is not None:
                self.price_history[symbol].append(prices[symbol])
                
                if self.is_simulation:
                    self.wallet.update_currency_price("trading", symbol.split('-')[0], prices[symbol])

    def should_buy(self, symbol, current_price):
        logger.debug(f"Checking if should buy {symbol}")
        if current_price is None or len(self.price_history[symbol]) < self.PRICE_HISTORY_LENGTH:
            return False
        
        price_mean = mean(self.price_history[symbol])
        price_stdev = stdev(self.price_history[symbol]) if len(set(self.price_history[symbol])) > 1 else 0

        should_buy = current_price < price_mean and (price_mean - current_price) < price_stdev
        logger.debug(f"Should buy {symbol}: {should_buy}")
        return should_buy

    def update_allocations(self, total_usdt, liquid_usdt_percentage):
        logger.debug("Updating allocations")
        liquid_usdt = total_usdt * liquid_usdt_percentage
        tradable_usdt = max(total_usdt - liquid_usdt, 0)
        if tradable_usdt == 0:
            self.symbol_allocations = {symbol: 0 for symbol in self.symbol_allocations}
        else:
            total_allocation = sum(self.symbol_allocations.values())
            if total_allocation > 0:
                for symbol in self.symbol_allocations:
                    self.symbol_allocations[symbol] = (self.symbol_allocations[symbol] / total_allocation) * tradable_usdt
            else:
                equal_allocation = tradable_usdt / len(self.symbol_allocations)
                self.symbol_allocations = {symbol: equal_allocation for symbol in self.symbol_allocations}

    def get_current_status(self, prices):
        logger.debug("Getting current status")
        current_total_usdt = self.get_account_balance('USDT')
        for symbol, price in prices.items():
            crypto_currency = symbol.split('-')[0]
            if price is not None:
                current_total_usdt += self.get_account_balance(crypto_currency) * price
            else:
                logger.warning(f"Skipping {symbol} in total USDT calculation due to unavailable price")

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
            'wallet_summary': self.wallet.get_account_summary() if self.is_simulation else None
        }
        
        self.status_history.append(status)
        return status

    def place_market_buy_order(self, symbol, amount_usdt):
        if self.is_simulation:
            return self.trading_client.place_market_order(symbol, amount_usdt, 'buy')
        else:
            try:
                order = self.trading_client.trade_client.create_market_order(symbol, 'buy', funds=amount_usdt)
                logger.info(f"Placed buy order for {symbol}: {amount_usdt:.4f} USDT, Order ID: {order['orderId']}")
                return order
            except Exception as e:
                logger.error(f"Error placing buy order for {symbol}: {type(e).__name__}")
                return None

    def place_market_sell_order(self, symbol, amount_crypto):
        if self.is_simulation:
            return self.trading_client.place_market_order(symbol, amount_crypto, 'sell')
        else:
            try:
                order = self.trading_client.trade_client.create_market_order(symbol, 'sell', size=amount_crypto)
                logger.info(f"Placed sell order for {symbol}: {amount_crypto:.8f}, Order ID: {order['orderId']}")
                return order
            except Exception as e:
                logger.error(f"Error placing sell order for {symbol}: {type(e).__name__}")
                return None

    def display_current_status(self, current_status):
        logger.debug("Displaying current status")
        st.write("### Current Status")
        st.write(f"Current Time: {current_status['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")

        # Display current prices, buy prices, and target sell prices
        price_data = []
        for symbol, price in current_status['prices'].items():
            row = {"Symbol": symbol, "Current Price": f"{price:.4f} USDT" if price is not None else "N/A"}
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
        st.write("### Profits")
        st.write(f"Profits per Symbol: {current_status['profits']}")
        st.write(f"Total Profit: {current_status['total_profit']:.4f} USDT")

        # Display account balances
        st.write("### Account Balances")
        st.write(f"Current Total USDT: {current_status['current_total_usdt']:.4f}")
        st.write(f"Tradable USDT: {current_status['tradable_usdt']:.4f}")
        st.write(f"Liquid USDT (not to be traded): {current_status['liquid_usdt']:.4f}")

        # Display wallet summary for simulation mode
        if self.is_simulation and current_status['wallet_summary']:
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

        # Display historical data as line charts for simulation mode
        if self.is_simulation:
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
