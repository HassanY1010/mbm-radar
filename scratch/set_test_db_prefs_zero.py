import asyncio
from sqlalchemy import select
from app.models.models import User, UserPreferences
from app.database.session import async_session
from app.core.config import settings

async def main():
    print(f"Connecting to database to update preferences to 0 for admin ID: {settings.ADMIN_TELEGRAM_ID}")
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
        
        print("Updating to test values: min_rvol=0.0, min_score_threshold=0.0")
        pref.min_rvol = 0.0
        pref.min_score_threshold = 0.0
        
        await db.commit()
        print("Database commit successful! Preferences updated.")

if __name__ == "__main__":
    asyncio.run(main())
