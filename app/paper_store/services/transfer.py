from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.financial_year import FinancialYear
from app.models.store import Store
from app.models.unit import Unit
from app.paper_store.models.item import PaperItem
from app.paper_store.models.transfer import PaperTransfer, PaperTransferLine
from app.paper_store.schemas.transfer import (
    PaperTransferCreateRequest,
    PaperTransferDispatchRequest,
    PaperTransferReceiveRequest,
)
from app.paper_store.services.stock import PaperStockService
from app.paper_store.services.units import (
    calc_sheet_weight_kg,
    decimal_reams_to_sheets,
    format_paper_balance,
    sheets_to_decimal_reams,
    to_total_sheets,
)
from app.services.authorization import AuthorizationService


class PaperTransferService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.auth = AuthorizationService(session)
        self.stock_svc = PaperStockService(session)

    async def _financial_year_for_date(self, target_date: date) -> FinancialYear:
        stmt = select(FinancialYear).where(
            FinancialYear.start_date <= target_date,
            FinancialYear.end_date >= target_date,
        )
        fy = (await self.session.execute(stmt)).scalar_one_or_none()
        if fy is None:
            raise HTTPException(422, "No financial year matches date")
        if fy.is_closed:
            raise HTTPException(409, "Financial year is closed")
        return fy

    async def _next_transfer_number(self, fy: FinancialYear) -> str:
        prefix = f"PTR-{fy.year_name}-"
        last_num = await self.session.scalar(
            select(func.max(PaperTransfer.transfer_no)).where(
                PaperTransfer.financial_year_id == fy.id,
                PaperTransfer.transfer_no.like(f"{prefix}%"),
            )
        )
        if not last_num:
            return f"{prefix}0001"
        try:
            seq = int(last_num.replace(prefix, "")) + 1
        except ValueError:
            seq = 1
        return f"{prefix}{seq:04d}"

    async def create(
        self, payload: PaperTransferCreateRequest, actor_id: int
    ) -> PaperTransfer:
        if payload.source_store_id == payload.destination_store_id:
            raise HTTPException(422, "Source and destination paper warehouses must be different")

        source_store = await self.auth.require_paper_warehouse(payload.source_store_id)
        dest_store = await self.auth.require_paper_warehouse(payload.destination_store_id)

        transfer_mode = (payload.transfer_mode or "PULL").upper()
        if transfer_mode not in ("PULL", "PUSH"):
            raise HTTPException(422, "transfer_mode must be PULL or PUSH")

        now = datetime.now(timezone.utc)
        fy = await (
            self.session.get(FinancialYear, payload.financial_year_id)
            if payload.financial_year_id
            else self._financial_year_for_date(payload.transfer_date)
        )
        if not fy:
            raise HTTPException(404, "Financial year not found")
        if fy.is_closed:
            raise HTTPException(409, "Financial year is closed")

        if transfer_mode == "PUSH":
            await self.auth.require_permission(actor_id, "PAPER_TRANSFER_DIRECTIVE")
            initial_status = "DIRECTORATE_DIRECTIVE"
            dir_approved_by = actor_id
            dir_approved_at = now
        else:
            await self.auth.require_permission(actor_id, "PAPER_TRANSFER_CREATE")
            await self.auth.require_store_assignment(actor_id, dest_store.id)
            initial_status = "SUBMITTED"
            dir_approved_by = None
            dir_approved_at = None

        if not payload.lines:
            raise HTTPException(422, "At least one paper line item is required")

        transfer_no = await self._next_transfer_number(fy)
        lines = []
        for line_req in payload.lines:
            item = await self.session.get(PaperItem, line_req.paper_item_id)
            if not item or not item.is_active:
                raise HTTPException(404, f"Paper item {line_req.paper_item_id} not found")
            unit = await self.session.get(Unit, line_req.unit_id or item.unit_id)
            if not unit:
                raise HTTPException(404, "Unit not found")

            spr = item.sheets_per_ream or 500
            if item.form_type == "SHEET":
                req_sh = (
                    to_total_sheets(line_req.requested_reams, line_req.requested_sheets, spr)
                    if (line_req.requested_reams or line_req.requested_sheets)
                    else decimal_reams_to_sheets(line_req.requested_quantity, spr)
                )
                if req_sh <= 0:
                    raise HTTPException(422, f"Requested Reams/Sheets must be positive for {item.name}")
                req_wt = line_req.weight_kg or calc_sheet_weight_kg(req_sh, spr, item.weight_per_ream_kg)
                lines.append(
                    PaperTransferLine(
                        paper_item_id=item.id,
                        unit_id=unit.id,
                        requested_quantity=sheets_to_decimal_reams(req_sh, spr),
                        approved_quantity=sheets_to_decimal_reams(req_sh, spr) if transfer_mode == "PUSH" else None,
                        requested_sheets=req_sh,
                        approved_sheets=req_sh if transfer_mode == "PUSH" else None,
                        requested_weight_kg=req_wt,
                        weight_kg=req_wt,
                        remarks=line_req.remarks,
                    )
                )
            else:
                req_wt = Decimal(str(line_req.weight_kg or line_req.requested_quantity or 0))
                if req_wt <= 0:
                    raise HTTPException(422, f"Requested Weight (KG) must be positive for {item.name}")
                lines.append(
                    PaperTransferLine(
                        paper_item_id=item.id,
                        unit_id=unit.id,
                        requested_quantity=req_wt,
                        approved_quantity=req_wt if transfer_mode == "PUSH" else None,
                        requested_sheets=0,
                        approved_sheets=0 if transfer_mode == "PUSH" else None,
                        requested_weight_kg=req_wt,
                        weight_kg=req_wt,
                        remarks=line_req.remarks,
                    )
                )

        transfer = PaperTransfer(
            transfer_no=transfer_no,
            transfer_date=payload.transfer_date,
            financial_year_id=fy.id,
            source_store_id=source_store.id,
            destination_store_id=dest_store.id,
            transfer_mode=transfer_mode,
            status=initial_status,
            remarks=payload.remarks,
            created_by=actor_id,
            directorate_approved_by=dir_approved_by,
            directorate_approved_at=dir_approved_at,
            lines=lines,
        )
        self.session.add(transfer)
        await self.session.commit()
        return await self.get(transfer.id)

    async def approve_branch(
        self, transfer_id: int, actor_id: int, remarks: str | None = None
    ) -> PaperTransfer:
        """Approves a pull request by the Branch Head of the supplying press."""
        await self.auth.require_permission(actor_id, "PAPER_TRANSFER_APPROVE")
        transfer = await self.get(transfer_id)
        if not transfer:
            raise HTTPException(404, "Transfer not found")
        if transfer.status != "SUBMITTED":
            raise HTTPException(409, f"Transfer is in status {transfer.status}; cannot approve")

        await self.auth.require_store_controller(actor_id, transfer.source_store_id)

        transfer.status = "BRANCH_APPROVED"
        transfer.branch_approved_by = actor_id
        transfer.branch_approved_at = datetime.now(timezone.utc)
        if remarks:
            transfer.remarks = f"{transfer.remarks or ''}\nBranch Approved: {remarks}".strip()

        for line in transfer.lines:
            if line.approved_quantity is None:
                line.approved_quantity = line.requested_quantity
            if line.approved_sheets is None:
                line.approved_sheets = line.requested_sheets

        await self.session.commit()
        return transfer

    async def dispatch(
        self, transfer_id: int, payload: PaperTransferDispatchRequest, actor_id: int
    ) -> PaperTransfer:
        """Dispatches paper from source warehouse with Gate Pass, updating ledger atomically."""
        await self.auth.require_permission(actor_id, "PAPER_TRANSFER_DISPATCH")
        transfer = await self.get(transfer_id)
        if not transfer:
            raise HTTPException(404, "Transfer not found")
        if transfer.status not in ("DIRECTORATE_DIRECTIVE", "BRANCH_APPROVED"):
            raise HTTPException(409, f"Transfer is {transfer.status}; cannot dispatch")

        await self.auth.require_store_assignment(actor_id, transfer.source_store_id)
        fy = await self.session.get(FinancialYear, transfer.financial_year_id)
        if not fy or fy.is_closed:
            raise HTTPException(409, "Financial year is missing or closed")

        now = datetime.now(timezone.utc)
        dispatch_group_id = uuid4()
        line_map = {l.id: l for l in transfer.lines}

        for d_line in payload.lines:
            if d_line.line_id not in line_map:
                raise HTTPException(404, f"Transfer line {d_line.line_id} not found in this transfer")
            t_line = line_map[d_line.line_id]
            item = t_line.paper_item
            spr = item.sheets_per_ream or 500

            if item.form_type == "SHEET":
                disp_sh = (
                    to_total_sheets(d_line.dispatch_reams, d_line.dispatch_sheets, spr)
                    if (d_line.dispatch_reams or d_line.dispatch_sheets)
                    else decimal_reams_to_sheets(d_line.dispatch_quantity, spr)
                )
                if disp_sh <= 0:
                    raise HTTPException(422, f"Dispatch Reams/Sheets must be positive for {item.name}")

                avail_sh, _ = await self.stock_svc.balance_for_item(
                    transfer.source_store_id, transfer.financial_year_id, item.id
                )
                if disp_sh > avail_sh:
                    raise HTTPException(
                        422,
                        f"Insufficient stock for {item.name}: available {format_paper_balance('SHEET', avail_sh, Decimal('0'), spr)}, dispatching {format_paper_balance('SHEET', disp_sh, Decimal('0'), spr)}",
                    )
                disp_wt = d_line.weight_kg or calc_sheet_weight_kg(disp_sh, spr, item.weight_per_ream_kg)
                t_line.dispatched_sheets = disp_sh
                t_line.dispatched_quantity = sheets_to_decimal_reams(disp_sh, spr)
                t_line.dispatched_weight_kg = disp_wt
                t_line.weight_kg = disp_wt

                await self.stock_svc.post_movement(
                    financial_year_id=transfer.financial_year_id,
                    store_id=transfer.source_store_id,
                    paper_item_id=item.id,
                    movement_date=transfer.transfer_date,
                    movement_type="TRANSFER_OUT",
                    sheets_in=0,
                    sheets_out=disp_sh,
                    weight_kg_in=Decimal("0"),
                    weight_kg_out=disp_wt,
                    reference_type="PAPER_TRANSFER",
                    reference_id=transfer.id,
                    reference_no=transfer.transfer_no,
                    posting_group_id=dispatch_group_id,
                    remarks=f"Dispatched to {transfer.destination_store.name} (Vehicle: {payload.vehicle_no or 'N/A'})",
                    created_by=actor_id,
                )
            else:
                disp_wt = Decimal(str(d_line.weight_kg or d_line.dispatch_quantity or 0))
                if disp_wt <= 0:
                    raise HTTPException(422, f"Dispatch Weight (KG) must be positive for {item.name}")

                _, avail_wt = await self.stock_svc.balance_for_item(
                    transfer.source_store_id, transfer.financial_year_id, item.id
                )
                if disp_wt > avail_wt:
                    raise HTTPException(
                        422,
                        f"Insufficient stock for {item.name}: available {avail_wt} kg, dispatching {disp_wt} kg",
                    )

                t_line.dispatched_sheets = 0
                t_line.dispatched_quantity = disp_wt
                t_line.dispatched_weight_kg = disp_wt
                t_line.weight_kg = disp_wt

                await self.stock_svc.post_movement(
                    financial_year_id=transfer.financial_year_id,
                    store_id=transfer.source_store_id,
                    paper_item_id=item.id,
                    movement_date=transfer.transfer_date,
                    movement_type="TRANSFER_OUT",
                    sheets_in=0,
                    sheets_out=0,
                    weight_kg_in=Decimal("0"),
                    weight_kg_out=disp_wt,
                    reference_type="PAPER_TRANSFER",
                    reference_id=transfer.id,
                    reference_no=transfer.transfer_no,
                    posting_group_id=dispatch_group_id,
                    remarks=f"Dispatched to {transfer.destination_store.name} (Vehicle: {payload.vehicle_no or 'N/A'})",
                    created_by=actor_id,
                )

        transfer.status = "DISPATCHED"
        transfer.vehicle_no = payload.vehicle_no.strip() if payload.vehicle_no else None
        transfer.driver_name = payload.driver_name.strip() if payload.driver_name else None
        transfer.carrier_name = payload.carrier_name.strip() if payload.carrier_name else None
        transfer.gate_pass_no = payload.gate_pass_no.strip() if payload.gate_pass_no else f"GP-{transfer.transfer_no}"
        transfer.dispatched_by = actor_id
        transfer.dispatched_at = now
        transfer.dispatch_posting_group_id = dispatch_group_id
        if payload.remarks:
            transfer.remarks = f"{transfer.remarks or ''}\nDispatch: {payload.remarks}".strip()

        await self.session.commit()
        return transfer

    async def receive(
        self, transfer_id: int, payload: PaperTransferReceiveRequest, actor_id: int
    ) -> PaperTransfer:
        """Receives paper at destination warehouse, checking for discrepancies and posting stock IN."""
        await self.auth.require_permission(actor_id, "PAPER_TRANSFER_RECEIVE")
        transfer = await self.get(transfer_id)
        if not transfer:
            raise HTTPException(404, "Transfer not found")
        if transfer.status != "DISPATCHED":
            raise HTTPException(409, f"Transfer is {transfer.status}; cannot receive")

        await self.auth.require_store_assignment(actor_id, transfer.destination_store_id)
        receive_date = date.today()
        dest_fy = await self._financial_year_for_date(receive_date)

        now = datetime.now(timezone.utc)
        receive_group_id = uuid4()
        line_map = {l.id: l for l in transfer.lines}
        has_discrepancy = False

        for r_line in payload.lines:
            if r_line.line_id not in line_map:
                raise HTTPException(404, f"Transfer line {r_line.line_id} not found in this transfer")
            t_line = line_map[r_line.line_id]
            item = t_line.paper_item
            spr = item.sheets_per_ream or 500

            if item.form_type == "SHEET":
                recv_sh = (
                    to_total_sheets(r_line.received_reams, r_line.received_sheets, spr)
                    if (r_line.received_reams or r_line.received_sheets)
                    else decimal_reams_to_sheets(r_line.received_quantity, spr)
                )
                if recv_sh < 0:
                    raise HTTPException(422, "Received sheets cannot be negative")

                t_line.received_sheets = recv_sh
                t_line.received_quantity = sheets_to_decimal_reams(recv_sh, spr)
                recv_wt = r_line.weight_kg or calc_sheet_weight_kg(recv_sh, spr, item.weight_per_ream_kg)
                t_line.received_weight_kg = recv_wt

                if recv_sh < t_line.dispatched_sheets:
                    has_discrepancy = True

                if recv_sh > 0:
                    await self.stock_svc.post_movement(
                        financial_year_id=dest_fy.id,
                        store_id=transfer.destination_store_id,
                        paper_item_id=item.id,
                        movement_date=receive_date,
                        movement_type="TRANSFER_IN",
                        sheets_in=recv_sh,
                        sheets_out=0,
                        weight_kg_in=recv_wt,
                        weight_kg_out=Decimal("0"),
                        reference_type="PAPER_TRANSFER",
                        reference_id=transfer.id,
                        reference_no=transfer.transfer_no,
                        posting_group_id=receive_group_id,
                        remarks=f"Received from {transfer.source_store.name}",
                        created_by=actor_id,
                    )
            else:
                recv_wt = Decimal(str(r_line.weight_kg or r_line.received_quantity or 0))
                if recv_wt < 0:
                    raise HTTPException(422, "Received weight cannot be negative")
                t_line.received_sheets = 0
                t_line.received_quantity = recv_wt
                t_line.received_weight_kg = recv_wt

                if recv_wt < t_line.dispatched_weight_kg:
                    has_discrepancy = True

                if recv_wt > 0:
                    await self.stock_svc.post_movement(
                        financial_year_id=dest_fy.id,
                        store_id=transfer.destination_store_id,
                        paper_item_id=item.id,
                        movement_date=receive_date,
                        movement_type="TRANSFER_IN",
                        sheets_in=0,
                        sheets_out=0,
                        weight_kg_in=recv_wt,
                        weight_kg_out=Decimal("0"),
                        reference_type="PAPER_TRANSFER",
                        reference_id=transfer.id,
                        reference_no=transfer.transfer_no,
                        posting_group_id=receive_group_id,
                        remarks=f"Received from {transfer.source_store.name}",
                        created_by=actor_id,
                    )

        transfer.status = "DISCREPANCY" if has_discrepancy else "RECEIVED"
        transfer.received_by = actor_id
        transfer.received_at = now
        transfer.receive_posting_group_id = receive_group_id
        if payload.remarks:
            transfer.remarks = f"{transfer.remarks or ''}\nReceipt: {payload.remarks}".strip()

        await self.session.commit()
        return transfer

    async def get(self, transfer_id: int) -> PaperTransfer | None:
        stmt = (
            select(PaperTransfer)
            .options(
                selectinload(PaperTransfer.lines).selectinload(PaperTransferLine.paper_item),
                selectinload(PaperTransfer.lines).selectinload(PaperTransferLine.unit),
                selectinload(PaperTransfer.source_store).selectinload(Store.office),
                selectinload(PaperTransfer.destination_store).selectinload(Store.office),
                selectinload(PaperTransfer.financial_year),
                selectinload(PaperTransfer.creator),
            )
            .where(PaperTransfer.id == transfer_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list(
        self, store_id: int | None = None, financial_year_id: int | None = None
    ) -> list[PaperTransfer]:
        stmt = (
            select(PaperTransfer)
            .options(
                selectinload(PaperTransfer.lines).selectinload(PaperTransferLine.paper_item),
                selectinload(PaperTransfer.lines).selectinload(PaperTransferLine.unit),
                selectinload(PaperTransfer.source_store).selectinload(Store.office),
                selectinload(PaperTransfer.destination_store).selectinload(Store.office),
                selectinload(PaperTransfer.financial_year),
                selectinload(PaperTransfer.creator),
            )
            .order_by(PaperTransfer.transfer_date.desc(), PaperTransfer.id.desc())
        )
        if store_id is not None:
            stmt = stmt.where(
                (PaperTransfer.source_store_id == store_id)
                | (PaperTransfer.destination_store_id == store_id)
            )
        if financial_year_id is not None:
            stmt = stmt.where(PaperTransfer.financial_year_id == financial_year_id)
        return list((await self.session.scalars(stmt)).all())
