import asyncio
from sqlalchemy import delete
from app.models.models import Signal
from app.database.session import async_session

async def main():
    print("Connecting to database to delete Signal ID 223 to clear cooldown...")
    async with async_session() as db:
        await db.execute(
            delete(Signal).where(Signal.id == 223)
        )
        await db.commit()
        print("Database commit successful! Signal 223 deleted.")

if __name__ == "__main__":
    asyncio.run(main())
