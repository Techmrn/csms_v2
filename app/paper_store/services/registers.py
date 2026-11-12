"""Dedicated operational registers for the Paper Warehouse module."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_year import FinancialYear
from app.models.section import Section
from app.models.store import Store
from app.paper_store.models.indent_issue import PaperIndent, PaperIssue, PaperIssueLine
from app.paper_store.models.item import PaperItem
from app.paper_store.models.receipt import PaperReceipt, PaperReceiptLine
from app.paper_store.models.stock import (
    PaperOpeningStock,
    PaperOpeningStockLine,
    PaperStockMovement,
)
from app.paper_store.models.transfer import PaperTransfer, PaperTransferLine
from app.paper_store.services.stock import PaperStockService
from app.paper_store.services.units import format_paper_balance
from app.services.authorization import AuthorizationService


class PaperRegisterService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.auth = AuthorizationService(session)
        self.stock_svc = PaperStockService(session)

    async def _warehouse_scope(
        self, actor_id: int, store_id: int | None = None
    ) -> list[int]:
        await self.auth.require_permission(actor_id, "PAPER_REGISTER_VIEW")
        visible = await self.auth.get_visible_paper_warehouses(actor_id)
        if store_id is not None:
            wh = await self.auth.require_paper_warehouse(store_id)
            if wh.id not in visible:
                raise HTTPException(403, "User is not authorized to view this Paper Warehouse")
            return [wh.id]
        return visible

    async def stock_register(
        self,
        actor_id: int,
        store_id: int,
        financial_year_id: int,
        search: str | None = None,
    ) -> list[dict]:
        await self._warehouse_scope(actor_id, store_id)
        rows = await self.stock_svc.current_stock(store_id, financial_year_id)
        out = []
        term = (search or "").strip().lower()
        for r in rows:
            item: PaperItem = r["item"]
            if term and term not in item.code.lower() and term not in item.name.lower() and term not in item.paper_type.lower():
                continue
            out.append({
                "item_id": item.id,
                "code": item.code,
                "name": item.name,
                "paper_type": item.paper_type,
                "form_type": item.form_type,
                "gsm": item.gsm,
                "sheets_per_ream": item.sheets_per_ream,
                "opening": r["formatted_opening"],
                "inward": r["formatted_inward"],
                "outward": r["formatted_outward"],
                "closing": r["formatted_balance"],
                "weight_kg": f"{r['balance_weight_kg']:.3f}",
            })
        return out

    async def receipt_register(
        self,
        actor_id: int,
        store_id: int | None = None,
        financial_year_id: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        search: str | None = None,
    ) -> list[dict]:
        scoped = await self._warehouse_scope(actor_id, store_id)
        if not scoped:
            return []
        stmt = (
            select(PaperReceiptLine, PaperReceipt, Store, PaperItem)
            .join(PaperReceipt, PaperReceipt.id == PaperReceiptLine.paper_receipt_id)
            .join(Store, Store.id == PaperReceipt.store_id)
            .join(PaperItem, PaperItem.id == PaperReceiptLine.paper_item_id)
            .where(PaperReceipt.store_id.in_(scoped))
        )
        if financial_year_id is not None:
            stmt = stmt.where(PaperReceipt.financial_year_id == financial_year_id)
        if from_date is not None:
            stmt = stmt.where(PaperReceipt.receipt_date >= from_date)
        if to_date is not None:
            stmt = stmt.where(PaperReceipt.receipt_date <= to_date)
        if search:
            t = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    PaperReceipt.receipt_no.ilike(t),
                    PaperReceipt.challan_no.ilike(t),
                    PaperReceipt.source_depot.ilike(t),
                    PaperItem.code.ilike(t),
                    PaperItem.name.ilike(t),
                )
            )
        stmt = stmt.order_by(PaperReceipt.receipt_date.desc(), PaperReceipt.id.desc()).limit(1000)
        res = (await self.session.execute(stmt)).all()
        rows = []
        for line, rec, store, item in res:
            spr = item.sheets_per_ream or 500
            rows.append({
                "receipt_id": rec.id,
                "receipt_no": rec.receipt_no,
                "receipt_date": rec.receipt_date,
                "warehouse_name": store.name,
                "source_depot": rec.source_depot,
                "challan_no": rec.challan_no or "—",
                "item_code": item.code,
                "item_name": item.name,
                "form_type": item.form_type,
                "accepted": format_paper_balance(item.form_type, line.accepted_sheets, line.weight_kg, spr),
                "damaged": format_paper_balance(item.form_type, line.damaged_sheets, Decimal(str(line.damaged_quantity or 0)), spr),
                "weight_kg": f"{line.weight_kg:.3f}",
            })
        return rows

    async def issue_register(
        self,
        actor_id: int,
        store_id: int | None = None,
        financial_year_id: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        search: str | None = None,
    ) -> list[dict]:
        scoped = await self._warehouse_scope(actor_id, store_id)
        if not scoped:
            return []
        stmt = (
            select(PaperIssueLine, PaperIssue, PaperIndent, Store, Section, PaperItem)
            .join(PaperIssue, PaperIssue.id == PaperIssueLine.issue_id)
            .join(PaperIndent, PaperIndent.id == PaperIssue.indent_id)
            .join(Store, Store.id == PaperIssue.store_id)
            .join(Section, Section.id == PaperIssue.section_id)
            .join(PaperItem, PaperItem.id == PaperIssueLine.paper_item_id)
            .where(PaperIssue.store_id.in_(scoped))
        )
        if financial_year_id is not None:
            stmt = stmt.where(PaperIssue.financial_year_id == financial_year_id)
        if from_date is not None:
            stmt = stmt.where(PaperIssue.issue_date >= from_date)
        if to_date is not None:
            stmt = stmt.where(PaperIssue.issue_date <= to_date)
        if search:
            t = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    PaperIssue.issue_no.ilike(t),
                    PaperIndent.indent_no.ilike(t),
                    PaperIssue.job_no.ilike(t),
                    Section.name.ilike(t),
                    PaperItem.code.ilike(t),
                    PaperItem.name.ilike(t),
                )
            )
        stmt = stmt.order_by(PaperIssue.issue_date.desc(), PaperIssue.id.desc()).limit(1000)
        res = (await self.session.execute(stmt)).all()
        rows = []
        for line, iss, ind, store, sec, item in res:
            spr = item.sheets_per_ream or 500
            rows.append({
                "indent_id": ind.id,
                "issue_no": iss.issue_no,
                "issue_date": iss.issue_date,
                "warehouse_name": store.name,
                "section_name": sec.name,
                "job_no": iss.job_no or "—",
                "indent_no": ind.indent_no,
                "item_code": item.code,
                "item_name": item.name,
                "form_type": item.form_type,
                "issued": format_paper_balance(item.form_type, line.sheets, line.weight_kg, spr),
                "weight_kg": f"{line.weight_kg:.3f}",
            })
        return rows

    async def transfer_register(
        self,
        actor_id: int,
        store_id: int | None = None,
        financial_year_id: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        search: str | None = None,
    ) -> list[dict]:
        scoped = await self._warehouse_scope(actor_id, store_id)
        if not scoped:
            return []
        stores_map = {s.id: s.name for s in (await self.session.scalars(select(Store))).all()}
        stmt = (
            select(PaperTransferLine, PaperTransfer, PaperItem)
            .join(PaperTransfer, PaperTransfer.id == PaperTransferLine.transfer_id)
            .join(PaperItem, PaperItem.id == PaperTransferLine.paper_item_id)
            .where(
                or_(
                    PaperTransfer.source_store_id.in_(scoped),
                    PaperTransfer.destination_store_id.in_(scoped),
                )
            )
        )
        if financial_year_id is not None:
            stmt = stmt.where(PaperTransfer.financial_year_id == financial_year_id)
        if from_date is not None:
            stmt = stmt.where(PaperTransfer.transfer_date >= from_date)
        if to_date is not None:
            stmt = stmt.where(PaperTransfer.transfer_date <= to_date)
        if search:
            t = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    PaperTransfer.transfer_no.ilike(t),
                    PaperTransfer.gate_pass_no.ilike(t),
                    PaperItem.code.ilike(t),
                    PaperItem.name.ilike(t),
                )
            )
        stmt = stmt.order_by(PaperTransfer.transfer_date.desc(), PaperTransfer.id.desc()).limit(1000)
        res = (await self.session.execute(stmt)).all()
        rows = []
        for line, trf, item in res:
            spr = item.sheets_per_ream or 500
            rows.append({
                "transfer_id": trf.id,
                "transfer_no": trf.transfer_no,
                "transfer_date": trf.transfer_date,
                "transfer_mode": trf.transfer_mode,
                "source_warehouse": stores_map.get(trf.source_store_id, str(trf.source_store_id)),
                "destination_warehouse": stores_map.get(trf.destination_store_id, str(trf.destination_store_id)),
                "gate_pass_no": trf.gate_pass_no or "—",
                "status": trf.status,
                "item_code": item.code,
                "item_name": item.name,
                "dispatched": format_paper_balance(item.form_type, line.dispatched_sheets, line.dispatched_weight_kg, spr),
                "received": format_paper_balance(item.form_type, line.received_sheets, line.received_weight_kg, spr),
            })
        return rows

    async def opening_register(
        self,
        actor_id: int,
        store_id: int | None = None,
        financial_year_id: int | None = None,
        search: str | None = None,
    ) -> list[dict]:
        scoped = await self._warehouse_scope(actor_id, store_id)
        if not scoped:
            return []
        stmt = (
            select(PaperOpeningStockLine, PaperOpeningStock, Store, FinancialYear, PaperItem)
            .join(PaperOpeningStock, PaperOpeningStock.id == PaperOpeningStockLine.opening_stock_id)
            .join(Store, Store.id == PaperOpeningStock.store_id)
            .join(FinancialYear, FinancialYear.id == PaperOpeningStock.financial_year_id)
            .join(PaperItem, PaperItem.id == PaperOpeningStockLine.paper_item_id)
            .where(PaperOpeningStock.store_id.in_(scoped))
        )
        if financial_year_id is not None:
            stmt = stmt.where(PaperOpeningStock.financial_year_id == financial_year_id)
        if search:
            t = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    PaperOpeningStock.opening_no.ilike(t),
                    PaperItem.code.ilike(t),
                    PaperItem.name.ilike(t),
                )
            )
        stmt = stmt.order_by(PaperOpeningStock.opening_date.desc(), PaperOpeningStock.id.desc()).limit(1000)
        res = (await self.session.execute(stmt)).all()
        rows = []
        for line, op, store, fy, item in res:
            spr = item.sheets_per_ream or 500
            rows.append({
                "opening_id": op.id,
                "opening_no": op.opening_no,
                "opening_date": op.opening_date,
                "opening_type": op.opening_type,
                "warehouse_name": store.name,
                "fy_name": fy.year_name,
                "item_code": item.code,
                "item_name": item.name,
                "form_type": item.form_type,
                "opening_qty": format_paper_balance(item.form_type, line.total_sheets, line.weight_kg, spr),
                "weight_kg": f"{line.weight_kg:.3f}",
            })
        return rows

    async def ledger_register(
        self,
        actor_id: int,
        store_id: int | None = None,
        financial_year_id: int | None = None,
        paper_item_id: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        search: str | None = None,
    ) -> list[dict]:
        scoped = await self._warehouse_scope(actor_id, store_id)
        if not scoped:
            return []
        stmt = (
            select(PaperStockMovement, Store, PaperItem)
            .join(Store, Store.id == PaperStockMovement.store_id)
            .join(PaperItem, PaperItem.id == PaperStockMovement.paper_item_id)
            .where(PaperStockMovement.store_id.in_(scoped))
        )
        if financial_year_id is not None:
            stmt = stmt.where(PaperStockMovement.financial_year_id == financial_year_id)
        if paper_item_id is not None:
            stmt = stmt.where(PaperStockMovement.paper_item_id == paper_item_id)
        if from_date is not None:
            stmt = stmt.where(PaperStockMovement.movement_date >= from_date)
        if to_date is not None:
            stmt = stmt.where(PaperStockMovement.movement_date <= to_date)
        if search:
            t = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    PaperStockMovement.reference_no.ilike(t),
                    PaperStockMovement.movement_type.ilike(t),
                    PaperItem.code.ilike(t),
                    PaperItem.name.ilike(t),
                )
            )
        stmt = stmt.order_by(PaperStockMovement.movement_date.desc(), PaperStockMovement.id.desc()).limit(1000)
        res = (await self.session.execute(stmt)).all()
        rows = []
        for mv, store, item in res:
            spr = item.sheets_per_ream or 500
            rows.append({
                "id": mv.id,
                "movement_date": mv.movement_date,
                "movement_type": mv.movement_type,
                "warehouse_name": store.name,
                "item_code": item.code,
                "item_name": item.name,
                "form_type": item.form_type,
                "inward": format_paper_balance(item.form_type, mv.sheets_in, mv.weight_kg_in, spr) if (mv.sheets_in or mv.weight_kg_in) else "—",
                "outward": format_paper_balance(item.form_type, mv.sheets_out, mv.weight_kg_out, spr) if (mv.sheets_out or mv.weight_kg_out) else "—",
                "reference_no": mv.reference_no or mv.reference_type,
                "remarks": mv.remarks or "—",
            })
        return rows

