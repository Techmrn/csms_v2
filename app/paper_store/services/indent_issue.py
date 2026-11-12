from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.financial_year import FinancialYear
from app.models.section import Section
from app.models.store import Store
from app.models.unit import Unit
from app.models.user import User
from app.paper_store.models.indent_issue import (
    PaperIndent,
    PaperIndentLine,
    PaperIssue,
    PaperIssueLine,
)
from app.paper_store.models.item import PaperItem
from app.paper_store.schemas.indent_issue import (
    PaperManualIndentCreate,
    PaperOnlineIndentCreate,
    PaperOnlineIndentIssueRequest,
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


class PaperIndentIssueService:
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

    async def _next_indent_number(self, fy: FinancialYear) -> str:
        prefix = f"PIN-{fy.year_name}-"
        last_num = await self.session.scalar(
            select(func.max(PaperIndent.indent_no)).where(
                PaperIndent.financial_year_id == fy.id,
                PaperIndent.indent_no.like(f"{prefix}%"),
            )
        )
        if not last_num:
            return f"{prefix}0001"
        try:
            seq = int(last_num.replace(prefix, "")) + 1
        except ValueError:
            seq = 1
        return f"{prefix}{seq:04d}"

    async def _next_issue_number(self, fy: FinancialYear) -> str:
        prefix = f"PIS-{fy.year_name}-"
        last_num = await self.session.scalar(
            select(func.max(PaperIssue.issue_no)).where(
                PaperIssue.financial_year_id == fy.id,
                PaperIssue.issue_no.like(f"{prefix}%"),
            )
        )
        if not last_num:
            return f"{prefix}0001"
        try:
            seq = int(last_num.replace(prefix, "")) + 1
        except ValueError:
            seq = 1
        return f"{prefix}{seq:04d}"

    async def create_manual_indent_and_issue(
        self, payload: PaperManualIndentCreate, actor_id: int
    ) -> tuple[PaperIndent, PaperIssue]:
        """Atomically records a manual paper indent and issues paper to the press section."""
        await self.auth.require_permission(actor_id, "PAPER_ISSUE")
        store = await self.auth.require_paper_warehouse(payload.store_id)
        await self.auth.require_store_assignment(actor_id, store.id)

        section = await self.session.get(Section, payload.section_id)
        if not section or not section.is_active:
            raise HTTPException(404, "Press section not found or inactive")
        if section.office_id != store.office_id:
            raise HTTPException(422, "Section does not belong to the press office of this warehouse")

        fy = await (
            self.session.get(FinancialYear, payload.financial_year_id)
            if payload.financial_year_id
            else self._financial_year_for_date(payload.indent_date)
        )
        if not fy:
            raise HTTPException(404, "Financial year not found")
        if fy.is_closed:
            raise HTTPException(409, "Financial year is closed")

        if not payload.lines:
            raise HTTPException(422, "At least one paper line item is required")

        indent_no = await self._next_indent_number(fy)
        issue_no = await self._next_issue_number(fy)
        posting_group_id = uuid4()
        now = datetime.now(timezone.utc)

        indent = PaperIndent(
            indent_no=indent_no,
            indent_date=payload.indent_date,
            financial_year_id=fy.id,
            store_id=store.id,
            section_id=section.id,
            job_no=payload.job_no.strip() if payload.job_no else None,
            request_source="PHYSICAL",
            status="FINALIZED",
            remarks=payload.remarks,
            created_by=actor_id,
        )
        self.session.add(indent)
        await self.session.flush()

        issue = PaperIssue(
            issue_no=issue_no,
            issue_date=payload.indent_date,
            financial_year_id=fy.id,
            indent_id=indent.id,
            store_id=store.id,
            section_id=section.id,
            job_no=payload.job_no.strip() if payload.job_no else None,
            status="FINALIZED",
            remarks=payload.remarks,
            created_by=actor_id,
            posted_by=actor_id,
            posted_at=now,
            posting_group_id=posting_group_id,
        )
        self.session.add(issue)
        await self.session.flush()

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
                req_sh = (
                    to_total_sheets(line_req.requested_reams, line_req.requested_sheets, spr)
                    if (line_req.requested_reams or line_req.requested_sheets)
                    else decimal_reams_to_sheets(line_req.requested_quantity, spr)
                )
                if req_sh <= 0:
                    raise HTTPException(422, f"Requested Reams/Sheets must be positive for {item.name}")

                if line_req.issued_reams is not None or line_req.issued_sheets is not None:
                    iss_sh = to_total_sheets(line_req.issued_reams or 0, line_req.issued_sheets or 0, spr)
                elif line_req.issued_quantity is not None:
                    iss_sh = decimal_reams_to_sheets(line_req.issued_quantity, spr)
                else:
                    iss_sh = req_sh

                if iss_sh < 0:
                    raise HTTPException(422, "Issued sheets cannot be negative")
                if iss_sh > req_sh:
                    raise HTTPException(422, "Issued quantity cannot exceed requested quantity")

                if iss_sh > 0:
                    avail_sh, _ = await self.stock_svc.balance_for_item(store.id, fy.id, item.id)
                    if iss_sh > avail_sh:
                        avail_str = format_paper_balance("SHEET", avail_sh, Decimal("0"), spr)
                        iss_str = format_paper_balance("SHEET", iss_sh, Decimal("0"), spr)
                        raise HTTPException(
                            422,
                            f"Insufficient stock for {item.name}: available {avail_str}, requested to issue {iss_str}",
                        )

                wt_kg = line_req.weight_kg or Decimal("0")
                if wt_kg == 0 and item.weight_per_ream_kg:
                    wt_kg = calc_sheet_weight_kg(iss_sh, spr, item.weight_per_ream_kg)

                self.session.add(
                    PaperIndentLine(
                        indent_id=indent.id,
                        paper_item_id=item.id,
                        unit_id=unit.id,
                        requested_quantity=sheets_to_decimal_reams(req_sh, spr),
                        approved_quantity=sheets_to_decimal_reams(iss_sh, spr),
                        issued_quantity=sheets_to_decimal_reams(iss_sh, spr),
                        requested_sheets=req_sh,
                        approved_sheets=iss_sh,
                        issued_sheets=iss_sh,
                        requested_weight_kg=calc_sheet_weight_kg(req_sh, spr, item.weight_per_ream_kg),
                        approved_weight_kg=wt_kg,
                        issued_weight_kg=wt_kg,
                        remarks=line_req.remarks,
                    )
                )
                self.session.add(
                    PaperIssueLine(
                        issue_id=issue.id,
                        paper_item_id=item.id,
                        unit_id=unit.id,
                        quantity=sheets_to_decimal_reams(iss_sh, spr),
                        sheets=iss_sh,
                        weight_kg=wt_kg,
                        remarks=line_req.remarks,
                    )
                )
                if iss_sh > 0:
                    await self.stock_svc.post_movement(
                        financial_year_id=fy.id,
                        store_id=store.id,
                        paper_item_id=item.id,
                        movement_date=payload.indent_date,
                        movement_type="ISSUE_SECTION",
                        sheets_in=0,
                        sheets_out=iss_sh,
                        weight_kg_in=Decimal("0"),
                        weight_kg_out=wt_kg,
                        reference_type="PAPER_ISSUE",
                        reference_id=issue.id,
                        reference_no=issue.issue_no,
                        posting_group_id=posting_group_id,
                        remarks=f"Issued to {section.name} (Job: {payload.job_no or 'General'})",
                        created_by=actor_id,
                    )
            else:
                # REEL paper tracked strictly in KG
                req_wt = Decimal(str(line_req.requested_quantity or line_req.weight_kg or 0))
                if req_wt <= 0:
                    raise HTTPException(422, f"Requested Weight (KG) must be positive for {item.name}")
                iss_wt = Decimal(
                    str(
                        line_req.issued_quantity
                        if line_req.issued_quantity is not None
                        else (line_req.weight_kg if line_req.weight_kg is not None else req_wt)
                    )
                )
                if iss_wt < 0:
                    raise HTTPException(422, "Issued weight cannot be negative")
                if iss_wt > req_wt:
                    raise HTTPException(422, "Issued weight cannot exceed requested weight")

                if iss_wt > 0:
                    _, avail_wt = await self.stock_svc.balance_for_item(store.id, fy.id, item.id)
                    if iss_wt > avail_wt:
                        raise HTTPException(
                            422,
                            f"Insufficient stock for {item.name}: available {avail_wt} kg, requested to issue {iss_wt} kg",
                        )

                self.session.add(
                    PaperIndentLine(
                        indent_id=indent.id,
                        paper_item_id=item.id,
                        unit_id=unit.id,
                        requested_quantity=req_wt,
                        approved_quantity=iss_wt,
                        issued_quantity=iss_wt,
                        requested_sheets=0,
                        approved_sheets=0,
                        issued_sheets=0,
                        requested_weight_kg=req_wt,
                        approved_weight_kg=iss_wt,
                        issued_weight_kg=iss_wt,
                        remarks=line_req.remarks,
                    )
                )
                self.session.add(
                    PaperIssueLine(
                        issue_id=issue.id,
                        paper_item_id=item.id,
                        unit_id=unit.id,
                        quantity=iss_wt,
                        sheets=0,
                        weight_kg=iss_wt,
                        remarks=line_req.remarks,
                    )
                )
                if iss_wt > 0:
                    await self.stock_svc.post_movement(
                        financial_year_id=fy.id,
                        store_id=store.id,
                        paper_item_id=item.id,
                        movement_date=payload.indent_date,
                        movement_type="ISSUE_SECTION",
                        sheets_in=0,
                        sheets_out=0,
                        weight_kg_in=Decimal("0"),
                        weight_kg_out=iss_wt,
                        reference_type="PAPER_ISSUE",
                        reference_id=issue.id,
                        reference_no=issue.issue_no,
                        posting_group_id=posting_group_id,
                        remarks=f"Issued to {section.name} (Job: {payload.job_no or 'General'})",
                        created_by=actor_id,
                    )

        await self.session.commit()
        return indent, issue

    async def create_online_indent(
        self, payload: PaperOnlineIndentCreate, actor_id: int
    ) -> PaperIndent:
        """Allows press section users to submit an online indent for paper."""
        await self.auth.require_permission(actor_id, "PAPER_INDENT_CREATE")
        actor = await self.session.get(User, actor_id)
        if not actor or not actor.is_active:
            raise HTTPException(403, "User inactive")

        store = await self.auth.require_paper_warehouse(payload.store_id)
        section_id = payload.section_id or actor.section_id
        if not section_id:
            raise HTTPException(422, "Press section is required")

        section = await self.session.get(Section, section_id)
        if not section or not section.is_active or section.office_id != store.office_id:
            raise HTTPException(422, "Section must belong to the same office as the paper warehouse")
        if actor.section_id and actor.section_id != section.id:
            raise HTTPException(403, "Section user can only raise requests for their assigned section")

        fy = await (
            self.session.get(FinancialYear, payload.financial_year_id)
            if payload.financial_year_id
            else self._financial_year_for_date(payload.indent_date)
        )
        if not fy or fy.is_closed:
            raise HTTPException(409, "Financial year missing or closed")

        indent_no = await self._next_indent_number(fy)
        indent = PaperIndent(
            indent_no=indent_no,
            indent_date=payload.indent_date,
            financial_year_id=fy.id,
            store_id=store.id,
            section_id=section.id,
            job_no=payload.job_no.strip() if payload.job_no else None,
            request_source="ONLINE",
            status="SUBMITTED",
            remarks=payload.remarks,
            created_by=actor_id,
        )
        self.session.add(indent)
        await self.session.flush()

        for line_req in payload.lines:
            item = await self.session.get(PaperItem, line_req.paper_item_id)
            if not item or not item.is_active:
                raise HTTPException(404, f"Item {line_req.paper_item_id} not found")
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
                line = PaperIndentLine(
                    indent_id=indent.id,
                    paper_item_id=item.id,
                    unit_id=unit.id,
                    requested_quantity=sheets_to_decimal_reams(req_sh, spr),
                    requested_sheets=req_sh,
                    requested_weight_kg=calc_sheet_weight_kg(req_sh, spr, item.weight_per_ream_kg),
                    remarks=line_req.remarks,
                )
            else:
                req_wt = Decimal(str(line_req.requested_quantity or line_req.weight_kg or 0))
                if req_wt <= 0:
                    raise HTTPException(422, f"Requested Weight (KG) must be positive for {item.name}")
                line = PaperIndentLine(
                    indent_id=indent.id,
                    paper_item_id=item.id,
                    unit_id=unit.id,
                    requested_quantity=req_wt,
                    requested_sheets=0,
                    requested_weight_kg=req_wt,
                    remarks=line_req.remarks,
                )
            self.session.add(line)

        await self.session.commit()
        return await self.get_indent(indent.id)

    async def issue_from_online_indent(
        self, indent_id: int, payload: PaperOnlineIndentIssueRequest, actor_id: int
    ) -> PaperIssue:
        """Warehouseman finalizes and issues paper against a Section User online request."""
        await self.auth.require_permission(actor_id, "PAPER_ISSUE")
        indent = await self.get_indent(indent_id)
        if not indent:
            raise HTTPException(404, "Paper indent not found")
        if indent.request_source != "ONLINE":
            raise HTTPException(409, "Only ONLINE indents can be issued via fulfillment")
        if indent.status not in ("SUBMITTED", "APPROVED"):
            raise HTTPException(409, f"Indent status is {indent.status}; cannot issue")

        await self.auth.require_store_assignment(actor_id, indent.store_id)
        fy = await self.session.get(FinancialYear, indent.financial_year_id)
        if not fy or fy.is_closed:
            raise HTTPException(409, "Financial year is missing or closed")

        issue_date = payload.issue_date or date.today()
        issue_no = await self._next_issue_number(fy)
        posting_group_id = uuid4()
        now = datetime.now(timezone.utc)

        issue = PaperIssue(
            issue_no=issue_no,
            issue_date=issue_date,
            financial_year_id=fy.id,
            indent_id=indent.id,
            store_id=indent.store_id,
            section_id=indent.section_id,
            job_no=indent.job_no,
            status="FINALIZED",
            remarks=payload.remarks or indent.remarks,
            created_by=actor_id,
            posted_by=actor_id,
            posted_at=now,
            posting_group_id=posting_group_id,
        )
        self.session.add(issue)
        await self.session.flush()

        line_map = {l.id: l for l in indent.lines}
        for i_line in payload.lines:
            indent_line = line_map.get(i_line.indent_line_id)
            if not indent_line:
                raise HTTPException(404, f"Indent line {i_line.indent_line_id} not found")
            item = indent_line.paper_item
            spr = item.sheets_per_ream or 500

            if item.form_type == "SHEET":
                iss_sh = to_total_sheets(i_line.issued_reams, i_line.issued_sheets, spr)
                if iss_sh > indent_line.requested_sheets:
                    raise HTTPException(422, f"Issued quantity exceeds requested quantity for {item.name}")
                if iss_sh > 0:
                    avail_sh, _ = await self.stock_svc.balance_for_item(indent.store_id, fy.id, item.id)
                    if iss_sh > avail_sh:
                        raise HTTPException(
                            422,
                            f"Insufficient stock for {item.name}: available {format_paper_balance('SHEET', avail_sh, Decimal('0'), spr)}",
                        )
                wt_kg = i_line.weight_kg or calc_sheet_weight_kg(iss_sh, spr, item.weight_per_ream_kg)
                indent_line.approved_sheets = iss_sh
                indent_line.issued_sheets = iss_sh
                indent_line.approved_quantity = sheets_to_decimal_reams(iss_sh, spr)
                indent_line.issued_quantity = sheets_to_decimal_reams(iss_sh, spr)
                indent_line.issued_weight_kg = wt_kg

                self.session.add(
                    PaperIssueLine(
                        issue_id=issue.id,
                        paper_item_id=item.id,
                        unit_id=indent_line.unit_id,
                        quantity=sheets_to_decimal_reams(iss_sh, spr),
                        sheets=iss_sh,
                        weight_kg=wt_kg,
                        remarks=i_line.remarks,
                    )
                )
                if iss_sh > 0:
                    await self.stock_svc.post_movement(
                        financial_year_id=fy.id,
                        store_id=indent.store_id,
                        paper_item_id=item.id,
                        movement_date=issue_date,
                        movement_type="ISSUE_SECTION",
                        sheets_in=0,
                        sheets_out=iss_sh,
                        weight_kg_in=Decimal("0"),
                        weight_kg_out=wt_kg,
                        reference_type="PAPER_ISSUE",
                        reference_id=issue.id,
                        reference_no=issue.issue_no,
                        posting_group_id=posting_group_id,
                        remarks=f"Issued to {indent.section.name if indent.section else 'Section'} (Job: {indent.job_no or 'General'})",
                        created_by=actor_id,
                    )
            else:
                iss_wt = Decimal(str(i_line.weight_kg or 0))
                if iss_wt < 0:
                    raise HTTPException(422, "Issued weight cannot be negative")
                if iss_wt > indent_line.requested_weight_kg:
                    raise HTTPException(422, f"Issued weight exceeds requested weight for {item.name}")
                if iss_wt > 0:
                    _, avail_wt = await self.stock_svc.balance_for_item(indent.store_id, fy.id, item.id)
                    if iss_wt > avail_wt:
                        raise HTTPException(422, f"Insufficient stock for {item.name}: available {avail_wt} kg")

                indent_line.approved_quantity = iss_wt
                indent_line.issued_quantity = iss_wt
                indent_line.approved_weight_kg = iss_wt
                indent_line.issued_weight_kg = iss_wt

                self.session.add(
                    PaperIssueLine(
                        issue_id=issue.id,
                        paper_item_id=item.id,
                        unit_id=indent_line.unit_id,
                        quantity=iss_wt,
                        sheets=0,
                        weight_kg=iss_wt,
                        remarks=i_line.remarks,
                    )
                )
                if iss_wt > 0:
                    await self.stock_svc.post_movement(
                        financial_year_id=fy.id,
                        store_id=indent.store_id,
                        paper_item_id=item.id,
                        movement_date=issue_date,
                        movement_type="ISSUE_SECTION",
                        sheets_in=0,
                        sheets_out=0,
                        weight_kg_in=Decimal("0"),
                        weight_kg_out=iss_wt,
                        reference_type="PAPER_ISSUE",
                        reference_id=issue.id,
                        reference_no=issue.issue_no,
                        posting_group_id=posting_group_id,
                        remarks=f"Issued to {indent.section.name if indent.section else 'Section'} (Job: {indent.job_no or 'General'})",
                        created_by=actor_id,
                    )

        indent.status = "FINALIZED"
        await self.session.commit()
        return issue

    async def get_indent(self, indent_id: int) -> PaperIndent | None:
        stmt = (
            select(PaperIndent)
            .options(
                selectinload(PaperIndent.lines).selectinload(PaperIndentLine.paper_item),
                selectinload(PaperIndent.lines).selectinload(PaperIndentLine.unit),
                selectinload(PaperIndent.store).selectinload(Store.office),
                selectinload(PaperIndent.section),
                selectinload(PaperIndent.financial_year),
                selectinload(PaperIndent.issue).selectinload(PaperIssue.lines),
                selectinload(PaperIndent.issue).selectinload(PaperIssue.poster),
            )
            .where(PaperIndent.id == indent_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_indents(
        self,
        store_id: int | None = None,
        financial_year_id: int | None = None,
        section_id: int | None = None,
    ) -> list[PaperIndent]:
        stmt = (
            select(PaperIndent)
            .options(
                selectinload(PaperIndent.lines).selectinload(PaperIndentLine.paper_item),
                selectinload(PaperIndent.lines).selectinload(PaperIndentLine.unit),
                selectinload(PaperIndent.store).selectinload(Store.office),
                selectinload(PaperIndent.section),
                selectinload(PaperIndent.financial_year),
            )
            .order_by(PaperIndent.indent_date.desc(), PaperIndent.id.desc())
        )
        if store_id is not None:
            stmt = stmt.where(PaperIndent.store_id == store_id)
        if financial_year_id is not None:
            stmt = stmt.where(PaperIndent.financial_year_id == financial_year_id)
        if section_id is not None:
            stmt = stmt.where(PaperIndent.section_id == section_id)
        return list((await self.session.scalars(stmt)).all())
