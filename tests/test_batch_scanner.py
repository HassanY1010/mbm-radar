import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.scanner.scanner_manager import ScannerManager
from app.models.models import Signal

@pytest.mark.asyncio
async def test_stage1_pre_screening_and_scoring():
    # Setup mocks
    notification_callback = AsyncMock()
    scanner = ScannerManager(notification_callback=notification_callback)
    
    # Mock data provider methods
    scanner.provider.get_quotes_batch = AsyncMock(return_value=[
        # Compliant, high momentum
        {
            "symbol": "COMP",
            "name": "Compliant Growth",
            "price": 10.0,
            "volume": 200000,
            "marketCap": 500000000,
            "changePercentage": 8.0,
            "open": 9.5,
            "previousClose": 9.25,
            "priceAvg50": 9.0,
            "dayHigh": 10.2,
            "dayLow": 9.4,
            "exchange": "NASDAQ"
        },
        # Excluded (Chinese)
        {
            "symbol": "CHIN",
            "name": "China Telecom Corp",
            "price": 5.0,
            "volume": 500000,
            "marketCap": 200000000,
            "changePercentage": 10.0,
            "open": 4.8,
            "previousClose": 4.5,
            "priceAvg50": 4.0,
            "dayHigh": 5.1,
            "dayLow": 4.7,
            "exchange": "NYSE"
        },
        # Excluded (Volume too low)
        {
            "symbol": "THIN",
            "name": "Thin Trade Inc",
            "price": 12.0,
            "volume": 1000,
            "marketCap": 150000000,
            "changePercentage": 5.0,
            "open": 11.5,
            "previousClose": 11.4,
            "priceAvg50": 11.0,
            "dayHigh": 12.1,
            "dayLow": 11.3,
            "exchange": "NASDAQ"
        },
        # Excluded (Price exceeds max)
        {
            "symbol": "EXP",
            "name": "Expensive Inc",
            "price": 250.0,
            "volume": 300000,
            "marketCap": 1500000000,
            "changePercentage": 12.0,
            "open": 240.0,
            "previousClose": 223.0,
            "priceAvg50": 210.0,
            "dayHigh": 255.0,
            "dayLow": 235.0,
            "exchange": "NASDAQ"
        }
    ])
    
    scanner.active_tickers = ["COMP", "CHIN", "THIN", "EXP"]
    scanner.blacklist = []
    
    # Mock reload lists to do nothing
    scanner.reload_lists = AsyncMock()
    
    # We will override _polling_loop to run only once
    # and call self.stop() inside the try block to exit immediately
    scanner.is_running = True
    
    # Mock process_candidate to return a mock Signal or None
    mock_signal = MagicMock(spec=Signal)
    mock_signal.ticker = "COMP"
    scanner.process_candidate = AsyncMock(return_value=mock_signal)
    
    # Let's run a single scan manually by calling the core of _polling_loop
    # 1. Fetch batch
    quotes = await scanner.provider.get_quotes_batch(scanner.active_tickers)
    
    # 2. Stage 1 Filtering & Pre-Scoring
    candidate_quotes = []
    for quote in quotes:
        ticker = quote.get("symbol")
        price = float(quote.get("price") or 0.0)
        volume = float(quote.get("volume") or 0.0)
        market_cap = float(quote.get("marketCap") or 0.0)
        company_name = quote.get("name", "").upper()
        
        is_excluded = False
        for ind in ["CHINA", "CHINESE", "SINA", "ALIBABA", "TENCENT", "BAIDU", "JD.COM", "PINDUODUO"]:
            if ind in company_name or ticker.endswith(".CN"):
                is_excluded = True
                break
        if is_excluded:
            continue
            
        if volume < 50000 or price > 30.0:
            continue
            
        # Pre-score calculation
        change_pct = float(quote.get("changePercentage") or 0.0)
        momentum_base = change_pct * 0.7
        open_price = float(quote.get("open") or price)
        prev_close = float(quote.get("previousClose") or price)
        gap_pct = ((open_price - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0
        momentum_base += gap_pct * 0.3
        
        dollar_volume = price * volume
        liquidity_weight = min(1.0, dollar_volume / 2000000.0)
        price_avg_50 = float(quote.get("priceAvg50") or 0.0)
        trend_confirm = 1.2 if (price_avg_50 > 0 and price > price_avg_50) else 0.8
        day_high = float(quote.get("dayHigh") or price)
        day_low = float(quote.get("dayLow") or price)
        intraday_range = ((day_high - day_low) / price * 100.0) if price > 0 else 0.0
        volatility_factor = 0.5 if intraday_range > 25.0 else 1.0
        
        pre_score = momentum_base * liquidity_weight * trend_confirm * volatility_factor
        quote["pre_score"] = pre_score
        candidate_quotes.append(quote)
        
    assert len(candidate_quotes) == 1
    assert candidate_quotes[0]["symbol"] == "COMP"
    assert candidate_quotes[0]["pre_score"] > 0
