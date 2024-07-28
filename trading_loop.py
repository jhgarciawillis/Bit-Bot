import time
import streamlit as st
from datetime import datetime
from trading_bot import TradingBot

def safe_divide(numerator, denominator):
    return numerator / denominator if denominator != 0 else 0

def trading_loop(bot, chosen_symbols, profit_margin, num_orders):
    while True:
        try:
            # Fetch current prices
            prices = bot.get_current_prices(chosen_symbols)
            if not prices:
                raise ValueError("Failed to fetch current prices")

            bot.update_price_history(chosen_symbols, prices)

            current_status = bot.get_current_status(prices)
            if current_status['tradable_usdt'] <= 0:
                st.warning("No USDT available for trading. Please adjust your liquid USDT percentage.")
                time.sleep(5)  # Wait for 5 seconds before checking again
                continue

            for symbol in chosen_symbols:
                current_price = prices[symbol]
                if current_price is None:
                    st.warning(f"Skipping {symbol} due to unavailable price data")
                    continue

                allocated_value = safe_divide(current_status['tradable_usdt'] * bot.symbol_allocations[symbol], 1)
                base_currency = symbol.split('-')[1]
                base_balance = bot.get_account_balance(base_currency)

                # Check if we should buy
                if base_balance > 0 and bot.should_buy(symbol, current_price):
                    buy_amount_usdt = min(allocated_value, base_balance)
                    if buy_amount_usdt > 0:
                        order_amount = safe_divide(buy_amount_usdt, num_orders)
                        for _ in range(num_orders):
                            order = bot.place_market_buy_order(symbol, order_amount)
                            if order:
                                if bot.is_simulation:
                                    bot.wallet.simulate_market_buy("trading", symbol.split('-')[0], order_amount, current_price)

                                target_sell_price = order['price'] * (1 + profit_margin + 2*bot.FEE_RATE)
                                bot.active_trades[order['orderId']] = {
                                    'symbol': symbol,
                                    'buy_price': order['price'],
                                    'amount': order['amount'],
                                    'target_sell_price': target_sell_price,
                                    'fee_usdt': order['fee_usdt'],
                                    'buy_time': datetime.now()
                                }
                                st.session_state.trade_messages.append(f"Placed buy order for {symbol}: {order_amount:.4f} USDT at {order['price']:.4f}, Order ID: {order['orderId']}")

                # Check active trades for selling
                for order_id, trade in list(bot.active_trades.items()):
                    if trade['symbol'] == symbol and current_price >= trade['target_sell_price']:
                        sell_amount_crypto = trade['amount']
                        sell_order = bot.place_market_sell_order(symbol, sell_amount_crypto)
                        if sell_order:
                            if bot.is_simulation:
                                bot.wallet.simulate_market_sell("trading", symbol.split('-')[0], sell_amount_crypto, current_price)

                            sell_amount_usdt = sell_order['amount']
                            total_fee = trade['fee_usdt'] + sell_order['fee_usdt']
                            profit = sell_amount_usdt - (trade['amount'] * trade['buy_price']) - total_fee
                            bot.profits[symbol] += profit
                            bot.total_profit += profit
                            st.session_state.trade_messages.append(f"Placed sell order for {symbol}: {sell_amount_usdt:.4f} USDT at {sell_order['price']:.4f}, Profit: {profit:.4f} USDT, Total Fee: {total_fee:.4f} USDT, Order ID: {sell_order['orderId']}")
                            del bot.active_trades[order_id]

            # Update allocations based on new total USDT value
            bot.update_allocations(current_status['current_total_usdt'], bot.usdt_liquid_percentage)

            # Sleep for a short duration before the next iteration
            time.sleep(1)

        except Exception as e:
            st.session_state.error_message = f"An error occurred: {str(e)}"
            time.sleep(5)  # Wait for 5 seconds before the next iteration
