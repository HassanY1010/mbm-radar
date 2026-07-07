import asyncio
from sqlalchemy import select
from app.models.models import User, UserPreferences
from app.database.session import async_session
from app.core.config import settings

async def main():
    print(f"Connecting to database to check preferences for admin ID: {settings.ADMIN_TELEGRAM_ID}")
    async with async_session() as db:
        res = await db.execute(
            select(User).where(User.telegram_id == settings.ADMIN_TELEGRAM_ID)
        )
        user = res.scalar_one_or_none()
        if not user:
            print("Admin user not found in the database!")
            return
            
        print(f"User found: ID={user.id}, username={user.username}, is_admin={user.is_admin}")
        
        res_pref = await db.execute(
            select(UserPreferences).where(UserPreferences.user_id == user.id)
        )
        pref = res_pref.scalar_one_or_none()
        if not pref:
            print("UserPreferences record not found for admin!")
            return
            
        print("UserPreferences found:")
        print(f"  max_price: {pref.max_price}")
        print(f"  max_float: {pref.max_float}")
        print(f"  max_market_cap: {pref.max_market_cap}")
        print(f"  min_rvol: {pref.min_rvol}")
        print(f"  min_volume: {pref.min_volume}")
        print(f"  min_gap_pct: {pref.min_gap_pct}")
        print(f"  min_change_pct: {pref.min_change_pct}")
        print(f"  cooldown_minutes: {pref.cooldown_minutes}")
        print(f"  alerts_enabled: {pref.alerts_enabled}")
        print(f"  alert_types: {pref.alert_types}")
        print(f"  is_shariah_only: {pref.is_shariah_only}")
        print(f"  volume_filter_type: {getattr(pref, 'volume_filter_type', None)}")
        print(f"  min_score_threshold: {getattr(pref, 'min_score_threshold', None)}")

if __name__ == "__main__":
    asyncio.run(main())
