import asyncio
import datetime
from app.core.config import settings
from app.database.session import async_session
from app.bot.bot_service import bot
from app.notifications.notifier import Notifier
from app.models.models import Signal
from app.scanner.scanner_manager import translate_text_to_arabic

async def main():
    print("Initializing bot and database session...")
    notifier = Notifier(bot)
    
    # 1. Translate news summary dynamically
    english_catalyst = "Demo Biotech announces successful Phase 3 FDA clinical trial results, which boosted investor confidence and drove the stock to a strong surge accompanied by a high volume."
    print("Translating catalyst to Arabic...")
    arabic_catalyst = await translate_text_to_arabic(english_catalyst)
    print(f"Translated Text: {arabic_catalyst}")

    # 2. Construct the mock signal with real parameters
    mock_signal = Signal(
        ticker="DEMO",
        company_name="Demo Biotech Inc.",
        sector="Healthcare",
        industry="Biotechnology",
        exchange="NASDAQ",
        price=7.50,
        ask=7.55,
        bid=7.45,
        spread=0.10,
        change_pct=12.50,
        gap_pct=8.20,
        volume=18700000,      # 18.7M shares
        rvol=9.5,
        dollar_volume=140300000,  # 140.3M USD
        float_size=12.5,  # 12.5M
        market_cap=145800000, # 145.8M USD
        vwap=7.20,
        hod=7.60,
        lod=6.80,
        open_price=6.93,
        prev_close=6.66,
        atr14=0.40,
        avg_volume_30d=55000,
        support=6.80,
        resistance=7.60,
        entry_price=7.50,
        target1=8.10,
        target2=8.70,
        target3=9.50,
        stop_loss=7.10,
        risk_reward=1.5,
        momentum_score=9.0,
        quality_score=9.5,
        score_rating="Excellent",
        signal_type="VWAP Breakout",
        catalyst=arabic_catalyst,
        latest_news=arabic_catalyst,
        sec_link="https://www.sec.gov/edgar/searchedgar/companysearch.html?q=DEMO",
        timestamp=datetime.datetime.utcnow()
    )
    mock_signal.rsi_14 = 33.5

    # 3. Save mock signal to database to generate a real ID
    async with async_session() as db:
        print("Saving mock signal to DB...")
        db.add(mock_signal)
        await db.commit()
        await db.refresh(mock_signal)
        print(f"Mock signal saved with ID: {mock_signal.id}")

    # 4. Clear Redis cooldown for DEMO to ensure it dispatches
    print("Clearing cooldown locks...")
    await notifier.redis_client.delete("cooldown:DEMO")
    
    # 5. Dispatch the persisted signal to the channel
    print("Dispatching signal to channel...")
    await notifier.dispatch_signal(mock_signal)
    print("Signal dispatch complete!")
    
    # Close session
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
