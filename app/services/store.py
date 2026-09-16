from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store import Store
from app.repositories.store import StoreRepository
from app.schemas.store import StoreCreate


class StoreService:
    def __init__(self, session: AsyncSession):
        self.repository = StoreRepository(session)

    async def list_stores(self) -> list[Store]:
        return await self.repository.list()

    async def create_store(self, data: StoreCreate, actor_id: int) -> Store:
        from app.services.authorization import AuthorizationService
        await AuthorizationService(self.repository.session).require_permission(actor_id, "ORGANIZATION_MANAGE")
        store = Store(**data.model_dump())
        return await self.repository.create(store)
