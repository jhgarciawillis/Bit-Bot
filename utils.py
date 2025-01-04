import logging
from typing import Any, Callable
from kucoin.client import Client

logger = logging.getLogger(__name__)

def handle_errors(func: Callable) -> Callable:
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"An error occurred in {func.__name__}: {str(e)}")
            raise
    return wrapper

def handle_trading_errors(func: Callable) -> Callable:
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"An error occurred in {func.__name__}: {str(e)}")
    return wrapper

class KucoinClientManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(KucoinClientManager, cls).__new__(cls)
            cls._instance.client = None
        return cls._instance

    def initialize(self, api_key: str, api_secret: str, api_passphrase: str) -> None:
        try:
            logger.info("Initializing KuCoin client")
            self.client = Client(
                api_key=api_key,
                api_secret=api_secret,
                passphrase=api_passphrase,
                sandbox=False
            )
            # Test connection
            self.client.get_timestamp()
            logger.info("KuCoin client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize KuCoin client: {e}")
            raise

    def get_client(self) -> Client:
        return self.client

def create_simulated_trade_client(fees: dict, max_orders: int, allocations: dict) -> SimulatedTradeClient:
    return SimulatedTradeClient(fees, max_orders, allocations)