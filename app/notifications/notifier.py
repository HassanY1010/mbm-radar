import datetime
import redis.asyncio as aioredis
import pytz
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
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

    async def _check_and_set_cooldown(self, ticker: str, trace_id: str = "N/A") -> bool:
        """
        Check if ticker is in cooldown period in Redis using atomic SETNX.
        If not set, it sets the lock and returns True.
        """
        key = f"cooldown:{ticker.upper()}"
        success = await self.redis_client.set(key, "locked", ex=self.cooldown_seconds, nx=True)
        ttl = await self.redis_client.ttl(key)
        status = "Active" if not success else "Expired/Created"
        app_logger.info(f"[REDIS] TraceID={trace_id} | Cooldown Check | Key={key} | TTL={ttl} | Cooldown Status={status}")
        return bool(success)

    async def _get_ticker_alert_number(self, ticker: str) -> int:
        """
        Get and increment the per-ticker alert counter from Redis.
        Each stock has its own independent counter starting from 1.
        """
        key = f"alert_count:{ticker.upper()}"
        count = await self.redis_client.incr(key)
        # Expire counter in 7 days so it resets weekly
        await self.redis_client.expire(key, 604800)
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
        """Generates a compact, 1-2 line Arabic news story explaining the stock's price/volume movement"""
        direction = "ارتفاع" if s.change_pct >= 0 else "انخفاض"
        change_text = f"{direction} بنسبة {abs(s.change_pct):.1f}%"
        
        reasons = []
        rsi_val = getattr(s, "rsi_14", None)
        if rsi_val and rsi_val < 35.0:
            reasons.append("تكوين قاع عند RSI متدنٍ")
        elif s.hod and s.price >= s.hod:
            reasons.append("اختراق الـ HOD")
        elif s.vwap and s.price > s.vwap:
            reasons.append("اختراق الـ VWAP")
            
        if s.rvol >= 5.0:
            reasons.append(f"تضاعف الحجم النسبي {s.rvol:.1f}x")
        if s.dollar_volume >= 5_000_000:
            reasons.append("تدفق سيولة قوية")
        
        catalyst_text = ""
        if s.catalyst and s.catalyst != "No recent catalysts" and len(s.catalyst) > 5:
            cleaned_catalyst = s.catalyst.replace('"', '').strip()
            if len(cleaned_catalyst) > 80:
                cleaned_catalyst = cleaned_catalyst[:80] + "..."
            catalyst_text = f" بالتزامن مع خبر: \"{cleaned_catalyst}\""
            
        if not reasons:
            reasons.append("حركة تداول وزخم طبيعي")
            
        story = f"شهد السهم {change_text} نتيجة {reasons[0]}"
        if len(reasons) > 1:
            story += f" مع {reasons[1]}"
            
        story += f".{catalyst_text}"
        return story

    def _determine_movement_type(self, s: Signal) -> str:
        """Determine movement type matching requested categories: Breakout, Momentum, Whale Trade, Reversal"""
        rsi_val = getattr(s, "rsi_14", None)
        if s.change_pct >= 30.0 or s.rvol >= 10.0:
            return "تكوين قاع S 🛡️" if rsi_val and rsi_val < 35.0 else "زخم صعودي قوي 🔥"
        elif s.price >= (s.resistance or 0.0) and s.price > (s.vwap or 0.0):
            return "اختراق فني قوي 🚀"
        elif s.dollar_volume >= 5_000_000:
            return "صفقة حوت كبيرة 🐳"
        elif rsi_val and rsi_val < 35.0:
            return "تكوين قاع S 🛡️"
        return "زخم صعودي 📈"

    def _format_alert_message(self, s: Signal, alert_number: int) -> str:
        """Creates a beautifully formatted Arabic Telegram message matching the requested style exactly"""
        movement_type = self._determine_movement_type(s)
        
        # Select correct flag
        flag = "🇺🇸"
        if s.exchange and "TSX" in s.exchange.upper():
            flag = "🇨🇦"
            
        # Format metrics using Arabic terms and currency/shares suffix
        raw_float = s.float_size * 1_000_000 if s.float_size and s.float_size < 1000 else (s.float_size or 0)
        float_str = self._format_large_number_arabic(raw_float)
        market_cap_str = self._format_large_number_arabic(s.market_cap) + " دولار" if s.market_cap else "غير متوفر"
        volume_str = self._format_large_number_arabic(s.volume) + " سهم"
        liquidity_str = self._format_large_number_arabic(s.dollar_volume) + " دولار"
        
        # Convert UTC to Eastern Time (US/New York) dynamically handling DST
        utc_time = s.timestamp.replace(tzinfo=pytz.utc)
        eastern_time = utc_time.astimezone(pytz.timezone("America/New_York"))
        time_str = eastern_time.strftime("%H:%M:%S")

        # VWAP formatting
        vwap_status_compact = "فوق" if s.vwap and s.price > s.vwap else "تحت"
        hod_val = f"{s.hod:.2f}$" if s.hod else "غير متوفر"

        # Sector & Industry compact
        sector_clean = s.sector.strip() if s.sector else ""
        industry_clean = s.industry.strip() if s.industry else ""
        has_activity = (
            sector_clean and sector_clean != "غير متوفر" and sector_clean != "None"
        ) or (
            industry_clean and industry_clean != "غير متوفر" and industry_clean != "None"
        )
        sector_industry_line_compact = ""
        if has_activity:
            sector_industry_str = f"{s.sector or 'غير متوفر'} / {s.industry or 'غير متوفر'}"
            sector_industry_line_compact = f"📋 النشاط: <b>{sector_industry_str}</b>\n"

        # Trading Zones
        entry_val = f"{s.entry_price:.2f}$" if s.entry_price else f"{s.price * 0.98:.2f}$"
        tp1_val = f"{s.target1:.2f}$" if s.target1 else f"{s.price * 1.10:.2f}$"
        tp2_val = f"{s.target2:.2f}$" if s.target2 else f"{s.price * 1.25:.2f}$"
        tp3_val = f"{s.target3:.2f}$" if s.target3 else f"{s.price * 1.45:.2f}$"
        sl_val = f"{s.stop_loss:.2f}$" if s.stop_loss else f"{s.price * 0.90:.2f}$"

        # News section formatting - s.catalyst contains the translated Arabic news text
        has_real_news = s.catalyst and s.catalyst != "No recent catalysts" and "لا يوجد خبر مؤثر" not in s.catalyst
        news_section_label = "الخبر (آخر 24 ساعة)" if has_real_news else "الخبر"
        news_content = s.catalyst if has_real_news else "لا يوجد خبر مؤثر خلال آخر 24 ساعة."
        news_section = f"📰 {news_section_label}:\n{news_content}"

        # Build message using compact layout with minimal newlines and exact specified fields
        return (
            f"🚨 <b>MBM RADAR | ⏰ {time_str}</b>\n\n"
            f"🔥 نوع التنبيه: <b>{movement_type}</b>\n\n"
            f"📌 الرمز: <b>{s.ticker} {flag}</b>\n"
            f"⚡️ التنبيه رقم: <b>{alert_number} ⚡️</b>\n\n"
            f"💲 السعر الحالي: <b>{s.price:.2f}$ ({s.change_pct:+.2f}%)</b>\n\n"
            f"📊 الأسهم المتاحة: <b>{float_str}</b>\n"
            f"🏦 القيمة السوقية: <b>{market_cap_str}</b>\n"
            f"📈 الحجم النسبي (RVOL): <b>{s.rvol:.1f}x</b>\n"
            f"🔥 الفوليوم: <b>{volume_str}</b>\n"
            f"💧 السيولة: <b>{liquidity_str}</b>\n"
            f"{sector_industry_line_compact}"
            f"✅ VWAP: <b>{vwap_status_compact}</b>\n"
            f"🔝 أعلى سعر اليوم (HOD): <b>{hod_val}</b>\n\n"
            f"━━━━━━━━━━━━━━\n\n"
            f"🟢 دخول مقترح: <b>{entry_val}</b>\n\n"
            f"🎯 الهدف الأول: <b>{tp1_val}</b>\n"
            f"🎯 الهدف الثاني: <b>{tp2_val}</b>\n"
            f"🎯 الهدف الثالث: <b>{tp3_val}</b>\n\n"
            f"🛑 وقف الخسارة: <b>{sl_val}</b>\n\n"
            f"━━━━━━━━━━━━━━\n\n"
            f"⭐ جودة الفرصة: <b>{s.quality_score:.1f}/10</b>\n\n"
            f"{news_section}"
        )

    async def dispatch_signal(self, signal: Signal):
        """Dispatches signal to Channel and active subscribers"""
        trace_id = getattr(signal, "trace_id", "N/A")
        app_logger.info(f"[AUDIT] TraceID={trace_id} | Pipeline Stage: NOTIFIER RECEIVED")

        # 1. Cooldown Check
        try:
            if not await self._check_and_set_cooldown(signal.ticker, trace_id=trace_id):
                reason = "in Redis cooldown lock"
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=RedisCooldown | Required=NotInCooldown | Actual=InCooldown | Result=Rejected | Reason={reason}")
                return
            app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=RedisCooldown | Required=NotInCooldown | Actual=NotInCooldown | Result=Passed")
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            app_logger.error(f"[ERROR] TraceID={trace_id} | Exception during Cooldown Check: {str(e)} | Stacktrace: {tb}")

        # Get the per-ticker sequential alert number
        try:
            alert_number = await self._get_ticker_alert_number(signal.ticker)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            app_logger.error(f"[ERROR] TraceID={trace_id} | Exception during Alert Counter fetch: {str(e)} | Stacktrace: {tb}")
            alert_number = 1

        # Apply Admin User preferences as filters for the Channel alerts
        pref = None
        try:
            async with async_session() as db:
                query = select(UserPreferences).join(User).where(User.telegram_id == settings.ADMIN_TELEGRAM_ID)
                res = await db.execute(query)
                pref = res.scalar_one_or_none()
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            app_logger.error(f"[ERROR] TraceID={trace_id} | Exception querying Admin Preferences: {str(e)} | Stacktrace: {tb}")

        if pref:
            # 1. Alert status check
            if not pref.alerts_enabled:
                reason = "Channel alerts are disabled by admin preference"
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AlertsEnabled | Required=True | Actual={pref.alerts_enabled} | Result=Rejected | Reason={reason}")
                return
            app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AlertsEnabled | Required=True | Actual={pref.alerts_enabled} | Result=Passed")
                
            # 2. Price filter
            if signal.price > pref.max_price:
                reason = f"price ${signal.price:.2f} exceeds admin max ${pref.max_price:.2f}"
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminMaxPrice | Required=<={pref.max_price:.2f} | Actual={signal.price:.2f} | Result=Rejected | Reason={reason}")
                return
            app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminMaxPrice | Required=<={pref.max_price:.2f} | Actual={signal.price:.2f} | Result=Passed")
                
            # 3. Market cap filter
            if signal.market_cap and signal.market_cap > pref.max_market_cap:
                reason = f"market cap {signal.market_cap} exceeds admin max {pref.max_market_cap}"
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminMaxMarketCap | Required=<={pref.max_market_cap} | Actual={signal.market_cap} | Result=Rejected | Reason={reason}")
                return
            app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminMaxMarketCap | Required=<={pref.max_market_cap} | Actual={signal.market_cap} | Result=Passed")
                
            # 4. Float size filter
            if signal.float_size and signal.float_size > pref.max_float:
                reason = f"float size {signal.float_size} exceeds admin max {pref.max_float}"
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminMaxFloat | Required=<={pref.max_float} | Actual={signal.float_size} | Result=Rejected | Reason={reason}")
                return
            app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminMaxFloat | Required=<={pref.max_float} | Actual={signal.float_size} | Result=Passed")
                
            # 5. RVOL filter
            if signal.rvol < pref.min_rvol:
                reason = f"RVOL {signal.rvol:.2f}x below admin min {pref.min_rvol:.2f}x"
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminMinRVOL | Required=>={pref.min_rvol:.2f} | Actual={signal.rvol:.2f} | Result=Rejected | Reason={reason}")
                return
            app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminMinRVOL | Required=>={pref.min_rvol:.2f} | Actual={signal.rvol:.2f} | Result=Passed")
                
            # 6. Gap percentage filter
            if signal.gap_pct < pref.min_gap_pct:
                reason = f"gap {signal.gap_pct:+.2f}% below admin min {pref.min_gap_pct:.2f}%"
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminMinGap | Required=>={pref.min_gap_pct:.2f} | Actual={signal.gap_pct:+.2f}% | Result=Rejected | Reason={reason}")
                return
            app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminMinGap | Required=>={pref.min_gap_pct:.2f}% | Actual={signal.gap_pct:+.2f}% | Result=Passed")
                
            # 7. Change percentage filter
            if abs(signal.change_pct) < pref.min_change_pct:
                reason = f"change {signal.change_pct:+.2f}% below admin min {pref.min_change_pct:.2f}%"
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminMinChange | Required=>={pref.min_change_pct:.2f}% | Actual={signal.change_pct:+.2f}% | Result=Rejected | Reason={reason}")
                return
            app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminMinChange | Required=>={pref.min_change_pct:.2f}% | Actual={signal.change_pct:+.2f}% | Result=Passed")
                
            # 8. Volume filter (with operator check)
            volume_op = getattr(pref, "volume_filter_type", ">=")
            if volume_op == "<=":
                if signal.volume > pref.min_volume:
                    reason = f"volume {signal.volume} exceeds admin max {pref.min_volume}"
                    app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminVolume | Required=<={pref.min_volume} | Actual={signal.volume} | Result=Rejected | Reason={reason}")
                    return
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminVolume | Required=<={pref.min_volume} | Actual={signal.volume} | Result=Passed")
            else:  # ">="
                if signal.volume < pref.min_volume:
                    reason = f"volume {signal.volume} below admin min {pref.min_volume}"
                    app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminVolume | Required=>={pref.min_volume} | Actual={signal.volume} | Result=Rejected | Reason={reason}")
                    return
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminVolume | Required=>={pref.min_volume} | Actual={signal.volume} | Result=Passed")

            # 9. Alert types filter
            if pref.alert_types and isinstance(pref.alert_types, list):
                matched_type = False
                for t in pref.alert_types:
                    if t.lower() in signal.signal_type.lower():
                        matched_type = True
                        break
                if not matched_type:
                    reason = f"signal type '{signal.signal_type}' not in admin allowed types {pref.alert_types}"
                    app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminAlertTypes | Required={pref.alert_types} | Actual='{signal.signal_type}' | Result=Rejected | Reason={reason}")
                    return
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminAlertTypes | Required={pref.alert_types} | Actual='{signal.signal_type}' | Result=Passed")
            
            # 10. Minimum Opportunity Score filter
            min_score = getattr(pref, "min_score_threshold", 3.5)
            if signal.quality_score < min_score:
                reason = f"quality score {signal.quality_score:.1f} below admin min {min_score:.1f}"
                app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminMinScore | Required=>={min_score:.1f} | Actual={signal.quality_score:.1f} | Result=Rejected | Reason={reason}")
                return
            app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminMinScore | Required=>={min_score:.1f} | Actual={signal.quality_score:.1f} | Result=Passed")
        else:
            app_logger.info(f"[FILTER] TraceID={trace_id} | Filter=AdminPreferences | Required=Loaded | Actual=None | Result=Passed | Reason=Bypassed filters due to missing admin profile")

        # Format the Arabic message exactly matching the RadarBot style
        message_text = self._format_alert_message(signal, alert_number)

        # 2. Dispatch to Telegram Channel
        app_logger.info(f"[AUDIT] TraceID={trace_id} | Pipeline Stage: TELEGRAM SEND STARTED")
        bot_token_loaded = bool(getattr(self.bot, "token", None))
        app_logger.info(
            f"[NOTIFIER] TraceID={trace_id} | Sending Alert | Chat ID={settings.ADMIN_TELEGRAM_ID} | "
            f"Channel ID={settings.TELEGRAM_CHANNEL_ID} | Bot Token Loaded={bot_token_loaded} | "
            f"Alert Length={len(message_text)} | Alert Preview={message_text[:80]}..."
        )

        channel_msg_id = None
        start_time = datetime.datetime.utcnow()
        try:
            chan_msg = await self.bot.send_message(
                chat_id=settings.TELEGRAM_CHANNEL_ID,
                text=message_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            channel_msg_id = chan_msg.message_id
            latency = (datetime.datetime.utcnow() - start_time).total_seconds()
            app_logger.info(f"[AUDIT] TraceID={trace_id} | Pipeline Stage: TELEGRAM RESPONSE RECEIVED")
            app_logger.info(
                f"[NOTIFIER] TraceID={trace_id} | Telegram API Response | HTTP Status=200 | "
                f"Latency={latency:.3f}s | Retry Count=0 | Response Body=Message ID: {channel_msg_id}"
            )
            app_logger.info(f"Arabic Signal alert sent to Telegram Channel {settings.TELEGRAM_CHANNEL_ID}")
        except Exception as e:
            latency = (datetime.datetime.utcnow() - start_time).total_seconds()
            import traceback
            tb = traceback.format_exc()
            app_logger.error(
                f"[NOTIFIER] TraceID={trace_id} | Telegram API Response | HTTP Status=Error | "
                f"Latency={latency:.3f}s | Retry Count=0 | Response Body={str(e)}"
            )
            app_logger.error(f"[ERROR] TraceID={trace_id} | Failed to send alert to Channel: {str(e)} | Stacktrace: {tb}")

        # Log notification in Database
        try:
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
            app_logger.info(f"[DATABASE] TraceID={trace_id} | Signal Log | Status=Saved")
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            app_logger.error(f"[ERROR] TraceID={trace_id} | Failed to save Notification log to DB: {str(e)} | Stacktrace: {tb}")

