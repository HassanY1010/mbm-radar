from typing import Dict, Any, List, Optional
from app.core.config import settings

class StockFilter:
    """
    Applies the custom technical and fundamental criteria filters for momentum scanning.
    Supports user preferences override.
    """
    
    @staticmethod
    def match_criteria(
        quote: Dict[str, Any],
        user_pref: Optional[Dict[str, Any]] = None,
        blacklist: Optional[List[str]] = None,
        whitelist: Optional[List[str]] = None
    ) -> tuple[bool, str]:
        """
        Check if stock quote matches criteria.
        Returns:
            (is_match: bool, reason_for_failure: str)
        """
        ticker = quote.get("symbol", "").upper()
        if not ticker:
            return False, "Empty Ticker"

        # 1. Whitelist / Blacklist checks
        if whitelist and ticker in whitelist:
            return True, "Whitelisted"
        if blacklist and ticker in blacklist:
            return False, "Blacklisted"

        # 2. Get active thresholds (user specific overrides or global settings)
        max_price = user_pref.get("max_price") if user_pref else settings.SCANNER_MAX_PRICE
        max_float = user_pref.get("max_float") if user_pref else settings.SCANNER_MAX_FLOAT
        max_market_cap = user_pref.get("max_market_cap") if user_pref else settings.SCANNER_MAX_MARKET_CAP
        min_rvol = user_pref.get("min_rvol") if user_pref else settings.SCANNER_MIN_RVOL
        min_volume = user_pref.get("min_volume") if user_pref else settings.SCANNER_MIN_VOLUME
        min_gap_pct = user_pref.get("min_gap_pct") if user_pref else settings.SCANNER_MIN_GAP_PCT
        min_change_pct = user_pref.get("min_change_pct") if user_pref else settings.SCANNER_MIN_CHANGE_PCT
        
        # 3. Values from quote
        price = quote.get("price", 0.0)
        volume = quote.get("volume", 0)
        market_cap = quote.get("marketCap", 0.0) or quote.get("marketCapitalization", 0.0)
        float_size = quote.get("float", 0.0) or quote.get("sharesOutstanding", 0.0) # fallback
        change_pct = quote.get("changePercent", 0.0) or quote.get("changesPercentage", 0.0)
        gap_pct = quote.get("gapPercent", 0.0) or 0.0
        
        # Calculate derived metrics
        # Dollar Volume = Price * Volume
        dollar_volume = price * volume
        
        # Relative Volume (RVOL) - fallback if not calculated in TA
        rvol = quote.get("rvol", 1.0)
        
        # Filter checks:
        
        # Minimum price (avoid sub-penny stocks) & Max price
        if price < 0.10:
            return False, f"Price too low: ${price}"
        if price > max_price:
            return False, f"Price ${price} exceeds max ${max_price}"

        # Volume
        if volume < min_volume:
            return False, f"Volume {volume} below min {min_volume}"

        # Dollar Volume
        if dollar_volume < 100000:  # Minimum 100k dollar volume
            return False, f"Dollar Volume ${dollar_volume:.2f} too low"

        # Market Cap
        if market_cap > max_market_cap:
            return False, f"Market Cap ${market_cap:,.2f} exceeds max ${max_market_cap:,.2f}"

        # Float Size
        if float_size > max_float:
            return False, f"Float size {float_size:,.0f} exceeds max {max_float:,.0f}"

        # Relative Volume (RVOL)
        if rvol < min_rvol:
            return False, f"RVOL {rvol:.2f} below min {min_rvol:.2f}"

        # Change & Gap
        if abs(change_pct) < min_change_pct:
            return False, f"Change {change_pct:.2f}% below min {min_change_pct:.2f}%"

        # 4. Special exclusions
        company_name = quote.get("name", "").upper() or quote.get("companyName", "").upper()
        
        # Chinese Stock Exclusion
        chinese_indicators = [".CN", "CHINA", "CHINESE", "SINA", "ALIBABA", "TENCENT", "BAIDU", "JD.COM", "PINDUODUO"]
        for ind in chinese_indicators:
            if ind in company_name or ticker.endswith(".CN"):
                return False, "Chinese Stock Exclusion"

        # SPAC Exclusions
        spac_indicators = ["SPAC", "ACQUISITION", "BLANK CHECK", "UNIT", "WARRANT"]
        for ind in spac_indicators:
            if ind in company_name:
                return False, "SPAC Exclusion"

        # ETF Exclusions
        if "ETF" in company_name or quote.get("isETF") or quote.get("isEtf"):
            return False, "ETF Exclusion"

        # ADR check (usually symbols ending in Y or contains ADR)
        if "ADR" in company_name or (len(ticker) == 5 and ticker.endswith("Y")):
            return False, "ADR Exclusion"

        return True, "Passed criteria"
