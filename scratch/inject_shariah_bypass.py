"""
Injects Shariah cache bypass for simulation mode into get_shariah_status in scanner_manager.py
"""

file_path = "app/scanner/scanner_manager.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target_shariah_start = """    async def get_shariah_status(self, ticker: str, company_name: str, sector: str, industry: str, trace_id: str = "N/A") -> bool:
        \"\"\"Determines and caches Shariah compliance status of a stock\"\"\"
        ticker = ticker.upper()
        if ticker in self.shariah_cache:"""

replacement_shariah_start = """    async def get_shariah_status(self, ticker: str, company_name: str, sector: str, industry: str, trace_id: str = "N/A") -> bool:
        \"\"\"Determines and caches Shariah compliance status of a stock\"\"\"
        ticker = ticker.upper()
        
        # In simulation mode, skip caching and database reads to ensure dynamic generation is always used
        if settings.SIMULATION_MODE:
            financials = await self.provider.get_key_financials(ticker)
            is_compliant, reason = ShariahFilter.is_compliant(
                ticker=ticker,
                company_name=company_name,
                sector=sector,
                industry=industry,
                key_financials=financials or {},
                trace_id=trace_id
            )
            return is_compliant

        if ticker in self.shariah_cache:"""

assert target_shariah_start in content, "FAILED: get_shariah_status target not found"
content = content.replace(target_shariah_start, replacement_shariah_start, 1)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Programmatic cache bypass injected successfully!")
