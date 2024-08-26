import logging
from typing import Dict, List, Any, Optional
import streamlit as st
from kucoin.client import Market, Trade, User

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Default trading symbols
DEFAULT_TRADING_SYMBOLS: List[str] = ['BTC-USDT', 'ETH-USDT', 'XRP-USDT', 'ADA-USDT', 'DOT-USDT']

# Trading parameters
DEFAULT_PROFIT_MARGIN: float = 0.01  # 1%
DEFAULT_NUM_ORDERS: int = 1
DEFAULT_USDT_LIQUID_PERCENTAGE: float = 0.5  # 50%

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
        self.market_client = Market(key=api_key, secret=api_secret, passphrase=api_passphrase, url=api_url)
        self.trade_client = Trade(key=api_key, secret=api_secret, passphrase=api_passphrase, url=api_url)
        self.user_client = User(key=api_key, secret=api_secret, passphrase=api_passphrase, url=api_url)

    def get_client(self, client_type: type) -> Any:
        if client_type == Market:
            return self.market_client
        elif client_type == Trade:
            return self.trade_client
        elif client_type == User:
            return self.user_client
        else:
            raise ValueError(f"Unknown client type: {client_type}")

kucoin_client_manager = KucoinClientManager()

def load_config() -> Dict[str, Any]:
    """
    Load configuration from Streamlit secrets and default values.
    """
    config = {
        'api_key': st.secrets["api_credentials"]["api_key"],
        'api_secret': st.secrets["api_credentials"]["api_secret"],
        'api_passphrase': st.secrets["api_credentials"]["api_passphrase"],
        'api_url': 'https://api.kucoin.com',  # You might want to add this to secrets if it can change
        'live_trading_access_key': st.secrets["api_credentials"]["live_trading_access_key"],
        'simulation_mode': SIMULATION_MODE,
        'chart_config': CHART_CONFIG,
        'bot_config': BOT_CONFIG,
        'error_config': ERROR_CONFIG,
        'default_usdt_liquid_percentage': DEFAULT_USDT_LIQUID_PERCENTAGE,
        'default_profit_margin': DEFAULT_PROFIT_MARGIN,
        'default_num_orders': DEFAULT_NUM_ORDERS,
        'default_trading_symbols': DEFAULT_TRADING_SYMBOLS,
    }
    
    # Validate and update the default trading symbols
    config = validate_default_trading_symbols(config)

    return config

def validate_default_trading_symbols(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and update the default trading symbols in the configuration."""
    available_symbols = get_available_trading_symbols(config)
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

def get_available_trading_symbols(config: Dict[str, Any]) -> List[str]:
    """Fetch available trading symbols from KuCoin API."""
    try:
        market_client = kucoin_client_manager.get_client(Market)
        symbols = market_client.get_symbol_list()
        available_symbols = [symbol['symbol'] for symbol in symbols if symbol['quoteCurrency'] == 'USDT']
        return available_symbols
    except Exception as e:
        logger.error(f"Unexpected error fetching symbol list: {e}")
        return DEFAULT_TRADING_SYMBOLS

def verify_live_trading_access(input_key: str) -> bool:
    """
    Verify the live trading access key.
    
    :param input_key: The key input by the user
    :return: Boolean indicating whether the key is correct
    """
    correct_key = st.secrets["api_credentials"]["live_trading_access_key"]
    return input_key == correct_key

def fetch_real_time_prices(symbols: List[str]) -> Dict[str, float]:
    """
    Fetch real-time prices for the given symbols using KuCoin API.
    
    :param symbols: List of trading symbols
    :return: Dictionary of symbol prices
    """
    prices = {}
    try:
        market_client = kucoin_client_manager.get_client(Market)
        for symbol in symbols:
            ticker = market_client.get_ticker(symbol)
            prices[symbol] = float(ticker['price'])
        logger.info(f"Fetched real-time prices: {prices}")
    except Exception as e:
        logger.error(f"Unexpected error fetching real-time prices: {e}")
    return prices

def place_spot_order(symbol: str, side: str, price: float, size: float, is_simulation: bool = False) -> Dict[str, Any]:
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
            import time
            order = {
                'orderId': f'sim_{side}_{symbol}_{time.time()}',
                'symbol': symbol,
                'side': side,
                'price': price,
                'size': size,
                'fee': size * price * 0.001  # Simulated 0.1% fee
            }
        else:
            trade_client = kucoin_client_manager.get_client(Trade)
            order = trade_client.create_limit_order(
                symbol=symbol,
                side=side,
                price=str(price),
                size=str(size)
            )
        logger.info(f"{'Simulated' if is_simulation else 'Placed'} {side} order for {symbol}: {order}")
        return order
    except Exception as e:
        logger.error(f"Unexpected error {'simulating' if is_simulation else 'placing'} {side} order for {symbol}: {e}")
        return {}

def initialize_kucoin_client(config: Dict[str, Any]) -> None:
    """Initialize the KuCoin client with the provided credentials."""
    kucoin_client_manager.initialize(config['api_key'], config['api_secret'], config['api_passphrase'], config['api_url'])

if __name__ == "__main__":
    # This block allows running config-related functions independently for testing
    config = load_config()
    print("Loaded configuration:", config)
    
    initialize_kucoin_client(config)
    
    symbols = get_available_trading_symbols(config)
    print("Available trading symbols:", symbols)
    
    prices = fetch_real_time_prices(config['default_trading_symbols'])
    print("Fetched real-time prices:", prices)
