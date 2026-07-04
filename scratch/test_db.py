import asyncio
import asyncpg
from app.core.config import settings

async def main():
    dsn = settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql").replace("hhaall112233$", "hhaall112233%24").replace(":5432/", ":6543/")
    print("Testing connection to:", dsn)
    try:
        conn = await asyncpg.connect(dsn)
        print("Successfully connected!")
        await conn.close()
    except Exception as e:
        print("Connection failed:", type(e), e)

if __name__ == "__main__":
    asyncio.run(main())
