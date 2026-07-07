import asyncio
from sqlalchemy import select, delete
from app.models.models import User, UserPreferences, Signal
from app.database.session import async_session
from app.core.config import settings

async def main():
    print("Connecting to database to relax all admin filters and clear cooldown signals...")
    async with async_session() as db:
        # 1. Relax UserPreferences
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
        print(f"  min_gap_pct: {pref.min_gap_pct}")
        print(f"  min_change_pct: {pref.min_change_pct}")
        
        print("Relaxing preferences to maximum permissive levels...")
        pref.min_rvol = 0.0
        pref.min_score_threshold = 0.0
        pref.min_gap_pct = -100.0
        pref.min_change_pct = -100.0
        pref.min_volume = 0
        pref.max_price = 1000.0
        pref.max_float = 10000000000.0
        pref.max_market_cap = 100000000000.0
        
        # 2. Clear Cooldown Signal for CMCL
        print("Deleting signal history for CMCL to bypass cooldown check...")
        await db.execute(
            delete(Signal).where(Signal.ticker == "CMCL")
        )
        
        await db.commit()
        print("Database commit successful! Cooldown cleared and all filters relaxed.")

if __name__ == "__main__":
    asyncio.run(main())
