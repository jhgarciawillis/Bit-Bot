# config.py
import streamlit as st
from kucoin.client import Market, Trade, User

AVAILABLE_SYMBOLS = [
    'BTC-USDT',
    'ETH-USDT',
    'ADA-USDT',
    'DOT-USDT',
    'XRP-USDT',
]

def initialize_clients():
    global market_client, trade_client, user_client

    API_KEY = st.secrets["API_KEY"]
    API_SECRET = st.secrets["API_SECRET"]
    API_PASSPHRASE = st.secrets["API_PASSPHRASE"]
    API_URL = 'https://api.kucoin.com'

    market_client = Market(url=API_URL)
    trade_client = Trade(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE, url=API_URL)
    user_client = User(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE, url=API_URL)
