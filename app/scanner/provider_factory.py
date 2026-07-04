from app.core.config import settings
from app.scanner.base_provider import BaseDataProvider
from app.scanner.fmp_provider import FMPDataProvider
from app.core.logging import scanner_logger

class DataProviderFactory:
    """Factory to fetch active data provider class"""
    
    @staticmethod
    def get_provider() -> BaseDataProvider:
        provider_name = settings.ACTIVE_DATA_PROVIDER.upper()
        if provider_name == "FMP":
            scanner_logger.info("Initializing Financial Modeling Prep (FMP) Data Provider")
            return FMPDataProvider()
        else:
            # Fallback to FMP as it is our primary source
            scanner_logger.warning(f"Provider {provider_name} is not fully configured. Falling back to FMP.")
            return FMPDataProvider()
