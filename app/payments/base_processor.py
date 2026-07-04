from abc import ABC, abstractmethod
from typing import Dict, Any

class BasePaymentProcessor(ABC):
    """
    Abstract Base Class for Payment Gateways.
    Allows easy switching between Mock, Stripe, PayPal, Crypto, etc.
    """
    
    @abstractmethod
    async def create_checkout_session(self, user_id: int, plan_id: int, amount: float) -> Dict[str, Any]:
        """
        Creates a payment session/intent.
        Returns:
            Dict containing checkout_url, transaction_id, and status
        """
        pass

    @abstractmethod
    async def verify_payment(self, payload: Dict[str, Any], signature: str = "") -> bool:
        """
        Verifies if the webhook payment event is valid.
        """
        pass
