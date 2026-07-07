from typing import Dict, Any, List, Optional
from app.core.config import settings
from app.core.logging import scanner_logger

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
        whitelist: Optional[List[str]] = None,
        trace_id: str = "N/A"
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
            scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=Whitelist | Required=None | Actual={ticker} | Result=Passed | Reason=Whitelisted")
            return True, "Whitelisted"
        if blacklist and ticker in blacklist:
            scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=Blacklist | Required=None | Actual={ticker} | Result=Rejected | Reason=Blacklisted")
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
        float_size = quote.get("float") or quote.get("sharesOutstanding") or ((quote.get("marketCap", 0.0) / quote.get("price", 1.0)) if quote.get("price") else 0.0)
        change_pct = quote.get("changePercentage", 0.0) or quote.get("changePercent", 0.0) or quote.get("changesPercentage", 0.0)
        gap_pct = quote.get("gapPercent", 0.0) or quote.get("gapPercentage", 0.0) or change_pct
        
        # Calculate derived metrics
        dollar_volume = price * volume
        rvol = quote.get("rvol")
        
        # Filter checks:
        
        # Minimum price & Max price
        if price < 0.10:
            reason = f"Price ${price:.2f} too low (minimum $0.10)"
            scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=MinPrice | Required=>=0.10 | Actual={price:.2f} | Result=Rejected | Reason={reason}")
            return False, reason
        if price > max_price:
            reason = f"Price ${price:.2f} exceeds max ${max_price:.2f}"
            scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=MaxPrice | Required=<={max_price:.2f} | Actual={price:.2f} | Result=Rejected | Reason={reason}")
            return False, reason
        scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=PriceRange | Required=0.10 to {max_price:.2f} | Actual={price:.2f} | Result=Passed")
 
        # Volume
        if volume < min_volume:
            reason = f"Volume {volume} below min {min_volume}"
            scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=Volume | Required=>={min_volume} | Actual={volume} | Result=Rejected | Reason={reason}")
            return False, reason
        scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=Volume | Required=>={min_volume} | Actual={volume} | Result=Passed")
 
        # Dollar Volume
        if dollar_volume < 100000:
            reason = f"Dollar Volume ${dollar_volume:.2f} too low (minimum $100,000)"
            scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=DollarVolume | Required=>=100000 | Actual={dollar_volume:.2f} | Result=Rejected | Reason={reason}")
            return False, reason
        scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=DollarVolume | Required=>=100000 | Actual={dollar_volume:.2f} | Result=Passed")
 
        # Market Cap
        if market_cap and market_cap > max_market_cap:
            reason = f"Market Cap ${market_cap:,.2f} exceeds max ${max_market_cap:,.2f}"
            scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=MarketCap | Required=<={max_market_cap:,.2f} | Actual={market_cap:,.2f} | Result=Rejected | Reason={reason}")
            return False, reason
        scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=MarketCap | Required=<={max_market_cap:,.2f} | Actual={market_cap:,.2f} | Result=Passed")
 
        # Float Size
        if float_size and float_size > max_float:
            reason = f"Float size {float_size:,.0f} exceeds max {max_float:,.0f}"
            scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=FloatSize | Required=<={max_float:,.0f} | Actual={float_size:,.0f} | Result=Rejected | Reason={reason}")
            return False, reason
        scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=FloatSize | Required=<={max_float:,.0f} | Actual={float_size:,.0f} | Result=Passed")
 
        # Relative Volume (RVOL)
        if rvol is not None and rvol < min_rvol:
            reason = f"RVOL {rvol:.2f} below min {min_rvol:.2f}"
            scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=RVOL | Required=>={min_rvol:.2f} | Actual={rvol:.2f} | Result=Rejected | Reason={reason}")
            return False, reason
        if rvol is not None:
            scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=RVOL | Required=>={min_rvol:.2f} | Actual={rvol:.2f} | Result=Passed")
 
        # Change & Gap
        if abs(change_pct) < min_change_pct:
            reason = f"Change {change_pct:.2f}% below min {min_change_pct:.2f}%"
            scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=ChangePercent | Required=>={min_change_pct:.2f}% | Actual={change_pct:.2f}% | Result=Rejected | Reason={reason}")
            return False, reason
        scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=ChangePercent | Required=>={min_change_pct:.2f}% | Actual={change_pct:.2f}% | Result=Passed")
 
        # 4. Special exclusions
        company_name = quote.get("name", "").upper() or quote.get("companyName", "").upper()
        
        # Chinese Stock Exclusion
        chinese_indicators = [".CN", "CHINA", "CHINESE", "SINA", "ALIBABA", "TENCENT", "BAIDU", "JD.COM", "PINDUODUO"]
        for ind in chinese_indicators:
            if ind in company_name or ticker.endswith(".CN"):
                scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=ChineseExclusion | Required=Non-Chinese | Actual={company_name} | Result=Rejected | Reason=Chinese Stock")
                return False, "Chinese Stock Exclusion"
 
        # SPAC Exclusions
        spac_indicators = ["SPAC", "ACQUISITION", "BLANK CHECK", "UNIT", "WARRANT"]
        for ind in spac_indicators:
            if ind in company_name:
                scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=SPACExclusion | Required=Non-SPAC | Actual={company_name} | Result=Rejected | Reason=SPAC Stock")
                return False, "SPAC Exclusion"
 
        # ETF Exclusions
        if "ETF" in company_name or quote.get("isETF") or quote.get("isEtf"):
            scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=ETFExclusion | Required=Non-ETF | Actual={company_name} | Result=Rejected | Reason=ETF Stock")
            return False, "ETF Exclusion"
 
        # ADR check
        if "ADR" in company_name or (len(ticker) == 5 and ticker.endswith("Y")):
            scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=ADRExclusion | Required=Non-ADR | Actual={company_name} | Result=Rejected | Reason=ADR Stock")
            return False, "ADR Exclusion"
 
        scanner_logger.info(f"[FILTER] TraceID={trace_id} | Filter=Exclusions | Required=None | Actual=Passed | Result=Passed")
        return True, "Passed criteria"
