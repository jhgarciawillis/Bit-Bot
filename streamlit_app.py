import streamlit as st
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from trading_bot import TradingBot
from chart_utils import ChartCreator
from trading_loop import initialize_trading_loop, stop_trading_loop
from ui_components import StatusTable, TradeMessages, ErrorMessage, initialize_session_state, SidebarConfig, SymbolSelector, TradingParameters, TradingControls, ChartDisplay, SimulationIndicator, WalletBalance, LiveTradingVerification
from config import load_config, initialize_kucoin_client, get_available_trading_symbols, fetch_real_time_prices
from wallet import create_wallet

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def initialize_bot(config: Dict[str, Any], is_simulation: bool, simulated_usdt_balance: float = 0) -> TradingBot:
    logger.info("Initializing bot...")
    api_key = config['api_key']
    api_secret = config['api_secret']
    api_passphrase = config['api_passphrase']
    
    bot = TradingBot(api_key, api_secret, api_passphrase, config['bot_config']['update_interval'])
    bot.is_simulation = is_simulation
    
    if is_simulation:
        logger.info("Simulation mode enabled, updating USDT balance.")
        await bot.wallet.update_account_balance("trading", "USDT", simulated_usdt_balance)
    else:
        logger.info("Live trading mode, initializing bot.")
        await bot.initialize()
    
    logger.info("Bot initialized successfully.")
    return bot

async def save_chart(fig, filename):
    logger.info(f"Saving chart as {filename}...")
    await fig.write_image(filename)
    logger.info(f"Chart saved as {filename}")
    st.success(f"Chart saved as {filename}")

async def main():
    logger.info("Starting main function...")
    st.set_page_config(layout="wide")
    st.title("Cryptocurrency Trading Bot")

    error_container = st.container()

    try:
        logger.info("Loading configuration...")
        config = await load_config()
        logger.info("Initializing KuCoin client...")
        await initialize_kucoin_client(config)
        logger.info("Initializing session state...")
        await initialize_session_state()

        if 'is_trading' not in st.session_state:
            st.session_state.is_trading = False
        if 'stop_event' not in st.session_state:
            st.session_state.stop_event = None
        if 'trading_task' not in st.session_state:
            st.session_state.trading_task = None
        if 'user_inputs' not in st.session_state:
            st.session_state.user_inputs = {}

        logger.info("Configuring sidebar...")
        sidebar_config = SidebarConfig(config)
        is_simulation, simulated_usdt_balance = await sidebar_config.configure()

        if is_simulation is not None:
            logger.info(f"Simulation mode: {is_simulation}")
            if not is_simulation:
                logger.info("Live trading mode, verifying access key...")
                live_trading_verification = LiveTradingVerification(config)
                if not await live_trading_verification.verify():
                    return
            
            logger.info("Creating wallet...")
            wallet = await create_wallet()
            logger.info("Initializing bot...")
            bot = await initialize_bot(config, is_simulation, simulated_usdt_balance)
            bot.wallet = wallet

            logger.info("Displaying wallet balance...")
            wallet_balance = WalletBalance(bot)
            await wallet_balance.display()

            logger.info("Displaying simulation indicator...")
            simulation_indicator = SimulationIndicator(is_simulation)
            await simulation_indicator.display()

            logger.info("Fetching available trading symbols...")
            available_symbols = await get_available_trading_symbols(config)
            if not available_symbols:
                logger.warning("No available trading symbols found. Please check your KuCoin API connection.")
                st.warning("No available trading symbols found. Please check your KuCoin API connection.")
                return
            
            logger.info("Displaying symbol selector...")
            symbol_selector = SymbolSelector(available_symbols, config['default_trading_symbols'])
            user_selected_symbols = await symbol_selector.display()

            if not user_selected_symbols:
                logger.warning("No symbols selected for trading.")
                st.warning("Please select at least one symbol to trade.")
                return

            logger.info("Displaying trading parameters...")
            trading_params = TradingParameters(config)
            usdt_liquid_percentage, profit_margin_percentage, num_orders_per_trade = await trading_params.display()

            logger.info("Informing users about total fees and suggested profit margin.")
            st.sidebar.info("Please note that the total fees for buying and selling are 0.2%. It is recommended to set a profit margin higher than 0.2% to cover the fees.")

            logger.info("Saving user inputs to session state...")
            st.session_state.user_inputs = {
                'user_selected_symbols': user_selected_symbols,
                'usdt_liquid_percentage': usdt_liquid_percentage,
                'profit_margin_percentage': profit_margin_percentage,
                'num_orders_per_trade': num_orders_per_trade
            }

            bot.usdt_liquid_percentage = usdt_liquid_percentage

            logger.info("Getting user allocations...")
            bot.symbol_allocations, tradable_usdt_amount = await bot.get_user_allocations(user_selected_symbols, await bot.wallet.get_total_balance_in_usdt())
            if tradable_usdt_amount <= 0:
                logger.warning("No USDT available for trading. Please adjust your liquid USDT percentage.")
                st.warning("No USDT available for trading. Please adjust your liquid USDT percentage.")
                return

            logger.info(f"Tradable USDT Amount: {tradable_usdt_amount:.2f}")
            st.sidebar.info(f"Tradable USDT Amount: {tradable_usdt_amount:.2f}")

            logger.info("Displaying trading controls...")
            trading_controls = TradingControls(config)
            start_button, stop_button = await trading_controls.display()

            if start_button and not st.session_state.is_trading:
                logger.info("Starting trading...")
                st.session_state.is_trading = True
                st.session_state.stop_event, st.session_state.trading_task = await initialize_trading_loop(
                    bot, user_selected_symbols, profit_margin_percentage, num_orders_per_trade
                )

            if st.session_state.is_trading:
                logger.info("Trading is in progress, updating charts and status...")
                chart_creator = ChartCreator(bot)
                chart_container = st.container()
                chart_display = ChartDisplay(chart_container)
                status_container = st.container()
                trade_messages_container = st.container()
                last_update_time = datetime.now() - timedelta(seconds=31)  # Ensure first update happens immediately

                try:
                    current_time = datetime.now()
                    if (current_time - last_update_time).total_seconds() >= 30:
                        logger.info("Updating charts and status...")
                        charts = await chart_creator.create_charts_async()
                        await chart_display.display(charts)

                        logger.info("Fetching current prices and updating status table...")
                        current_prices = await fetch_real_time_prices(user_selected_symbols, is_simulation)
                        current_status = await bot.get_current_status(current_prices)
                        status_table = StatusTable(status_container, bot, user_selected_symbols)
                        await status_table.display(current_status)

                        logger.info("Displaying trade messages...")
                        trade_messages = TradeMessages(trade_messages_container)
                        await trade_messages.display()

                        last_update_time = current_time

                except Exception as e:
                    logger.error(f"An error occurred in the main loop: {e}")
                    error_message = ErrorMessage(error_container)
                    await error_message.display()

            if stop_button or (not st.session_state.is_trading and st.session_state.stop_event):
                logger.info("Stopping trading...")
                st.session_state.is_trading = False
                if st.session_state.stop_event and st.session_state.trading_task:
                    await stop_trading_loop(st.session_state.stop_event, st.session_state.trading_task)
                    st.session_state.stop_event = None
                    st.session_state.trading_task = None
                st.sidebar.success("Trading stopped.")
                chart_display.chart_container.empty()

    except Exception as e:
        logger.error(f"An error occurred in the main function: {e}")
        error_message = ErrorMessage(error_container)
        await error_message.display()

if __name__ == "__main__":
    asyncio.run(main())
