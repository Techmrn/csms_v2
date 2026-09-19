from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.security.auth import get_current_user
from app.models.user import User
from app.schemas.stock_return import StockReturnCreate, StockReturnResponse
from app.services.stock_return import StockReturnService
from app.services.authorization import AuthorizationService

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
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "STOCK_RETURN_VIEW")
    user = await session.get(User, current_user.id)
    scoped = await auth.scoped_store_ids(current_user.id, store_id)
    service = StockReturnService(session)
    if scoped is None:
        return await service.list(None, status)
    rows = []
    for sid in scoped:
        rows.extend(await service.list(sid, status))
    if not rows and user is not None and user.section_id is not None:
        all_rows = await service.list(store_id, status) if store_id is not None else await service.list(None, status)
        rows = [row for row in all_rows if row.returning_section_id == user.section_id]
    return rows


@router.get("/{return_id}", response_model=StockReturnResponse)
async def get_return(return_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "STOCK_RETURN_VIEW")
    row = await StockReturnService(session).get(return_id)
    visible = await auth.get_visible_stores(current_user.id)
    if visible is not None and row.store_id not in visible:
        # Section users may view their own section returns without store assignment.
        user = await session.get(User, current_user.id)
        if user is None or row.returning_section_id != user.section_id:
            raise HTTPException(403, "User is not authorized to access this return")
    return row


@router.post("/{return_id}/verify", response_model=StockReturnResponse)
async def verify_return(return_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return await StockReturnService(session).verify(return_id, current_user.id)


@router.post("/{return_id}/post", response_model=StockReturnResponse)
async def post_return(return_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return await StockReturnService(session).post(return_id, current_user.id)
