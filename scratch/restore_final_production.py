import asyncio
from sqlalchemy import select, delete
from app.models.models import User, UserPreferences, Signal
from app.database.session import async_session
from app.core.config import settings

async def main():
    print("Connecting to database to restore production preferences and clean up test signals...")
    async with async_session() as db:
        # 1. Restore UserPreferences to final production defaults
        res = await db.execute(
            select(User).where(User.telegram_id == settings.ADMIN_TELEGRAM_ID)
        )
        user = res.scalar_one_or_none()
        if not user:
            print("Admin user not found in the database!")
            return
            
        res_pref = await db.execute(
            select(UserPreferences).where(UserPreferences.user_id == user.id)
        )
        pref = res_pref.scalar_one_or_none()
        if not pref:
            print("UserPreferences record not found for admin!")
            return
            
        print("Restoring preferences to production defaults...")
        pref.min_rvol = 1.5
        pref.min_score_threshold = 3.5
        pref.min_gap_pct = 2.0
        pref.min_change_pct = 1.0
        pref.min_volume = 50000
        pref.max_price = 30.0
        pref.max_float = 20000000.0
        pref.max_market_cap = 3000000000.0
        pref.is_shariah_only = True
        
        # 2. Clear all test signals from database
        print("Cleaning up test signals from database...")
        tickers_to_clean = ["ALIT", "XE", "CMCO", "CMCL", "CLPT", "CGCT"]
        for ticker in tickers_to_clean:
            await db.execute(
                delete(Signal).where(Signal.ticker == ticker)
            )
        
        await db.commit()
        print("Database commit successful! Production preferences restored and clean-up completed.")

if __name__ == "__main__":
    asyncio.run(main())
