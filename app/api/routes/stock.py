from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.security.auth import get_current_user
from app.models.user import User
from app.schemas.stock import OpeningStockCreate, OpeningStockResponse, StockBalanceResponse, StockRegisterRow
from app.services.stock import StockService

router = APIRouter(prefix="/stock", tags=["stock"])


@router.post("/openings", response_model=OpeningStockResponse, status_code=status.HTTP_201_CREATED)
async def create_opening(
    payload: OpeningStockCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = StockService(session)
    try:
        opening = await service.create_opening(payload, current_user.id)
        await session.commit()
        await session.refresh(opening)
        return opening
    except HTTPException:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise


@router.post("/openings/manual", response_model=OpeningStockResponse, status_code=status.HTTP_201_CREATED)
async def create_and_post_opening(
    payload: OpeningStockCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = StockService(session)
    try:
        return await service.create_and_post_opening(payload, current_user.id)
    except HTTPException:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise



@router.post("/openings/{opening_id}/post", response_model=OpeningStockResponse)
async def post_opening(
    opening_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    service = StockService(session)
    try:
        return await service.post_opening(opening_id, current_user.id)
    except HTTPException:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise


@router.get("/balances", response_model=list[StockBalanceResponse])
async def current_stock(
    store_id: int,
    financial_year_id: int,
    item_id: int | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    rows = await StockService(session).current_stock(store_id, financial_year_id, item_id)
    return [
        StockBalanceResponse(
            store_id=row.store_id,
            financial_year_id=row.financial_year_id,
            item_id=row.item_id,
            item_code=row.code,
            item_name=row.name,
            unit_code=row[5],
            balance=row.balance,
        )
        for row in rows
    ]


@router.get("/register", response_model=list[StockRegisterRow])
async def stock_register(
    store_id: int,
    financial_year_id: int,
    item_id: int,
    from_date: date | None = None,
    to_date: date | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    rows = await StockService(session).stock_register(
        store_id, financial_year_id, item_id, from_date, to_date
    )
    return [StockRegisterRow.model_validate(row) for row in rows]
