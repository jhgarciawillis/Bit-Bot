import os
import logging
from typing import Dict, List, Any
from kucoin.client import Market, Trade, User
import yaml
import streamlit as st

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables
market_client: Market = None
trade_client: Trade = None
user_client: User = None

# Default trading symbols
DEFAULT_TRADING_SYMBOLS: List[str] = ['BTC-USDT', 'ETH-USDT', 'XRP-USDT', 'ADA-USDT', 'DOT-USDT']

# Trading parameters
DEFAULT_PROFIT_MARGIN: float = 0.01  # 1%
DEFAULT_NUM_ORDERS: int = 1
DEFAULT_USDT_LIQUID_PERCENTAGE: float = 0.5  # 50%

def initialize_clients() -> None:
    """Initialize KuCoin API clients."""
    global market_client, trade_client, user_client

    try:
        API_KEY = st.secrets["api_credentials"]["api_key"]
        API_SECRET = st.secrets["api_credentials"]["api_secret"]
        API_PASSPHRASE = st.secrets["api_credentials"]["api_passphrase"]
        API_URL = 'https://api.kucoin.com'

        if not all([API_KEY, API_SECRET, API_PASSPHRASE]):
            raise ValueError("Missing KuCoin API credentials in Streamlit secrets")

        market_client = Market(url=API_URL)
        trade_client = Trade(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE, url=API_URL)
        user_client = User(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE, url=API_URL)
        logger.info("Clients initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing clients: {e}")
        market_client = None
        trade_client = None
        user_client = None

def get_available_trading_symbols() -> List[str]:
    """Fetch available trading symbols from KuCoin API."""
    try:
        if market_client:
            symbol_list = market_client.get_symbol_list()
            available_symbols = [item['symbol'] for item in symbol_list if isinstance(item, dict) and 'symbol' in item and item['symbol'].endswith('-USDT')]
            available_symbols = [symbol.replace('-USDT', '') for symbol in available_symbols]
            return available_symbols
        else:
            logger.warning("Market client not initialized. Using default trading symbols.")
            return DEFAULT_TRADING_SYMBOLS
    except ConnectionError as e:
        logger.error(f"Connection error while fetching symbol list: {e}")
        return DEFAULT_TRADING_SYMBOLS
    except Exception as e:
        logger.error(f"Unexpected error fetching symbol list: {e}")
        return DEFAULT_TRADING_SYMBOLS

def validate_default_trading_symbols(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and update the default trading symbols in the configuration."""
    available_symbols = get_available_trading_symbols()
    default_trading_symbols = config.get('default_trading_symbols', DEFAULT_TRADING_SYMBOLS)

    # Check if the default trading symbols are available
    valid_default_symbols = [symbol for symbol in default_trading_symbols if symbol in available_symbols]

    # If any default symbols are not available, use the available symbols instead
    if len(valid_default_symbols) != len(default_trading_symbols):
        logger.warning(f"Some default trading symbols are not available: {set(default_trading_symbols) - set(available_symbols)}")
        logger.info(f"Using available trading symbols: {valid_default_symbols}")
        config['default_trading_symbols'] = valid_default_symbols
    else:
        config['default_trading_symbols'] = default_trading_symbols

    return config

# Configuration for simulation mode
SIMULATION_MODE: Dict[str, Any] = {
    'enabled': True,
    'initial_balance': 1000.0,
}

# Chart configuration
CHART_CONFIG: Dict[str, int] = {
    'update_interval': 1,  # in seconds
    'history_length': 120,  # in minutes
}

# Trading bot configuration
BOT_CONFIG: Dict[str, int] = {
    'update_interval': 1,  # in seconds
    'price_check_interval': 5,  # in seconds
}

# Error handling configuration
ERROR_CONFIG: Dict[str, int] = {
    'max_retries': 3,
    'retry_delay': 5,  # in seconds
}

def load_config(config_file: str = 'config.yaml') -> Dict[str, Any]:
    """
    Load configuration from a YAML file and Streamlit secrets.
    
    :param config_file: Path to the YAML configuration file
    :return: Dictionary containing the configuration
    """
    # Load configuration from YAML file
    try:
        with open(config_file, 'r') as file:
            config = yaml.safe_load(file)
    except FileNotFoundError:
        logger.warning(f"Configuration file {config_file} not found. Using default configuration.")
        config = {}

    # Override with Streamlit secrets
    config['api_url'] = 'https://api.kucoin.com'
    config['api_key'] = st.secrets["api_credentials"]["api_key"]
    config['api_secret'] = st.secrets["api_credentials"]["api_secret"]
    config['api_passphrase'] = st.secrets["api_credentials"]["api_passphrase"]
    config['live_trading_access_key'] = st.secrets["api_credentials"]["perso_key"]
    
    # Merge with default configurations
    config['simulation_mode'] = {**SIMULATION_MODE, **config.get('simulation_mode', {})}
    config['chart_config'] = {**CHART_CONFIG, **config.get('chart_config', {})}
    config['bot_config'] = {**BOT_CONFIG, **config.get('bot_config', {})}
    config['error_config'] = {**ERROR_CONFIG, **config.get('error_config', {})}
    
    # Ensure that the default_usdt_liquid_percentage is a valid value
    config['default_usdt_liquid_percentage'] = config.get('default_usdt_liquid_percentage', DEFAULT_USDT_LIQUID_PERCENTAGE)
    if config['default_usdt_liquid_percentage'] < 0 or config['default_usdt_liquid_percentage'] > 1:
        logger.warning(f"Invalid value for default_usdt_liquid_percentage: {config['default_usdt_liquid_percentage']}")
        config['default_usdt_liquid_percentage'] = DEFAULT_USDT_LIQUID_PERCENTAGE
        logger.info(f"Using default value for default_usdt_liquid_percentage: {DEFAULT_USDT_LIQUID_PERCENTAGE}")

    # Ensure that the default_profit_margin is a valid value
    config['default_profit_margin'] = config.get('default_profit_margin', DEFAULT_PROFIT_MARGIN)
    if config['default_profit_margin'] < 0 or config['default_profit_margin'] > 1:
        logger.warning(f"Invalid value for default_profit_margin: {config['default_profit_margin']}")
        config['default_profit_margin'] = DEFAULT_PROFIT_MARGIN
        logger.info(f"Using default value for default_profit_margin: {DEFAULT_PROFIT_MARGIN}")

    # Ensure that the default_num_orders is a valid value
    config['default_num_orders'] = config.get('default_num_orders', DEFAULT_NUM_ORDERS)
    if config['default_num_orders'] < 1 or config['default_num_orders'] > 10:
        logger.warning(f"Invalid value for default_num_orders: {config['default_num_orders']}")
        config['default_num_orders'] = DEFAULT_NUM_ORDERS
        logger.info(f"Using default value for default_num_orders: {DEFAULT_NUM_ORDERS}")

    # Validate and update the default trading symbols
    config = validate_default_trading_symbols(config)

    return config

def verify_live_trading_access(input_key: str) -> bool:
    """
    Verify the live trading access key.
    
    :param input_key: The key input by the user
    :return: Boolean indicating whether the key is correct
    """
    correct_key = st.secrets["api_credentials"]["perso_key"]
    return input_key == correct_key
