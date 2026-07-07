import asyncio
from sqlalchemy import select
from app.models.models import Signal
from app.database.session import async_session

async def main():
    print("Connecting to database to check Signal ID 223...")
    async with async_session() as db:
        res = await db.execute(
            select(Signal).where(Signal.id == 223)
        )
        sig = res.scalar_one_or_none()
        if not sig:
            print("Signal ID 223 not found!")
            return
            
        print("Signal 223 details:")
        print(f"  Ticker: {sig.ticker}")
        print(f"  Timestamp: {sig.timestamp}")
        print(f"  Price: {sig.price}")
        print(f"  Change %: {sig.change_pct}")
        print(f"  Gap %: {sig.gap_pct}")
        print(f"  RVOL: {sig.rvol}")
        print(f"  Score: {sig.quality_score}")

if __name__ == "__main__":
    asyncio.run(main())
