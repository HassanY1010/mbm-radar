import asyncio
from sqlalchemy import select, delete
from app.models.models import User, UserPreferences, Signal
from app.database.session import async_session
from app.core.config import settings

async def main():
    print("Connecting to database to set temporary test values...")
    async with async_session() as db:
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
            
        print("Existing preferences:")
        print(f"  min_rvol: {pref.min_rvol}")
        print(f"  min_score_threshold: {pref.min_score_threshold}")
        print(f"  min_gap_pct: {pref.min_gap_pct}")
        print(f"  min_change_pct: {pref.min_change_pct}")
        print(f"  min_volume: {pref.min_volume}")
        print(f"  max_price: {pref.max_price}")
        print(f"  max_float: {pref.max_float}")
        print(f"  max_market_cap: {pref.max_market_cap}")
        
        print("Updating preferences to user's test specification...")
        pref.min_rvol = 1.0
        pref.min_score_threshold = 2.5
        pref.min_gap_pct = 0.0
        pref.min_change_pct = 0.0
        pref.min_volume = 100000
        pref.max_price = 30.0
        pref.max_float = 30000000.0
        pref.max_market_cap = 3000000000.0
        pref.is_shariah_only = True
        
        print("Clearing all cooldown signals...")
        await db.execute(
            delete(Signal)
        )
        
        await db.commit()
        print("Database commit successful! Test preferences set and cooldowns cleared.")

if __name__ == "__main__":
    asyncio.run(main())
