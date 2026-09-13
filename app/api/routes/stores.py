from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.security.auth import get_current_user
from app.models.user import User
from app.schemas.store import StoreCreate, StoreResponse
from app.services.store import StoreService

router = APIRouter(prefix="/stores", tags=["stores"])


@router.get("", response_model=list[StoreResponse])
async def list_stores(session: AsyncSession = Depends(get_db_session)):
    return await StoreService(session).list_stores()


@router.post("", response_model=StoreResponse, status_code=status.HTTP_201_CREATED)
async def create_store(payload: StoreCreate, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    service = StoreService(session)
    try:
        office = await session.get(__import__("app.models.office", fromlist=["Office"]).Office, payload.office_id)
        if office is None:
            raise HTTPException(status_code=404, detail="Office not found")
        store = await service.create_store(payload)
        await session.commit()
        await session.refresh(store)
        return store
    except HTTPException:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise
