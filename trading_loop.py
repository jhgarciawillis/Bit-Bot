import time
import streamlit as st
from trading_bot import TradingBot
import logging

logger = logging.getLogger(__name__)

def trading_loop(bot: TradingBot, chosen_symbols, profit_margin, num_orders):
    while True:
        try:
            prices = bot.trading_client.get_current_prices(chosen_symbols)
            bot.update_price_history(chosen_symbols, prices)

            current_status = bot.get_current_status(prices)
            tradable_usdt = current_status['tradable_usdt']

            for symbol in chosen_symbols:
                current_price = prices[symbol]
                if current_price is None:
                    logger.warning(f"Skipping {symbol} due to unavailable price data")
                    continue

                allocated_value = bot.symbol_allocations[symbol] * tradable_usdt
                base_currency = symbol.split('-')[0]
                base_balance = bot.get_account_balance('USDT')  # We're always trading with USDT

                # Check if we should buy
                if base_balance > 0 and bot.should_buy(symbol, current_price):
                    buy_amount_usdt = min(allocated_value, base_balance)
                    if buy_amount_usdt > 0:
                        order_amount = buy_amount_usdt / num_orders
                        for _ in range(num_orders):
                            order = bot.place_market_buy_order(symbol, order_amount)
                            if order:
                                target_sell_price = order['price'] * (1 + profit_margin + 2*bot.FEE_RATE)
                                bot.active_trades[order['orderId']] = {
                                    'symbol': symbol,
                                    'buy_price': order['price'],
                                    'amount': order['amount'],
                                    'target_sell_price': target_sell_price,
                                    'fee_usdt': order['fee_usdt'],
                                    'buy_time': current_status['timestamp']
                                }
                                st.session_state.trade_messages.append(f"Placed buy order for {symbol}: {order_amount:.4f} USDT at {order['price']:.4f}, Order ID: {order['orderId']}")

                # Check active trades for selling
                for order_id, trade in list(bot.active_trades.items()):
                    if trade['symbol'] == symbol and current_price >= trade['target_sell_price']:
                        sell_amount_crypto = trade['amount']
                        sell_order = bot.place_market_sell_order(symbol, sell_amount_crypto, trade['target_sell_price'])
                        if sell_order:
                            sell_amount_usdt = sell_order['amount_usdt']
                            total_fee = trade['fee_usdt'] + sell_order['fee_usdt']
                            profit = sell_amount_usdt - (trade['amount'] * trade['buy_price']) - total_fee
                            bot.profits[symbol] += profit
                            bot.total_profit += profit
                            bot.total_trades += 1
                            bot.avg_profit_per_trade = bot.total_profit / bot.total_trades
                            st.session_state.trade_messages.append(f"Placed sell order for {symbol}: {sell_amount_usdt:.4f} USDT at {sell_order['price']:.4f}, Profit: {profit:.4f} USDT, Total Fee: {total_fee:.4f} USDT, Order ID: {sell_order['orderId']}")
                            del bot.active_trades[order_id]

            # Update allocations based on new total USDT value
            bot.update_allocations(current_status['current_total_usdt'], bot.usdt_liquid_percentage)

            # Display current status
            bot.display_current_status(current_status)

            # Sleep for a short duration before the next iteration
            time.sleep(1)

        except Exception as e:
            logger.error(f"An error occurred in the trading loop: {str(e)}")
            st.session_state.error_message = f"An error occurred: {str(e)}"
            time.sleep(5)  # Wait for 5 seconds before the next iteration
