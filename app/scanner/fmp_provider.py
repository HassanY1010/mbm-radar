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
        """Fetch list of all active stocks on NYSE, NASDAQ, AMEX"""
        try:
            session = await self._get_session()
            url = f"{self.base_url}/v3/stock/list?apikey={self.api_key}"
            async with session.get(url) as response:
                if response.status != 200:
                    scanner_logger.error(f"FMP Active Tickers error: HTTP {response.status}")
                    return []
                data = await response.json()
                
                # Filter for US equities on major exchanges
                tickers = []
                for item in data:
                    exchange = item.get("exchangeShortName", "").upper()
                    item_type = item.get("type", "").lower()
                    if exchange in ["NASDAQ", "NYSE", "AMEX"] and "stock" in item_type:
                        tickers.append(item.get("symbol"))
                scanner_logger.info(f"FMP loaded {len(tickers)} active US stocks")
                return tickers
        except Exception as e:
            scanner_logger.error(f"FMP get_active_tickers exception: {str(e)}")
            return []

    async def get_quote(self, ticker: str) -> Dict[str, Any]:
        """Fetch real-time quote for a specific ticker"""
        try:
            session = await self._get_session()
            url = f"{self.base_url}/v3/quote/{ticker}?apikey={self.api_key}"
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
        """Fetch historical bars (daily candles) for indicator calculation"""
        try:
            session = await self._get_session()
            # timeseries parameter restricts the number of rows returned
            url = f"{self.base_url}/v3/historical-price-full/{ticker}?seriestype=line&apikey={self.api_key}"
            async with session.get(url) as response:
                if response.status != 200:
                    return []
                data = await response.json()
                historical = data.get("historical", [])
                # Return limited candles (sorted from oldest to newest)
                bars = historical[:limit]
                bars.reverse()
                return bars
        except Exception as e:
            scanner_logger.error(f"FMP get_historical_bars error for {ticker}: {str(e)}")
            return []

    async def get_key_financials(self, ticker: str) -> Dict[str, Any]:
        """Fetch key metrics (TTM) for Shariah compliance ratio check"""
        try:
            session = await self._get_session()
            # Fetch balance sheet and key metrics ttm
            url = f"{self.base_url}/v3/key-metrics-ttm/{ticker}?apikey={self.api_key}"
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
        """Fetch latest stock news as catalysts"""
        try:
            session = await self._get_session()
            url = f"{self.base_url}/v3/stock_news?tickers={ticker}&limit={limit}&apikey={self.api_key}"
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
