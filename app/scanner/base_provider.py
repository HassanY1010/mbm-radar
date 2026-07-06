from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseDataProvider(ABC):
    """
    Abstract Base Class for Stock Data Providers.
    Allows easy switching between FMP, Polygon, Finnhub, Alpaca, etc.
    """
    
    @abstractmethod
    async def connect_websocket(self, callback) -> None:
        """Connects to real-time WebSocket and streams quotes to the callback function"""
        pass

    @abstractmethod
    async def disconnect_websocket(self) -> None:
        """Closes the WebSocket connection"""
        pass

    @abstractmethod
    async def get_quote(self, ticker: str) -> Dict[str, Any]:
        """Fetches the latest real-time stock quote (REST fallback)"""
        pass

    @abstractmethod
    async def get_historical_bars(self, ticker: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetches historical price bars for technical indicators (daily candles)"""
        pass

    @abstractmethod
    async def get_key_financials(self, ticker: str) -> Dict[str, Any]:
        """Fetches financial data like total assets, debt, cash (for Shariah screening)"""
        pass

    @abstractmethod
    async def get_news_and_catalysts(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetches news and potential catalysts for a given ticker"""
        pass

    @abstractmethod
    async def get_active_tickers(self) -> List[str]:
        """Fetches a list of all active stock tickers on NASDAQ, NYSE, and AMEX"""
        pass

    @abstractmethod
    async def get_quotes_batch(self, tickers: List[str]) -> List[Dict[str, Any]]:
        """Fetches the latest real-time stock quotes in batch"""
        pass
