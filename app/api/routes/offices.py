from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.office import OfficeCreate, OfficeResponse
from app.services.office import OfficeService

router = APIRouter(prefix="/offices", tags=["offices"])


@router.get("", response_model=list[OfficeResponse])
async def list_offices(session: AsyncSession = Depends(get_db_session)):
    return await OfficeService(session).list_offices()


@router.post("", response_model=OfficeResponse, status_code=status.HTTP_201_CREATED)
async def create_office(payload: OfficeCreate, session: AsyncSession = Depends(get_db_session)):
    service = OfficeService(session)
    try:
        office = await service.create_office(payload)
        await session.commit()
        await session.refresh(office)
        return office
    except Exception:
        await session.rollback()
        raise
