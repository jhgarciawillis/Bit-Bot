import os
import logging
from typing import Dict, List, Any
from kucoin.client import Market, Trade, User
import yaml

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
        API_KEY = os.environ.get('KUCOIN_API_KEY')
        API_SECRET = os.environ.get('KUCOIN_API_SECRET')
        API_PASSPHRASE = os.environ.get('KUCOIN_API_PASSPHRASE')
        API_URL = os.environ.get('KUCOIN_API_URL', 'https://api.kucoin.com')

        if not all([API_KEY, API_SECRET, API_PASSPHRASE]):
            raise ValueError("Missing KuCoin API credentials in environment variables")

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
            return [item['symbol'] for item in symbol_list if isinstance(item, dict) and 'symbol' in item and item['symbol'].endswith('-USDT')]
        else:
            logger.warning("Market client not initialized. Using default trading symbols.")
            return DEFAULT_TRADING_SYMBOLS
    except ConnectionError as e:
        logger.error(f"Connection error while fetching symbol list: {e}")
        return DEFAULT_TRADING_SYMBOLS
    except Exception as e:
        logger.error(f"Unexpected error fetching symbol list: {e}")
        return DEFAULT_TRADING_SYMBOLS

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
    Load configuration from a YAML file and environment variables.
    
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

    # Override with environment variables
    config['api_url'] = os.environ.get('KUCOIN_API_URL', config.get('api_url', 'https://api.kucoin.com'))
    
    # Merge with default configurations
    config['simulation_mode'] = {**SIMULATION_MODE, **config.get('simulation_mode', {})}
    config['chart_config'] = {**CHART_CONFIG, **config.get('chart_config', {})}
    config['bot_config'] = {**BOT_CONFIG, **config.get('bot_config', {})}
    config['error_config'] = {**ERROR_CONFIG, **config.get('error_config', {})}
    
    config['default_trading_symbols'] = config.get('default_trading_symbols', DEFAULT_TRADING_SYMBOLS)
    config['default_profit_margin'] = config.get('default_profit_margin', DEFAULT_PROFIT_MARGIN)
    config['default_num_orders'] = config.get('default_num_orders', DEFAULT_NUM_ORDERS)
    config['default_usdt_liquid_percentage'] = config.get('default_usdt_liquid_percentage', DEFAULT_USDT_LIQUID_PERCENTAGE)

    return config
