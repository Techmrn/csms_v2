from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store import Store


class StoreRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, store_id: int) -> Store | None:
        return await self.session.get(Store, store_id)

    async def list(self) -> list[Store]:
        result = await self.session.scalars(select(Store).order_by(Store.name))
        return list(result.all())

    async def create(self, store: Store) -> Store:
        self.session.add(store)
        await self.session.flush()
        return store
