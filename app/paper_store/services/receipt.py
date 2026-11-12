from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_year import FinancialYear
from app.models.store import Store
from app.models.unit import Unit
from app.paper_store.models.item import PaperItem
from app.paper_store.models.receipt import PaperReceipt, PaperReceiptLine
from app.paper_store.repositories.receipt import PaperReceiptRepository
from app.paper_store.schemas.receipt import PaperReceiptCreate
from app.paper_store.services.stock import PaperStockService
from app.paper_store.services.units import (
    calc_sheet_weight_kg,
    decimal_reams_to_sheets,
    sheets_to_decimal_reams,
    to_total_sheets,
)
from app.services.authorization import AuthorizationService


class PaperReceiptService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.auth = AuthorizationService(session)
        self.repo = PaperReceiptRepository(session)
        self.stock_svc = PaperStockService(session)

    async def _financial_year_for_date(self, receipt_date) -> FinancialYear:
        stmt = select(FinancialYear).where(
            FinancialYear.start_date <= receipt_date,
            FinancialYear.end_date >= receipt_date,
        )
        fy = (await self.session.execute(stmt)).scalar_one_or_none()
        if fy is None:
            raise HTTPException(422, "No financial year matches receipt date")
        if fy.is_closed:
            raise HTTPException(409, "Financial year is closed")
        return fy

    async def create_and_post(self, payload: PaperReceiptCreate, actor_id: int) -> PaperReceipt:
        await self.auth.require_permission(actor_id, "PAPER_RECEIPT_CREATE")
        await self.auth.require_permission(actor_id, "PAPER_RECEIPT_POST")

        store = await self.auth.require_paper_warehouse(payload.store_id)
        await self.auth.require_store_assignment(actor_id, store.id)

        if payload.financial_year_id:
            fy = await self.session.get(FinancialYear, payload.financial_year_id)
            if not fy:
                raise HTTPException(404, "Financial year not found")
            if fy.is_closed:
                raise HTTPException(409, "Financial year is closed")
            if not (fy.start_date <= payload.receipt_date <= fy.end_date):
                raise HTTPException(422, "Receipt date outside specified financial year")
        else:
            fy = await self._financial_year_for_date(payload.receipt_date)

        if not payload.lines:
            raise HTTPException(422, "At least one paper line item is required")

        lines_to_create = []
        for line_req in payload.lines:
            item = await self.session.get(PaperItem, line_req.paper_item_id)
            if not item or not item.is_active:
                raise HTTPException(404, f"Paper item {line_req.paper_item_id} not found or inactive")

            unit_id = line_req.unit_id or item.unit_id
            unit = await self.session.get(Unit, unit_id)
            if not unit:
                raise HTTPException(404, f"Unit {unit_id} not found")

            spr = item.sheets_per_ream or 500
            if item.form_type == "SHEET":
                chal_sh = (
                    to_total_sheets(line_req.challan_reams, line_req.challan_sheets, spr)
                    if (line_req.challan_reams or line_req.challan_sheets)
                    else decimal_reams_to_sheets(line_req.challan_quantity, spr)
                )
                rec_sh = (
                    to_total_sheets(line_req.received_reams, line_req.received_sheets, spr)
                    if (line_req.received_reams or line_req.received_sheets)
                    else decimal_reams_to_sheets(line_req.received_quantity, spr)
                )
                acc_sh = (
                    to_total_sheets(line_req.accepted_reams, line_req.accepted_sheets, spr)
                    if (line_req.accepted_reams or line_req.accepted_sheets)
                    else decimal_reams_to_sheets(line_req.accepted_quantity, spr)
                )
                dmg_sh = (
                    to_total_sheets(line_req.damaged_reams, line_req.damaged_sheets, spr)
                    if (line_req.damaged_reams or line_req.damaged_sheets)
                    else decimal_reams_to_sheets(line_req.damaged_quantity, spr)
                )

                if rec_sh <= 0:
                    raise HTTPException(422, f"Received Reams/Sheets must be positive for {item.name}")
                if acc_sh < 0 or dmg_sh < 0:
                    raise HTTPException(422, "Accepted and damaged quantities cannot be negative")
                if acc_sh + dmg_sh > rec_sh:
                    raise HTTPException(422, "Sum of accepted and damaged quantity exceeds received quantity")

                wt_kg = line_req.weight_kg
                if wt_kg == 0 and item.weight_per_ream_kg:
                    wt_kg = calc_sheet_weight_kg(acc_sh, spr, item.weight_per_ream_kg)

                lines_to_create.append(
                    PaperReceiptLine(
                        paper_item_id=item.id,
                        unit_id=unit.id,
                        challan_quantity=sheets_to_decimal_reams(chal_sh, spr),
                        received_quantity=sheets_to_decimal_reams(rec_sh, spr),
                        accepted_quantity=sheets_to_decimal_reams(acc_sh, spr),
                        damaged_quantity=sheets_to_decimal_reams(dmg_sh, spr),
                        challan_sheets=chal_sh,
                        received_sheets=rec_sh,
                        accepted_sheets=acc_sh,
                        damaged_sheets=dmg_sh,
                        weight_kg=wt_kg,
                        reel_count=None,
                        reel_numbers=None,
                        remarks=line_req.remarks,
                    )
                )
            else:
                # REEL paper tracked strictly in KG
                wt_kg = Decimal(str(line_req.weight_kg or line_req.accepted_quantity or line_req.received_quantity or 0))
                if wt_kg <= 0:
                    raise HTTPException(422, f"Weight (KG) must be positive for reel paper {item.name}")
                chal_qty = Decimal(str(line_req.challan_quantity or wt_kg))
                rec_qty = Decimal(str(line_req.received_quantity or wt_kg))
                acc_qty = Decimal(str(line_req.accepted_quantity if line_req.accepted_quantity is not None else wt_kg))
                dmg_qty = Decimal(str(line_req.damaged_quantity or 0))
                if acc_qty + dmg_qty > rec_qty:
                    raise HTTPException(422, "Sum of accepted and damaged weight exceeds received weight")

                lines_to_create.append(
                    PaperReceiptLine(
                        paper_item_id=item.id,
                        unit_id=unit.id,
                        challan_quantity=chal_qty,
                        received_quantity=rec_qty,
                        accepted_quantity=acc_qty,
                        damaged_quantity=dmg_qty,
                        challan_sheets=0,
                        received_sheets=0,
                        accepted_sheets=0,
                        damaged_sheets=0,
                        weight_kg=wt_kg,
                        reel_count=line_req.reel_count,
                        reel_numbers=line_req.reel_numbers,
                        remarks=line_req.remarks,
                    )
                )

        receipt_no = await self.repo.next_receipt_number(fy)
        posting_group_id = uuid4()
        now = datetime.now(timezone.utc)

        receipt = PaperReceipt(
            receipt_no=receipt_no,
            receipt_date=payload.receipt_date,
            financial_year_id=fy.id,
            store_id=store.id,
            source_depot=payload.source_depot.strip(),
            allotment_no=payload.allotment_no.strip() if payload.allotment_no else None,
            allotment_date=payload.allotment_date,
            challan_no=payload.challan_no.strip() if payload.challan_no else None,
            challan_date=payload.challan_date,
            vehicle_no=payload.vehicle_no.strip() if payload.vehicle_no else None,
            carrier_name=payload.carrier_name.strip() if payload.carrier_name else None,
            lorry_receipt_no=payload.lorry_receipt_no.strip() if payload.lorry_receipt_no else None,
            status="POSTED",
            remarks=payload.remarks,
            created_by=actor_id,
            posted_by=actor_id,
            posted_at=now,
            posting_group_id=posting_group_id,
            lines=lines_to_create,
        )
        self.session.add(receipt)
        await self.session.flush()

        for line in lines_to_create:
            if line.accepted_sheets > 0 or line.weight_kg > 0:
                await self.stock_svc.post_movement(
                    financial_year_id=fy.id,
                    store_id=store.id,
                    paper_item_id=line.paper_item_id,
                    movement_date=receipt.receipt_date,
                    movement_type="RECEIPT_STATIONERY",
                    sheets_in=line.accepted_sheets,
                    sheets_out=0,
                    weight_kg_in=line.weight_kg,
                    weight_kg_out=Decimal("0"),
                    reference_type="PAPER_RECEIPT",
                    reference_id=receipt.id,
                    reference_no=receipt.receipt_no,
                    posting_group_id=posting_group_id,
                    remarks=f"Stationery Dept DC: {receipt.challan_no or 'N/A'}",
                    created_by=actor_id,
                )

        await self.session.commit()
        return await self.repo.get(receipt.id)
