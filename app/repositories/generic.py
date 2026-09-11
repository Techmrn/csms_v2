from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class GenericRepository:
    def __init__(self, model: type[T], session: AsyncSession):
        self.model = model
        self.session = session

    async def get(self, object_id: int) -> T | None:
        return await self.session.get(self.model, object_id)

    async def list_active(self) -> list[T]:
        result = await self.session.scalars(
            select(self.model).where(self.model.is_active.is_(True))
        )
        return list(result.all())

    async def add(self, entity: T) -> T:
        self.session.add(entity)
        await self.session.flush()
        return entity
