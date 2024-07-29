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
    FEE_RATE = 0.001

    def __init__(self, api_key, api_secret, api_passphrase, api_url):
        self.trading_client = TradingClient(api_key, api_secret, api_passphrase, api_url)
        self.wallet = Wallet()
        self.wallet.add_account("trading")
        self.is_simulation = False
        self.profits = {}
        self.total_profit = 0
        self.symbol_allocations = {}
        self.usdt_liquid_percentage = 0
        self.price_history = {}
        self.active_trades = {}
        self.PRICE_HISTORY_LENGTH = 30
        self.total_trades = 0
        self.avg_profit_per_trade = 0
        self.status_history = []

    def initialize(self):
        self.trading_client.initialize()
        if not self.is_simulation:
            self.update_wallet_balances()

    def update_wallet_balances(self):
        if self.trading_client.user_client:
            try:
                accounts = self.trading_client.user_client.get_account_list()
                for account in accounts:
                    if account['type'] == 'trade':
                        self.wallet.update_account_balance("trading", account['currency'], float(account['available']))
                logger.info(f"Updated wallet balances: {self.wallet.get_account_summary()}")
            except Exception as e:
                logger.error(f"Error updating wallet balances: {e}")

    def get_account_balance(self, currency='USDT'):
        return self.wallet.get_account("trading").get_currency_balance(currency)

    def get_tradable_balance(self, currency='USDT'):
        return self.wallet.get_account("trading").get_currency_balance(currency)

    def get_user_allocations(self, user_selected_symbols, total_usdt_balance):
        tradable_usdt_amount = total_usdt_balance * (1 - self.usdt_liquid_percentage)
        
        if tradable_usdt_amount <= 0 or not user_selected_symbols:
            return {}, 0

        symbol_allocations = {symbol: 1 / len(user_selected_symbols) for symbol in user_selected_symbols}
        for symbol in user_selected_symbols:
            if symbol not in self.profits:
                self.profits[symbol] = 0
        
        return symbol_allocations, tradable_usdt_amount

    def update_price_history(self, symbols, prices):
        for symbol in symbols:
            if symbol not in self.price_history:
                self.price_history[symbol] = deque(maxlen=self.PRICE_HISTORY_LENGTH)
            if prices[symbol] is not None:
                self.price_history[symbol].append(prices[symbol])
                self.wallet.update_currency_price("trading", symbol.split('-')[0], prices[symbol])

    def should_buy(self, symbol, current_price):
        if current_price is None or len(self.price_history[symbol]) < self.PRICE_HISTORY_LENGTH:
            return None
        
        price_mean = mean(self.price_history[symbol])
        price_stdev = stdev(self.price_history[symbol]) if len(set(self.price_history[symbol])) > 1 else 0
        
        if current_price < price_mean and (price_mean - current_price) < price_stdev:
            return price_mean
        
        return None

    def place_limit_buy_order(self, symbol, amount_usdt, limit_price):
        amount_usdt_with_fee = amount_usdt / (1 + self.FEE_RATE)
        amount_crypto = amount_usdt_with_fee / limit_price
        fee_usdt = amount_usdt - amount_usdt_with_fee

        if self.is_simulation:
            order_id = f"sim_buy_{symbol}_{time.time()}"
            self.wallet.update_account_balance("trading", "USDT", self.get_account_balance('USDT') - amount_usdt)
            self.wallet.update_account_balance("trading", symbol.split('-')[0], self.get_account_balance(symbol.split('-')[0]) + amount_crypto)
        else:
            try:
                order = self.trading_client.trade_client.create_limit_order(symbol, 'buy', amount_crypto, limit_price)
                order_id = order['orderId']
                fee_usdt = float(order['fee'])
                self.update_wallet_balances()
            except Exception as e:
                logger.error(f"Error placing buy order for {symbol}: {e}")
                return None

        return {'orderId': order_id, 'price': limit_price, 'amount': amount_crypto, 'fee_usdt': fee_usdt}

    def place_limit_sell_order(self, symbol, amount_crypto, target_sell_price):
        if self.is_simulation:
            order_id = f"sim_sell_{symbol}_{time.time()}"
            self.wallet.update_account_balance("trading", "USDT", self.get_account_balance('USDT') + amount_crypto * target_sell_price)
            self.wallet.update_account_balance("trading", symbol.split('-')[0], self.get_account_balance(symbol.split('-')[0]) - amount_crypto)
            fee_usdt = amount_crypto * target_sell_price * self.FEE_RATE
        else:
            try:
                order = self.trading_client.trade_client.create_limit_order(symbol, 'sell', amount_crypto, target_sell_price)
                order_id = order['orderId']
                fee_usdt = float(order['fee'])
                self.update_wallet_balances()
            except Exception as e:
                logger.error(f"Error placing sell order for {symbol}: {e}")
                return None

        return {'orderId': order_id, 'price': target_sell_price, 'amount_usdt': amount_crypto * target_sell_price - fee_usdt, 'fee_usdt': fee_usdt}

    def get_current_status(self, prices):
        current_total_usdt = self.wallet.get_total_balance_in_usdt(lambda symbol: prices.get(symbol))
        liquid_usdt = current_total_usdt * self.usdt_liquid_percentage
        tradable_usdt = max(current_total_usdt - liquid_usdt, 0)
        
        status = {
            'timestamp': datetime.now(),
            'prices': prices,
            'active_trades': self.active_trades.copy(),
            'profits': self.profits.copy(),
            'total_profit': self.total_profit,
            'current_total_usdt': current_total_usdt,
            'tradable_usdt': tradable_usdt,
            'liquid_usdt': liquid_usdt,
            'wallet_summary': self.wallet.get_account_summary(),
            'total_trades': self.total_trades,
            'avg_profit_per_trade': self.avg_profit_per_trade,
        }
        
        self.status_history.append(status)
        
        return status

    def update_allocations(self, total_usdt, liquid_usdt_percentage):
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
