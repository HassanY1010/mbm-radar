import pytest
from app.indicators.technical_analysis import TechnicalAnalysis

def test_ta_calculator():
    # Construct dummy daily historical bars
    bars = []
    base_price = 10.0
    for i in range(50):
        # rising price trend
        close_p = base_price + (i * 0.1)
        bars.append({
            "open": close_p - 0.05,
            "high": close_p + 0.1,
            "low": close_p - 0.1,
            "close": close_p,
            "volume": 100000 + (i * 1000)
        })
        
    quote = {
        "price": 15.0,
        "volume": 300000
    }
    
    results = TechnicalAnalysis.calculate_all(bars, quote)
    
    # Assert output structure and indicators existence
    assert "sma_20" in results
    assert "ema_9" in results
    assert "rsi_14" in results
    assert "atr_14" in results
    assert "support" in results
    assert "resistance" in results
    assert "vwap" in results
    assert "rvol" in results
    
    # Check that calculations returned logical values
    assert results["sma_20"] > 0
    assert results["atr_14"] > 0
    assert 0 <= results["rsi_14"] <= 100
    assert results["rvol"] > 0
