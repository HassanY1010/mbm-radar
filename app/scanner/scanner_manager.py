import asyncio
import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from app.database.session import async_session
from app.models.models import Stock, Blacklist, Whitelist, UserPreferences, Signal
from app.scanner.provider_factory import DataProviderFactory
from app.filters.shariah_filter import ShariahFilter
from app.filters.stock_filter import StockFilter
from app.indicators.technical_analysis import TechnicalAnalysis
from app.signals.scoring_system import ScoringSystem
from app.core.logging import scanner_logger
from app.core.config import settings

class ScannerManager:
    """
    Scanner manager that orchestrates:
    1. Initial loading of stocks and Shariah screening.
    2. Realtime WebSocket subscription / Polling loop.
    3. Technical indicator calculation.
    4. Scoring and Signal Generation.
    5. Triggering notifications.
    """
    
    def __init__(self, notification_callback):
        self.provider = DataProviderFactory.get_provider()
        self.notification_callback = notification_callback
        self.is_running = False
        self.active_tickers: List[str] = []
        self.shariah_cache: Dict[str, Tuple[bool, str]] = {}
        self.blacklist: List[str] = []
        self.whitelist: List[str] = []
        self.task: Optional[asyncio.Task] = None
        self.last_tickers_fetch: Optional[datetime.datetime] = None

    async def reload_lists(self):
        """Reloads whitelist, blacklist, and active tickers"""
        async with async_session() as db:
            # Blacklist
            res = await db.execute(select(Blacklist.ticker))
            self.blacklist = [t.upper() for t in res.scalars().all()]
            
            # Whitelist
            res = await db.execute(select(Whitelist.ticker))
            self.whitelist = [t.upper() for t in res.scalars().all()]
            
        scanner_logger.info(f"Loaded lists: Whitelist={len(self.whitelist)}, Blacklist={len(self.blacklist)}")
        
        # Load active tickers only if cache is empty or expired (e.g., 30 minutes)
        now = datetime.datetime.utcnow()
        cache_duration = settings.SCANNER_CACHE_MINUTES * 60
        if not self.active_tickers or not self.last_tickers_fetch or (now - self.last_tickers_fetch).total_seconds() > cache_duration:
            tickers = await self.provider.get_active_tickers()
            if tickers:
                self.active_tickers = tickers
                self.last_tickers_fetch = now
                scanner_logger.info(f"Updated active tickers cache: {len(tickers)} symbols loaded.")
            elif not self.active_tickers:
                # Fallback tickers for testing
                self.active_tickers = ["AAPL", "TSLA", "NVDA", "AMD", "PLTR", "SMCI", "MSFT", "META", "AMZN"]

    async def get_shariah_status(self, ticker: str, company_name: str, sector: str, industry: str) -> bool:
        """Determines and caches Shariah compliance status of a stock"""
        ticker = ticker.upper()
        if ticker in self.shariah_cache:
            return self.shariah_cache[ticker][0]

        async with async_session() as db:
            # Check DB cache
            res = await db.execute(select(Stock).filter_by(ticker=ticker))
            stock = res.scalar_one_or_none()
            
            if stock:
                # If cached within 7 days, use it
                if stock.last_updated > datetime.datetime.utcnow() - datetime.timedelta(days=7):
                    self.shariah_cache[ticker] = (stock.is_shariah, stock.shariah_reason or "")
                    return stock.is_shariah
            
            # Fetch financials and calculate
            financials = await self.provider.get_key_financials(ticker)
            is_compliant, reason = ShariahFilter.is_compliant(
                ticker=ticker,
                company_name=company_name,
                sector=sector,
                industry=industry,
                key_financials=financials
            )
            
            # Cache to DB
            if stock:
                stock.is_shariah = is_compliant
                stock.shariah_reason = reason
                stock.last_updated = datetime.datetime.utcnow()
            else:
                db.add(Stock(
                    ticker=ticker,
                    name=company_name,
                    sector=sector,
                    industry=industry,
                    is_shariah=is_compliant,
                    shariah_reason=reason
                ))
            await db.commit()
            
        self.shariah_cache[ticker] = (is_compliant, reason)
        return is_compliant

    async def process_quote(self, quote: Dict[str, Any]):
        """Dispatches quote to filters, TA, scoring, and dispatches signals"""
        ticker = quote.get("symbol", "").upper()
        if not ticker:
            return

        company_name = quote.get("name", quote.get("companyName", ticker))
        sector = quote.get("sector", "")
        industry = quote.get("industry", "")
        
        # 1. Quick activity-based Shariah pre-screen (avoid fetching financials if already failed)
        if not ShariahFilter.is_activity_compliant(sector, industry, company_name):
            return

        # 2. Match general criteria (Price, Volume, RVOL threshold, Gap, etc.)
        is_match, reason = StockFilter.match_criteria(
            quote=quote,
            blacklist=self.blacklist,
            whitelist=self.whitelist
        )
        if not is_match:
            return

        # 3. Comprehensive Shariah financial check
        is_shariah = await self.get_shariah_status(ticker, company_name, sector, industry)
        if not is_shariah:
            return

        # 4. Fetch historical daily bars to calculate Indicators
        historical_bars = await self.provider.get_historical_bars(ticker, limit=100)
        if not historical_bars or len(historical_bars) < 14:
            return

        # Calculate Indicators
        ta_metrics = TechnicalAnalysis.calculate_all(historical_bars, quote)
        if not ta_metrics:
            return

        # Update quote with calculated relative volume (RVOL)
        rvol = ta_metrics.get("rvol", 1.0)
        
        # Check if RVOL meets criteria (re-screen with calculated RVOL)
        if rvol < settings.SCANNER_MIN_RVOL:
            return

        # 5. Fetch News / Catalyst
        news_items = await self.provider.get_news_and_catalysts(ticker, limit=2)
        has_news = len(news_items) > 0
        latest_news_str = news_items[0].get("title", "") if has_news else "No recent catalysts"
        sec_link = news_items[0].get("url", "") if has_news else ""

        # 6. Opportunity Scoring
        price = float(quote.get("price", 0.0))
        change_pct = float(quote.get("changePercentage", 0.0) or quote.get("changePercent", 0.0) or quote.get("changesPercentage", 0.0))
        gap_pct = float(quote.get("gapPercent", 0.0) or quote.get("gapPercentage", 0.0) or change_pct)
        
        momentum_score, quality_score, rating = ScoringSystem.evaluate(
            price=price,
            rvol=rvol,
            gap_pct=gap_pct,
            change_pct=change_pct,
            has_news=has_news,
            vwap=ta_metrics.get("vwap", price),
            resistance=ta_metrics.get("resistance", price),
            support=ta_metrics.get("support", price),
            rsi=ta_metrics.get("rsi_14", 50.0)
        )

        # Ignore weak opportunities
        if quality_score < settings.MIN_SCORE_THRESHOLD:
            return

        # 7. Generate Target Entries / Stop Loss
        atr = ta_metrics.get("atr_14", price * 0.05)
        entry = price
        target1 = entry + (1.5 * atr)
        target2 = entry + (3.0 * atr)
        target3 = entry + (5.0 * atr)
        stop_loss = entry - (1.5 * atr)
        
        # Risk Reward Ratio
        risk = entry - stop_loss
        reward = target1 - entry
        rr_ratio = reward / (risk + 1e-9)

        # 8. Save Signal to DB
        async with async_session() as db:
            new_signal = Signal(
                ticker=ticker,
                company_name=company_name,
                sector=sector,
                industry=industry,
                exchange=quote.get("exchange", "NASDAQ"),
                price=price,
                ask=quote.get("ask", price),
                bid=quote.get("bid", price),
                spread=quote.get("spread", 0.0),
                change_pct=change_pct,
                gap_pct=gap_pct,
                volume=quote.get("volume", 0),
                rvol=rvol,
                dollar_volume=price * quote.get("volume", 0),
                float_size=quote.get("float") or quote.get("sharesOutstanding") or ((quote.get("marketCap", 0.0) / price) if price else None),
                market_cap=quote.get("marketCap"),
                vwap=ta_metrics.get("vwap"),
                hod=ta_metrics.get("resistance"),
                lod=ta_metrics.get("support"),
                open_price=quote.get("open", price),
                prev_close=quote.get("previousClose", price),
                atr14=atr,
                avg_volume_30d=ta_metrics.get("avg_volume_30"),
                support=ta_metrics.get("support"),
                resistance=ta_metrics.get("resistance"),
                entry_price=entry,
                target1=target1,
                target2=target2,
                target3=target3,
                stop_loss=stop_loss,
                risk_reward=rr_ratio,
                momentum_score=momentum_score,
                quality_score=quality_score,
                score_rating=rating,
                signal_type="VWAP Breakout" if price > ta_metrics.get("vwap", price) else "Momentum Alert",
                catalyst=latest_news_str,
                latest_news=latest_news_str,
                sec_link=sec_link,
                timestamp=datetime.datetime.utcnow()
            )
            db.add(new_signal)
            await db.commit()
            await db.refresh(new_signal)

        # 9. Trigger notifications callback
        new_signal.rsi_14 = ta_metrics.get("rsi_14")
        await self.notification_callback(new_signal)

    async def _polling_loop(self):
        """Fallback polling scanning loops for REST provider data extraction"""
        scanner_logger.info("Starting stock scanner REST polling loop...")
        while self.is_running:
            try:
                # Reload criteria lists
                await self.reload_lists()
                
                # Scan active tickers in parallel batches of 20 to avoid rate limits
                batch_size = 20
                for i in range(0, len(self.active_tickers), batch_size):
                    if not self.is_running:
                        break
                    batch = self.active_tickers[i:i+batch_size]
                    
                    # Fetch quotes in parallel using stable get_quote
                    tasks = [self.provider.get_quote(ticker) for ticker in batch]
                    quotes = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for quote in quotes:
                        if isinstance(quote, dict) and quote.get("symbol"):
                            # Run background tasks to process each ticker
                            asyncio.create_task(self.process_quote(quote))
                            
                    await asyncio.sleep(1) # rate limit delay between batches
                    
            except Exception as e:
                scanner_logger.error(f"Scanner manager polling exception: {str(e)}")
            
            # Wait 60 seconds before scanning the market again
            await asyncio.sleep(60)

    async def start(self):
        """Starts the scanning engine"""
        self.is_running = True
        await self.reload_lists()
        # Launch REST polling engine (or websockets if FMP websocket credentials are active)
        self.task = asyncio.create_task(self._polling_loop())
        scanner_logger.info("Stock scanner engine started successfully.")

    async def stop(self):
        """Stops the scanning engine"""
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        await self.provider.disconnect_websocket()
        scanner_logger.info("Stock scanner engine stopped.")
