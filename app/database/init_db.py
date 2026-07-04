import asyncio
import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import Base, async_engine, async_session
from app.models.models import Plan, Settings
from app.core.logging import database_logger

async def init_db():
    database_logger.info("Initializing database...")
    
    # Create all tables
    async with async_engine.begin() as conn:
        # For development / first run: create tables if they do not exist
        await conn.run_sync(Base.metadata.create_all)
    
    # Add seed data
    async with async_session() as session:
        # Check if plans exist, if not seed them
        from sqlalchemy import select
        result = await session.execute(select(Plan))
        plans = result.scalars().all()
        
        if not plans:
            database_logger.info("Seeding default subscription plans...")
            monthly = Plan(name="Monthly", duration_days=30, price=29.99, is_active=True)
            quarterly = Plan(name="Quarterly", duration_days=90, price=79.99, is_active=True)
            yearly = Plan(name="Yearly", duration_days=365, price=249.99, is_active=True)
            session.add_all([monthly, quarterly, yearly])
        
        # Check if settings exist, seed defaults
        settings_to_seed = {
            "active_provider": "FMP",
            "scanner_max_price": "20.0",
            "scanner_max_float": "20000000.0",
            "scanner_max_market_cap": "1500000000.0",
            "scanner_min_rvol": "3.0",
            "scanner_min_volume": "100000",
            "scanner_min_gap_pct": "2.0",
            "scanner_min_change_pct": "1.0",
            "cooldown_period_minutes": "15"
        }
        
        for key, value in settings_to_seed.items():
            res = await session.execute(select(Settings).filter_by(key=key))
            existing_setting = res.scalar_one_or_none()
            if not existing_setting:
                session.add(Settings(key=key, value=value, description=f"Default setting for {key}"))
                
        await session.commit()
    database_logger.info("Database initialization completed successfully.")

if __name__ == "__main__":
    asyncio.run(init_db())
