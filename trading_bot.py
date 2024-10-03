import logging
from typing import Dict, List, Any, Optional
import streamlit as st
from kucoin.client import Market, Trade, User
import time

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Default configurations
DEFAULT_CONFIG = {
    'trading_symbols': ['BTC-USDT', 'ETH-USDT', 'XRP-USDT', 'ADA-USDT', 'DOT-USDT'],
    'profit_margin': 0.0001,  # 0.01% (changed from 0.01)
    'num_orders': 1,
    'liquid_ratio': 0.5,  # 50%
    'simulation_mode': {
        'enabled': True,
        'initial_balance': 1000.0,
    },
    'chart_config': {
        'update_interval': 1,  # in seconds
        'history_length': 120,  # in minutes
        'height': 600,
        'width': 800,
    },
    'bot_config': {
        'update_interval': 1,  # in seconds
        'price_check_interval': 5,  # in seconds
    },
    'error_config': {
        'max_retries': 3,
        'retry_delay': 5,  # in seconds
    },
    'fees': {
        'maker': 0.001,  # 0.1%
        'taker': 0.001,  # 0.1%
    },
    'max_total_orders': 10,
    'currency_allocations': {},
}

class KucoinClientManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(KucoinClientManager, cls).__new__(cls)
            cls._instance.market_client = None
            cls._instance.trade_client = None
            cls._instance.user_client = None
        return cls._instance

    def initialize(self, api_key: str, api_secret: str, api_passphrase: str, api_url: str) -> None:
        try:
            logger.info("Initializing KuCoin clients.")
            self.market_client = Market(key=api_key, secret=api_secret, passphrase=api_passphrase, url=api_url)
            self.trade_client = Trade(key=api_key, secret=api_secret, passphrase=api_passphrase, url=api_url)
            self.user_client = User(key=api_key, secret=api_secret, passphrase=api_passphrase, url=api_url)
            logger.info("KuCoin clients initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize KuCoin clients: {e}")
            raise

    def get_client(self, client_type: type) -> Any:
        if client_type == Market:
            logger.info("Returning KuCoin Market client.")
            return self.market_client
        elif client_type == Trade:
            logger.info("Returning KuCoin Trade client.")
            return self.trade_client
        elif client_type == User:
            logger.info("Returning KuCoin User client.")
            return self.user_client
        else:
            logger.error(f"Unknown client type: {client_type}")
            raise ValueError(f"Unknown client type: {client_type}")

kucoin_client_manager = KucoinClientManager()

class ConfigManager:
    def __init__(self):
        self.config = None
        logger.info("Initializing KuCoin client.")
        self.initialize_kucoin_client()
        logger.info("Loading configuration.")
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        logger.info("Loading default configuration.")
        config = DEFAULT_CONFIG.copy()
        try:
            logger.info("Updating configuration with API credentials from Streamlit secrets.")
            config.update({
                'api_key': st.secrets["api_credentials"]["api_key"],
                'api_secret': st.secrets["api_credentials"]["api_secret"],
                'api_passphrase': st.secrets["api_credentials"]["api_passphrase"],
                'api_url': 'https://api.kucoin.com',
                'live_trading_access_key': st.secrets["api_credentials"]["live_trading_access_key"],
            })
        except KeyError as e:
            logger.error(f"Missing API credential in Streamlit secrets: {e}")
            raise
        return config

    def validate_trading_symbols(self, symbols: List[str]) -> List[str]:
        logger.info("Validating trading symbols.")
        available_symbols = self.get_available_trading_symbols()
        valid_symbols = [symbol for symbol in symbols if symbol in available_symbols]
        if len(valid_symbols) != len(symbols):
            logger.warning(f"Some trading symbols are not available: {set(symbols) - set(valid_symbols)}")
            logger.info(f"Using available trading symbols: {valid_symbols}")
        return valid_symbols

    def get_available_trading_symbols(self) -> List[str]:
        logger.info("Fetching available trading symbols.")
        try:
            market_client = kucoin_client_manager.get_client(Market)
            symbols = market_client.get_symbol_list()
            return [symbol['symbol'] for symbol in symbols if symbol['quoteCurrency'] == 'USDT']
        except Exception as e:
            logger.error(f"Unexpected error fetching symbol list: {e}")
            return []

    def verify_live_trading_access(self, input_key: str) -> bool:
        logger.info(f"Verifying live trading access key: {input_key}")
        return input_key == self.config['live_trading_access_key']

    def fetch_real_time_prices(self, symbols: List[str]) -> Dict[str, float]:
        logger.info(f"Fetching real-time prices for symbols: {symbols}")
        prices = {}
        try:
            market_client = kucoin_client_manager.get_client(Market)
            for symbol in symbols:
                logger.info(f"Fetching price for symbol: {symbol}")
                ticker = market_client.get_ticker(symbol)
                prices[symbol] = float(ticker['price'])
            logger.info(f"Fetched real-time prices: {prices}")
        except Exception as e:
            logger.error(f"Unexpected error fetching real-time prices: {e}")
        return prices

    def place_spot_order(self, symbol: str, side: str, price: float, size: float, is_simulation: bool = False) -> Dict[str, Any]:
        logger.info(f"Placing {side} order for {symbol} at price: {price}, size: {size}, simulation mode: {is_simulation}")
        try:
            if is_simulation:
                fee = size * price * self.config['fees']['taker']
                order = {
                    'orderId': f'sim_{side}_{symbol}_{time.time()}',
                    'symbol': symbol,
                    'side': side,
                    'price': price,
                    'size': size,
                    'fee': fee,
                    'dealSize': size,
                    'dealFunds': size * price,
                }
            else:
                trade_client = kucoin_client_manager.get_client(Trade)
                order = trade_client.create_limit_order(
                    symbol=symbol,
                    side=side,
                    price=str(price),
                    size=str(size)
                )
                # Fetch order details to get the actual filled amount and fees
                order_details = trade_client.get_order_details(order['orderId'])
                order.update({
                    'dealSize': float(order_details['dealSize']),
                    'dealFunds': float(order_details['dealFunds']),
                    'fee': float(order_details['fee']),
                })
            logger.info(f"{'Simulated' if is_simulation else 'Placed'} {side} order for {symbol}: {order}")
            return order
        except Exception as e:
            logger.error(f"Unexpected error {'simulating' if is_simulation else 'placing'} {side} order for {symbol}: {e}")
            return {}

    def initialize_kucoin_client(self) -> None:
        try:
            logger.info("Initializing KuCoin client with API credentials from Streamlit secrets.")
            kucoin_client_manager.initialize(
                st.secrets["api_credentials"]["api_key"],
                st.secrets["api_credentials"]["api_secret"],
                st.secrets["api_credentials"]["api_passphrase"],
                'https://api.kucoin.com'
            )
        except KeyError as e:
            logger.error(f"Missing API credential in Streamlit secrets: {e}")
            raise

    def get_account_list(self) -> List[Dict[str, Any]]:
        logger.info("Fetching account list from KuCoin.")
        try:
            user_client = kucoin_client_manager.get_client(User)
            return user_client.get_account_list()
        except Exception as e:
            logger.error(f"Unexpected error fetching account list: {e}")
            return []

    def update_config(self, key: str, value: Any) -> None:
        logger.info(f"Updating configuration: {key} = {value}")
        self.config[key] = value

    def get_config(self, key: str, default: Any = None) -> Any:
        logger.info(f"Getting configuration value for key: {key}")
        return self.config.get(key, default)

    def set_max_total_orders(self, max_orders: int) -> None:
        logger.info(f"Setting max total orders to: {max_orders}")
        self.config['max_total_orders'] = max_orders

    def get_max_total_orders(self) -> int:
        return self.config['max_total_orders']

    def set_currency_allocations(self, allocations: Dict[str, float]) -> None:
        logger.info(f"Setting currency allocations: {allocations}")
        self.config['currency_allocations'] = allocations

    def get_currency_allocations(self) -> Dict[str, float]:
        return self.config['currency_allocations']

config_manager = ConfigManager()

if __name__ == "__main__":
    logger.info("Running config.py as the main script.")
    logger.info(f"Loaded configuration: {config_manager.config}")
    symbols = config_manager.get_available_trading_symbols()
    logger.info(f"Available trading symbols: {symbols}")
    prices = config_manager.fetch_real_time_prices(config_manager.config['trading_symbols'])
    logger.info(f"Fetched real-time prices: {prices}")
