import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, update
from app.database.session import async_session
from app.models.models import Subscription, User
from app.bot.bot_service import bot
from app.core.config import settings
from app.core.logging import scheduler_logger

scheduler = AsyncIOScheduler()

async def check_expired_subscriptions():
    """
    Periodic job that checks for expired subscriptions:
    1. Sets status='expired' for subscriptions whose end_date is in the past.
    2. Revokes private Telegram channel membership (kick user).
    3. Sends notification message.
    """
    scheduler_logger.info("Running expired subscription checker...")
    
    async with async_session() as db:
        # Fetch active subscriptions that have expired
        now = datetime.datetime.utcnow()
        query = (
            select(Subscription)
            .join(User)
            .where(
                Subscription.status == "active",
                Subscription.end_date < now
            )
        )
        res = await db.execute(query)
        expired_subs = res.scalars().all()
        
        for sub in expired_subs:
            # 1. Update DB Status
            sub.status = "expired"
            user_tg_id = sub.user.telegram_id
            
            scheduler_logger.info(f"Subscription for user {user_tg_id} expired. Revoking access...")
            
            # 2. Kick user from private Telegram channel
            try:
                # Ban & Unban is the standard Telegram protocol to kick/remove a user from a channel
                await bot.ban_chat_member(chat_id=settings.TELEGRAM_CHANNEL_ID, user_id=user_tg_id)
                await bot.unban_chat_member(chat_id=settings.TELEGRAM_CHANNEL_ID, user_id=user_tg_id)
                scheduler_logger.info(f"Removed user {user_tg_id} from private channel {settings.TELEGRAM_CHANNEL_ID}")
            except Exception as tg_err:
                scheduler_logger.error(f"Failed to remove user {user_tg_id} from Telegram channel: {str(tg_err)}")

            # 3. Notify user directly via bot
            try:
                expire_msg = (
                    "⚠️ <b>تنبيه انتهاء الاشتراك!</b>\n\n"
                    "انتهت فترة اشتراكك في خدمة MBM Radar وتمت إزالتك من القناة الخاصة تلقائياً.\n"
                    "لتجديد الاشتراك وتفعيل الخدمة مجدداً، يرجى فتح البوت واختيار باقة اشتراك جديدة."
                )
                await bot.send_message(chat_id=user_tg_id, text=expire_msg, parse_mode="HTML")
            except Exception as notify_err:
                scheduler_logger.warning(f"Could not notify user {user_tg_id} about expiration: {str(notify_err)}")
                
        await db.commit()
    scheduler_logger.info("Finished expired subscription check.")

def setup_scheduler():
    """Register cron tasks"""
    # Check expired subscriptions every hour
    scheduler.add_job(check_expired_subscriptions, "interval", hours=1, id="check_expiry")
    scheduler_logger.info("Scheduler tasks configured.")
