from app.core.config import settings
from app.payments.base_processor import BasePaymentProcessor
from app.payments.mock_processor import MockPaymentProcessor
from app.payments.stripe_processor import StripePaymentProcessor
from app.core.logging import app_logger

class PaymentService:
    """
    Factory service loader to return the active Payment Gateway Processor.
    """
    
    @staticmethod
    def get_processor() -> BasePaymentProcessor:
        provider = settings.PAYMENT_PROVIDER.upper()
        if provider == "STRIPE":
            app_logger.info("Initializing Stripe Payment Gateway Integration.")
            return StripePaymentProcessor()
        else:
            app_logger.info("Initializing Default Mock Payment Gateway Processor.")
            return MockPaymentProcessor()
