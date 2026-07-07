"""
SimulationProvider — Synthetic market data provider for MBM Radar.

Generates realistic stock quote data that passes Stage 1 and Stage 2 filters,
flowing through the exact same pipeline as real market signals.

INTERNAL USE ONLY: The is_simulated flag is stored in the database and logs
but is NEVER exposed to end users, Telegram messages, WebSocket events,
or any client-facing interface.
"""

import random
import math
import datetime
from typing import List, Dict, Any, Optional

from app.scanner.base_provider import BaseDataProvider
from app.core.config import settings
from app.core.logging import scanner_logger


# ---------------------------------------------------------------------------
# Static pool of synthetic ticker symbols — rotate to avoid repetition
# ---------------------------------------------------------------------------
_SIM_TICKERS = [
    "MSTT", "NXBT", "FLWR", "DRVN", "QBTX",
    "ZRLT", "BRKV", "PLXN", "CMVR", "GRND",
    "VTEX", "PRXA", "SBNK", "LWFT", "RNVT",
    "MXLS", "CTRQ", "BVNK", "FXPR", "DLRX",
]

_SIM_COMPANIES = {
    "MSTT":  ("Mostech Technologies", "Technology", "Software—Infrastructure"),
    "NXBT":  ("Nexbit Corp", "Healthcare", "Biotechnology"),
    "FLWR":  ("Floware Inc", "Financial Services", "Asset Management"),
    "DRVN":  ("Driven Mobility", "Consumer Cyclical", "Auto Parts"),
    "QBTX":  ("Quantum Biosciences", "Healthcare", "Drug Manufacturers—Specialty"),
    "ZRLT":  ("Zerolift Systems", "Industrials", "Aerospace & Defense"),
    "BRKV":  ("Breckvale Capital", "Financial Services", "Insurance"),
    "PLXN":  ("Plexon Networks", "Communication Services", "Telecom Services"),
    "CMVR":  ("Commvera Inc", "Technology", "Software—Application"),
    "GRND":  ("Groundrise Energy", "Energy", "Oil & Gas E&P"),
    "VTEX":  ("Vitex Pharma", "Healthcare", "Biotechnology"),
    "PRXA":  ("Proxia Analytics", "Technology", "Information Technology Services"),
    "SBNK":  ("Sunbank Holdings", "Financial Services", "Banks—Regional"),
    "LWFT":  ("Lowfloat Retail", "Consumer Defensive", "Discount Stores"),
    "RNVT":  ("Renovate Pro", "Real Estate", "Real Estate Services"),
    "MXLS":  ("Maxiless Corp", "Industrials", "Specialty Industrial Machinery"),
    "CTRQ":  ("Contriq Solutions", "Technology", "Electronic Components"),
    "BVNK":  ("Bravebank Ltd", "Financial Services", "Banks—Diversified"),
    "FXPR":  ("Flexpar Medical", "Healthcare", "Medical Devices"),
    "DLRX":  ("Dalrex Mining", "Basic Materials", "Copper"),
}

# 7 scenario templates — rotate for signal variety
_SCENARIOS = [
    "Momentum Breakout",
    "Volume Spike",
    "Low Float Runner",
    "High RVOL Move",
    "Pre-market Gap Up",
    "Intraday Momentum",
    "Reversal Setup",
]

# Track last used ticker index for rotation
_ticker_rotation_index = 0
_scenario_rotation_index = 0


def _next_ticker() -> str:
    global _ticker_rotation_index
    ticker = _SIM_TICKERS[_ticker_rotation_index % len(_SIM_TICKERS)]
    _ticker_rotation_index += 1
    return ticker


def _next_scenario() -> str:
    global _scenario_rotation_index
    scenario = _SCENARIOS[_scenario_rotation_index % len(_SCENARIOS)]
    _scenario_rotation_index += 1
    return scenario


def _rand(lo: float, hi: float, decimals: int = 2) -> float:
    """Uniform random float rounded to specified decimals."""
    return round(random.uniform(lo, hi), decimals)


def _build_quote(ticker: str, scenario: str) -> Dict[str, Any]:
    """
    Build a synthetic stock quote dict that satisfies Stage 1 filters:
    - price in [1.0, SCANNER_MAX_PRICE]
    - volume >= SCANNER_MIN_VOLUME * 3 (comfortable margin)
    - marketCap <= SCANNER_MAX_MARKET_CAP
    - float <= SCANNER_MAX_FLOAT
    - changePercentage >= max(3.0, SCANNER_MIN_CHANGE_PCT) + 1%
    - gapPercent >= max(3.0, SCANNER_MIN_GAP_PCT) + 0.5%
    - dollar_volume >= 600_000
    """
    max_price = min(settings.SCANNER_MAX_PRICE, 29.99)
    max_float = settings.SCANNER_MAX_FLOAT
    max_cap = settings.SCANNER_MAX_MARKET_CAP

    # --- Scenario-specific parameters ---
    if scenario == "Momentum Breakout":
        price = _rand(5.0, max_price * 0.7)
        change_pct = _rand(6.0, 18.0)
        gap_pct = _rand(5.0, 15.0)
        rvol_sim = _rand(1.8, 4.5)
        vol_multiplier = _rand(3, 8)

    elif scenario == "Volume Spike":
        price = _rand(2.0, max_price * 0.5)
        change_pct = _rand(4.0, 12.0)
        gap_pct = _rand(3.5, 10.0)
        rvol_sim = _rand(3.0, 8.0)
        vol_multiplier = _rand(6, 15)

    elif scenario == "Low Float Runner":
        price = _rand(1.50, 10.0)
        change_pct = _rand(8.0, 35.0)
        gap_pct = _rand(7.0, 30.0)
        rvol_sim = _rand(2.5, 7.0)
        vol_multiplier = _rand(4, 12)

    elif scenario == "High RVOL Move":
        price = _rand(3.0, max_price * 0.8)
        change_pct = _rand(5.0, 20.0)
        gap_pct = _rand(4.0, 18.0)
        rvol_sim = _rand(5.0, 12.0)
        vol_multiplier = _rand(5, 14)

    elif scenario == "Pre-market Gap Up":
        price = _rand(4.0, max_price * 0.6)
        change_pct = _rand(10.0, 40.0)
        gap_pct = _rand(9.0, 38.0)
        rvol_sim = _rand(2.0, 6.0)
        vol_multiplier = _rand(3, 9)

    elif scenario == "Intraday Momentum":
        price = _rand(2.0, max_price * 0.9)
        change_pct = _rand(4.0, 14.0)
        gap_pct = _rand(3.0, 12.0)
        rvol_sim = _rand(1.5, 4.0)
        vol_multiplier = _rand(2, 7)

    else:  # Reversal Setup
        price = _rand(1.0, max_price * 0.4)
        change_pct = _rand(5.0, 22.0)
        gap_pct = _rand(4.0, 20.0)
        rvol_sim = _rand(2.0, 5.0)
        vol_multiplier = _rand(3, 10)

    # Derive volume from RVOL and a base avg volume that passes filters
    min_vol = max(settings.SCANNER_MIN_VOLUME * 3, 150_000)
    avg_volume_30d = int(random.uniform(min_vol, min_vol * 2))
    volume = int(avg_volume_30d * rvol_sim * vol_multiplier / 4)
    volume = max(volume, min_vol)  # Ensure minimum threshold

    # Ensure dollar volume passes $500K minimum
    if price * volume < 600_000:
        volume = int(600_001 / max(price, 0.01)) + 1

    # Derive float: stay well below SCANNER_MAX_FLOAT
    float_size = int(random.uniform(max_float * 0.1, max_float * 0.9))

    # Market cap = price * float (rough approximation)
    market_cap = float(price * float_size)
    market_cap = min(market_cap, max_cap * 0.85)

    # OHLC derived values
    prev_close = round(price / (1 + change_pct / 100), 2)
    open_price = round(prev_close * (1 + gap_pct / 100), 2)
    day_high = round(price * _rand(1.01, 1.12), 2)
    day_low = round(price * _rand(0.88, 0.98), 2)
    vwap = round((open_price + day_high + day_low + price) / 4, 2)
    price_avg_50 = round(prev_close * _rand(0.80, 1.05), 2)

    company_name, sector, industry = _SIM_COMPANIES.get(
        ticker, (f"{ticker} Corp", "Technology", "Software—Application")
    )

    return {
        "symbol": ticker,
        "name": company_name,
        "price": price,
        "open": open_price,
        "previousClose": prev_close,
        "dayHigh": day_high,
        "dayLow": day_low,
        "volume": volume,
        "marketCap": market_cap,
        "float": float(float_size),
        "sharesOutstanding": float(float_size),
        "changePercentage": change_pct,
        "changesPercentage": change_pct,
        "changePercent": change_pct,
        "gapPercent": gap_pct,
        "gapPercentage": gap_pct,
        "vwap": vwap,
        "priceAvg50": price_avg_50,
        "exchange": "NASDAQ",
        "sector": sector,
        "industry": industry,
        "ask": round(price + 0.02, 2),
        "bid": round(price - 0.02, 2),
        "spread": 0.04,
        # Injected RVOL hint for Stage 2 TA calculations
        "_sim_rvol": rvol_sim,
        "_sim_avg_volume": float(avg_volume_30d),
        "_sim_scenario": scenario,
    }


def _build_historical_bars(price: float, n: int = 100) -> List[Dict[str, Any]]:
    """
    Generate n synthetic daily OHLCV bars that produce realistic ATR, VWAP,
    RSI (~50–75 to indicate momentum), and support/resistance levels.
    """
    bars = []
    current = price * _rand(0.70, 0.90)  # Start below current price (uptrend)
    for i in range(n):
        atr_pct = _rand(0.03, 0.08)
        day_range = current * atr_pct
        open_p = current
        close_p = current * (1 + _rand(-0.03, 0.06))  # Slight upward bias
        high_p = max(open_p, close_p) + _rand(0, day_range * 0.5)
        low_p = min(open_p, close_p) - _rand(0, day_range * 0.5)
        vol = int(_rand(80_000, 500_000))
        ts = datetime.datetime.utcnow() - datetime.timedelta(days=(n - i))
        bars.append({
            "date": ts.strftime("%Y-%m-%d"),
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "close": round(close_p, 2),
            "volume": vol,
        })
        current = close_p
    return bars


class SimulationProvider(BaseDataProvider):
    """
    Synthetic market data provider. Feeds realistic stock quotes through
    the exact same real-world scanning pipeline without touching FMP API.

    Used exclusively when settings.SIMULATION_MODE = True.
    All generated data is internally flagged via Signal.is_simulated = True
    in the database, but NEVER exposed to end users.
    """

    def __init__(self):
        scanner_logger.info("[SIMULATION] SimulationProvider initialized — synthetic signals active")
        self._active_tickers: List[str] = list(_SIM_TICKERS)

    # ------------------------------------------------------------------
    # BaseDataProvider interface implementation
    # ------------------------------------------------------------------

    async def connect_websocket(self, callback) -> None:
        """No WebSocket for simulation — REST polling mode only."""
        pass

    async def disconnect_websocket(self) -> None:
        pass

    async def get_active_tickers(self) -> List[str]:
        """Return the pool of simulated tickers."""
        return self._active_tickers

    async def get_quotes_batch(self, tickers: List[str]) -> List[Dict[str, Any]]:
        """
        Generate one realistic synthetic quote per batch call.
        Uses rotating ticker and scenario to ensure variety.
        """
        ticker = _next_ticker()
        scenario = _next_scenario()
        quote = _build_quote(ticker, scenario)
        scanner_logger.debug(
            f"[SIMULATION] Generated quote: {ticker} | scenario={scenario} | "
            f"price={quote['price']} | change={quote['changePercentage']:.1f}% | "
            f"rvol_hint={quote.get('_sim_rvol', 'N/A')}"
        )
        return [quote]

    async def get_quote(self, ticker: str) -> Dict[str, Any]:
        """Return a single synthetic quote for the given ticker."""
        scenario = _next_scenario()
        # Override ticker to match requested symbol
        quote = _build_quote(ticker if ticker in _SIM_TICKERS else _next_ticker(), scenario)
        quote["symbol"] = ticker
        return quote

    async def get_historical_bars(self, ticker: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Generate synthetic historical OHLCV bars for TA calculations."""
        # Use a plausible price range for the given ticker
        base_price = _rand(2.0, min(settings.SCANNER_MAX_PRICE, 25.0))
        return _build_historical_bars(base_price, n=limit)

    async def get_key_financials(self, ticker: str) -> Dict[str, Any]:
        """
        Return Shariah-compliant financials: debt < 33%, cash < 33%, clean activities.
        Fetches the generated quote first to align key financial ratios with actual marketCap.
        """
        # Retrieve the generated quote to align market capitalization
        quote = await self.get_quote(ticker)
        market_cap = float(quote.get("marketCap") or 100_000_000.0)
        
        return {
            "marketCapitalization": market_cap,
            "marketCapTTM": market_cap,
            "totalDebt": market_cap * _rand(0.05, 0.20),
            "totalDebtTTM": market_cap * _rand(0.05, 0.20),
            "cashAndCashEquivalents": market_cap * _rand(0.05, 0.22),
            "cashAndShortTermInvestmentsTTM": market_cap * _rand(0.05, 0.22),
            "intangibleAssets": 0.0,
            "goodwill": 0.0,
        }

    async def get_news_and_catalysts(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Alternate between returning a simulated catalyst and no news,
        to exercise both branches of the news section in Telegram alerts.
        """
        news_pool = [
            f"{ticker}: شركة تُعلن عن عقد حكومي ضخم بقيمة 200 مليون دولار",
            f"{ticker}: توقعات إيرادات الربع الثالث تتجاوز تقديرات المحللين بنسبة 15%",
            f"{ticker}: الشركة تُعلن عن شراكة استراتيجية مع عملاق قطاعها",
            f"{ticker}: تقرير FDA يُشير إلى نتائج إيجابية للمنتج الجديد",
            f"{ticker}: الشركة تُنهي اتفاقية استحواذ بقيمة 350 مليون دولار",
        ]
        # Alternate: 60% chance of having news
        if random.random() < 0.6:
            headline = random.choice(news_pool)
            return [{
                "title": headline,
                "url": f"https://example.com/news/{ticker.lower()}",
                "publishedDate": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "site": "SimMarketNews",
            }]
        return []
