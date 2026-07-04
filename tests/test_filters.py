import pytest
from app.filters.shariah_filter import ShariahFilter
from app.filters.stock_filter import StockFilter

def test_shariah_activity_filter():
    # Compliant
    assert ShariahFilter.is_activity_compliant("Technology", "Software", "CleanTech Inc") == True
    
    # Non-compliant
    assert ShariahFilter.is_activity_compliant("Financial Services", "Commercial Banks", "Usury Bank") == False
    assert ShariahFilter.is_activity_compliant("Consumer Defensive", "Tobacco", "Smoke King Corp") == False
    assert ShariahFilter.is_activity_compliant("Entertainment", "Casinos & Gaming", "Vegas Slots Group") == False

def test_shariah_financial_ratios():
    # Pass financial screens:
    # totalDebt = 10m, cash = 10m, market cap = 100m.
    # ratios: Debt/Cap = 10% (<33%), Cash/Cap = 10% (<33%)
    financials_good = {
        "marketCapTTM": 100000000,
        "totalDebtTTM": 10000000,
        "cashAndShortTermInvestmentsTTM": 10000000
    }
    compliant, reason = ShariahFilter.is_compliant(
        ticker="GOOD",
        company_name="Halal Tech",
        sector="Technology",
        industry="Software",
        key_financials=financials_good
    )
    assert compliant == True
    
    # Fail financial screens:
    # debt = 50m, cap = 100m. Ratio = 50% (>33%)
    financials_bad = {
        "marketCapTTM": 100000000,
        "totalDebtTTM": 50000000,
        "cashAndShortTermInvestmentsTTM": 5000000
    }
    compliant, reason = ShariahFilter.is_compliant(
        ticker="BAD",
        company_name="Leveraged Tech",
        sector="Technology",
        industry="Software",
        key_financials=financials_bad
    )
    assert compliant == False
    assert "Limit: 33%" in reason

def test_stock_criteria_filter():
    # Compliant Stock quote matching criteria
    good_quote = {
        "symbol": "PLTR",
        "name": "Palantir Technologies",
        "price": 15.0,
        "volume": 2000000,
        "marketCap": 500000000,
        "float": 10000000,
        "changePercent": 5.0,
        "gapPercent": 2.5,
        "rvol": 4.5
    }
    matched, reason = StockFilter.match_criteria(good_quote)
    assert matched == True
    
    # Price exceeding maximum
    high_price_quote = good_quote.copy()
    high_price_quote["price"] = 250.0  # limit is 20
    matched, reason = StockFilter.match_criteria(high_price_quote)
    assert matched == False
    assert "exceeds max" in reason

    # Chinese Stock Exclusion
    chinese_quote = good_quote.copy()
    chinese_quote["name"] = "China Mobile Limited"
    matched, reason = StockFilter.match_criteria(chinese_quote)
    assert matched == False
    assert "Chinese Stock Exclusion" in reason
