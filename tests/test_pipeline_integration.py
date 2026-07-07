import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import select, delete
from app.models.models import Signal, User, UserPreferences, Notification, Stock
from app.database.session import async_session
from app.scanner.scanner_manager import ScannerManager
from app.notifications.notifier import Notifier
from app.core.config import settings

@pytest.mark.asyncio
async def test_full_pipeline_integration():
    # 1. Set up mocks for Bot and Redis
    mock_bot = MagicMock()
    mock_bot.token = "fake_bot_token"
    mock_bot.send_message = AsyncMock(return_value=MagicMock(message_id=9999))
    
    # Mock Redis client using mock class
    mock_redis = MagicMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.ttl = AsyncMock(return_value=60)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock(return_value=True)
    
    # 2. Mock FMP Provider responses
    mock_provider = MagicMock()
    mock_provider.get_historical_bars = AsyncMock(return_value=[
        {"date": f"2026-07-06 09:{30+i}:00", "open": 10.0 + i*0.1, "high": 10.5 + i*0.1, "low": 9.8 + i*0.1, "close": 10.2 + i*0.1, "volume": 150000}
        for i in range(20)
    ])
    mock_provider.get_news_and_catalysts = MagicMock()
    mock_provider.get_news_and_catalysts.return_value = AsyncMock()
    mock_provider.get_news_and_catalysts = AsyncMock(return_value=[
        {"title": "Awesome Biotech Breakout FDA approval", "text": "Biotech company receives FDA approval for blockbuster drug.", "url": "https://sec.gov", "publishedDate": "2026-07-07T05:00:00Z"}
    ])
    mock_provider.get_key_financials = AsyncMock(return_value={
        "marketCapTTM": 100000000,
        "totalDebtTTM": 500000,
        "cashAndShortTermInvestmentsTTM": 20000000
    })
    
    # 3. Create notifier and mock its redis client
    notifier = Notifier(mock_bot)
    notifier.redis_client = mock_redis
    
    # Mock WebSocket client
    mock_ws = AsyncMock()
    mock_ws.send_json = AsyncMock()
    
    # Setup callback which connects notifier and WebSocket
    from app.main import websocket_connections
    websocket_connections.clear()
    websocket_connections.append(mock_ws)
    
    async def integration_callback(signal: Signal):
        # Dispatch to telegram
        await notifier.dispatch_signal(signal)
        
        # Broadcast to websockets
        signal_data = {
            "ticker": signal.ticker,
            "price": signal.price,
            "change_pct": signal.change_pct,
            "gap_pct": signal.gap_pct,
            "rvol": signal.rvol,
            "score": signal.quality_score,
            "rating": signal.score_rating,
            "signal_type": signal.signal_type,
            "timestamp": signal.timestamp.isoformat(),
            "trace_id": getattr(signal, "trace_id", "N/A")
        }
        await mock_ws.send_json(signal_data)

    # Clean up any existing test data for TPI to avoid cooldown skips
    async with async_session() as db:
        await db.execute(delete(Notification).where(Notification.ticker == "TPI"))
        await db.execute(delete(Signal).where(Signal.ticker == "TPI"))
        await db.execute(delete(Stock).where(Stock.ticker == "TPI"))
        await db.commit()

    # 4. Instantiate scanner manager and inject mocked provider
    scanner = ScannerManager(notification_callback=integration_callback)
    scanner.provider = mock_provider
    
    # Configure mock preferences for admin user (so we test filters)
    async with async_session() as db:
        # Create admin user if not exists
        res = await db.execute(select(User).where(User.telegram_id == settings.ADMIN_TELEGRAM_ID))
        admin = res.scalar_one_or_none()
        if not admin:
            admin = User(telegram_id=settings.ADMIN_TELEGRAM_ID, is_admin=True, username="admin_tester")
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            
        res_pref = await db.execute(select(UserPreferences).where(UserPreferences.user_id == admin.id))
        pref = res_pref.scalar_one_or_none()
        if not pref:
            pref = UserPreferences(
                user_id=admin.id,
                max_price=30.0,
                max_float=50_000_000.0,
                max_market_cap=2_000_000_000.0,
                min_rvol=1.0,
                min_volume=100_000,
                min_gap_pct=1.0,
                min_change_pct=1.0,
                min_score_threshold=3.5,
                alerts_enabled=True
            )
            db.add(pref)
            await db.commit()
        else:
            # Overwrite values to ensure compliant state for mock signal
            pref.max_price = 30.0
            pref.max_float = 50_000_000.0
            pref.max_market_cap = 2_000_000_000.0
            pref.min_rvol = 1.0
            pref.min_volume = 100_000
            pref.min_gap_pct = 1.0
            pref.min_change_pct = 1.0
            pref.min_score_threshold = 3.5
            pref.alerts_enabled = True
            await db.commit()
            
    # Mock data quote for Stage 1
    quote = {
        "symbol": "TPI",
        "name": "Pipeline Integration Inc",
        "price": 12.50,
        "volume": 200000,
        "marketCap": 150000000,
        "float": 8000000,
        "changePercentage": 6.5,
        "gapPercent": 2.0,
        "priceAvg50": 11.0,
        "dayHigh": 13.0,
        "dayLow": 12.0,
        "exchange": "NASDAQ"
    }
    
    # 5. Execute process_candidate
    trace_id = "TR_TPI_123456789"
    semaphore = asyncio.Semaphore(1)
    
    signal = await scanner.process_candidate(quote, semaphore, trace_id=trace_id)
    
    # 6. Verify assertions
    assert signal is not None
    
    # Manually invoke the callback since _polling_loop is mocked/bypassed here
    await scanner.notification_callback(signal)
    
    assert signal.ticker == "TPI"
    assert signal.trace_id == trace_id
    assert signal.price == 12.50
    assert signal.quality_score >= 3.5
    
    # Verify notifier callback was invoked and sent message to telegram
    mock_bot.send_message.assert_called_once()
    args, kwargs = mock_bot.send_message.call_args
    assert kwargs["chat_id"] == settings.TELEGRAM_CHANNEL_ID
    assert "TPI" in kwargs["text"]
    
    # Verify WebSocket broadcast was completed
    mock_ws.send_json.assert_called_once()
    broadcast_data = mock_ws.send_json.call_args[0][0]
    assert broadcast_data["ticker"] == "TPI"
    assert broadcast_data["trace_id"] == trace_id
    
    # Verify notification log saved in DB
    async with async_session() as db:
        res_notif = await db.execute(select(Notification).where(Notification.ticker == "TPI"))
        notif = res_notif.scalars().all()
        assert len(notif) > 0
        assert notif[0].telegram_message_id == 9999
        
    # Clean up test signals & notifications
    async with async_session() as db:
        await db.execute(delete(Notification).where(Notification.ticker == "TPI"))
        await db.execute(delete(Signal).where(Signal.ticker == "TPI"))
        await db.execute(delete(Stock).where(Stock.ticker == "TPI"))
        await db.commit()
