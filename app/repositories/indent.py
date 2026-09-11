from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.indent import Indent


class IndentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, indent_id: int) -> Indent | None:
        result = await self.session.execute(
            select(Indent)
            .options(selectinload(Indent.lines))
            .where(Indent.id == indent_id)
        )
        return result.scalar_one_or_none()

    async def list(self, store_id: int | None = None, status: str | None = None) -> list[Indent]:
        stmt = select(Indent).options(selectinload(Indent.lines)).order_by(Indent.indent_date.desc(), Indent.id.desc())
        if store_id is not None:
            stmt = stmt.where(Indent.store_id == store_id)
        if status is not None:
            stmt = stmt.where(Indent.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
