from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.category import Category
from app.models.financial_year import FinancialYear
from app.models.item import Item
from app.models.unit import Unit
from app.schemas.category import CategoryCreate, CategoryResponse
from app.schemas.financial_year import FinancialYearCreate, FinancialYearResponse
from app.schemas.item import ItemCreate, ItemResponse
from app.schemas.unit import UnitCreate, UnitResponse

router = APIRouter(prefix="/masters", tags=["masters"])


@router.get("/financial-years", response_model=list[FinancialYearResponse])
async def list_financial_years(session: AsyncSession = Depends(get_db_session)):
    result = await session.scalars(select(FinancialYear).order_by(FinancialYear.start_date.desc()))
    return list(result.all())


@router.post("/financial-years", response_model=FinancialYearResponse, status_code=status.HTTP_201_CREATED)
async def create_financial_year(payload: FinancialYearCreate, session: AsyncSession = Depends(get_db_session)):
    if payload.is_current:
        existing = await session.scalars(select(FinancialYear).where(FinancialYear.is_current.is_(True)))
        if existing.first() is not None:
            raise HTTPException(status_code=409, detail="A current financial year already exists")
    fy = FinancialYear(**payload.model_dump())
    session.add(fy)
    await session.commit()
    await session.refresh(fy)
    return fy


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(session: AsyncSession = Depends(get_db_session)):
    result = await session.scalars(select(Category).order_by(Category.name))
    return list(result.all())


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(payload: CategoryCreate, session: AsyncSession = Depends(get_db_session)):
    category = Category(**payload.model_dump())
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


@router.get("/units", response_model=list[UnitResponse])
async def list_units(session: AsyncSession = Depends(get_db_session)):
    result = await session.scalars(select(Unit).order_by(Unit.name))
    return list(result.all())


@router.post("/units", response_model=UnitResponse, status_code=status.HTTP_201_CREATED)
async def create_unit(payload: UnitCreate, session: AsyncSession = Depends(get_db_session)):
    unit = Unit(**payload.model_dump())
    session.add(unit)
    await session.commit()
    await session.refresh(unit)
    return unit


@router.get("/items", response_model=list[ItemResponse])
async def list_items(session: AsyncSession = Depends(get_db_session)):
    result = await session.scalars(select(Item).order_by(Item.name))
    return list(result.all())


@router.post("/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(payload: ItemCreate, session: AsyncSession = Depends(get_db_session)):
    category = await session.get(Category, payload.category_id)
    unit = await session.get(Unit, payload.unit_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if unit is None:
        raise HTTPException(status_code=404, detail="Unit not found")
    item = Item(**payload.model_dump())
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item
