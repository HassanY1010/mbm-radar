import asyncio
from sqlalchemy import text
from app.database.session import async_engine

async def migrate():
    async with async_engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE signals ADD COLUMN IF NOT EXISTS is_simulated BOOLEAN DEFAULT FALSE;"
        ))
    print("Migration successful: is_simulated column added to signals table.")

if __name__ == "__main__":
    asyncio.run(migrate())
