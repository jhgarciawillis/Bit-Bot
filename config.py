import os
import logging
from typing import Dict, List, Any
import yaml
import streamlit as st
import asyncio
import random

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try to import KuCoin client, handle potential import errors
try:
    from kucoin.client import Market, Trade, User
    KUCOIN_IMPORT_SUCCESSFUL = True
except ImportError:
    logger.warning("Failed to import KuCoin client. Some features may not be available.")
    KUCOIN_IMPORT_SUCCESSFUL = False
    Market, Trade, User = None, None, None

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

async def initialize_clients() -> None:
    """Initialize KuCoin API clients asynchronously."""
    global market_client, trade_client, user_client

    if not KUCOIN_IMPORT_SUCCESSFUL:
        logger.error("KuCoin client import failed. Cannot initialize clients.")
        return

    try:
        API_KEY = st.secrets["api_credentials"]["api_key"]
        API_SECRET = st.secrets["api_credentials"]["api_secret"]
        API_PASSPHRASE = st.secrets["api_credentials"]["api_passphrase"]
        API_URL = 'https://api.kucoin.com'

        if not all([API_KEY, API_SECRET, API_PASSPHRASE]):
            raise ValueError("Missing KuCoin API credentials in Streamlit secrets")

        market_client = await asyncio.to_thread(Market, url=API_URL)
        trade_client = await asyncio.to_thread(Trade, key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE, url=API_URL)
        user_client = await asyncio.to_thread(User, key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE, url=API_URL)
        logger.info("Clients initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing clients: {e}")
        market_client = None
        trade_client = None
        user_client = None

async def get_available_trading_symbols() -> List[str]:
    """Fetch available trading symbols from KuCoin API asynchronously."""
    try:
        if market_client:
            symbol_list = await asyncio.to_thread(market_client.get_symbol_list)
            available_symbols = [item['symbol'] for item in symbol_list if isinstance(item, dict) and 'symbol' in item and item['symbol'].endswith('-USDT')]
            return available_symbols  # Keep the '-USDT' suffix
        else:
            logger.warning("Market client not initialized. Using default trading symbols.")
            return DEFAULT_TRADING_SYMBOLS
    except Exception as e:
        logger.error(f"Error fetching symbol list: {e}")
        return DEFAULT_TRADING_SYMBOLS

async def validate_default_trading_symbols(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and update the default trading symbols in the configuration asynchronously."""
    available_symbols = await get_available_trading_symbols()
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
CHART_CONFIG: Dict[str, Any] = {
    'update_interval': 1,  # in seconds
    'history_length': 120,  # in minutes
    'height': 600,
    'width': 800,
}

# Trading bot configuration
BOT_CONFIG: Dict[str, Any] = {
    'update_interval': 1,  # in seconds
    'price_check_interval': 5,  # in seconds
}

# Error handling configuration
ERROR_CONFIG: Dict[str, Any] = {
    'max_retries': 3,
    'retry_delay': 5,  # in seconds
}

async def load_config(config_file: str = 'config.yaml') -> Dict[str, Any]:
    """
    Load configuration from a YAML file and Streamlit secrets asynchronously.
    
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
    config = await validate_default_trading_symbols(config)

    return config

def verify_live_trading_access(input_key: str) -> bool:
    """
    Verify the live trading access key.
    
    :param input_key: The key input by the user
    :return: Boolean indicating whether the key is correct
    """
    correct_key = st.secrets["api_credentials"]["perso_key"]
    return input_key == correct_key

async def fetch_real_time_prices(symbols: List[str], is_simulation: bool = False) -> Dict[str, float]:
    """
    Fetch real-time prices for the given symbols using KuCoin API or simulate prices.
    
    :param symbols: List of trading symbols
    :param is_simulation: Boolean indicating whether to use simulated prices
    :return: Dictionary of symbol prices
    """
    prices = {}
    try:
        if is_simulation:
            for symbol in symbols:
                # Simulate price movements
                base_price = 100  # You can adjust this or use a different base for each symbol
                price_change = random.uniform(-0.001, 0.001)  # -0.1% to 0.1% change
                prices[symbol] = round(base_price * (1 + price_change), 2)
        else:
            for symbol in symbols:
                ticker = await asyncio.to_thread(market_client.get_ticker, symbol)
                prices[symbol] = float(ticker['price'])
        logger.info(f"Fetched {'simulated' if is_simulation else 'real-time'} prices: {prices}")
    except Exception as e:
        logger.error(f"Error fetching {'simulated' if is_simulation else 'real-time'} prices: {e}")
    return prices

async def place_spot_order(symbol: str, side: str, price: float, size: float, is_simulation: bool = False) -> Dict[str, Any]:
    """
    Place a spot order on KuCoin or simulate order placement.
    
    :param symbol: Trading symbol
    :param side: 'buy' or 'sell'
    :param price: Order price
    :param size: Order size
    :param is_simulation: Boolean indicating whether to simulate order placement
    :return: Order details
    """
    try:
        if is_simulation:
            # Simulate order placement
            order = {
                'orderId': f'sim_{side}_{symbol}_{asyncio.get_event_loop().time()}',
                'symbol': symbol,
                'side': side,
                'price': price,
                'size': size,
                'fee': size * price * 0.001  # Simulated 0.1% fee
            }
        else:
            order = await asyncio.to_thread(
                trade_client.create_limit_order,
                symbol=symbol,
                side=side,
                price=str(price),
                size=str(size)
            )
        logger.info(f"Placed {'simulated' if is_simulation else 'real'} {side} order for {symbol}: {order}")
        return order
    except Exception as e:
        logger.error(f"Error placing {'simulated' if is_simulation else 'real'} {side} order for {symbol}: {e}")
        return {}
