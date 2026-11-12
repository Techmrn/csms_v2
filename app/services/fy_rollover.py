"""Financial Year closing balance carry-forward engine for both General Stores and Paper Warehouses."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.financial_year import FinancialYear
from app.models.item import Item
from app.models.stock import OpeningStock, OpeningStockLine, StockAccount, StockMovement
from app.models.store import Store
from app.paper_store.models.stock import (
    PaperOpeningStock,
    PaperOpeningStockLine,
    PaperStockMovement,
)
from app.paper_store.services.stock import PaperStockService
from app.services.authorization import AuthorizationService


class FinancialYearRolloverService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.auth = AuthorizationService(session)

    async def next_open_fy(self, source_fy: FinancialYear) -> FinancialYear | None:
        return await self.session.scalar(
            select(FinancialYear)
            .where(
                FinancialYear.start_date > source_fy.end_date,
                FinancialYear.is_closed.is_(False),
            )
            .order_by(FinancialYear.start_date.asc())
            .limit(1)
        )

    async def previous_fy(self, target_fy: FinancialYear) -> FinancialYear | None:
        return await self.session.scalar(
            select(FinancialYear)
            .where(FinancialYear.end_date < target_fy.start_date)
            .order_by(FinancialYear.end_date.desc())
            .limit(1)
        )

    async def carry_forward(
        self,
        source_fy_id: int,
        target_fy_id: int,
        actor_id: int,
    ) -> dict[str, int]:
        """Carries forward positive closing balances from source_fy into target_fy idempotently.

        Applies uniformly to:
        1. General Store consumables (Assets remain continuous outside FY stock ledger).
        2. Paper Warehouse commodities (Sheet Reams+Sheets and Reel Weight KG).
        """
        source_fy = await self.session.get(FinancialYear, source_fy_id)
        target_fy = await self.session.get(FinancialYear, target_fy_id)
        if not source_fy or not target_fy:
            raise HTTPException(404, "Financial year not found")
        if target_fy.is_closed:
            raise HTTPException(409, "Target financial year is closed")
        if source_fy.end_date >= target_fy.start_date:
            raise HTTPException(422, "Source financial year must precede target financial year")

        now = datetime.now(timezone.utc)
        general_count = 0
        paper_count = 0

        # 1. Carry forward General Store Consumables
        gen_stores = list(
            (
                await self.session.scalars(
                    select(Store)
                    .where(Store.is_active.is_(True), Store.store_type != "PAPER_WAREHOUSE")
                    .order_by(Store.id)
                )
            ).all()
        )
        for store in gen_stores:
            # Query consumable net closing balance in source_fy
            bal_expr = func.coalesce(func.sum(StockMovement.quantity_in), 0) - func.coalesce(
                func.sum(StockMovement.quantity_out), 0
            )
            src_rows = (
                await self.session.execute(
                    select(Item, bal_expr.label("balance"))
                    .join(StockMovement, StockMovement.item_id == Item.id)
                    .join(Category, Category.id == Item.category_id)
                    .where(
                        StockMovement.store_id == store.id,
                        StockMovement.financial_year_id == source_fy.id,
                        Category.type == "CONSUMABLE",
                    )
                    .group_by(Item.id)
                    .having(bal_expr > 0)
                )
            ).all()
            if not src_rows:
                continue

            existing_target_items = set(
                (
                    await self.session.scalars(
                        select(StockMovement.item_id)
                        .where(
                            StockMovement.store_id == store.id,
                            StockMovement.financial_year_id == target_fy.id,
                            StockMovement.movement_type.in_(("OPENING", "CARRY_FORWARD")),
                        )
                        .distinct()
                    )
                ).all()
            )
            lines_to_add: list[tuple[OpeningStockLine, Decimal]] = []
            for item, bal in src_rows:
                if item.id in existing_target_items:
                    continue
                qty = Decimal(str(bal)).quantize(Decimal("0.001"))
                if qty <= 0:
                    continue
                lines_to_add.append(
                    (
                        OpeningStockLine(
                            store_id=store.id,
                            financial_year_id=target_fy.id,
                            item_id=item.id,
                            quantity=qty,
                            unit_id=item.unit_id,
                            remarks=f"Carry-forward closing balance from FY {source_fy.year_name}",
                        ),
                        qty,
                    )
                )

            if lines_to_add:
                group_id = uuid4()
                opening_no = f"CF-{source_fy.year_name}-{target_fy.year_name}-S{store.id}"
                # Ensure unique opening_no if partial subsequent carry-forward runs
                existing_op = await self.session.scalar(
                    select(OpeningStock.id).where(OpeningStock.opening_no == opening_no).limit(1)
                )
                if existing_op is not None:
                    opening_no = f"{opening_no}-{uuid4().hex[:4].upper()}"

                opening = OpeningStock(
                    opening_no=opening_no,
                    opening_date=target_fy.start_date,
                    financial_year_id=target_fy.id,
                    store_id=store.id,
                    opening_type="CARRY_FORWARD",
                    source_financial_year_id=source_fy.id,
                    status="POSTED",
                    remarks=f"Auto carry-forward from FY {source_fy.year_name}",
                    created_by=actor_id,
                    posted_by=actor_id,
                    posted_at=now,
                    posting_group_id=group_id,
                    lines=[row[0] for row in lines_to_add],
                )
                self.session.add(opening)
                await self.session.flush()

                for line, qty in lines_to_add:
                    await self.session.execute(
                        pg_insert(StockAccount)
                        .values(
                            store_id=store.id,
                            financial_year_id=target_fy.id,
                            item_id=line.item_id,
                        )
                        .on_conflict_do_nothing(
                            index_elements=["store_id", "financial_year_id", "item_id"]
                        )
                    )
                    await self.session.scalar(
                        select(StockAccount)
                        .where(
                            StockAccount.store_id == store.id,
                            StockAccount.financial_year_id == target_fy.id,
                            StockAccount.item_id == line.item_id,
                        )
                        .with_for_update()
                    )
                    self.session.add(
                        StockMovement(
                            financial_year_id=target_fy.id,
                            store_id=store.id,
                            item_id=line.item_id,
                            movement_date=target_fy.start_date,
                            movement_type="CARRY_FORWARD",
                            quantity_in=qty,
                            quantity_out=Decimal("0"),
                            reference_type="OPENING_STOCK_LINE",
                            reference_id=line.id,
                            reference_no=opening.opening_no,
                            posting_group_id=group_id,
                            remarks=f"Carry-forward from {source_fy.year_name}",
                            created_by=actor_id,
                        )
                    )
                    general_count += 1

        # 2. Carry forward Paper Warehouse Stock
        paper_svc = PaperStockService(self.session)
        paper_warehouses = list(
            (
                await self.session.scalars(
                    select(Store)
                    .where(Store.is_active.is_(True), Store.store_type == "PAPER_WAREHOUSE")
                    .order_by(Store.id)
                )
            ).all()
        )
        for wh in paper_warehouses:
            stock_rows = await paper_svc.current_stock(wh.id, source_fy.id)
            if not stock_rows:
                continue

            existing_paper_items = set(
                (
                    await self.session.scalars(
                        select(PaperStockMovement.paper_item_id)
                        .where(
                            PaperStockMovement.store_id == wh.id,
                            PaperStockMovement.financial_year_id == target_fy.id,
                            PaperStockMovement.movement_type.in_(("OPENING", "CARRY_FORWARD")),
                        )
                        .distinct()
                    )
                ).all()
            )
            p_lines_to_add: list[PaperOpeningStockLine] = []
            for row in stock_rows:
                item = row["item"]
                if item.id in existing_paper_items:
                    continue
                sh = int(row["balance_sheets"] or 0)
                wt = Decimal(str(row["balance_weight_kg"] or 0)).quantize(Decimal("0.001"))
                has_stock = (item.form_type == "SHEET" and sh > 0) or (item.form_type == "REEL" and wt > 0)
                if not has_stock:
                    continue

                p_lines_to_add.append(
                    PaperOpeningStockLine(
                        store_id=wh.id,
                        financial_year_id=target_fy.id,
                        paper_item_id=item.id,
                        unit_id=item.unit_id,
                        total_sheets=sh if item.form_type == "SHEET" else 0,
                        weight_kg=wt,
                        remarks=f"Carry-forward closing balance from FY {source_fy.year_name}",
                    )
                )

            if p_lines_to_add:
                p_group_id = uuid4()
                p_opening_no = f"PCF-{source_fy.year_name}-{target_fy.year_name}-W{wh.id}"
                existing_pop = await self.session.scalar(
                    select(PaperOpeningStock.id).where(PaperOpeningStock.opening_no == p_opening_no).limit(1)
                )
                if existing_pop is not None:
                    p_opening_no = f"{p_opening_no}-{uuid4().hex[:4].upper()}"

                p_opening = PaperOpeningStock(
                    opening_no=p_opening_no,
                    opening_date=target_fy.start_date,
                    financial_year_id=target_fy.id,
                    store_id=wh.id,
                    opening_type="CARRY_FORWARD",
                    source_financial_year_id=source_fy.id,
                    status="POSTED",
                    remarks=f"Auto carry-forward from FY {source_fy.year_name}",
                    created_by=actor_id,
                    posted_by=actor_id,
                    posted_at=now,
                    posting_group_id=p_group_id,
                    lines=p_lines_to_add,
                )
                self.session.add(p_opening)
                await self.session.flush()

                for p_line in p_opening.lines:
                    await paper_svc.post_movement(
                        financial_year_id=target_fy.id,
                        store_id=wh.id,
                        paper_item_id=p_line.paper_item_id,
                        movement_date=target_fy.start_date,
                        movement_type="CARRY_FORWARD",
                        sheets_in=p_line.total_sheets,
                        sheets_out=0,
                        weight_kg_in=p_line.weight_kg,
                        weight_kg_out=Decimal("0"),
                        reference_type="PAPER_OPENING_STOCK_LINE",
                        reference_id=p_line.id,
                        reference_no=p_opening.opening_no,
                        posting_group_id=p_group_id,
                        remarks=f"Carry-forward from {source_fy.year_name}",
                        created_by=actor_id,
                    )
                    paper_count += 1

        await self.session.flush()
        return {"general_items_carried": general_count, "paper_items_carried": paper_count}

