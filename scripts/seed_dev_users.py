import asyncio

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import AsyncSessionLocal, engine
from app.models.role import Role
from app.models.store import Store
from app.models.user import User, user_roles, user_stores
from app.models.office import Office


DEV_USERS = [
    ("DEV-DIR", "dev_director", "Director (DEV)", "DIRECTOR", "DIR", None, None),
    ("DEV-DY", "dev_deputy", "Deputy Superintendent, Stock & Stores (DEV)", "DEPUTY_SUPDT_STORES", "DIR", "CENTRAL", None),
    ("DEV-GSK", "dev_general_sk", "General Storekeeper (DEV)", "GENERAL_STOREKEEPER", "DIR", "CENTRAL", None),
    ("DEV-ASK", "dev_assistant_sk", "Assistant Storekeeper (DEV)", "ASSISTANT_STOREKEEPER", "DIR", "CENTRAL", None),
    ("DEV-PBH", "dev_press_head", "Central Press Branch Head (DEV)", "BRANCH_HEAD", "PRESS", "PRESS-STORE", None),
    ("DEV-PBSK", "dev_press_sk", "Central Press Storekeeper (DEV)", "BRANCH_STOREKEEPER", "PRESS", "PRESS-STORE", None),
]


async def seed_dev_users():
    async with AsyncSessionLocal() as session:
        roles = {r.code: r.id for r in (await session.scalars(select(Role))).all()}
        offices = {o.code: o.id for o in (await session.scalars(select(Office))).all()}
        stores = {s.code: s.id for s in (await session.scalars(select(Store))).all()}

        for code, username, full_name, role_code, office_code, store_code, section_id in DEV_USERS:
            user = await session.scalar(select(User).where(User.username == username))
            if user is None:
                user = User(
                    code=code,
                    username=username,
                    password_hash="DEV_ONLY_NOT_AUTHENTICATED",
                    full_name=full_name,
                    designation=full_name,
                    office_id=offices.get(office_code),
                    section_id=section_id,
                    is_active=True,
                )
                session.add(user)
                await session.flush()
            if role_code in roles:
                await session.execute(
                    pg_insert(user_roles)
                    .values(user_id=user.id, role_id=roles[role_code])
                    .on_conflict_do_nothing()
                )
            if store_code and store_code in stores:
                await session.execute(
                    pg_insert(user_stores)
                    .values(user_id=user.id, store_id=stores[store_code], is_primary=True)
                    .on_conflict_do_nothing()
                )
            print(f"{username}: user_id={user.id}, role={role_code}, store={store_code or '-'}")

        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_dev_users())
