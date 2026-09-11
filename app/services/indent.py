from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from app.models.category import Category
from app.models.financial_year import FinancialYear
from app.models.indent import Indent, IndentLine
from app.models.item import Item
from app.models.office import Office
from app.models.section import Section
from app.models.store import Store
from app.repositories.indent import IndentRepository
from app.schemas.indent import IndentCreate


class IndentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = IndentRepository(session)

    async def create(self, payload: IndentCreate) -> Indent:
        fy = await self.session.get(FinancialYear, payload.financial_year_id)
        store = await self.session.get(Store, payload.store_id)
        office = await self.session.get(Office, payload.office_id)
        if fy is None:
            raise HTTPException(404, "Financial year not found")
        if store is None:
            raise HTTPException(404, "Store not found")
        if office is None:
            raise HTTPException(404, "Office not found")
        if fy.is_closed:
            raise HTTPException(409, "Financial year is closed")
        if not (fy.start_date <= payload.indent_date <= fy.end_date):
            raise HTTPException(422, "Indent date is outside the financial year")
        if payload.request_source not in {"PHYSICAL", "ONLINE"}:
            raise HTTPException(422, "request_source must be PHYSICAL or ONLINE")
        if payload.section_id is not None:
            section = await self.session.get(Section, payload.section_id)
            if section is None:
                raise HTTPException(404, "Section not found")
            if section.office_id != office.id:
                raise HTTPException(422, "Section does not belong to the selected office")

        seen: set[int] = set()
        lines: list[IndentLine] = []
        for line in payload.lines:
            if line.item_id in seen:
                raise HTTPException(422, f"Duplicate item {line.item_id} in indent")
            seen.add(line.item_id)
            item = await self.session.get(Item, line.item_id)
            if item is None or not item.is_active:
                raise HTTPException(404, f"Item {line.item_id} not found or inactive")
            category = await self.session.get(Category, item.category_id)
            if category is None:
                raise HTTPException(409, f"Item {item.code} has no valid category")
            if category.type != "CONSUMABLE":
                raise HTTPException(422, f"Manual stock issue currently supports consumables only: {item.code}")
            lines.append(
                IndentLine(
                    item_id=line.item_id,
                    requested_quantity=line.requested_quantity,
                    remarks=line.remarks,
                )
            )

        indent = Indent(
            indent_no=await self._next_number(),
            indent_date=payload.indent_date,
            received_date=date.today(),
            financial_year_id=payload.financial_year_id,
            store_id=payload.store_id,
            office_id=payload.office_id,
            section_id=payload.section_id,
            request_source=payload.request_source,
            request_type=payload.request_type,
            reference_no=payload.reference_no,
            reference_date=payload.reference_date,
            status="RECORDED",
            remarks=payload.remarks,
            lines=lines,
        )
        self.session.add(indent)
        await self.session.commit()
        await self.session.refresh(indent)
        return indent

    async def get(self, indent_id: int) -> Indent:
        indent = await self.repository.get(indent_id)
        if indent is None:
            raise HTTPException(404, "Indent not found")
        return indent

    async def list(self, store_id: int | None = None, status: str | None = None) -> list[Indent]:
        return await self.repository.list(store_id, status)

    async def _next_number(self) -> str:
        from sqlalchemy import text
        value = await self.session.scalar(text("SELECT nextval('indent_no_seq')"))
        return f"IND-{int(value):06d}"
