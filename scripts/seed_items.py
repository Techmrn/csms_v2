import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models import Category, Item, Unit

async def seed_items():
    async with AsyncSessionLocal() as session:
        cat_con = await session.scalar(select(Category).where(Category.type == "CONSUMABLE"))
        cat_asset = await session.scalar(select(Category).where(Category.type == "ASSET"))
        unit = await session.scalar(select(Unit).limit(1))
        
        con_item = Item(
            code="TEST-CON-1",
            name="Test Consumable",
            category_id=cat_con.id,
            unit_id=unit.id,
        )
        asset_item = Item(
            code="TEST-ASS-1",
            name="Test Asset",
            category_id=cat_asset.id,
            unit_id=unit.id,
        )
        session.add_all([con_item, asset_item])
        await session.commit()

if __name__ == "__main__":
    asyncio.run(seed_items())
