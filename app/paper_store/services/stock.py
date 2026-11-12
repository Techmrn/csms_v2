from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.paper_store.models.item import PaperItem
from app.paper_store.models.stock import PaperStockAccount, PaperStockMovement
from app.paper_store.services.units import (
    format_paper_balance,
    from_total_sheets,
    sheets_to_decimal_reams,
)


class PaperStockService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def lock_paper_account(
        self, store_id: int, financial_year_id: int, paper_item_id: int
    ) -> PaperStockAccount:
        """Atomically ensures the PaperStockAccount exists and locks it with SELECT FOR UPDATE."""
        await self.session.execute(
            pg_insert(PaperStockAccount)
            .values(
                store_id=store_id,
                financial_year_id=financial_year_id,
                paper_item_id=paper_item_id,
            )
            .on_conflict_do_nothing(
                index_elements=["store_id", "financial_year_id", "paper_item_id"]
            )
        )
        account = await self.session.scalar(
            select(PaperStockAccount)
            .where(
                PaperStockAccount.store_id == store_id,
                PaperStockAccount.financial_year_id == financial_year_id,
                PaperStockAccount.paper_item_id == paper_item_id,
            )
            .with_for_update()
        )
        if account is None:
            raise HTTPException(status_code=500, detail="Unable to acquire lock on paper stock account")
        return account

    async def post_movement(
        self,
        *,
        financial_year_id: int,
        store_id: int,
        paper_item_id: int,
        movement_date: date,
        movement_type: str,
        sheets_in: int = 0,
        sheets_out: int = 0,
        weight_kg_in: Decimal = Decimal("0"),
        weight_kg_out: Decimal = Decimal("0"),
        quantity_in: Decimal | None = None,
        quantity_out: Decimal | None = None,
        reference_type: str,
        reference_id: int,
        reference_no: str | None = None,
        posting_group_id: UUID | None = None,
        remarks: str | None = None,
        created_by: int | None = None,
    ) -> PaperStockMovement:
        """Posts an immutable paper stock movement after locking the stock account."""
        await self.lock_paper_account(store_id, financial_year_id, paper_item_id)

        item = await self.session.get(PaperItem, paper_item_id)
        spr = item.sheets_per_ream if item and item.sheets_per_ream else 500
        if quantity_in is None:
            quantity_in = (
                sheets_to_decimal_reams(sheets_in, spr)
                if item and item.form_type == "SHEET"
                else Decimal(str(weight_kg_in or 0))
            )
        if quantity_out is None:
            quantity_out = (
                sheets_to_decimal_reams(sheets_out, spr)
                if item and item.form_type == "SHEET"
                else Decimal(str(weight_kg_out or 0))
            )

        movement = PaperStockMovement(
            financial_year_id=financial_year_id,
            store_id=store_id,
            paper_item_id=paper_item_id,
            movement_date=movement_date,
            movement_type=movement_type,
            quantity_in=quantity_in,
            quantity_out=quantity_out,
            sheets_in=int(sheets_in or 0),
            sheets_out=int(sheets_out or 0),
            weight_kg_in=Decimal(str(weight_kg_in or 0)),
            weight_kg_out=Decimal(str(weight_kg_out or 0)),
            reference_type=reference_type,
            reference_id=reference_id,
            reference_no=reference_no,
            posting_group_id=posting_group_id,
            remarks=remarks,
            created_by=created_by,
        )
        self.session.add(movement)
        return movement

    async def current_stock(
        self, store_id: int, financial_year_id: int, paper_item_id: int | None = None
    ) -> list[dict]:
        """Calculates FY-wise Opening, Inward, Outward, and Closing Paper Balances."""
        is_opening = PaperStockMovement.movement_type.in_(("OPENING", "CARRY_FORWARD"))

        open_sheets_expr = func.coalesce(
            func.sum(case((is_opening, PaperStockMovement.sheets_in), else_=0)), 0
        )
        in_sheets_expr = func.coalesce(
            func.sum(case((~is_opening, PaperStockMovement.sheets_in), else_=0)), 0
        )
        out_sheets_expr = func.coalesce(func.sum(PaperStockMovement.sheets_out), 0)

        open_wt_expr = func.coalesce(
            func.sum(case((is_opening, PaperStockMovement.weight_kg_in), else_=0)), 0
        )
        in_wt_expr = func.coalesce(
            func.sum(case((~is_opening, PaperStockMovement.weight_kg_in), else_=0)), 0
        )
        out_wt_expr = func.coalesce(func.sum(PaperStockMovement.weight_kg_out), 0)

        query = (
            select(
                PaperItem,
                open_sheets_expr.label("open_sheets"),
                in_sheets_expr.label("in_sheets"),
                out_sheets_expr.label("out_sheets"),
                open_wt_expr.label("open_wt"),
                in_wt_expr.label("in_wt"),
                out_wt_expr.label("out_wt"),
            )
            .options(selectinload(PaperItem.unit))
            .join(PaperStockMovement, PaperStockMovement.paper_item_id == PaperItem.id)
            .where(
                PaperStockMovement.store_id == store_id,
                PaperStockMovement.financial_year_id == financial_year_id,
            )
            .group_by(PaperItem.id)
            .order_by(PaperItem.name)
        )
        if paper_item_id is not None:
            query = query.where(PaperItem.id == paper_item_id)

        rows = (await self.session.execute(query)).all()
        result = []
        for item, o_sh, i_sh, out_sh, o_wt, i_wt, out_wt in rows:
            open_sh = int(o_sh or 0)
            in_sh = int(i_sh or 0)
            out_sh = int(out_sh or 0)
            bal_sh = open_sh + in_sh - out_sh

            open_wt = Decimal(str(o_wt or 0)).quantize(Decimal("0.001"))
            in_wt = Decimal(str(i_wt or 0)).quantize(Decimal("0.001"))
            out_wt = Decimal(str(out_wt or 0)).quantize(Decimal("0.001"))
            bal_wt = (open_wt + in_wt - out_wt).quantize(Decimal("0.001"))

            spr = item.sheets_per_ream or 500
            reams, loose_sheets = from_total_sheets(bal_sh, spr)

            result.append(
                {
                    "item": item,
                    "opening_sheets": open_sh,
                    "inward_sheets": in_sh,
                    "outward_sheets": out_sh,
                    "balance_sheets": bal_sh,
                    "balance_reams": reams,
                    "balance_loose_sheets": loose_sheets,
                    "opening_weight_kg": open_wt,
                    "inward_weight_kg": in_wt,
                    "outward_weight_kg": out_wt,
                    "balance_weight_kg": bal_wt,
                    "balance_qty": (
                        sheets_to_decimal_reams(bal_sh, spr)
                        if item.form_type == "SHEET"
                        else bal_wt
                    ),
                    "formatted_opening": format_paper_balance(item.form_type, open_sh, open_wt, spr),
                    "formatted_inward": format_paper_balance(item.form_type, in_sh, in_wt, spr),
                    "formatted_outward": format_paper_balance(item.form_type, out_sh, out_wt, spr),
                    "formatted_balance": format_paper_balance(item.form_type, bal_sh, bal_wt, spr),
                }
            )
        return result

    async def balance_for_item(
        self, store_id: int, financial_year_id: int, paper_item_id: int
    ) -> tuple[int, Decimal]:
        """Returns (balance_sheets, balance_weight_kg) for a specific paper item."""
        result = await self.session.execute(
            select(
                func.coalesce(func.sum(PaperStockMovement.sheets_in), 0)
                - func.coalesce(func.sum(PaperStockMovement.sheets_out), 0),
                func.coalesce(func.sum(PaperStockMovement.weight_kg_in), 0)
                - func.coalesce(func.sum(PaperStockMovement.weight_kg_out), 0),
            ).where(
                PaperStockMovement.store_id == store_id,
                PaperStockMovement.financial_year_id == financial_year_id,
                PaperStockMovement.paper_item_id == paper_item_id,
            )
        )
        row = result.first()
        if not row:
            return 0, Decimal("0.000")
        return int(row[0] or 0), Decimal(str(row[1] or 0)).quantize(Decimal("0.001"))
