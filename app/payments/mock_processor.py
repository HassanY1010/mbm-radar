import datetime
from typing import Dict, Any
from app.payments.base_processor import BasePaymentProcessor

class MockPaymentProcessor(BasePaymentProcessor):
    """
    Mock payment processor for testing and demo purchases.
    Instantly completes and activates subscription period.
    """
    
    async def create_checkout_session(self, user_id: int, plan_id: int, amount: float) -> Dict[str, Any]:
        transaction_id = f"MOCK_TXN_{int(datetime.datetime.utcnow().timestamp())}"
        return {
            "checkout_url": f"https://t.me/mock_checkout?txn={transaction_id}",
            "transaction_id": transaction_id,
            "status": "completed"
        }

    async def verify_payment(self, payload: Dict[str, Any], signature: str = "") -> bool:
        # Mock payment verifies instantly if mock status is completed
        return payload.get("status") == "completed"
