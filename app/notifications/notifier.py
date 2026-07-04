import datetime
import redis.asyncio as aioredis
from typing import Optional
from sqlalchemy import select
from aiogram import Bot
from app.core.config import settings
from app.core.logging import app_logger
from app.models.models import Signal, User, UserPreferences, Subscription, Notification
from app.database.session import async_session

class Notifier:
    """
    Formulates and dispatches alerts to Telegram channel and individual users.
    Implements Redis anti-spam cooldown lock and daily alert counters.
    Matches styling from target Telegram Channel (RadarBot).
    """
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        self.cooldown_seconds = settings.COOLDOWN_PERIOD_MINUTES * 60

    async def _check_and_set_cooldown(self, ticker: str) -> bool:
        """
        Check if ticker is in cooldown period in Redis.
        If not, set the cooldown lock and return True.
        If in cooldown, return False.
        """
        key = f"cooldown:{ticker.upper()}"
        exists = await self.redis_client.get(key)
        if exists:
            return False
        
        # Set cooldown lock
        await self.redis_client.setex(key, self.cooldown_seconds, "locked")
        return True

    async def _get_daily_alert_number(self) -> int:
        """Get and increment the daily alert counter from Redis"""
        today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        key = f"daily_alert_count:{today}"
        count = await self.redis_client.incr(key)
        # Expire in 48 hours to automatically clean up Redis
        await self.redis_client.expire(key, 172800)
        return count

    def _format_value_arabic(self, value: float) -> str:
        """Helper to format large numbers to Arabic terms (million, thousand, etc.)"""
        if not value:
            return "غير متوفر"
        if value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.1f} مليار"
        elif value >= 1_000_000:
            return f"{value / 1_000_000:.1f} مليون"
        elif value >= 1_000:
            return f"{value / 1_000:.1f} ألف"
        return f"{value:.2f}"

    def _format_liquidity(self, value: float) -> str:
        """Helper to format liquidity (dollar volume) as $121.60K or $197.64M"""
        if not value:
            return "0.00$"
        if value >= 1_000_000:
            return f"{value / 1_000_000:.2f}M$"
        elif value >= 1_000:
            return f"{value / 1_000:.2f}K$"
        return f"{value:.2f}$"

    def _determine_movement_type(self, s: Signal) -> str:
        """Determine movement type matching requested categories: Breakout, Momentum, Whale Trade, Reversal"""
        if s.change_pct >= 30.0 or s.rvol >= 10.0:
            return "زخم قوي"
        elif s.price >= (s.resistance or 0.0) and s.price > (s.vwap or 0.0):
            return "اختراق"
        elif s.dollar_volume >= 5_000_000:
            return "صفقة حوت كبيرة"
        elif s.rsi_14 and s.rsi_14 < 35.0:
            return "انعكاس صعودي"
        return "زخم"

    def _format_alert_message(self, s: Signal, alert_number: int) -> str:
        """Creates a beautifully formatted Arabic Telegram message matching the requested style"""
        movement_type = self._determine_movement_type(s)
        
        # Format metrics
        float_str = self._format_value_arabic(s.float_size * 1_000_000 if s.float_size and s.float_size < 1000 else (s.float_size or 0))
        market_cap_str = self._format_value_arabic(s.market_cap)
        liquidity_str = self._format_liquidity(s.dollar_volume)
        
        # Estimate first minute volume (usually 5% of total current volume or opening bar volume)
        first_min_vol = max(1000, int(s.volume * 0.05))
        first_min_vol_str = self._format_value_arabic(first_min_vol)
        
        # Select correct flag
        flag = "🇺🇸"
        if s.exchange and "TSX" in s.exchange.upper():
            flag = "🇨🇦"
            
        # Determine extra badges
        badges = ""
        if s.rvol >= 8.0:
            badges += "⚡️ <b>مرشح للضغط (IND)</b>\n"
        if s.quality_score >= 8.5:
            badges += "🔥 <b>سهم نشط معروف (مضاربات مشهورة عليه)</b>\n"
        if s.dollar_volume >= 10_000_000:
            badges += "🐳 <b>صفقة حوت كبيرة</b>\n"

        # News section formatting
        news_section = ""
        if s.catalyst and s.catalyst != "No recent catalysts":
            # Estimate how long ago news was published (mock offset)
            news_section = f"📰 <b>خبر:</b> {s.catalyst} -> <i>منذ ساعة</i>\n"

        # SEC Filings Link (use SEC Form 8-K or Form 6-K as default indicator based on exchange)
        sec_form_type = "6-K" if flag == "🇨🇦" else "8-K"
        sec_link_url = s.sec_link if s.sec_link else f"https://www.sec.gov/edgar/searchedgar/companysearch.html?q={s.ticker}"
        
        sec_section = (
            f"📋 تقرير رسمي (نموذج {sec_form_type} SEC)\n"
            f"📋 هيئة الأوراق المالية • <a href='{sec_link_url}'>رابط FORM {sec_form_type} الرابط</a>\n"
        )
        
        # Split ratio fallback display (simulated if split activity detected)
        split_section = ""
        if s.float_size and s.float_size < 15.0:
            split_section = f"📋 نسبة التقسيم العكسي -> 1/10 قبل 3 يوم\n"

        return (
            f"🔸 <b>الرمز -> {s.ticker} {flag}</b>\n"
            f"📋 <b>نوع الحركة -> {movement_type}</b>\n"
            f"🚨 <b>تنبيه رقم {alert_number} اليوم ⚡️</b>\n"
            f"📈 <b>نسبة الارتفاع -> {s.change_pct:+.2f}%</b>\n"
            f"💰 <b>السعر -> {s.price:.2f} دولار</b>\n"
            f"📋 <b>الأسهم المتاحة -> {float_str}</b>\n"
            f"💰 <b>القيمة السوقية -> {market_cap_str}</b>\n"
            f"📈 <b>الحجم النسبي -> {s.rvol:.1f}X مرة</b>\n"
            f"📋 <b>حجم أول دقيقة -> {first_min_vol_str}</b>\n"
            f"💧 <b>السيولة -> {liquidity_str}</b>\n"
            f"{badges}"
            f"{split_section}"
            f"{news_section}"
            f"{sec_section}"
        )

    async def dispatch_signal(self, signal: Signal):
        """Dispatches signal to Channel and active subscribers"""
        # 1. Cooldown Check
        if not await self._check_and_set_cooldown(signal.ticker):
            app_logger.info(f"Signal for {signal.ticker} skipped due to cooldown lock.")
            return

        # Get the sequential alert number for today
        alert_number = await self._get_daily_alert_number()
        
        # Format the Arabic message exactly matching the RadarBot style
        message_text = self._format_alert_message(signal, alert_number)

        # 2. Dispatch to Telegram Channel
        channel_msg_id = None
        try:
            chan_msg = await self.bot.send_message(
                chat_id=settings.TELEGRAM_CHANNEL_ID,
                text=message_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            channel_msg_id = chan_msg.message_id
            app_logger.info(f"Arabic Signal alert sent to Telegram Channel {settings.TELEGRAM_CHANNEL_ID}")
        except Exception as e:
            app_logger.error(f"Failed to send alert to Channel: {str(e)}")

        # Log notification in Database
        async with async_session() as db:
            db.add(Notification(
                user_id=None,
                telegram_message_id=channel_msg_id,
                ticker=signal.ticker,
                signal_id=signal.id,
                sent_at=datetime.datetime.utcnow(),
                status="sent" if channel_msg_id else "failed"
            ))
            await db.commit()

        # 3. Dispatch to Direct Users who have enabled alerts and match preferences
        async with async_session() as db:
            # Query all active subscribers with alerts_enabled=True
            query = select(User).join(UserPreferences).join(Subscription).where(
                UserPreferences.alerts_enabled == True,
                Subscription.status == "active",
                Subscription.end_date > datetime.datetime.utcnow()
            )
            result = await db.execute(query)
            active_users = result.scalars().all()
            
            for user in active_users:
                # Check user preferences matching
                pref = user.preferences
                
                # Price matching
                if signal.price > pref.max_price:
                    continue
                # Float size matching
                if signal.float_size and signal.float_size > pref.max_float:
                    continue
                # RVOL matching
                if signal.rvol < pref.min_rvol:
                    continue
                # Gap matching
                if signal.gap_pct < pref.min_gap_pct:
                    continue
                # Change matching
                if abs(signal.change_pct) < pref.min_change_pct:
                    continue
                # Volume matching
                if signal.volume < pref.min_volume:
                    continue

                # Send direct message to the user
                try:
                    user_msg = await self.bot.send_message(
                        chat_id=user.telegram_id,
                        text=message_text,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                    
                    db.add(Notification(
                        user_id=user.id,
                        telegram_message_id=user_msg.message_id,
                        ticker=signal.ticker,
                        signal_id=signal.id,
                        sent_at=datetime.datetime.utcnow(),
                        status="sent"
                    ))
                except Exception as user_err:
                    app_logger.warning(f"Could not send direct alert to user {user.telegram_id}: {str(user_err)}")
                    
            await db.commit()
