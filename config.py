import streamlit as st
import logging
from kucoin.client import Market, Trade, User

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables
market_client = None
trade_client = None
user_client = None

# Default trading symbols
DEFAULT_TRADING_SYMBOLS = ['BTC-USDT', 'ETH-USDT', 'XRP-USDT', 'ADA-USDT', 'DOT-USDT']

# Trading parameters
DEFAULT_PROFIT_MARGIN = 0.01  # 1%
DEFAULT_NUM_ORDERS = 1
DEFAULT_USDT_LIQUID_PERCENTAGE = 0.5  # 50%

def initialize_clients():
    global market_client, trade_client, user_client

    try:
        API_KEY = st.secrets["api_credentials"]["api_key"]
        API_SECRET = st.secrets["api_credentials"]["api_secret"]
        API_PASSPHRASE = st.secrets["api_credentials"]["api_passphrase"]
        API_URL = 'https://api.kucoin.com'

        market_client = Market(url=API_URL)
        trade_client = Trade(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE, url=API_URL)
        user_client = User(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE, url=API_URL)
        logger.info("Clients initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing clients: {e}")
        market_client = None
        trade_client = None
        user_client = None

def get_available_trading_symbols():
    try:
        if market_client:
            symbol_list = market_client.get_symbol_list()
            return [item['symbol'] for item in symbol_list if isinstance(item, dict) and 'symbol' in item and item['symbol'].endswith('-USDT')]
        else:
            logger.warning("Market client not initialized. Using default trading symbols.")
            return DEFAULT_TRADING_SYMBOLS
    except Exception as e:
        logger.error(f"Error fetching symbol list: {e}")
        return DEFAULT_TRADING_SYMBOLS

# Configuration for simulation mode
SIMULATION_MODE = {
    'enabled': True,
    'initial_balance': 1000.0,
}

# Chart configuration
CHART_CONFIG = {
    'update_interval': 1,  # in seconds
    'history_length': 120,  # in minutes
}

# Trading bot configuration
BOT_CONFIG = {
    'update_interval': 1,  # in seconds
    'price_check_interval': 5,  # in seconds
}

# Error handling configuration
ERROR_CONFIG = {
    'max_retries': 3,
    'retry_delay': 5,  # in seconds
}

def load_config():
    # This function can be expanded to load configuration from a file or environment variables
    return {
        'simulation_mode': SIMULATION_MODE,
        'chart_config': CHART_CONFIG,
        'bot_config': BOT_CONFIG,
        'error_config': ERROR_CONFIG,
        'default_trading_symbols': DEFAULT_TRADING_SYMBOLS,
        'default_profit_margin': DEFAULT_PROFIT_MARGIN,
        'default_num_orders': DEFAULT_NUM_ORDERS,
        'default_usdt_liquid_percentage': DEFAULT_USDT_LIQUID_PERCENTAGE,
    }
