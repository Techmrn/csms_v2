import asyncio
import os

from sqlalchemy import select

from app.db.session import AsyncSessionLocal, engine
from app.models.user import User
from app.security.auth import password_hash


async def set_passwords() -> None:
    password = os.getenv("CSMS_DEV_PASSWORD")
    if not password:
        raise SystemExit("Set CSMS_DEV_PASSWORD before running this development-only script.")

    usernames = {
        "dev_director",
        "dev_deputy",
        "dev_general_sk",
        "dev_assistant_sk",
        "dev_press_head",
        "dev_press_sk",
    }

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.username.in_(usernames)))
        users = result.scalars().all()
        for user in users:
            user.password_hash = password_hash.hash(password)
            print(f"Password set for {user.username}")
        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(set_passwords())
