import streamlit as st
from kucoin.client import Market, Trade, User
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def initialize_clients():
    global market_client, trade_client, user_client

    try:
        API_KEY = st.secrets["api_credentials"]["api_key"]
        API_SECRET = st.secrets["api_credentials"]["api_secret"]
        API_PASSPHRASE = st.secrets["api_credentials"]["api_passphrase"]
        API_URL = 'https://api.kucoin.com'

        market_client = Market(url=API_URL)
        trade_client = Trade(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE, url=API_URL)
        user_client = User(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE, url=API_URL)
        logger.info("Clients initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing clients: {e}")
        market_client = None
        trade_client = None
        user_client = None
