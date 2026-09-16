from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.financial_year import FinancialYear
from app.models.indent import Indent, IndentLine
from app.models.item import Item
from app.models.office import Office
from app.models.section import Section
from app.models.store import Store
from app.models.unit import Unit
from app.repositories.indent import IndentRepository
from app.schemas.indent import (
    IndentCreate,
    ManualIndentCreate,
    ManualIndentLineCreate,
)


class IndentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = IndentRepository(session)

    async def _validate_header(
        self,
        *,
        indent_date: date,
        financial_year_id: int,
        store_id: int,
        office_id: int,
        section_id: int | None,
        actor_id: int,
        permission: str,
        request_source: str | None = None,
    ) -> tuple[FinancialYear, Store, Office, Section | None]:
        from app.services.authorization import AuthorizationService

        auth = AuthorizationService(self.session)
        await auth.require_permission(actor_id, permission)
        if request_source == "PHYSICAL":
            await auth.require_store_assignment(actor_id, store_id)
        elif request_source == "ONLINE":
            from app.models.user import User
            actor = await self.session.get(User, actor_id)
            if actor is None or actor.office_id != office_id:
                raise HTTPException(403, "User cannot create an online indent for another office")
            if actor.section_id is None or section_id != actor.section_id:
                raise HTTPException(403, "User can create an online indent only for their assigned section")

        fy = await self.session.get(FinancialYear, financial_year_id)
        store = await self.session.get(Store, store_id)
        office = await self.session.get(Office, office_id)

        if fy is None:
            raise HTTPException(404, "Financial year not found")
        if store is None:
            raise HTTPException(404, "Store not found")
        if office is None:
            raise HTTPException(404, "Office not found")
        if fy.is_closed:
            raise HTTPException(409, "Financial year is closed")
        if not (fy.start_date <= indent_date <= fy.end_date):
            raise HTTPException(422, "Indent date is outside the financial year")
        if store.office_id == office.id and office.office_type == "BRANCH":
            pass
        elif store.office_id != office.id:
            # Central Store may issue to Directorate or a branch/office.
            if store.store_type != "CENTRAL":
                raise HTTPException(422, "Selected store does not belong to the selected office")
        if section_id is not None:
            section = await self.session.get(Section, section_id)
            if section is None:
                raise HTTPException(404, "Section not found")
            if section.office_id != office.id:
                raise HTTPException(422, "Section does not belong to the selected office")
        else:
            section = None

        return fy, store, office, section

    async def _build_indent(
        self,
        *,
        indent_date: date,
        financial_year_id: int,
        store_id: int,
        office_id: int,
        section_id: int | None,
        request_source: str,
        request_type: str | None,
        reference_no: str | None,
        reference_date: date | None,
        remarks: str | None,
        line_specs: list[tuple[int, Decimal, str | None]],
        actor_id: int,
    ) -> Indent:
        permission = "INDENT_PROCESS" if request_source == "PHYSICAL" else "INDENT_CREATE"
        fy, store, office, section = await self._validate_header(
            indent_date=indent_date,
            financial_year_id=financial_year_id,
            store_id=store_id,
            office_id=office_id,
            section_id=section_id,
            actor_id=actor_id,
            permission=permission,
            request_source=request_source,
        )

        seen: set[int] = set()
        lines: list[IndentLine] = []
        for item_id, requested_quantity, line_remarks in line_specs:
            if item_id in seen:
                raise HTTPException(422, f"Duplicate item {item_id} in indent")
            seen.add(item_id)

            item = await self.session.get(Item, item_id)
            if item is None or not item.is_active:
                raise HTTPException(404, f"Item {item_id} not found or inactive")

            category = await self.session.get(Category, item.category_id)
            if category is None or category.type not in ("CONSUMABLE", "ASSET"):
                raise HTTPException(422, f"Unsupported item type for issue: {item.code}")

            lines.append(
                IndentLine(
                    item_id=item_id,
                    requested_quantity=requested_quantity,
                    remarks=line_remarks,
                )
            )

        indent = Indent(
            indent_no=await self._next_number(),
            indent_date=indent_date,
            received_date=date.today(),
            financial_year_id=financial_year_id,
            store_id=store_id,
            office_id=office_id,
            section_id=section_id,
            request_source=request_source,
            request_type=request_type,
            reference_no=reference_no,
            reference_date=reference_date,
            status="RECORDED",
            remarks=remarks,
            created_by=actor_id,
            lines=lines,
        )
        self.session.add(indent)
        await self.session.flush()
        return indent

    async def create(self, payload: IndentCreate, actor_id: int) -> Indent:
        indent = await self._build_indent(
            indent_date=payload.indent_date,
            financial_year_id=payload.financial_year_id,
            store_id=payload.store_id,
            office_id=payload.office_id,
            section_id=payload.section_id,
            request_source=payload.request_source,
            request_type=payload.request_type,
            reference_no=payload.reference_no,
            reference_date=payload.reference_date,
            remarks=payload.remarks,
            line_specs=[
                (line.item_id, line.requested_quantity, line.remarks)
                for line in payload.lines
            ],
            actor_id=actor_id,
        )
        await self.session.commit()
        await self.session.refresh(indent)
        return indent

    async def create_manual_and_issue(
        self,
        payload: ManualIndentCreate,
        actor_id: int,
    ):
        """
        Manual indent is an approved physical document. Saving it creates the
        indent and finalizes the corresponding issue atomically in one DB
        transaction. There is no draft/approval step for this workflow.
        """
        # Validate the store/office/user boundary once before constructing the
        # document. IssueService performs the authoritative stock/asset checks
        # again under row locks.
        await self._validate_header(
            indent_date=payload.indent_date,
            financial_year_id=payload.financial_year_id,
            store_id=payload.store_id,
            office_id=payload.office_id,
            section_id=payload.section_id,
            actor_id=actor_id,
            permission="INDENT_PROCESS",
            request_source="PHYSICAL",
        )

        line_specs = []
        for line in payload.lines:
            item = await self.session.get(Item, line.item_id)
            if item is None:
                raise HTTPException(404, f"Item {line.item_id} not found")
            unit = await self.session.get(Unit, line.unit_id)
            if unit is None:
                raise HTTPException(404, f"Unit {line.unit_id} not found")
            if unit.id != item.unit_id:
                raise HTTPException(
                    422,
                    f"Unit {unit.code} is not the master unit for item {item.code}",
                )
            if line.issued_quantity > line.requested_quantity:
                raise HTTPException(
                    422,
                    f"Issued quantity {line.issued_quantity} exceeds requested quantity {line.requested_quantity} for item {item.code}",
                )
            if line.issued_quantity > 0 and line.asset_ids and line.issued_quantity != len(line.asset_ids):
                raise HTTPException(
                    422,
                    f"Asset count does not match issued quantity for item {item.code}",
                )
            line_specs.append((line.item_id, line.requested_quantity, line.remarks))

        indent = await self._build_indent(
            indent_date=payload.indent_date,
            financial_year_id=payload.financial_year_id,
            store_id=payload.store_id,
            office_id=payload.office_id,
            section_id=payload.section_id,
            request_source="PHYSICAL",
            request_type="MANUAL",
            reference_no=None,
            reference_date=None,
            remarks=payload.remarks,
            line_specs=line_specs,
            actor_id=actor_id,
        )

        from app.schemas.indent import IssueFinalizeLine, IssueFinalizeRequest
        from app.services.issue import IssueService

        issue_payload = IssueFinalizeRequest(
            issue_date=payload.indent_date,
            remarks=payload.remarks,
            lines=[
                IssueFinalizeLine(
                    indent_line_id=indent_line.id,
                    issued_quantity=manual_line.issued_quantity,
                    asset_ids=manual_line.asset_ids,
                    remarks=manual_line.remarks,
                )
                for indent_line, manual_line in zip(indent.lines, payload.lines)
            ],
        )

        # IssueService commits the whole transaction. If it raises, the caller
        # rolls the transaction back, removing both the indent and the issue.
        issue = await IssueService(self.session).finalize_from_indent(
            indent.id,
            issue_payload,
            actor_id,
        )
        return indent, issue

    async def approve_online(self, indent_id: int, actor_id: int) -> Indent:
        from app.services.authorization import AuthorizationService
        auth = AuthorizationService(self.session)
        await auth.require_permission(actor_id, "INDENT_APPROVE")
        indent = await self.session.scalar(select(Indent).where(Indent.id == indent_id, Indent.request_source == "ONLINE").with_for_update())
        if indent is None:
            raise HTTPException(404, "Online indent not found")
        if indent.status != "RECORDED":
            raise HTTPException(409, f"Indent is {indent.status} and cannot be approved")
        if indent.created_by == actor_id:
            raise HTTPException(403, "The indent creator cannot approve the same indent")
        await auth.require_store_controller(actor_id, indent.store_id)
        indent.status = "PROCESSING"
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
