from sqlalchemy.ext.asyncio import AsyncSession

from app.models.office import Office
from app.repositories.office import OfficeRepository
from app.schemas.office import OfficeCreate


class OfficeService:
    def __init__(self, session: AsyncSession):
        self.repository = OfficeRepository(session)

    async def list_offices(self) -> list[Office]:
        return await self.repository.list()

    async def create_office(self, data: OfficeCreate, actor_id: int) -> Office:
        from app.services.authorization import AuthorizationService
        await AuthorizationService(self.repository.session).require_permission(actor_id, "ORGANIZATION_MANAGE")
        office = Office(**data.model_dump())
        return await self.repository.create(office)
