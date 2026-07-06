import asyncio
import json
import aiohttp
from typing import List, Dict, Any, Optional
from app.scanner.base_provider import BaseDataProvider
from app.core.config import settings
from app.core.logging import scanner_logger

class FMPDataProvider(BaseDataProvider):
    """
    Financial Modeling Prep (FMP) Data Provider.
    Implements REST and WebSocket streaming.
    """
    def __init__(self):
        self.api_key = settings.FMP_API_KEY
        self.base_url = "https://financialmodelingprep.com/api"
        self.ws_url = "wss://financialmodelingprep.com/websocket"
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws = None
        self.is_connected = False

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _request_json(self, url: str, max_retries: int = 3) -> Any:
        """Helper to send HTTP GET requests with exponential backoff on 429/failures"""
        session = await self._get_session()
        retries = 0
        backoff = 1.0
        
        # Scrub apikey in logs for security
        sanitized_url = url.split("apikey=")[0] + "apikey=***" if "apikey=" in url else url
        
        while retries <= max_retries:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:
                        scanner_logger.warning(f"FMP API Rate Limited (429) for {sanitized_url}. Retrying in {backoff}s... (Attempt {retries + 1}/{max_retries + 1})")
                    else:
                        scanner_logger.error(f"FMP API HTTP {response.status} for {sanitized_url}. Retrying in {backoff}s... (Attempt {retries + 1}/{max_retries + 1})")
            except Exception as e:
                scanner_logger.error(f"FMP API request exception for {sanitized_url}: {str(e)}. Retrying in {backoff}s... (Attempt {retries + 1}/{max_retries + 1})")
            
            if retries == max_retries:
                break
            await asyncio.sleep(backoff)
            retries += 1
            backoff *= 2.0
        return None

    async def get_active_tickers(self) -> List[str]:
        """Fetch list of active candidate stocks matching filters on NYSE, NASDAQ, AMEX using stable company-screener"""
        try:
            # Calculate buffers (volume > 50% threshold, price < 150% threshold)
            volume_min = max(20000, int(settings.SCANNER_MIN_VOLUME * 0.5))
            price_max = float(settings.SCANNER_MAX_PRICE * 1.5)
            
            market_cap_max = int(settings.SCANNER_MAX_MARKET_CAP * 1.5)
            
            # Request filtered candidates directly from FMP screener using high limit (5000) to fetch the entire active market
            # since stable screener ignores marketCapLowerThan when combined with price filters
            limit = max(5000, settings.SCANNER_LIMIT)
            url = f"https://financialmodelingprep.com/stable/company-screener?exchange=NASDAQ,NYSE,AMEX&volumeMoreThan={volume_min}&limit={limit}&apikey={self.api_key}"
            data = await self._request_json(url)
            if not data or not isinstance(data, list):
                return []
                
            tickers = []
            for item in data:
                symbol = item.get("symbol")
                price = item.get("price", 0.0)
                market_cap = item.get("marketCap") or 0.0
                
                # Client-side price & market cap filters
                if price > price_max or price < 0.10:
                    continue
                if market_cap > market_cap_max:
                    continue
                # Strict validation for standard US tickers
                if symbol and symbol.isalpha() and symbol.isupper() and len(symbol) <= 5:
                    tickers.append(symbol)
            scanner_logger.info(f"FMP loaded {len(tickers)} active candidate tickers (volume > {volume_min}, price < {price_max}, cap < {market_cap_max}) using stable screener")
            return tickers
        except Exception as e:
            scanner_logger.error(f"FMP get_active_tickers exception: {str(e)}")
            return []

    async def get_quote(self, ticker: str) -> Dict[str, Any]:
        """Fetch real-time quote for a specific ticker using stable quote endpoint"""
        try:
            url = f"https://financialmodelingprep.com/stable/quote?symbol={ticker}&apikey={self.api_key}"
            data = await self._request_json(url)
            if data and isinstance(data, list):
                return data[0]
            return {}
        except Exception as e:
            scanner_logger.error(f"FMP get_quote error for {ticker}: {str(e)}")
            return {}

    async def get_quotes_batch(self, tickers: List[str]) -> List[Dict[str, Any]]:
        """Fetch real-time quotes for a batch of tickers using stable batch-quote endpoint"""
        if not tickers:
            return []
        try:
            symbols_str = ",".join(tickers)
            url = f"https://financialmodelingprep.com/stable/batch-quote?symbols={symbols_str}&apikey={self.api_key}"
            data = await self._request_json(url)
            if data and isinstance(data, list):
                return data
            return []
        except Exception as e:
            scanner_logger.error(f"FMP get_quotes_batch exception: {str(e)}")
            return []

    async def get_historical_bars(self, ticker: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch historical bars (daily candles) using stable EOD endpoint"""
        try:
            url = f"https://financialmodelingprep.com/stable/historical-price-eod/full?symbol={ticker}&apikey={self.api_key}"
            data = await self._request_json(url)
            bars = data if isinstance(data, list) else []
            bars = bars[:limit]
            bars.reverse()
            return bars
        except Exception as e:
            scanner_logger.error(f"FMP get_historical_bars error for {ticker}: {str(e)}")
            return []

    async def get_key_financials(self, ticker: str) -> Dict[str, Any]:
        """Fetch key metrics (TTM) for Shariah compliance check using stable key-metrics-ttm"""
        try:
            url = f"https://financialmodelingprep.com/stable/key-metrics-ttm?symbol={ticker}&apikey={self.api_key}"
            data = await self._request_json(url)
            if data and isinstance(data, list):
                return data[0]
            return {}
        except Exception as e:
            scanner_logger.error(f"FMP get_key_financials error for {ticker}: {str(e)}")
            return {}

    async def get_news_and_catalysts(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch latest stock news using stable news endpoint"""
        try:
            url = f"https://financialmodelingprep.com/stable/news/stock?symbols={ticker}&limit={limit}&apikey={self.api_key}"
            data = await self._request_json(url)
            return data if isinstance(data, list) else []
        except Exception as e:
            scanner_logger.error(f"FMP get_news error for {ticker}: {str(e)}")
            return []

    async def connect_websocket(self, callback) -> None:
        """Connects to FMP WebSocket and streams realtime trade quotes"""
        self.is_connected = True
        session = await self._get_session()
        
        while self.is_connected:
            try:
                scanner_logger.info("Connecting to FMP WebSocket...")
                async with session.ws_connect(self.ws_url) as ws:
                    self.ws = ws
                    # Login
                    login_msg = {"event": "login", "data": {"apiKey": self.api_key}}
                    await ws.send_str(json.dumps(login_msg))
                    
                    # Receive login confirmation
                    resp = await ws.receive()
                    scanner_logger.info(f"FMP WebSocket login response: {resp.data}")
                    
                    # Subscribe to US Stocks (all us market symbols or active lists)
                    # Note: FMP WebSocket allows subscribing to individual tickers or "stocks" for entire feed.
                    subscribe_msg = {"event": "subscribe", "data": ["us_market"]}
                    await ws.send_str(json.dumps(subscribe_msg))
                    
                    # Listen loop
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            # Call the scanner dispatcher
                            await callback(data)
                        elif msg.type in [aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR]:
                            break
            except Exception as e:
                scanner_logger.error(f"FMP WebSocket exception: {str(e)}. Retrying in 5 seconds...")
                await asyncio.sleep(5)
                
    async def disconnect_websocket(self) -> None:
        self.is_connected = False
        if self.ws:
            await self.ws.close()
            self.ws = None
            scanner_logger.info("FMP WebSocket disconnected.")

    async def close(self) -> None:
        await self.disconnect_websocket()
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
