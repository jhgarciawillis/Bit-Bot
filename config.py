def initialize_clients():
    global market_client, trade_client, user_client

    logger.debug("Initializing clients")

    try:
        API_KEY = st.secrets["api_credentials"]["api_key"]
        logger.debug(f"API_KEY: {API_KEY}")

        API_SECRET = st.secrets["api_credentials"]["api_secret"]
        logger.debug(f"API_SECRET: {API_SECRET}")

        API_PASSPHRASE = st.secrets["api_credentials"]["api_passphrase"]
        logger.debug(f"API_PASSPHRASE: {API_PASSPHRASE}")

        API_URL = 'https://api.kucoin.com'
        logger.debug(f"API_URL: {API_URL}")

        logger.debug("Initializing Market client")
        market_client = Market(url=API_URL)
        logger.debug("Market client initialized")

        logger.debug("Initializing Trade client")
        trade_client = Trade(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE, url=API_URL)
        logger.debug("Trade client initialized")

        logger.debug("Initializing User client")
        user_client = User(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE, url=API_URL)
        logger.debug("User client initialized")

        logger.info("Clients initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing clients: {e}")
        logger.exception("Exception traceback:")
        market_client = None
        trade_client = None
        user_client = None
