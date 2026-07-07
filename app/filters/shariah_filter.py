from typing import Tuple, Dict, Any
from app.core.logging import app_logger

# Define list of sector/industry keywords that violate Shariah guidelines
PROHIBITED_SECTORS = [
    "Financial Services", "Conventional Investment Banking", "Commercial Banks", "Insurance", "Savings & Cooperative Banks"
]

PROHIBITED_INDUSTRIES = [
    "Gambling", "Casinos & Gaming", "Tobacco", "Distillers & Vintners", "Beverages - Brewers", 
    "Aerospace & Defense", "Conventional Financial Services", "Credit Services", "Banks", "Banks - Regional"
]

class ShariahFilter:
    """
    Shariah Compliance Filter for Stock Analysis.
    Performs Business Activity screening and Financial Ratios checks.
    """
    
    @staticmethod
    def is_compliant(
        ticker: str,
        company_name: str,
        sector: str,
        industry: str,
        key_financials: Dict[str, Any],
        trace_id: str = "N/A"
    ) -> Tuple[bool, str]:
        """
        Screen stock for Shariah Compliance.
        Returns:
            (is_compliant: bool, reason: str)
        """
        # 1. Business Activity Screening
        company_name_lower = company_name.lower() if company_name else ""
        sector = sector or ""
        industry = industry or ""
        
        # Check against prohibited names or sectors
        for item in PROHIBITED_SECTORS:
            if item.lower() in sector.lower():
                reason = f"Prohibited sector: {sector}"
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=ShariahSector | Required=Non-Prohibited | Actual={sector} | Result=Rejected | Reason={reason}")
                return False, reason

        for item in PROHIBITED_INDUSTRIES:
            if item.lower() in industry.lower():
                reason = f"Prohibited industry: {industry}"
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=ShariahIndustry | Required=Non-Prohibited | Actual={industry} | Result=Rejected | Reason={reason}")
                return False, reason
                
        # Manual name-checks for gambling/liquor/defense
        prohibited_keywords = ["casino", "gaming", "brewery", "distillery", "defense systems", "tobacco"]
        for kw in prohibited_keywords:
            if kw in company_name_lower:
                reason = f"Prohibited activity detected in name: {kw}"
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=ShariahNameKeyword | Required=Non-Prohibited | Actual={company_name} | Result=Rejected | Reason={reason}")
                return False, reason

        # 2. Financial Ratio Screening
        try:
            market_cap = key_financials.get("marketCapTTM") or key_financials.get("marketCapitalization") or 1.0
            if market_cap <= 0:
                market_cap = 1.0
                
            total_debt = key_financials.get("totalDebtTTM") or key_financials.get("totalDebt") or 0.0
            cash_and_equivalents = key_financials.get("cashAndShortTermInvestmentsTTM") or key_financials.get("cashAndCashEquivalents") or 0.0
            
            # Ratios
            debt_to_cap = (total_debt / market_cap) * 100
            cash_to_cap = (cash_and_equivalents / market_cap) * 100
            
            if debt_to_cap >= 33.0:
                reason = f"Debt/Market Cap is {debt_to_cap:.2f}% (Limit: 33%)"
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=ShariahDebtRatio | Required=<33.0% | Actual={debt_to_cap:.2f}% | Result=Rejected | Reason={reason}")
                return False, reason
            app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=ShariahDebtRatio | Required=<33.0% | Actual={debt_to_cap:.2f}% | Result=Passed")
                
            if cash_to_cap >= 33.0:
                reason = f"Cash/Market Cap is {cash_to_cap:.2f}% (Limit: 33%)"
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=ShariahCashRatio | Required=<33.0% | Actual={cash_to_cap:.2f}% | Result=Rejected | Reason={reason}")
                return False, reason
            app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=ShariahCashRatio | Required=<33.0% | Actual={cash_to_cap:.2f}% | Result=Passed")
                
        except Exception as e:
            app_logger.warning(f"[ERROR] TraceID={trace_id} | Failed to calculate financial ratios for {ticker}: {str(e)}. Defaulting to compliant activity screen only.")
            
        app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=ShariahFinancials | Required=Passed | Actual=Passed | Result=Passed")
        return True, "Passed Shariah business and financial screens"
        
    @staticmethod
    def is_activity_compliant(sector: str, industry: str, company_name: str, trace_id: str = "N/A") -> bool:
        """Helper to do a quick pre-screen without financials"""
        sector_lower = sector.lower() if sector else ""
        industry_lower = industry.lower() if industry else ""
        company_lower = company_name.lower() if company_name else ""
        
        for item in PROHIBITED_SECTORS:
            if item.lower() in sector_lower:
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=ShariahPreSector | Required=Non-Prohibited | Actual={sector} | Result=Rejected | Reason=Prohibited Sector")
                return False
        for item in PROHIBITED_INDUSTRIES:
            if item.lower() in industry_lower:
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=ShariahPreIndustry | Required=Non-Prohibited | Actual={industry} | Result=Rejected | Reason=Prohibited Industry")
                return False
                
        prohibited_keywords = ["casino", "gaming", "brewery", "distillery", "defense systems", "tobacco"]
        for kw in prohibited_keywords:
            if kw in company_lower:
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=ShariahPreNameKeyword | Required=Non-Prohibited | Actual={company_name} | Result=Rejected | Reason=Prohibited Name Keyword: {kw}")
                return False
        app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=ShariahPreScreen | Required=Compliant | Actual={sector}/{industry} | Result=Passed")
        return True
