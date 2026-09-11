from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.financial_year import FinancialYear
from app.models.item import Item
from app.models.stock import OpeningStock, OpeningStockLine, StockAccount, StockMovement
from app.models.store import Store
from app.models.unit import Unit
from app.repositories.stock import StockRepository
from app.schemas.stock import OpeningStockCreate


class StockService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = StockRepository(session)

    async def create_opening(self, payload: OpeningStockCreate) -> OpeningStock:
        fy = await self.session.get(FinancialYear, payload.financial_year_id)
        store = await self.session.get(Store, payload.store_id)
        if fy is None:
            raise HTTPException(status_code=404, detail="Financial year not found")
        if store is None:
            raise HTTPException(status_code=404, detail="Store not found")
        if fy.is_closed:
            raise HTTPException(status_code=409, detail="Financial year is closed")
        if not (fy.start_date <= payload.opening_date <= fy.end_date):
            raise HTTPException(status_code=422, detail="Opening date is outside the financial year")

        seen_items: set[int] = set()
        lines: list[OpeningStockLine] = []
        for line in payload.lines:
            if line.item_id in seen_items:
                raise HTTPException(status_code=422, detail=f"Duplicate item {line.item_id} in opening stock")
            seen_items.add(line.item_id)

            item = await self.session.get(Item, line.item_id)
            unit = await self.session.get(Unit, line.unit_id)
            if item is None:
                raise HTTPException(status_code=404, detail=f"Item {line.item_id} not found")
            if unit is None:
                raise HTTPException(status_code=404, detail=f"Unit {line.unit_id} not found")
            category = await self.session.get(Category, item.category_id)
            if category is None:
                raise HTTPException(status_code=409, detail=f"Item {item.id} has no valid category")
            if category.type != "CONSUMABLE":
                raise HTTPException(
                    status_code=422,
                    detail=f"Opening stock in this stock ledger is only for consumables; item {item.code} is {category.type}",
                )
            if unit.id != item.unit_id:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unit {unit.code} is not the master unit for item {item.code}",
                )

            lines.append(
                OpeningStockLine(
                    item_id=line.item_id,
                    quantity=line.quantity,
                    unit_id=line.unit_id,
                    remarks=line.remarks,
                )
            )

        opening_no = await self._next_opening_number(payload.financial_year_id)
        opening = OpeningStock(
            opening_no=opening_no,
            opening_date=payload.opening_date,
            financial_year_id=payload.financial_year_id,
            store_id=payload.store_id,
            status="OPEN",
            remarks=payload.remarks,
            lines=lines,
        )
        self.session.add(opening)
        await self.session.flush()
        return opening

    async def post_opening(self, opening_id: int) -> OpeningStock:
        """Development posting path until authentication/approval is wired in.

        Production policy will require the appropriate authorization transition before posting.
        """
        opening = await self.session.get(OpeningStock, opening_id)
        if opening is None:
            raise HTTPException(status_code=404, detail="Opening stock not found")
        if opening.status != "OPEN":
            raise HTTPException(status_code=409, detail=f"Opening stock is {opening.status}, not OPEN")

        fy = await self.session.get(FinancialYear, opening.financial_year_id)
        if fy is None or fy.is_closed:
            raise HTTPException(status_code=409, detail="Financial year is missing or closed")
        if not (fy.start_date <= opening.opening_date <= fy.end_date):
            raise HTTPException(status_code=422, detail="Opening date is outside the financial year")

        async with self.session.begin_nested():
            posting_group_id = uuid4()
            for line in opening.lines:
                # Ensure a stable row exists, then lock it for the duration of posting.
                await self.session.execute(
                    pg_insert(StockAccount)
                    .values(
                        store_id=opening.store_id,
                        financial_year_id=opening.financial_year_id,
                        item_id=line.item_id,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["store_id", "financial_year_id", "item_id"]
                    )
                )
                account = await self.session.scalar(
                    select(StockAccount)
                    .where(
                        StockAccount.store_id == opening.store_id,
                        StockAccount.financial_year_id == opening.financial_year_id,
                        StockAccount.item_id == line.item_id,
                    )
                    .with_for_update()
                )
                if account is None:
                    raise HTTPException(status_code=500, detail="Unable to lock stock account")

                duplicate = await self.session.scalar(
                    select(StockMovement.id)
                    .where(
                        StockMovement.reference_type == "OPENING_STOCK_LINE",
                        StockMovement.reference_id == line.id,
                        StockMovement.item_id == line.item_id,
                        StockMovement.movement_type == "OPENING",
                    )
                    .limit(1)
                )
                if duplicate is not None:
                    raise HTTPException(status_code=409, detail="Opening stock is already posted")

                self.session.add(
                    StockMovement(
                        financial_year_id=opening.financial_year_id,
                        store_id=opening.store_id,
                        item_id=line.item_id,
                        movement_date=opening.opening_date,
                        movement_type="OPENING",
                        quantity_in=line.quantity,
                        quantity_out=Decimal("0"),
                        reference_type="OPENING_STOCK_LINE",
                        reference_id=line.id,
                        reference_no=opening.opening_no,
                        posting_group_id=posting_group_id,
                        remarks=line.remarks,
                    )
                )

            opening.status = "POSTED"
            opening.posting_group_id = posting_group_id
            opening.posted_at = datetime.now(timezone.utc)

        await self.session.commit()
        await self.session.refresh(opening)
        return opening

    async def current_stock(self, store_id: int, financial_year_id: int, item_id: int | None = None):
        return await self.repository.balances(store_id, financial_year_id, item_id)

    async def stock_register(
        self,
        store_id: int,
        financial_year_id: int,
        item_id: int,
        from_date: date | None = None,
        to_date: date | None = None,
    ):
        return await self.repository.register(store_id, financial_year_id, item_id, from_date, to_date)

    async def _next_opening_number(self, financial_year_id: int) -> str:
        prefix = f"OPN-{financial_year_id}"
        existing = await self.session.scalars(
            select(OpeningStock.opening_no)
            .where(OpeningStock.opening_no.like(f"{prefix}-%"))
            .order_by(OpeningStock.opening_no.desc())
        )
        last = existing.first()
        next_number = 1
        if last:
            try:
                next_number = int(last.rsplit("-", 1)[1]) + 1
            except (ValueError, IndexError):
                next_number = 1
        return f"{prefix}-{next_number:05d}"
