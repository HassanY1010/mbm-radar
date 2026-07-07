"""
SimulationProvider — Dynamic Constraints Market Simulation Engine for MBM Radar.

Reads the active admin's filter preferences from the database and generates
mathematically coherent, scenario-driven synthetic stock data that passes through
the exact same real production pipeline:

  SimulationProvider → Stage 1 Screening → Stage 2 Detailed Scan
       → Shariah Filter → Scoring Engine → Notifier → Telegram / DB / WebSocket

All generated fields are mathematically linked (no independent random numbers):
  - Price is the anchor.
  - Previous Close is derived from Price and Change%.
  - Open Price is derived from Previous Close and Gap%.
  - Volume is derived from RVOL and Average Volume.
  - Market Cap = Float × Price (capped at max_market_cap by scaling Float).
  - HOD / LOD are bounded around Price realistically.
  - VWAP position depends on the scenario (bullish = below price, pullback = above).
  - Liquidity = Volume × Price.
  - Targets scale with scenario quality and RVOL strength.

INTERNAL: is_simulated=True is stored in the database but never exposed to
Telegram messages, WebSocket payloads, or public API responses.
"""

from __future__ import annotations

import random
import math
import datetime
from typing import List, Dict, Any, Optional

from app.core.config import settings
from app.core.logging import scanner_logger

# ---------------------------------------------------------------------------
# Simulated ticker pool — diverse sectors, realistic names
# ---------------------------------------------------------------------------
_SIM_POOL: List[Dict[str, str]] = [
    {"symbol": "AXBT",  "name": "Axebit Technologies",     "sector": "Technology",          "industry": "Software—Application"},
    {"symbol": "NVXR",  "name": "Nexavera Biotech",        "sector": "Healthcare",           "industry": "Drug Manufacturers—Specialty"},
    {"symbol": "DRVX",  "name": "DrivexAuto Solutions",    "sector": "Consumer Cyclical",    "industry": "Auto Parts"},
    {"symbol": "QCLD",  "name": "QuantCloud Systems",      "sector": "Technology",           "industry": "Software—Infrastructure"},
    {"symbol": "ZLTX",  "name": "Zeroltech Inc",           "sector": "Technology",           "industry": "Semiconductors"},
    {"symbol": "PLXV",  "name": "Plexova Pharma",          "sector": "Healthcare",           "industry": "Biotechnology"},
    {"symbol": "CMVX",  "name": "Commvex Corp",            "sector": "Technology",           "industry": "Information Technology Services"},
    {"symbol": "GRND",  "name": "Groundrise Energy",       "sector": "Energy",               "industry": "Oil & Gas E&P"},
    {"symbol": "VTXB",  "name": "Vitexbio Sciences",       "sector": "Healthcare",           "industry": "Medical Devices"},
    {"symbol": "PRXA",  "name": "Proxia Analytics",        "sector": "Technology",           "industry": "Data Analytics"},
    {"symbol": "RNVT",  "name": "Renovate Pro",            "sector": "Industrials",          "industry": "Specialty Industrial Machinery"},
    {"symbol": "MXLS",  "name": "Maxiless Corp",           "sector": "Industrials",          "industry": "Specialty Industrial Machinery"},
    {"symbol": "FXPR",  "name": "Flexpar Medical",         "sector": "Healthcare",           "industry": "Medical Devices"},
    {"symbol": "DLXE",  "name": "Delexe Mining",           "sector": "Basic Materials",      "industry": "Copper"},
    {"symbol": "BNXT",  "name": "Bionext Therapeutics",    "sector": "Healthcare",           "industry": "Biotechnology"},
    {"symbol": "STLR",  "name": "Stellar Robotics",        "sector": "Technology",           "industry": "Electronic Components"},
    {"symbol": "CTRX",  "name": "Contrax Solutions",       "sector": "Technology",           "industry": "Electronic Components"},
    {"symbol": "WVEX",  "name": "Wavex Semiconductors",    "sector": "Technology",           "industry": "Semiconductors"},
    {"symbol": "HLVR",  "name": "Heliovera Energy",        "sector": "Energy",               "industry": "Solar"},
    {"symbol": "MSTR2", "name": "Mastertech AI",           "sector": "Technology",           "industry": "Artificial Intelligence"},
]

# 5 distinct scenarios that shape VWAP, targets, news, and alert type
_SCENARIOS = [
    "momentum_breakout",
    "volume_spike",
    "low_float_runner",
    "pullback_reversal",
    "news_catalyst",
]

# Arabic scenario news templates — news_catalyst only, others return no news or empty catalyst
_NEWS_TEMPLATES = {
    "news_catalyst": [
        "الشركة تُعلن عن عقد حكومي ضخم يتجاوز 200 مليون دولار",
        "نتائج الربع الثالث تتجاوز تقديرات المحللين بنسبة 18%",
        "الشركة تُعلن عن شراكة استراتيجية مع عملاق قطاعها",
        "موافقة FDA على المنتج الجديد — اختراق تنظيمي مهم",
        "الشركة تُنهي اتفاقية استحواذ بقيمة 350 مليون دولار",
    ],
    "momentum_breakout": [
        "ارتفاع غير اعتيادي في حجم التداول مع كسر مستويات مقاومة رئيسية",
    ],
    "volume_spike": [
        "تدفق شرائي قوي مع ارتفاع حجم التداول بأكثر من 5 أضعاف المتوسط",
    ],
    "low_float_runner":  [],   # No news — pure float squeeze
    "pullback_reversal": [],   # No news — technical reversal
}

# Sector-specific alert types aligned with scenario
_SCENARIO_ALERT_TYPES = {
    "momentum_breakout": "Momentum",
    "volume_spike":      "Volume Spike",
    "low_float_runner":  "High Of Day",
    "pullback_reversal": "VWAP Breakout",
    "news_catalyst":     "News",
}

# Rotation indices (module-level)
_ticker_idx = 0
_scenario_idx = 0


# ---------------------------------------------------------------------------
# Preference dataclass (lightweight, no ORM dependency needed at runtime)
# ---------------------------------------------------------------------------
class _Prefs:
    """Holds active admin filter thresholds used as generation bounds."""
    __slots__ = (
        "min_price", "max_price",
        "min_change_pct", "min_gap_pct",
        "min_volume", "min_rvol",
        "max_float", "max_market_cap",
        "min_score_threshold",
    )

    def __init__(self, **kwargs):
        self.min_price:           float = kwargs.get("min_price",           1.0)
        self.max_price:           float = kwargs.get("max_price",           30.0)
        self.min_change_pct:      float = kwargs.get("min_change_pct",      1.0)
        self.min_gap_pct:         float = kwargs.get("min_gap_pct",         2.0)
        self.min_volume:          int   = kwargs.get("min_volume",          50_000)
        self.min_rvol:            float = kwargs.get("min_rvol",            1.5)
        self.max_float:           float = kwargs.get("max_float",           20_000_000.0)
        self.max_market_cap:      float = kwargs.get("max_market_cap",      3_000_000_000.0)
        self.min_score_threshold: float = kwargs.get("min_score_threshold", 3.5)


def _default_prefs() -> _Prefs:
    """Fallback preferences from app config settings."""
    return _Prefs(
        min_price           = getattr(settings, "SCANNER_MIN_PRICE",        1.0),
        max_price           = getattr(settings, "SCANNER_MAX_PRICE",        30.0),
        min_change_pct      = getattr(settings, "SCANNER_MIN_CHANGE_PCT",   1.0),
        min_gap_pct         = getattr(settings, "SCANNER_MIN_GAP_PCT",      2.0),
        min_volume          = getattr(settings, "SCANNER_MIN_VOLUME",       50_000),
        min_rvol            = getattr(settings, "STAGE2_MIN_RVOL",          1.5),
        max_float           = getattr(settings, "SCANNER_MAX_FLOAT",        20_000_000.0),
        max_market_cap      = getattr(settings, "SCANNER_MAX_MARKET_CAP",   3_000_000_000.0),
        min_score_threshold = getattr(settings, "MIN_SCORE_THRESHOLD",      3.5),
    )


async def _fetch_admin_prefs() -> _Prefs:
    """
    Fetch the admin's active UserPreferences from the database.
    Falls back to config defaults on any error.
    """
    try:
        from sqlalchemy import select
        from app.database.session import async_session
        from app.models.models import UserPreferences, User

        async with async_session() as db:
            result = await db.execute(
                select(UserPreferences)
                .join(User, UserPreferences.user_id == User.id)
                .where(User.telegram_id == settings.ADMIN_TELEGRAM_ID)
                .limit(1)
            )
            pref = result.scalar_one_or_none()
            if pref:
                return _Prefs(
                    min_price           = 1.0,           # No hard min_price in UserPreferences
                    max_price           = pref.max_price,
                    min_change_pct      = pref.min_change_pct,
                    min_gap_pct         = pref.min_gap_pct,
                    min_volume          = pref.min_volume,
                    min_rvol            = pref.min_rvol,
                    max_float           = pref.max_float,
                    max_market_cap      = pref.max_market_cap,
                    min_score_threshold = pref.min_score_threshold,
                )
    except Exception as exc:
        scanner_logger.warning(
            f"[SIMULATION] Failed to fetch admin preferences — using config defaults. Error: {exc}"
        )
    return _default_prefs()


# ---------------------------------------------------------------------------
# Core data builder
# ---------------------------------------------------------------------------
def _rf(lo: float, hi: float, d: int = 2) -> float:
    """Round a uniform random float to `d` decimal places."""
    return round(random.uniform(lo, hi), d)


def _build_coherent_quote(meta: Dict[str, str], scenario: str, prefs: _Prefs) -> Dict[str, Any]:
    """
    Build a fully coherent synthetic quote dict where every field is
    mathematically derived from the price anchor and admin filter bounds.
    """
    symbol  = meta["symbol"]
    sector  = meta["sector"]
    industry = meta["industry"]

    # ── 1. Price ────────────────────────────────────────────────────────────
    min_p = max(1.0, prefs.min_price)
    max_p = min(prefs.max_price, 29.99)
    if min_p >= max_p:
        max_p = min_p + 5.0
    price = _rf(min_p, max_p)

    # ── 2. Change % → Previous Close ────────────────────────────────────────
    change_pct = round(prefs.min_change_pct + _rf(1.0, 15.0), 2)
    prev_close = round(price / (1 + change_pct / 100), 2)

    # ── 3. Gap % → Open Price ───────────────────────────────────────────────
    gap_pct = round(prefs.min_gap_pct + _rf(0.5, 10.0), 2)
    open_price = round(prev_close * (1 + gap_pct / 100), 2)

    # ── 4. RVOL → Volume → Average Volume ───────────────────────────────────
    rvol = round(prefs.min_rvol + _rf(0.5, 6.0), 2)
    # Derive a plausible average volume, then compute actual volume
    base_avg_vol = int(_rf(max(prefs.min_volume, 100_000), max(prefs.min_volume * 4, 500_000)))
    volume = max(int(base_avg_vol * rvol), prefs.min_volume + random.randint(10_000, 100_000))
    # Recalculate average volume so that RVOL = volume / avg_volume holds exactly
    avg_volume_30d = round(volume / max(rvol, 0.01))

    # ── 5. Float → Market Cap (capped) ──────────────────────────────────────
    float_shares = _rf(prefs.max_float * 0.1, prefs.max_float * 0.9)
    market_cap = float_shares * price
    # If Market Cap exceeds limit, shrink float to comply
    if market_cap > prefs.max_market_cap * 0.95:
        float_shares = (prefs.max_market_cap * 0.95) / max(price, 0.01)
        market_cap = float_shares * price

    # ── 6. HOD / LOD — realistic bounds ─────────────────────────────────────
    anchor = max(price, open_price)
    hod = round(anchor * _rf(1.01, 1.15), 2)
    lod = round(price  * _rf(0.85, 0.99), 2)
    # Guarantee: LOD < price < HOD
    lod = min(lod, price - 0.01)
    hod = max(hod, price + 0.01)

    # ── 7. VWAP — scenario-dependent ────────────────────────────────────────
    if scenario == "pullback_reversal":
        vwap = round(price * _rf(1.01, 1.05), 2)   # Price below VWAP (pullback)
    else:
        vwap = round(price * _rf(0.93, 0.99), 2)   # Price above VWAP (bullish)

    # ── 8. Liquidity = Volume × Price ───────────────────────────────────────
    dollar_volume = round(volume * price, 2)

    # ── 9. Price averages ────────────────────────────────────────────────────
    price_avg_50 = round(price * _rf(0.75, 0.98), 2)

    # ── 10. Scenario-driven alert type ──────────────────────────────────────
    alert_type = _SCENARIO_ALERT_TYPES.get(scenario, "Momentum")

    scanner_logger.debug(
        f"[SIMULATION] Built quote: {symbol} | scenario={scenario} | "
        f"price={price} | change={change_pct:+.1f}% | gap={gap_pct:+.1f}% | "
        f"rvol={rvol}x | vol={volume:,} | float={float_shares/1e6:.1f}M | "
        f"mcap=${market_cap/1e6:.1f}M | vwap={vwap} | liq=${dollar_volume/1e6:.1f}M"
    )

    return {
        # Identity
        "symbol": symbol,
        "name":   meta["name"],
        "exchange": "NASDAQ",
        "sector":   sector,
        "industry": industry,
        # Price fields
        "price":         price,
        "previousClose": prev_close,
        "open":          open_price,
        "dayHigh":       hod,
        "dayLow":        lod,
        "vwap":          vwap,
        "priceAvg50":    price_avg_50,
        # Change
        "changePercentage":  change_pct,
        "changesPercentage": change_pct,
        "changePercent":     change_pct,
        # Gap
        "gapPercent":        gap_pct,
        "gapPercentage":     gap_pct,
        # Volume
        "volume":            volume,
        # Float / cap
        "float":             float_shares,
        "sharesOutstanding": float_shares,
        "marketCap":         market_cap,
        # Spread (tight for low-price stocks)
        "ask":    round(price + random.uniform(0.01, 0.05), 2),
        "bid":    round(price - random.uniform(0.01, 0.05), 2),
        "spread": round(random.uniform(0.02, 0.08), 2),
        # Internal hints for TA and Scoring
        "_sim_rvol":        rvol,
        "_sim_avg_volume":  float(avg_volume_30d),
        "_sim_dollar_vol":  dollar_volume,
        "_sim_scenario":    scenario,
        "_sim_alert_type":  alert_type,
    }


def _build_coherent_bars(price: float, rvol_hint: float, avg_vol: float, n: int = 100) -> List[Dict[str, Any]]:
    """
    Generate n daily OHLCV bars that converge toward `price` over time,
    with volume trending upward near the end to match the simulated RVOL spike.
    """
    bars = []
    current = price * _rf(0.60, 0.80)   # Start well below to produce realistic uptrend
    for i in range(n):
        # Gradual trend toward current price
        target_pct = i / n
        drift = (price - current) * target_pct * 0.15
        day_change = current * _rf(-0.04, 0.07) + drift
        close_p = round(max(0.10, current + day_change), 2)
        open_p  = round(current * _rf(0.98, 1.02), 2)
        atr_est = current * _rf(0.03, 0.08)
        high_p  = round(max(open_p, close_p) + _rf(0, atr_est * 0.6), 2)
        low_p   = round(min(open_p, close_p) - _rf(0, atr_est * 0.6), 2)

        # Volume: spike in last 5 bars to simulate the RVOL surge
        if i >= n - 5:
            vol = int(avg_vol * _rf(rvol_hint * 0.8, rvol_hint * 1.2))
        else:
            vol = int(avg_vol * _rf(0.4, 1.2))
        vol = max(vol, 10_000)

        ts = datetime.datetime.utcnow() - datetime.timedelta(days=(n - i))
        bars.append({
            "date":   ts.strftime("%Y-%m-%d"),
            "open":   open_p,
            "high":   high_p,
            "low":    low_p,
            "close":  close_p,
            "volume": vol,
        })
        current = close_p
    return bars


def _build_compliant_financials(market_cap: float) -> Dict[str, Any]:
    """
    Generate Shariah-compliant key financials using the quote's actual market_cap
    as the denominator so that all ratios stay comfortably below 33%.
    """
    return {
        "marketCapitalization":          market_cap,
        "marketCapTTM":                  market_cap,
        "totalDebt":                     market_cap * _rf(0.03, 0.18),
        "totalDebtTTM":                  market_cap * _rf(0.03, 0.18),
        "cashAndCashEquivalents":        market_cap * _rf(0.04, 0.20),
        "cashAndShortTermInvestmentsTTM": market_cap * _rf(0.04, 0.20),
        "intangibleAssets": 0.0,
        "goodwill":         0.0,
    }


def _pick_news(scenario: str, symbol: str) -> List[Dict[str, Any]]:
    """Return an Arabic catalyst headline matching the scenario, or empty list."""
    templates = _NEWS_TEMPLATES.get(scenario, [])
    if not templates:
        return []
    headline = random.choice(templates)
    return [{
        "title":         f"{symbol}: {headline}",
        "url":           f"https://markets.example.com/news/{symbol.lower()}",
        "publishedDate": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "site":          "MarketWire",
    }]


# ---------------------------------------------------------------------------
# SimulationProvider class
# ---------------------------------------------------------------------------
class SimulationProvider:
    """
    Dynamic Constraints Market Simulation Engine.

    Reads admin filter preferences from the database and generates mathematically
    coherent stock quote data through the exact same real-world pipeline as live
    market signals.

    Used exclusively when settings.SIMULATION_MODE = True.
    The is_simulated flag is stored internally in DB/logs, NEVER shown to users.
    """

    def __init__(self):
        scanner_logger.info(
            "[SIMULATION] Dynamic Constraints SimulationProvider initialized — "
            "reading admin preferences for signal generation bounds."
        )
        self._active_tickers: List[str] = [m["symbol"] for m in _SIM_POOL]
        # In-process cache for this session's prefs (refreshed every 50 calls)
        self._prefs: Optional[_Prefs] = None
        self._prefs_call_count: int    = 0

    # ── Private helpers ─────────────────────────────────────────────────────

    async def _get_prefs(self) -> _Prefs:
        """Return cached prefs, refreshing from DB every 50 calls."""
        self._prefs_call_count += 1
        if self._prefs is None or self._prefs_call_count % 50 == 0:
            self._prefs = await _fetch_admin_prefs()
            scanner_logger.info(
                f"[SIMULATION] Loaded admin prefs — "
                f"price=[{self._prefs.min_price:.0f},{self._prefs.max_price:.0f}] "
                f"rvol≥{self._prefs.min_rvol} vol≥{self._prefs.min_volume:,} "
                f"float≤{self._prefs.max_float/1e6:.0f}M "
                f"mcap≤{self._prefs.max_market_cap/1e6:.0f}M"
            )
        return self._prefs

    def _next_meta(self) -> Dict[str, str]:
        global _ticker_idx
        meta = _SIM_POOL[_ticker_idx % len(_SIM_POOL)]
        _ticker_idx += 1
        return meta

    def _next_scenario(self) -> str:
        global _scenario_idx
        sc = _SCENARIOS[_scenario_idx % len(_SCENARIOS)]
        _scenario_idx += 1
        return sc

    # ── BaseDataProvider interface ───────────────────────────────────────────

    async def connect_websocket(self, callback) -> None:
        pass

    async def disconnect_websocket(self) -> None:
        pass

    async def get_active_tickers(self) -> List[str]:
        return self._active_tickers

    async def get_quotes_batch(self, tickers: List[str]) -> List[Dict[str, Any]]:
        """
        Generate one coherent synthetic quote per batch call.
        Uses rotating meta and scenario pool to guarantee variety.
        """
        prefs    = await self._get_prefs()
        meta     = self._next_meta()
        scenario = self._next_scenario()
        quote    = _build_coherent_quote(meta, scenario, prefs)
        return [quote]

    async def get_quote(self, ticker: str) -> Dict[str, Any]:
        """Return a single synthetic quote for the requested symbol."""
        prefs    = await self._get_prefs()
        scenario = self._next_scenario()
        # Find matching meta or create a placeholder
        meta = next((m for m in _SIM_POOL if m["symbol"] == ticker), {
            "symbol":   ticker,
            "name":     f"{ticker} Corp",
            "sector":   "Technology",
            "industry": "Software—Application",
        })
        return _build_coherent_quote(meta, scenario, prefs)

    async def get_historical_bars(self, ticker: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Generate synthetic historical OHLCV bars whose volume profile converges
        into a realistic RVOL spike on the last 5 bars for TA calculations.
        """
        prefs    = await self._get_prefs()
        # Use mid-range price so bars converge realistically
        mid_price = (prefs.min_price + prefs.max_price) / 2
        avg_vol   = max(prefs.min_volume * 2, 200_000)
        rvol_hint = prefs.min_rvol + 2.0
        return _build_coherent_bars(mid_price, rvol_hint, avg_vol, n=limit)

    async def get_key_financials(self, ticker: str) -> Dict[str, Any]:
        """
        Return Shariah-compliant financials anchored to the quote's actual
        market cap so all debt/cash ratios stay well below 33%.
        """
        quote      = await self.get_quote(ticker)
        market_cap = float(quote.get("marketCap") or 100_000_000.0)
        return _build_compliant_financials(market_cap)

    async def get_news_and_catalysts(self, ticker: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Return scenario-appropriate Arabic catalysts.
        Only news_catalyst and certain momentum scenarios return a headline.
        """
        # Determine which scenario was last used — approximate by ticker rotation
        scenario = _SCENARIOS[(_ticker_idx - 1) % len(_SCENARIOS)]
        return _pick_news(scenario, ticker)
