import asyncio
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal, engine
from app.models import Category, FinancialYear, Office, Permission, Role, Store, Unit

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

PERMISSIONS = [
    ("STOCK_VIEW", "View stock", "STOCK", "VIEW"),
    ("STOCK_RECEIPT", "Receive stock", "STOCK", "RECEIPT"),
    ("STOCK_ISSUE", "Issue stock", "STOCK", "ISSUE"),
    ("STOCK_TRANSFER_DISPATCH", "Dispatch transfer", "STOCK", "TRANSFER_DISPATCH"),
    ("STOCK_TRANSFER_RECEIVE", "Receive transfer", "STOCK", "TRANSFER_RECEIVE"),
    ("STOCK_TRANSFER_DISCREPANCY_RESOLVE", "Resolve transfer discrepancy", "STOCK", "TRANSFER_DISCREPANCY_RESOLVE"),
    ("STOCK_RETURN", "Process stock return", "STOCK", "RETURN"),
    ("STOCK_VERIFY", "Verify stock", "STOCK", "VERIFY"),
    ("STOCK_ADJUST_AUTHORIZE", "Authorize stock adjustment", "STOCK", "ADJUST_AUTHORIZE"),
    ("STOCK_UNSERVICEABLE_AUTHORIZE", "Authorize unserviceable stock", "STOCK", "UNSERVICEABLE_AUTHORIZE"),
    ("STOCK_VERIFICATION_CREATE", "Create stock verification", "STOCK", "VERIFICATION_CREATE"),
    ("STOCK_ADJUST_CREATE", "Create stock adjustment", "STOCK", "ADJUST_CREATE"),
    ("STOCK_ADJUST_POST", "Post stock adjustment", "STOCK", "ADJUST_POST"),
    ("STOCK_UNSERVICEABLE_CREATE", "Report unserviceable stock", "STOCK", "UNSERVICEABLE_CREATE"),
    ("STOCK_UNSERVICEABLE_POST", "Post unserviceable stock", "STOCK", "UNSERVICEABLE_POST"),
    ("INDENT_CREATE", "Create indent", "INDENT", "CREATE"),
    ("INDENT_APPROVE", "Approve indent", "INDENT", "APPROVE"),
    ("INDENT_PROCESS", "Process indent", "INDENT", "PROCESS"),
    ("REQUISITION_CREATE", "Create central store requisition", "REQUISITION", "CREATE"),
    ("REQUISITION_APPROVE_BRANCH", "Approve branch requisition", "REQUISITION", "APPROVE_BRANCH"),
    ("REQUISITION_APPROVE_CENTRAL", "Approve central requisition", "REQUISITION", "APPROVE_CENTRAL"),
    ("ASSET_VIEW", "View assets", "ASSET", "VIEW"),
    ("ASSET_CREATE", "Create asset", "ASSET", "CREATE"),
    ("REPORT_VIEW", "View reports", "REPORT", "VIEW"),
    ("AUDIT_VIEW", "View audit history", "AUDIT", "VIEW"),
    ("PETTY_PURCHASE_CREATE", "Create petty purchase", "PETTY_PURCHASE", "CREATE"),
    ("PETTY_PURCHASE_VERIFY", "Verify petty purchase", "PETTY_PURCHASE", "VERIFY"),
    ("PETTY_PURCHASE_POST", "Post petty purchase", "PETTY_PURCHASE", "POST"),
]

ROLE_PERMISSIONS = {
    "SYSTEM_ADMIN": [p[0] for p in PERMISSIONS],
    "DIRECTOR": ["STOCK_VIEW", "REPORT_VIEW", "AUDIT_VIEW", "ASSET_VIEW"],
    "DEPUTY_SUPDT_STORES": [
        "STOCK_VIEW", "STOCK_VERIFY", "STOCK_ADJUST_AUTHORIZE",
        "STOCK_UNSERVICEABLE_AUTHORIZE", "STOCK_TRANSFER_DISCREPANCY_RESOLVE", "REQUISITION_APPROVE_CENTRAL",
        "REPORT_VIEW", "AUDIT_VIEW", "ASSET_VIEW", "PETTY_PURCHASE_VERIFY",
    ],
    "GENERAL_STOREKEEPER": [
        "STOCK_VIEW", "STOCK_RECEIPT", "STOCK_ISSUE",
        "STOCK_TRANSFER_DISPATCH", "STOCK_RETURN", "INDENT_PROCESS",
        "REQUISITION_CREATE", "ASSET_VIEW", "ASSET_CREATE", "PETTY_PURCHASE_CREATE", "PETTY_PURCHASE_POST",
        "STOCK_VERIFICATION_CREATE", "STOCK_ADJUST_CREATE", "STOCK_ADJUST_POST",
        "STOCK_UNSERVICEABLE_CREATE", "STOCK_UNSERVICEABLE_POST",
    ],
    "ASSISTANT_STOREKEEPER": [
        "STOCK_VIEW", "STOCK_RECEIPT", "STOCK_ISSUE",
        "STOCK_TRANSFER_DISPATCH", "STOCK_RETURN", "INDENT_PROCESS",
        "REQUISITION_CREATE", "ASSET_VIEW", "ASSET_CREATE", "PETTY_PURCHASE_CREATE", "PETTY_PURCHASE_POST",
        "STOCK_VERIFICATION_CREATE", "STOCK_ADJUST_CREATE", "STOCK_ADJUST_POST",
        "STOCK_UNSERVICEABLE_CREATE", "STOCK_UNSERVICEABLE_POST",
    ],
    "BRANCH_HEAD": [
        "STOCK_VIEW", "STOCK_TRANSFER_DISCREPANCY_RESOLVE", "STOCK_VERIFY", "INDENT_APPROVE",
        "REQUISITION_APPROVE_BRANCH", "REPORT_VIEW", "ASSET_VIEW", "PETTY_PURCHASE_VERIFY",
        "STOCK_ADJUST_AUTHORIZE", "STOCK_UNSERVICEABLE_AUTHORIZE",
    ],
    "BRANCH_STOREKEEPER": [
        "STOCK_VIEW", "STOCK_RECEIPT", "STOCK_ISSUE",
        "STOCK_TRANSFER_RECEIVE", "STOCK_RETURN", "INDENT_PROCESS",
        "INDENT_CREATE", "REQUISITION_CREATE", "ASSET_VIEW", "ASSET_CREATE",
        "PETTY_PURCHASE_CREATE", "PETTY_PURCHASE_POST",
        "STOCK_VERIFICATION_CREATE", "STOCK_ADJUST_CREATE", "STOCK_ADJUST_POST",
        "STOCK_UNSERVICEABLE_CREATE", "STOCK_UNSERVICEABLE_POST",
    ],
    "SECTION_USER": ["INDENT_CREATE"],
}


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

        roles_result = await session.execute(select(Role).options(selectinload(Role.permissions)))
        roles_by_code = {role.code: role for role in roles_result.scalars().all()}
        permissions_by_code = {permission.code: permission for permission in (await session.scalars(select(Permission))).all()}
        for role_code, permission_codes in ROLE_PERMISSIONS.items():
            role = roles_by_code[role_code]
            existing = {permission.code for permission in role.permissions}
            for permission_code in permission_codes:
                if permission_code in permissions_by_code and permission_code not in existing:
                    role.permissions.append(permissions_by_code[permission_code])

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
