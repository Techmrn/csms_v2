from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.security.auth import get_current_user
from app.models.user import User
from app.schemas.stock_return import StockReturnCreate, StockReturnResponse
from app.services.stock_return import StockReturnService

router = APIRouter(prefix="/returns", tags=["returns"])


@router.post("", response_model=StockReturnResponse, status_code=status.HTTP_201_CREATED)
async def create_return(
    payload: StockReturnCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await StockReturnService(session).create(payload, current_user.id)


@router.get("", response_model=list[StockReturnResponse])
async def list_returns(
    store_id: int | None = None,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await StockReturnService(session).list(store_id, status)


@router.get("/{return_id}", response_model=StockReturnResponse)
async def get_return(return_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return await StockReturnService(session).get(return_id)


@router.post("/{return_id}/verify", response_model=StockReturnResponse)
async def verify_return(return_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return await StockReturnService(session).verify(return_id, current_user.id)


@router.post("/{return_id}/post", response_model=StockReturnResponse)
async def post_return(return_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return await StockReturnService(session).post(return_id, current_user.id)
