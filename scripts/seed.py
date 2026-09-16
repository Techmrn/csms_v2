import asyncio
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal, engine
from app.models import Category, FinancialYear, Office, Permission, Role, Store, Unit
from app.security.permissions import PERMISSIONS, ROLE_PERMISSIONS

ROLES = [
    ("SYSTEM_ADMIN", "System Administrator"),
    ("DIRECTOR", "Director / Superintendent"),
    ("DEPUTY_SUPDT_STORES", "Deputy Superintendent, Stock & Stores"),
    ("GENERAL_STOREKEEPER", "General Storekeeper"),
    ("ASSISTANT_STOREKEEPER", "Assistant Storekeeper"),
    ("BRANCH_HEAD", "Branch Head"),
    ("BRANCH_STOREKEEPER", "Branch Storekeeper"),
    ("SECTION_USER", "Section User"),
]

CATEGORIES = [
    ("CONSUMABLE", "Consumable", "CONSUMABLE"),
    ("ASSET", "Asset", "ASSET"),
]

UNITS = [
    ("NOS", "Nos", "Nos", False),
    ("KG", "Kilogram", "kg", True),
    ("LTR", "Litre", "L", True),
    ("REAM", "Ream", "ream", False),
    ("BOX", "Box", "box", False),
    ("METER", "Meter", "m", True),
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        if await session.scalar(select(Office.id).limit(1)) is None:
            directorate = Office(code="DIR", name="Directorate", office_type="DIRECTORATE")
            press = Office(code="PRESS", name="Central Press", office_type="BRANCH")
            session.add_all([directorate, press])
            await session.flush()
            session.add(Store(office_id=directorate.id, code="CENTRAL", name="Central Store", store_type="CENTRAL"))
            session.add(Store(office_id=press.id, code="PRESS-STORE", name="Central Press Store", store_type="BRANCH"))

        for code, name, description in CATEGORIES:
            if await session.scalar(select(Category).where(Category.code == code)) is None:
                session.add(Category(code=code, name=name, type=description))

        for code, name, symbol, decimal_allowed in UNITS:
            if await session.scalar(select(Unit).where(Unit.code == code)) is None:
                session.add(Unit(code=code, name=name, symbol=symbol, decimal_allowed=decimal_allowed))

        for code, name in ROLES:
            if await session.scalar(select(Role).where(Role.code == code)) is None:
                session.add(Role(code=code, name=name))

        for code, name, module, action in PERMISSIONS:
            if await session.scalar(select(Permission).where(Permission.code == code)) is None:
                session.add(Permission(code=code, name=name, module=module, action=action))

        await session.flush()

        catalog_codes = {code for code, *_ in PERMISSIONS}
        all_permissions = (await session.scalars(select(Permission))).all()
        for permission in all_permissions:
            permission.is_active = permission.code in catalog_codes

        roles_result = await session.execute(select(Role).options(selectinload(Role.permissions)))
        roles_by_code = {role.code: role for role in roles_result.scalars().all()}
        permissions_by_code = {permission.code: permission for permission in (await session.scalars(select(Permission))).all()}
        for role_code, permission_codes in ROLE_PERMISSIONS.items():
            role = roles_by_code[role_code]
            # Synchronize the complete approved matrix. This deliberately removes
            # stale permissions left by older development seeds.
            role.permissions = [permissions_by_code[code] for code in permission_codes]

        if await session.scalar(select(FinancialYear.id).limit(1)) is None:
            session.add(
                FinancialYear(
                    year_name="2026-27",
                    start_date=date(2026, 4, 1),
                    end_date=date(2027, 3, 31),
                    is_current=True,
                )
            )

        await session.commit()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
