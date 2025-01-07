import logging
from typing import Any, Callable
from kucoin.client import Trade
import time
import uuid

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

    def initialize(self, key: str, secret: str, passphrase: str) -> None:
        try:
            logger.info("Initializing KuCoin client")
            self.client = Trade(
                key=key,
                secret=secret,
                passphrase=passphrase,
                is_sandbox=False
            )
            # Test connection
            self.client.get_timestamp()
            logger.info("KuCoin client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize KuCoin client: {e}")
            raise

    def get_client(self) -> Trade:
        return self.client

class SimulatedTradeClient:
    def __init__(self, fees: dict, max_total_orders: int, currency_allocations: dict):
        self.orders = {}
        self.MAKER_FEE = fees.get('maker', 0.001)  # Default 0.1%
        self.TAKER_FEE = fees.get('taker', 0.001)  # Default 0.1%
        self.max_total_orders = max_total_orders
        self.currency_allocations = currency_allocations

    def create_limit_order(self, symbol: str, side: str, price: str, size: str, **kwargs):
        if len(self.orders) >= self.max_total_orders:
            logger.warning(f"Maximum total orders ({self.max_total_orders}) reached")
            return {}

        order_id = str(uuid.uuid4())
        timestamp = int(time.time() * 1000)
        price = float(price)
        size = float(size)
        
        if side == Trade.SIDE_BUY:
            # Calculate initial USDT amount
            amount_usdt = size * price
            # Calculate fee in USDT
            fee_usdt = amount_usdt * self.TAKER_FEE
            # Calculate actual crypto amount received after fees
            actual_crypto_amount = (amount_usdt - fee_usdt) / price
            
            order = {
                'orderId': order_id,
                'symbol': symbol,
                'opType': 'DEAL',
                'type': Trade.ORDER_LIMIT,
                'side': side,
                'price': str(price),
                'size': str(actual_crypto_amount),
                'funds': str(amount_usdt),
                'dealFunds': str(amount_usdt),
                'dealSize': str(actual_crypto_amount),
                'fee': str(fee_usdt),
                'feeCurrency': symbol.split('-')[1],
                'createdAt': timestamp,
                'updatedAt': timestamp,
                'status': 'done',
                'timeInForce': kwargs.get('timeInForce', Trade.TIMEINFORCE_GOOD_TILL_CANCELLED),
                'postOnly': kwargs.get('postOnly', False),
                'hidden': kwargs.get('hidden', False),
                'iceberg': kwargs.get('iceberg', False),
                'visibleSize': kwargs.get('visibleSize', '0'),
                'cancelAfter': kwargs.get('cancelAfter', 0),
                'channel': 'API',
                'clientOid': kwargs.get('clientOid', f'simulated_{side}_{symbol}_{timestamp}'),
                'remark': kwargs.get('remark', None),
                'tags': kwargs.get('tags', None),
                'isActive': True,
                'cancelExist': False,
                'tradeType': 'TRADE'
            }
            
            logger.info(f"Created simulated buy order: {actual_crypto_amount:.8f} {symbol} "
                       f"at {price:.4f} USDT (Fee: {fee_usdt:.8f} USDT)")
            
        else:  # sell
            amount_crypto = size
            amount_usdt = amount_crypto * price
            fee_usdt = amount_usdt * self.TAKER_FEE
            actual_usdt_received = amount_usdt - fee_usdt
            
            order = {
                'orderId': order_id,
                'symbol': symbol,
                'opType': 'DEAL',
                'type': Trade.ORDER_LIMIT,
                'side': side,
                'price': str(price),
                'size': str(amount_crypto),
                'funds': str(actual_usdt_received),
                'dealFunds': str(amount_usdt),
                'dealSize': str(amount_crypto),
                'fee': str(fee_usdt),
                'feeCurrency': symbol.split('-')[1],
                'createdAt': timestamp,
                'updatedAt': timestamp,
                'status': 'done',
                'timeInForce': kwargs.get('timeInForce', Trade.TIMEINFORCE_GOOD_TILL_CANCELLED),
                'postOnly': kwargs.get('postOnly', False),
                'hidden': kwargs.get('hidden', False),
                'iceberg': kwargs.get('iceberg', False),
                'visibleSize': kwargs.get('visibleSize', '0'),
                'cancelAfter': kwargs.get('cancelAfter', 0),
                'channel': 'API',
                'clientOid': kwargs.get('clientOid', f'simulated_{side}_{symbol}_{timestamp}'),
                'remark': kwargs.get('remark', None),
                'tags': kwargs.get('tags', None),
                'isActive': True,
                'cancelExist': False,
                'tradeType': 'TRADE'
            }
            
            logger.info(f"Created simulated sell order: {amount_crypto:.8f} {symbol} "
                       f"at {price:.4f} USDT (Fee: {fee_usdt:.8f} USDT)")
        
        self.orders[order_id] = order
        return {'orderId': order_id}
    
    def get_order(self, order_id: str):
        return self.orders.get(order_id, {})

    def cancel_order(self, order_id: str):
        if order_id in self.orders:
            self.orders[order_id]['status'] = 'cancelled'
            self.orders[order_id]['isActive'] = False
            logger.info(f"Cancelled order: {order_id}")
            return {'cancelledOrderIds': [order_id]}
        return {'cancelledOrderIds': []}

    def get_fills(self, trade_type: str = 'TRADE', order_id: str = None):
        fills = []
        for order in self.orders.values():
            if order['status'] == 'done':
                if order_id is None or order['orderId'] == order_id:
                    fills.append({
                        'symbol': order['symbol'],
                        'tradeId': str(uuid.uuid4()),
                        'orderId': order['orderId'],
                        'counterOrderId': str(uuid.uuid4()),
                        'side': order['side'],
                        'liquidity': 'taker',
                        'forceTaker': True,
                        'price': order['price'],
                        'size': order['dealSize'],
                        'funds': order['dealFunds'],
                        'fee': order['fee'],
                        'feeRate': str(self.TAKER_FEE),
                        'feeCurrency': order['feeCurrency'],
                        'stop': '',
                        'type': 'limit',
                        'createdAt': order['createdAt'],
                        'tradeType': 'TRADE'
                    })
        return fills

    def get_orders(self, symbol: str = None, status: str = None):
        orders = []
        for order in self.orders.values():
            if (symbol is None or order['symbol'] == symbol) and \
               (status is None or 
                (status == 'active' and order['isActive']) or 
                (status == 'done' and not order['isActive'])):
                orders.append(order)
        return orders
    
def create_simulated_trade_client(fees: dict, max_total_orders: int, currency_allocations: dict) -> SimulatedTradeClient:
    return SimulatedTradeClient(fees, max_total_orders, currency_allocations)
