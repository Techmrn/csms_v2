from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.office import Office


class OfficeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, office_id: int) -> Office | None:
        return await self.session.get(Office, office_id)

    async def list(self) -> list[Office]:
        result = await self.session.scalars(select(Office).order_by(Office.display_order, Office.name))
        return list(result.all())

    async def create(self, office: Office) -> Office:
        self.session.add(office)
        await self.session.flush()
        return office
