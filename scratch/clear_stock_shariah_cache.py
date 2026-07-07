import asyncio
from sqlalchemy import delete
from app.models.models import Stock
from app.database.session import async_session
from app.scanner.simulation_provider import _SIM_TICKERS

async def main():
    print("Connecting to database to clear Shariah cache for simulated tickers...")
    async with async_session() as db:
        for ticker in _SIM_TICKERS:
            await db.execute(
                delete(Stock).where(Stock.ticker == ticker)
            )
        await db.commit()
        print("Successfully deleted simulation tickers from stocks database cache!")

if __name__ == "__main__":
    asyncio.run(main())
