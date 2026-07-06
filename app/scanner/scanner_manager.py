import asyncio
import datetime
from typing import Dict, Any, List, Optional, Tuple
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
        self.concurrency_semaphore = asyncio.Semaphore(settings.SCANNER_CONCURRENCY_LIMIT)

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
                self.active_tickers = list(dict.fromkeys(tickers))
                self.last_tickers_fetch = now
                scanner_logger.info(f"Updated active tickers cache: {len(self.active_tickers)} unique symbols loaded.")
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
            if not financials and stock is not None:
                scanner_logger.warning(f"Failed to fetch fresh financials for {ticker}, falling back to stale DB cache (updated: {stock.last_updated})")
                self.shariah_cache[ticker] = (stock.is_shariah, stock.shariah_reason or "")
                return stock.is_shariah

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

        # DB Cooldown Check
        cooldown_limit = datetime.datetime.utcnow() - datetime.timedelta(minutes=settings.COOLDOWN_PERIOD_MINUTES)
        async with async_session() as db:
            res = await db.execute(
                select(Signal).where(Signal.ticker == ticker, Signal.timestamp > cooldown_limit)
            )
            if res.scalar_one_or_none():
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

        # 4. Concurrency-controlled detailed indicators calculation
        async with self.concurrency_semaphore:
            # Fetch historical daily bars to calculate Indicators
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

    async def process_candidate(self, quote: Dict[str, Any], semaphore: asyncio.Semaphore) -> Optional[Signal]:
        """Runs the detailed Stage 2 scanning pipeline for a candidate quote under semaphore control"""
        ticker = quote.get("symbol", "").upper()
        if not ticker:
            return None

        # DB Cooldown Check to prevent duplicates and conserve FMP API calls
        cooldown_limit = datetime.datetime.utcnow() - datetime.timedelta(minutes=settings.COOLDOWN_PERIOD_MINUTES)
        async with async_session() as db:
            res = await db.execute(
                select(Signal).where(Signal.ticker == ticker, Signal.timestamp > cooldown_limit)
            )
            if res.scalar_one_or_none():
                scanner_logger.debug(f"Skipping Stage 2 for {ticker}: Already triggered in the cooldown period.")
                return None

        company_name = quote.get("name", quote.get("companyName", ticker))
        sector = quote.get("sector", "")
        industry = quote.get("industry", "")
        
        async with semaphore:
            try:
                # 1. Shariah financial compliance check
                is_shariah = await self.get_shariah_status(ticker, company_name, sector, industry)
                if not is_shariah:
                    return None

                # 2. Fetch historical daily bars
                historical_bars = await self.provider.get_historical_bars(ticker, limit=100)
                if not historical_bars or len(historical_bars) < 14:
                    return None

                # Calculate Indicators
                ta_metrics = TechnicalAnalysis.calculate_all(historical_bars, quote)
                if not ta_metrics:
                    return None

                rvol = ta_metrics.get("rvol", 1.0)
                if rvol < settings.SCANNER_MIN_RVOL:
                    return None

                # 3. Fetch News / Catalyst
                news_items = await self.provider.get_news_and_catalysts(ticker, limit=2)
                has_news = len(news_items) > 0
                latest_news_str = news_items[0].get("title", "") if has_news else "No recent catalysts"
                sec_link = news_items[0].get("url", "") if has_news else ""

                # 4. Opportunity Scoring
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

                if quality_score < settings.MIN_SCORE_THRESHOLD:
                    return None

                # Generate target entries and stop loss
                atr = ta_metrics.get("atr_14", price * 0.05)
                entry = price
                target1 = entry + (1.5 * atr)
                target2 = entry + (3.0 * atr)
                target3 = entry + (5.0 * atr)
                stop_loss = entry - (1.5 * atr)
                risk = entry - stop_loss
                reward = target1 - entry
                rr_ratio = reward / (risk + 1e-9)

                # Save to DB
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

                new_signal.rsi_14 = ta_metrics.get("rsi_14")
                return new_signal

            except Exception as e:
                scanner_logger.error(f"Error processing candidate {ticker}: {str(e)}")
                return None

    async def _polling_loop(self):
        """Fallback polling scanning loops for REST provider data extraction"""
        scanner_logger.info("Starting stock scanner REST polling loop...")
        while self.is_running:
            try:
                # Reload criteria lists
                await self.reload_lists()
                
                # 1. Fetch batch quotes for all active tickers
                all_quotes = []
                batch_size = 100
                for i in range(0, len(self.active_tickers), batch_size):
                    if not self.is_running:
                        break
                    batch = self.active_tickers[i:i+batch_size]
                    quotes = await self.provider.get_quotes_batch(batch)
                    if quotes:
                        all_quotes.extend(quotes)
                    await asyncio.sleep(0.5)  # Rate limit safety delay
                
                # 2. Stage 1: Fast Screening & Pre-Scoring
                candidate_quotes = []
                for quote in all_quotes:
                    if not isinstance(quote, dict) or not quote.get("symbol"):
                        continue
                    
                    ticker = quote.get("symbol", "").upper()
                    
                    # Whitelist / Blacklist checks
                    if ticker in self.blacklist:
                        continue
                    
                    price = float(quote.get("price") or 0.0)
                    volume = float(quote.get("volume") or 0.0)
                    market_cap = float(quote.get("marketCap") or 0.0)
                    company_name = quote.get("name", "").upper()
                    
                    float_size = float(quote.get("float") or quote.get("sharesOutstanding") or ((market_cap / price) if price else 0.0))
                    change_pct = float(quote.get("changePercentage") or quote.get("changePercent") or quote.get("changesPercentage") or 0.0)
                    gap_pct = float(quote.get("gapPercent") or quote.get("gapPercentage") or change_pct)
                    
                    # Exclude Chinese, SPAC, ETF, ADR in Stage 1
                    is_excluded = False
                    for ind in ["CHINA", "CHINESE", "SINA", "ALIBABA", "TENCENT", "BAIDU", "JD.COM", "PINDUODUO"]:
                        if ind in company_name or ticker.endswith(".CN"):
                            is_excluded = True
                            break
                    if is_excluded:
                        continue
                        
                    for ind in ["SPAC", "ACQUISITION", "BLANK CHECK", "UNIT", "WARRANT"]:
                        if ind in company_name:
                            is_excluded = True
                            break
                    if is_excluded:
                        continue
                        
                    if "ETF" in company_name or quote.get("isETF") or quote.get("isEtf"):
                        continue
                        
                    if "ADR" in company_name or (len(ticker) == 5 and ticker.endswith("Y")):
                        continue

                    # Basic criteria limits
                    if price < 0.10 or price > settings.SCANNER_MAX_PRICE:
                        continue
                    if volume < settings.SCANNER_MIN_VOLUME:
                        continue
                    if market_cap > settings.SCANNER_MAX_MARKET_CAP:
                        continue
                    if float_size > settings.SCANNER_MAX_FLOAT:
                        continue
                    if abs(change_pct) < settings.SCANNER_MIN_CHANGE_PCT:
                        continue
                    if abs(gap_pct) < settings.SCANNER_MIN_GAP_PCT:
                        continue

                    # Screener exclusion lists (Chinese, spacs, adrs, etfs)
                    if StockFilter.is_blacklisted(ticker):
                        continue
                    if StockFilter.is_spac_or_etf(quote.get("name", ""), ticker):
                        continue
                    if StockFilter.is_chinese_exclusion(quote.get("name", ""), quote.get("industry", "")):
                        continue

                    # Pre-scoring formula to prioritize candidates
                    momentum_base = change_pct * 0.7 + gap_pct * 0.3
                    
                    dollar_volume = price * volume
                    if dollar_volume < 100000:  # Dollar volume must be at least 100k
                        continue
                    liquidity_weight = min(1.0, dollar_volume / 2000000.0)
                    
                    # Trend confirmation using priceAvg50
                    price_avg_50 = float(quote.get("priceAvg50") or 0.0)
                    trend_confirm = 1.2 if (price_avg_50 > 0 and price > price_avg_50) else 0.8
                    
                    # Volatility normalization
                    day_high = float(quote.get("dayHigh") or price)
                    day_low = float(quote.get("dayLow") or price)
                    intraday_range = ((day_high - day_low) / price * 100.0) if price > 0 else 0.0
                    volatility_factor = 0.5 if intraday_range > 25.0 else 1.0  # Penalize extreme volatility pump & dumps
                    
                    pre_score = momentum_base * liquidity_weight * trend_confirm * volatility_factor
                    quote["pre_score"] = pre_score
                    candidate_quotes.append(quote)
                
                # Sort candidates by pre-score descending
                candidate_quotes.sort(key=lambda x: x.get("pre_score", 0.0), reverse=True)
                
                # 3. Dynamic Top-K selection
                # Count active high momentum stocks (changePercentage > 3%)
                high_momentum_count = sum(1 for q in candidate_quotes if float(q.get("changePercentage", 0.0)) > 3.0)
                dynamic_k = max(20, min(80, high_momentum_count))
                top_k_quotes = candidate_quotes[:dynamic_k]
                
                scanner_logger.info(f"Stage 1 screening done. Total active tickers: {len(all_quotes)}. Filtered candidates: {len(candidate_quotes)}. Dynamic Top-K selected: {len(top_k_quotes)}")
                
                # 4. Stage 2: Concurrency-controlled detailed analysis
                semaphore = asyncio.Semaphore(settings.SCANNER_CONCURRENCY_LIMIT)
                tasks = [self.process_candidate(quote, semaphore) for quote in top_k_quotes]
                
                # Gather all signals
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                signals_generated = 0
                for res in results:
                    if isinstance(res, Signal):
                        signals_generated += 1
                        await self.notification_callback(res)
                        
                scanner_logger.info(f"Stage 2 detailed scan completed. Total signals generated: {signals_generated}")
                
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
