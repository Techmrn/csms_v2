from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.financial_year import FinancialYear
from app.models.store import Store
from app.models.unit import Unit
from app.paper_store.models.item import PaperItem
from app.paper_store.models.stock import PaperOpeningStock, PaperOpeningStockLine
from app.paper_store.schemas.opening import PaperOpeningStockCreate
from app.paper_store.services.stock import PaperStockService
from app.paper_store.services.units import calc_sheet_weight_kg, to_total_sheets
from app.services.authorization import AuthorizationService


class PaperOpeningService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.auth = AuthorizationService(session)
        self.stock_svc = PaperStockService(session)

    async def _next_opening_number(self, financial_year_id: int) -> str:
        prefix = f"POPN-{financial_year_id}-"
        existing = await self.session.scalars(
            select(PaperOpeningStock.opening_no)
            .where(PaperOpeningStock.opening_no.like(f"{prefix}%"))
            .order_by(PaperOpeningStock.opening_no.desc())
        )
        last = existing.first()
        next_number = 1
        if last:
            try:
                next_number = int(last.rsplit("-", 1)[1]) + 1
            except (ValueError, IndexError):
                next_number = 1
        return f"{prefix}{next_number:05d}"

    async def create_and_post(
        self, payload: PaperOpeningStockCreate, actor_id: int
    ) -> PaperOpeningStock:
        await self.auth.require_permission(actor_id, "PAPER_OPENING_CREATE")
        store = await self.auth.require_paper_warehouse(payload.store_id)
        await self.auth.require_store_assignment(actor_id, store.id)

        fy = await self.session.get(FinancialYear, payload.financial_year_id)
        if not fy:
            raise HTTPException(404, "Financial year not found")
        if fy.is_closed:
            raise HTTPException(409, "Financial year is closed")
        if not (fy.start_date <= payload.opening_date <= fy.end_date):
            raise HTTPException(422, "Opening date is outside the financial year")

        if not payload.lines:
            raise HTTPException(422, "At least one paper line item is required")

        requested_ids = [line.paper_item_id for line in payload.lines]
        existing_ids = set(
            (
                await self.session.scalars(
                    select(PaperOpeningStockLine.paper_item_id)
                    .join(
                        PaperOpeningStock,
                        PaperOpeningStock.id == PaperOpeningStockLine.opening_stock_id,
                    )
                    .where(
                        PaperOpeningStock.store_id == store.id,
                        PaperOpeningStock.financial_year_id == fy.id,
                        PaperOpeningStock.status == "POSTED",
                        PaperOpeningStockLine.paper_item_id.in_(requested_ids),
                    )
                )
            ).all()
        )
        if existing_ids:
            raise HTTPException(
                409,
                "Opening stock already exists for paper item(s) "
                + ", ".join(str(x) for x in sorted(existing_ids))
                + " for this warehouse and financial year. Each paper item can be opened only once.",
            )

        seen_items: set[int] = set()
        lines_to_create: list[PaperOpeningStockLine] = []
        for line_req in payload.lines:
            if line_req.paper_item_id in seen_items:
                raise HTTPException(422, f"Duplicate paper item {line_req.paper_item_id} in opening stock")
            seen_items.add(line_req.paper_item_id)

            item = await self.session.get(PaperItem, line_req.paper_item_id)
            if not item or not item.is_active:
                raise HTTPException(404, f"Paper item {line_req.paper_item_id} not found or inactive")

            unit = await self.session.get(Unit, line_req.unit_id or item.unit_id)
            if not unit:
                raise HTTPException(404, "Unit not found")

            spr = item.sheets_per_ream or 500
            if item.form_type == "SHEET":
                total_sh = to_total_sheets(line_req.reams, line_req.sheets, spr)
                if total_sh <= 0:
                    raise HTTPException(422, f"Opening Reams/Sheets must be positive for {item.name}")
                wt_kg = line_req.weight_kg
                if wt_kg == 0 and item.weight_per_ream_kg:
                    wt_kg = calc_sheet_weight_kg(total_sh, spr, item.weight_per_ream_kg)

                lines_to_create.append(
                    PaperOpeningStockLine(
                        store_id=store.id,
                        financial_year_id=fy.id,
                        paper_item_id=item.id,
                        unit_id=unit.id,
                        total_sheets=total_sh,
                        weight_kg=wt_kg,
                        reel_count=None,
                        remarks=line_req.remarks,
                    )
                )
            else:
                wt_kg = Decimal(str(line_req.weight_kg or 0))
                if wt_kg <= 0:
                    raise HTTPException(422, f"Opening Weight (KG) must be positive for reel paper {item.name}")
                lines_to_create.append(
                    PaperOpeningStockLine(
                        store_id=store.id,
                        financial_year_id=fy.id,
                        paper_item_id=item.id,
                        unit_id=unit.id,
                        total_sheets=0,
                        weight_kg=wt_kg,
                        reel_count=line_req.reel_count,
                        remarks=line_req.remarks,
                    )
                )

        opening_no = await self._next_opening_number(fy.id)
        posting_group_id = uuid4()
        now = datetime.now(timezone.utc)

        opening = PaperOpeningStock(
            opening_no=opening_no,
            opening_date=payload.opening_date,
            financial_year_id=fy.id,
            store_id=store.id,
            opening_type="INITIAL",
            source_financial_year_id=None,
            status="POSTED",
            remarks=payload.remarks,
            created_by=actor_id,
            posted_by=actor_id,
            posted_at=now,
            posting_group_id=posting_group_id,
            lines=lines_to_create,
        )
        self.session.add(opening)
        await self.session.flush()

        for line in opening.lines:
            await self.stock_svc.post_movement(
                financial_year_id=fy.id,
                store_id=store.id,
                paper_item_id=line.paper_item_id,
                movement_date=opening.opening_date,
                movement_type="OPENING",
                sheets_in=line.total_sheets,
                sheets_out=0,
                weight_kg_in=line.weight_kg,
                weight_kg_out=Decimal("0"),
                reference_type="PAPER_OPENING_STOCK_LINE",
                reference_id=line.id,
                reference_no=opening.opening_no,
                posting_group_id=posting_group_id,
                remarks=line.remarks or "Warehouse initial opening stock",
                created_by=actor_id,
            )

        await self.session.commit()
        return await self.get(opening.id)

    async def get(self, opening_id: int) -> PaperOpeningStock | None:
        stmt = (
            select(PaperOpeningStock)
            .options(
                selectinload(PaperOpeningStock.lines).selectinload(PaperOpeningStockLine.paper_item),
                selectinload(PaperOpeningStock.lines).selectinload(PaperOpeningStockLine.unit),
                selectinload(PaperOpeningStock.store).selectinload(Store.office),
                selectinload(PaperOpeningStock.financial_year),
                selectinload(PaperOpeningStock.source_financial_year),
            )
            .where(PaperOpeningStock.id == opening_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list(
        self, store_id: int | None = None, financial_year_id: int | None = None
    ) -> list[PaperOpeningStock]:
        stmt = (
            select(PaperOpeningStock)
            .options(
                selectinload(PaperOpeningStock.lines).selectinload(PaperOpeningStockLine.paper_item),
                selectinload(PaperOpeningStock.store).selectinload(Store.office),
                selectinload(PaperOpeningStock.financial_year),
            )
            .order_by(PaperOpeningStock.opening_date.desc(), PaperOpeningStock.id.desc())
        )
        if store_id is not None:
            stmt = stmt.where(PaperOpeningStock.store_id == store_id)
        if financial_year_id is not None:
            stmt = stmt.where(PaperOpeningStock.financial_year_id == financial_year_id)
        return list((await self.session.scalars(stmt)).all())

