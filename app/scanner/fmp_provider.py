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

    async def get_active_tickers(self) -> List[str]:
        """Fetch list of active candidate stocks matching filters on NYSE, NASDAQ, AMEX using stable company-screener"""
        try:
            session = await self._get_session()
            # Calculate buffers (volume > 50% threshold, price < 150% threshold)
            volume_min = max(20000, int(settings.SCANNER_MIN_VOLUME * 0.5))
            price_max = float(settings.SCANNER_MAX_PRICE * 1.5)
            
            # Request filtered candidates directly from FMP screener to avoid polling 10k tickers
            url = f"https://financialmodelingprep.com/stable/company-screener?exchange=NASDAQ,NYSE,AMEX&volumeMoreThan={volume_min}&priceLessThan={price_max}&priceMoreThan=0.10&limit=5000&apikey={self.api_key}"
            async with session.get(url) as response:
                if response.status != 200:
                    scanner_logger.error(f"FMP Active Tickers error: HTTP {response.status}")
                    return []
                data = await response.json()
                
                tickers = []
                for item in data:
                    symbol = item.get("symbol")
                    # Strict validation for standard US tickers
                    if symbol and symbol.isalpha() and symbol.isupper() and len(symbol) <= 5:
                        tickers.append(symbol)
                scanner_logger.info(f"FMP loaded {len(tickers)} active candidate tickers (volume > {volume_min}, price < {price_max}) using stable screener")
                return tickers
        except Exception as e:
            scanner_logger.error(f"FMP get_active_tickers exception: {str(e)}")
            return []

    async def get_quote(self, ticker: str) -> Dict[str, Any]:
        """Fetch real-time quote for a specific ticker using stable quote endpoint"""
        try:
            session = await self._get_session()
            url = f"https://financialmodelingprep.com/stable/quote?symbol={ticker}&apikey={self.api_key}"
            async with session.get(url) as response:
                if response.status != 200:
                    return {}
                data = await response.json()
                if data and isinstance(data, list):
                    return data[0]
                return {}
        except Exception as e:
            scanner_logger.error(f"FMP get_quote error for {ticker}: {str(e)}")
            return {}

    async def get_historical_bars(self, ticker: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch historical bars (daily candles) using stable EOD endpoint"""
        try:
            session = await self._get_session()
            url = f"https://financialmodelingprep.com/stable/historical-price-eod/full?symbol={ticker}&apikey={self.api_key}"
            async with session.get(url) as response:
                if response.status != 200:
                    return []
                data = await response.json()
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
            session = await self._get_session()
            url = f"https://financialmodelingprep.com/stable/key-metrics-ttm?symbol={ticker}&apikey={self.api_key}"
            async with session.get(url) as response:
                if response.status != 200:
                    return {}
                data = await response.json()
                if data and isinstance(data, list):
                    return data[0]
                return {}
        except Exception as e:
            scanner_logger.error(f"FMP get_key_financials error for {ticker}: {str(e)}")
            return {}

    async def get_news_and_catalysts(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch latest stock news using stable news endpoint"""
        try:
            session = await self._get_session()
            url = f"https://financialmodelingprep.com/stable/news/stock?symbols={ticker}&limit={limit}&apikey={self.api_key}"
            async with session.get(url) as response:
                if response.status != 200:
                    return []
                data = await response.json()
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
