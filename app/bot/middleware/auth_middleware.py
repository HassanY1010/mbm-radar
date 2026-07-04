import datetime
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, CallbackQuery, Message
from sqlalchemy import select
from app.database.session import async_session
from app.models.models import User, Subscription
from app.core.config import settings

class SubscriptionMiddleware(BaseMiddleware):
    """
    Middleware that checks if user has an active subscription.
    Blocks access to filters/watchlist commands for unsubscribed users.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Check only for Messages and CallbackQueries
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        # Allow /start, /help, subscription, and admin routing commands always
        is_allowed_message = False
        if isinstance(event, Message):
            text = event.text or ""
            is_allowed_message = text.startswith("/start") or text.startswith("/help")
        elif isinstance(event, CallbackQuery):
            data_val = event.data or ""
            is_allowed_message = (
                data_val.startswith("menu_sub") or 
                data_val.startswith("buy_plan_") or 
                data_val.startswith("menu_main")
            )

        if is_allowed_message or user.id == settings.ADMIN_TELEGRAM_ID:
            return await handler(event, data)

        # Verify active subscription in Database
        async with async_session() as db:
            query = (
                select(Subscription)
                .join(User)
                .where(
                    User.telegram_id == user.id,
                    Subscription.status == "active",
                    Subscription.end_date > datetime.datetime.utcnow()
                )
            )
            res = await db.execute(query)
            active_sub = res.scalar_one_or_none()

        if not active_sub:
            # User is unsubscribed
            warning_text = (
                "⚠️ <b>عذراً، هذا التبويب يتطلب اشتراكاً نشطاً!</b>\n\n"
                "يرجى الانتقال إلى قسم الاشتراكات وتفعيل إحدى باقات الاشتراك المتاحة للوصول إلى هذه الميزات."
            )
            if isinstance(event, Message):
                await event.answer(warning_text, parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.message.answer(warning_text, parse_mode="HTML")
                await event.answer()
            return
            
        return await handler(event, data)
