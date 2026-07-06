import datetime
import redis.asyncio as aioredis
import pytz
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

    def _format_large_number_arabic(self, value: float) -> str:
        """Formats numbers into clean Arabic financial terms (مليون، مليار، ألف)"""
        if not value:
            return "0"
        if value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.1f} مليار"
        elif value >= 1_000_000:
            return f"{value / 1_000_000:.1f} مليون"
        elif value >= 1_000:
            return f"{value / 1_000:.1f} ألف"
        return f"{value:,.0f}"

    def _generate_movement_news(self, s: Signal, eastern_time: datetime.datetime) -> str:
        """Generates a dynamic Arabic news story explaining the stock's price and volume movement"""
        direction = "ارتفاع" if s.change_pct >= 0 else "انخفاض"
        change_text = f"{direction} السهم بنسبة {abs(s.change_pct):.2f}%"
        
        reasons = []
        if s.rsi_14 and s.rsi_14 < 35.0:
            reasons.append("تكوين قاع صعودي جديد واسترجاع القوة الشرائية عند مستويات الـ RSI المتدنية")
        elif s.hod and s.price >= s.hod:
            reasons.append("اختراق أعلى سعر سجله اليوم (High of Day) مع زخم صعودي قوي")
        elif s.vwap and s.price > s.vwap:
            reasons.append("صعود السهم فوق مستويات الـ VWAP وتأكيد المسار الصاعد")
            
        if s.rvol >= 5.0:
            reasons.append(f"ارتفاع ملحوظ في الحجم النسبي بمعدل {s.rvol:.1f} ضعف المعدل الطبيعي")
        if s.dollar_volume >= 5_000_000:
            reasons.append(f"تدفق سيولة قوية ومكثفة بقيمة {self._format_large_number_arabic(s.dollar_volume)}")
        
        # Catalyst news integration
        catalyst_text = ""
        if s.catalyst and s.catalyst != "No recent catalysts" and len(s.catalyst) > 5:
            cleaned_catalyst = s.catalyst.replace('"', '').strip()
            catalyst_text = f" بالتزامن مع الأخبار المتداولة: \"{cleaned_catalyst}\""
            
        if not reasons:
            reasons.append("حركة تداول وزخم طبيعي للمضاربة اليومية")
            
        story = f"شهدت جلسة اليوم {change_text}، نتيجة {reasons[0]}"
        if len(reasons) > 1:
            story += f" و{reasons[1]}"
            
        story += f".{catalyst_text}"
        return story

    def _determine_movement_type(self, s: Signal) -> str:
        """Determine movement type matching requested categories: Breakout, Momentum, Whale Trade, Reversal"""
        if s.change_pct >= 30.0 or s.rvol >= 10.0:
            return "تكوين قاع S 🛡️" if s.rsi_14 and s.rsi_14 < 35.0 else "زخم صعودي قوي 🔥"
        elif s.price >= (s.resistance or 0.0) and s.price > (s.vwap or 0.0):
            return "اختراق فني قوي 🚀"
        elif s.dollar_volume >= 5_000_000:
            return "صفقة حوت كبيرة 🐳"
        elif s.rsi_14 and s.rsi_14 < 35.0:
            return "تكوين قاع S 🛡️"
        return "زخم صعودي 📈"

    def _format_alert_message(self, s: Signal, alert_number: int) -> str:
        """Creates a beautifully formatted Arabic Telegram message matching the requested style exactly"""
        movement_type = self._determine_movement_type(s)
        
        # Select correct flag
        flag = "🇺🇸"
        if s.exchange and "TSX" in s.exchange.upper():
            flag = "🇨🇦"
            
        # Format metrics using Arabic terms
        volume_str = self._format_large_number_arabic(s.volume)
        raw_float = s.float_size * 1_000_000 if s.float_size and s.float_size < 1000 else (s.float_size or 0)
        float_str = self._format_large_number_arabic(raw_float)
        market_cap_str = self._format_large_number_arabic(s.market_cap)
        liquidity_str = self._format_large_number_arabic(s.dollar_volume)
        
        # Estimate first minute volume
        first_min_vol = max(1000, int(s.volume * 0.05))
        first_min_vol_str = self._format_large_number_arabic(first_min_vol)
        
        # Convert UTC to Eastern Time (US/New York) dynamically handling DST
        utc_time = s.timestamp.replace(tzinfo=pytz.utc)
        eastern_time = utc_time.astimezone(pytz.timezone("America/New_York"))
        time_str = eastern_time.strftime("%H:%M:%S")

        # VWAP formatting
        vwap_status = "✅ فوق VWAP" if s.vwap and s.price > s.vwap else "❌ تحت VWAP"
        vwap_val = f"{s.vwap:.2f}$" if s.vwap else "غير متوفر"
        hod_val = f"{s.hod:.2f}$" if s.hod else "غير متوفر"

        # Additional indicators
        indicators = []
        if s.rvol >= 8.0:
            indicators.append("مرشح للضغط (IND) ⚡️")
        if s.quality_score >= 7.5:
            indicators.append("عداء معروف 🏃")
        if s.dollar_volume >= 10_000_000:
            indicators.append("صفقة حوت كبيرة 🐳")
        if not indicators:
            indicators.append("نشاط زخم طبيعي 📊")
        indicators_str = " | ".join(indicators)

        # Sector & Industry
        sector_industry_str = f"{s.sector or 'غير متوفر'} / {s.industry or 'غير متوفر'}"

        # Trading Zones
        entry_val = f"{s.entry_price:.2f}$" if s.entry_price else f"{s.price * 0.98:.2f}$"
        tp1_val = f"{s.target1:.2f}$" if s.target1 else f"{s.price * 1.10:.2f}$"
        tp2_val = f"{s.target2:.2f}$" if s.target2 else f"{s.price * 1.25:.2f}$"
        tp3_val = f"{s.target3:.2f}$" if s.target3 else f"{s.price * 1.45:.2f}$"
        sl_val = f"{s.stop_loss:.2f}$" if s.stop_loss else f"{s.price * 0.90:.2f}$"

        # Gap preservation, ATR, Support/Resistance
        gap_val = f"{s.gap_pct:+.2f}%"
        avg_volume_str = self._format_large_number_arabic(s.avg_volume_30d or s.volume)
        atr_val = f"{s.atr14:.2f}" if s.atr14 else "0.00"
        
        res_val = f"{s.resistance:.2f}$" if s.resistance else "غير متوفر"
        sup_val = f"{s.support:.2f}$" if s.support else "غير متوفر"
        res_sup_str = f"{res_val} / {sup_val}"

        # Opportunity Quality
        score = s.quality_score or 0.0
        if score >= 9.0:
            quality_text = "🟢 فرصة استثنائية"
            stars = "⭐⭐⭐⭐⭐"
        elif score >= 7.5:
            quality_text = "🟢 فرصة ممتازة"
            stars = "⭐⭐⭐⭐"
        elif score >= 6.0:
            quality_text = "🟡 فرصة جيدة"
            stars = "⭐⭐⭐"
        elif score >= 4.5:
            quality_text = "🟠 فرصة متوسطة"
            stars = "⭐⭐"
        else:
            quality_text = "🔴 فرصة ضعيفة"
            stars = "⭐"

        # Generate the dynamic Movement News (الخبر)
        news_story = self._generate_movement_news(s, eastern_time)
        news_section = (
            f"\n📰 <b>الخبر:</b>\n"
            f"\"{news_story}\""
        )

        # SEC Link
        sec_form_type = "6-K" if flag == "🇨🇦" else "8-K"
        sec_link_url = s.sec_link if s.sec_link else f"https://www.sec.gov/edgar/searchedgar/companysearch.html?q={s.ticker}"
        sec_filing_str = f'<a href="{sec_link_url}">FORM {sec_form_type}</a>'

        return (
            f"<code>{time_str}</code>\n\n"
            f"🚨 <b>{movement_type} (تنبيه #{alert_number})</b>\n"
            f"♦️ الرمز ← <b>{s.ticker} {flag}</b>\n"
            f"• السعر الحالي: <b>{s.price:.2f}$ ({s.change_pct:+.2f}%)</b>\n"
            f"• الفوليوم: <b>{volume_str}</b>\n"
            f"📋 الأسهم المتاحة ← <b>{float_str}</b>\n"
            f"🏦 القيمة السوقية ← <b>{market_cap_str}</b>\n"
            f"📈 الحجم النسبي ← <b>{s.rvol:.1f}x</b>\n"
            f"💧 السيولة ← <b>{liquidity_str}</b>\n"
            f"📋 حجم أول دقيقة ← <b>{first_min_vol_str}</b>\n"
            f"📋 ملفات SEC · <b>{sec_filing_str}</b>\n"
            f"📊 VWAP: <b>{vwap_val} — {vwap_status}</b>\n"
            f"🔝 HOD: <b>{hod_val}</b>\n"
            f"🚩 مؤشرات إضافية: <b>{indicators_str}</b>\n"
            f"🏢 النشاط ← <b>{sector_industry_str}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📌 مناطق التداول:\n"
            f"🟢 دخول مقترح: <b>{entry_val}</b>\n"
            f"🎯 TP1: <b>{tp1_val}</b>\n"
            f"🎯 TP2: <b>{tp2_val}</b>\n"
            f"🎯 TP3: <b>{tp3_val}</b>\n"
            f"🛑 وقف خسارة: <b>{sl_val}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📈 نسبة الحفاظ على الفجوة: <b>{gap_val}</b>\n"
            f"📊 متوسط الحجم (30 يوم): <b>{avg_volume_str}</b>\n"
            f"📏 ATR-14: <b>{atr_val}</b>\n"
            f"📐 مقاومة/دعم (تاريخي): <b>{res_sup_str}</b>\n"
            f"🏆 جودة الفرصة: <b>{s.quality_score:.1f}/10 ({quality_text}) {stars}</b>"
            f"{news_section}"
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
                # Volume matching (flexible >= or <= operation)
                volume_op = getattr(pref, "volume_filter_type", ">=")
                if volume_op == "<=":
                    if signal.volume > pref.min_volume:
                        continue
                else:  # ">="
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
