import asyncio
from sqlalchemy import select
from app.models.models import Notification
from app.database.session import async_session

async def main():
    print("Connecting to database to check Notification for Signal ID 223...")
    async with async_session() as db:
        res = await db.execute(
            select(Notification).where(Notification.signal_id == 223)
        )
        notif = res.scalar_one_or_none()
        if not notif:
            print("Notification for Signal ID 223 not found!")
            return
            
        print("Notification found:")
        print(f"  ID: {notif.id}")
        print(f"  Signal ID: {notif.signal_id}")
        print(f"  Channel Message ID: {notif.channel_msg_id}")
        print(f"  Sent At: {notif.sent_at}")
        print(f"  Status: {notif.status}")

if __name__ == "__main__":
    asyncio.run(main())
