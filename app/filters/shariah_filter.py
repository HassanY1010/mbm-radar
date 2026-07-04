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
        key_financials: Dict[str, Any]
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
                return False, f"Prohibited sector: {sector}"

        for item in PROHIBITED_INDUSTRIES:
            if item.lower() in industry.lower():
                return False, f"Prohibited industry: {industry}"
                
        # Manual name-checks for gambling/liquor/defense
        prohibited_keywords = ["casino", "gaming", "brewery", "distillery", "defense systems", "tobacco"]
        for kw in prohibited_keywords:
            if kw in company_name_lower:
                return False, f"Prohibited activity detected in name: {kw}"

        # 2. Financial Ratio Screening
        # standard filters:
        # Debt / Market Cap < 33%
        # Cash + Interest-bearing securities / Market Cap < 33%
        
        # FMP key-metrics ttm provides:
        # 'debtToAssetsTTM' or we can check debt to market cap directly.
        # Let's extract values
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
                return False, f"Debt/Market Cap is {debt_to_cap:.2f}% (Limit: 33%)"
                
            if cash_to_cap >= 33.0:
                return False, f"Cash/Market Cap is {cash_to_cap:.2f}% (Limit: 33%)"
                
        except Exception as e:
            app_logger.warning(f"Failed to calculate financial ratios for {ticker}: {str(e)}. Defaulting to compliant activity screen only.")
            
        return True, "Passed Shariah business and financial screens"
        
    @staticmethod
    def is_activity_compliant(sector: str, industry: str, company_name: str) -> bool:
        """Helper to do a quick pre-screen without financials"""
        sector_lower = sector.lower() if sector else ""
        industry_lower = industry.lower() if industry else ""
        company_lower = company_name.lower() if company_name else ""
        
        for item in PROHIBITED_SECTORS:
            if item.lower() in sector_lower:
                return False
        for item in PROHIBITED_INDUSTRIES:
            if item.lower() in industry_lower:
                return False
                
        prohibited_keywords = ["casino", "gaming", "brewery", "distillery", "defense systems", "tobacco"]
        for kw in prohibited_keywords:
            if kw in company_lower:
                return False
        return True
