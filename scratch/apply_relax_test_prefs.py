import asyncio
from sqlalchemy import select, delete
from app.models.models import User, UserPreferences, Signal
from app.database.session import async_session
from app.core.config import settings

async def main():
    print("Connecting to database to apply permissive test values...")
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
        
        print("Updating preferences to 0.5 for testing...")
        pref.min_rvol = 0.5
        pref.min_score_threshold = 0.5
        pref.min_gap_pct = 0.0
        pref.min_change_pct = 0.0
        pref.min_volume = 50000
        
        print("Clearing all cooldown signals...")
        await db.execute(
            delete(Signal)
        )
        
        await db.commit()
        print("Database commit successful! Permissive test preferences set and cooldowns cleared.")

if __name__ == "__main__":
    asyncio.run(main())
