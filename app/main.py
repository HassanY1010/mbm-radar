import asyncio
import datetime
from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from aiogram.types import Update
from contextlib import asynccontextmanager
from typing import List
from sqlalchemy import select
from app.core.config import settings
from app.core.logging import app_logger
from app.database.init_db import init_db
from app.database.session import async_session
from app.models.models import Signal
from app.bot.bot_service import bot, dp, setup_bot
from app.scheduler.scheduler import scheduler, setup_scheduler
from app.scanner.scanner_manager import ScannerManager
from app.notifications.notifier import Notifier

# Real-time WebSocket clients list
websocket_connections: List[WebSocket] = []

# Instantiate notifier and scanner
notifier = Notifier(bot)

async def signal_alert_callback(signal: Signal):
    """Callback triggered by ScannerManager when a new signal matches criteria"""
    # 1. Dispatches Telegram Alert
    await notifier.dispatch_signal(signal)
    
    # 2. Streams to active WebSocket connections (e.g., frontend dashboard)
    dead_connections = []
    signal_data = {
        "ticker": signal.ticker,
        "price": signal.price,
        "change_pct": signal.change_pct,
        "gap_pct": signal.gap_pct,
        "rvol": signal.rvol,
        "score": signal.quality_score,
        "rating": signal.score_rating,
        "signal_type": signal.signal_type,
        "timestamp": signal.timestamp.isoformat()
    }
    
    for ws in websocket_connections:
        try:
            await ws.send_json(signal_data)
        except Exception:
            dead_connections.append(ws)
            
    # Cleanup dead WS connections
    for ws in dead_connections:
        if ws in websocket_connections:
            websocket_connections.remove(ws)

scanner = ScannerManager(notification_callback=signal_alert_callback)

# Task variables
bot_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot_task
    
    app_logger.info("Initializing system startup sequence...")
    
    # 1. DB Migrations & seed data
    await init_db()
    
    # 2. Setup Bot router/middleware and set webhook or start polling
    setup_bot()
    webhook_url = settings.WEBHOOK_URL.strip() if hasattr(settings, "WEBHOOK_URL") else ""
    if webhook_url:
        from urllib.parse import urlparse
        parsed = urlparse(webhook_url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"Invalid WEBHOOK_URL: {webhook_url}")
        
        # Security hardening: Validate webhook domain (allows production, localhost, and ngrok tunnels)
        allowed_domains = {"mbm-radar.onrender.com", "localhost", "127.0.0.1"}
        host = parsed.netloc.split(":")[0]
        if host not in allowed_domains and not host.endswith(".ngrok-free.app") and not host.endswith(".ngrok.io") and not host.endswith(".onrender.com"):
            raise ValueError(f"Unauthorized webhook domain: {parsed.netloc}")
            
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        full_webhook_url = f"{base_url}/webhook"
        
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(full_webhook_url)
        app_logger.info(f"Telegram Bot Webhook started at: {full_webhook_url}")
    else:
        bot_task = asyncio.create_task(dp.start_polling(bot))
        app_logger.info("Telegram Bot started in POLLING mode (no WEBHOOK_URL defined).")
    
    # 3. Setup and start APScheduler
    setup_scheduler()
    scheduler.start()
    app_logger.info("Scheduler started.")
    
    # 4. Start Scanner Engine
    await scanner.start()
    app_logger.info("Scanner Engine started.")
    
    yield
    
    app_logger.info("Executing system shutdown sequence...")
    # 1. Stop Scanner
    await scanner.stop()
    
    # 2. Stop Scheduler
    scheduler.shutdown()
    
    # 3. Stop Bot session/polling
    await dp.storage.close()
    if bot_task:
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
    else:
        # Delete webhook on shutdown to allow local getUpdates polling fallback
        try:
            await bot.delete_webhook()
            app_logger.info("Telegram Bot Webhook deleted.")
        except Exception as e:
            app_logger.error(f"Error deleting webhook on shutdown: {str(e)}")
            
    await bot.session.close()
    app_logger.info("System shutdown completed.")

app = FastAPI(
    title="MBM Radar API",
    description="Backend API Gateway for US Stock Scanner & Alerts",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# --- Routes ---
@app.get("/")
def health_check():
    return {"status": "healthy", "service": "MBM Radar", "timestamp": str(datetime.datetime.utcnow())}

@app.get("/api/status")
def system_status():
    scan_task = getattr(scanner, "scan_task", None)
    last_tickers_fetch = getattr(scanner, "last_tickers_fetch", None)
    return {
        "status": "healthy",
        "scanner": {
            "is_running": getattr(scanner, "is_running", False),
            "active_tickers_count": len(getattr(scanner, "active_tickers", [])),
            "last_tickers_fetch": str(last_tickers_fetch) if last_tickers_fetch else None,
            "scan_task_exists": scan_task is not None and not scan_task.done()
        }
    }

@app.post("/webhook")
async def bot_webhook(request: Request):
    """Telegram Webhook endpoint to receive updates"""
    try:
        data = await request.json()
        update = Update(**data)
        await dp.feed_update(bot, update)
    except Exception as e:
        app_logger.error(f"Error processing webhook update: {str(e)}")
    return {"status": "ok"}

@app.get("/api/signals")
async def get_signals(limit: int = 50, offset: int = 0):
    """Exposes REST endpoint to fetch recent signals"""
    async with async_session() as db:
        query = select(Signal).order_by(Signal.timestamp.desc()).limit(limit).offset(offset)
        res = await db.execute(query)
        signals = res.scalars().all()
        return signals

# Webhooks endpoint for Stripe
@app.post("/api/webhooks/stripe")
async def stripe_webhook(payload: dict):
    """
    Listener for Stripe Payment Webhook signals.
    Allows automated activation of user subscriptions upon payment.
    """
    app_logger.info(f"Stripe Webhook event received: {payload.get('type')}")
    # Process event, locate user by client_reference_id and activate subscription
    # (Mock implementation handles user upgrade details based on request payloads)
    return {"status": "success"}

# --- WebSocket Streaming ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    websocket_connections.append(websocket)
    app_logger.info(f"New WebSocket client connected. Active connections: {len(websocket_connections)}")
    try:
        while True:
            # Keep connection alive, listen for ping/pong
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in websocket_connections:
            websocket_connections.remove(websocket)
        app_logger.info("WebSocket client disconnected.")
    except Exception as e:
        app_logger.error(f"WebSocket connection error: {str(e)}")
        if websocket in websocket_connections:
            websocket_connections.remove(websocket)
