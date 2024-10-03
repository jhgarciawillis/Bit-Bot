import time
import uuid
from typing import Dict, Any, List
from config import config_manager

class SimulatedTradeClient:
    def __init__(self):
        self.orders = {}
        self.fees = config_manager.get_config('fees')
        self.max_total_orders = config_manager.get_max_total_orders()
        self.currency_allocations = config_manager.get_currency_allocations()

    def create_limit_order(self, symbol: str, side: str, price: str, size: str) -> Dict[str, Any]:
        if len(self.orders) >= self.max_total_orders:
            return {}

        order_id = str(uuid.uuid4())
        timestamp = int(time.time() * 1000)
        price = float(price)
        size = float(size)
        
        if side == 'buy':
            amount_usdt = size * price
            fee_usdt = amount_usdt * self.fees['taker']
            amount_crypto = (amount_usdt - fee_usdt) / price
            
            order = {
                'id': order_id,
                'symbol': symbol,
                'opType': 'DEAL',
                'type': 'limit',
                'side': side,
                'price': str(price),
                'size': str(amount_crypto),
                'funds': str(amount_usdt),
                'dealFunds': str(amount_usdt),
                'dealSize': str(amount_crypto),
                'fee': str(fee_usdt),
                'feeCurrency': symbol.split('-')[1],
                'createdAt': timestamp,
                'updatedAt': timestamp,
                'status': 'done',
                'clientOid': f'simulated_{side}_{symbol}_{timestamp}'
            }
        else:  # sell
            amount_crypto = size
            amount_usdt = amount_crypto * price
            fee_usdt = amount_usdt * self.fees['taker']
            
            order = {
                'id': order_id,
                'symbol': symbol,
                'opType': 'DEAL',
                'type': 'limit',
                'side': side,
                'price': str(price),
                'size': str(amount_crypto),
                'funds': str(amount_usdt),
                'dealFunds': str(amount_usdt),
                'dealSize': str(amount_crypto),
                'fee': str(fee_usdt),
                'feeCurrency': symbol.split('-')[1],
                'createdAt': timestamp,
                'updatedAt': timestamp,
                'status': 'done',
                'clientOid': f'simulated_{side}_{symbol}_{timestamp}'
            }
        
        self.orders[order_id] = order
        return order

    def create_market_order(self, symbol: str, side: str, size: str) -> Dict[str, Any]:
        current_price = config_manager.fetch_real_time_prices([symbol])[symbol]
        return self.create_limit_order(symbol, side, str(current_price), size)

    def get_order_details(self, order_id: str) -> Dict[str, Any]:
        return self.orders.get(order_id, {})

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if order_id in self.orders:
            self.orders[order_id]['status'] = 'cancelled'
            return {'cancelledOrderIds': [order_id]}
        return {'cancelledOrderIds': []}

    def get_fill_list(self, **kwargs) -> List[Dict[str, Any]]:
        fills = []
        for order in self.orders.values():
            if order['status'] == 'done':
                fill = {
                    'symbol': order['symbol'],
                    'side': order['side'],
                    'price': order['price'],
                    'size': order['size'],
                    'fee': order['fee'],
                    'feeCurrency': order['feeCurrency'],
                    'createdAt': order['createdAt'],
                    'tradeId': str(uuid.uuid4()),
                    'orderId': order['id'],
                    'liquidity': 'taker',
                    'forceTaker': True
                }
                fills.append(fill)
        return fills

    def get_recent_fills(self) -> List[Dict[str, Any]]:
        return self.get_fill_list()[-100:]  # Return last 100 fills

    def get_order_list(self, **kwargs) -> List[Dict[str, Any]]:
        return list(self.orders.values())

    def update_max_total_orders(self, max_orders: int):
        self.max_total_orders = max_orders

    def update_currency_allocations(self, allocations: Dict[str, float]):
        self.currency_allocations = allocations

def create_simulated_trade_client() -> SimulatedTradeClient:
    return SimulatedTradeClient()
