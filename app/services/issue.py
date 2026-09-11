from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.financial_year import FinancialYear
from app.models.indent import Indent, IndentLine
from app.models.item import Item
from app.models.issue import Issue, IssueLine
from app.models.stock import StockAccount, StockMovement
from app.models.unit import Unit
from app.repositories.stock import StockRepository
from app.schemas.indent import IssueFinalizeRequest


class IssueService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.stock = StockRepository(session)

    async def finalize_from_indent(self, indent_id: int, payload: IssueFinalizeRequest) -> Issue:
        result = await self.session.execute(
            select(Indent)
            .options(selectinload(Indent.lines))
            .where(Indent.id == indent_id)
            .with_for_update()
        )
        indent = result.scalar_one_or_none()
        if indent is None:
            raise HTTPException(404, "Indent not found")
        if indent.status not in {"RECORDED", "PROCESSING"}:
            raise HTTPException(409, f"Indent is {indent.status} and cannot be finalized")

        existing_issue = await self.session.scalar(
            select(Issue).where(Issue.indent_id == indent.id).limit(1)
        )
        if existing_issue is not None:
            raise HTTPException(409, "An issue already exists for this indent")

        fy = await self.session.get(FinancialYear, indent.financial_year_id)
        if fy is None or fy.is_closed:
            raise HTTPException(409, "Financial year is missing or closed")
        issue_date = payload.issue_date or date.today()
        if not (fy.start_date <= issue_date <= fy.end_date):
            raise HTTPException(422, "Issue date is outside the financial year")
        if issue_date < indent.indent_date:
            raise HTTPException(422, "Issue date cannot be before the indent date")

        request_map = {line.id: line for line in indent.lines}
        supplied = {entry.indent_line_id: entry for entry in payload.lines}
        expected_ids = set(request_map)
        if set(supplied) != expected_ids:
            missing = expected_ids - set(supplied)
            extra = set(supplied) - expected_ids
            detail = []
            if missing:
                detail.append(f"missing lines: {sorted(missing)}")
            if extra:
                detail.append(f"unknown lines: {sorted(extra)}")
            raise HTTPException(422, "Issue quantities must be supplied for every indent line (0 is valid); " + ", ".join(detail))

        quantities: dict[int, Decimal] = {}
        item_by_line: dict[int, Item] = {}
        unit_by_item: dict[int, Unit] = {}
        for line_id in sorted(expected_ids):
            indent_line = request_map[line_id]
            requested = Decimal(indent_line.requested_quantity)
            issued = Decimal(supplied[line_id].issued_quantity)
            if issued > requested:
                raise HTTPException(
                    422,
                    f"Issued quantity {issued} exceeds requested quantity {requested} for item line {line_id}",
                )
            item = await self.session.get(Item, indent_line.item_id)
            if item is None:
                raise HTTPException(404, f"Item {indent_line.item_id} not found")
            category = await self.session.get(Category, item.category_id)
            if category is None or category.type != "CONSUMABLE":
                raise HTTPException(422, f"Only consumable issues are supported in this module: {item.code}")
            unit = await self.session.get(Unit, item.unit_id)
            if unit is None:
                raise HTTPException(409, f"Item {item.code} has no valid master unit")
            quantities[line_id] = issued
            item_by_line[line_id] = item
            unit_by_item[item.id] = unit

        posting_group_id = uuid4()
        issue_lines: list[IssueLine] = []
        now = datetime.now(timezone.utc)

        async with self.session.begin_nested():
            # Create and lock all stock-account rows in deterministic item order.
            item_ids = sorted({request_map[line_id].item_id for line_id in expected_ids})
            for item_id in item_ids:
                await self.session.execute(
                    pg_insert(StockAccount)
                    .values(
                        store_id=indent.store_id,
                        financial_year_id=indent.financial_year_id,
                        item_id=item_id,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["store_id", "financial_year_id", "item_id"]
                    )
                )
                account = await self.session.scalar(
                    select(StockAccount)
                    .where(
                        StockAccount.store_id == indent.store_id,
                        StockAccount.financial_year_id == indent.financial_year_id,
                        StockAccount.item_id == item_id,
                    )
                    .with_for_update()
                )
                if account is None:
                    raise HTTPException(500, "Unable to lock stock account")

            # After locks are acquired, validate all requested OUT quantities against current stock.
            for line_id in sorted(expected_ids):
                qty = quantities[line_id]
                if qty <= 0:
                    continue
                item = item_by_line[line_id]
                available = await self.stock.current_balance(
                    indent.store_id, indent.financial_year_id, item.id
                )
                if qty > available:
                    raise HTTPException(
                        409,
                        f"Insufficient stock for {item.code}: available {available}, requested issue {qty}",
                    )

            issue = Issue(
                issue_no=await self._next_number(),
                issue_date=issue_date,
                financial_year_id=indent.financial_year_id,
                indent_id=indent.id,
                source_store_id=indent.store_id,
                destination_office_id=indent.office_id,
                destination_section_id=indent.section_id,
                destination_type="SECTION" if indent.section_id else "OFFICE",
                status="FINALIZED",
                remarks=payload.remarks,
                posted_at=now,
                posting_group_id=posting_group_id,
            )
            self.session.add(issue)
            await self.session.flush()

            # First flush IssueLines so their IDs exist.  This lets the ledger
            # reference the real IssueLine immediately instead of using a
            # temporary reference_id=0 and updating it later.
            for line_id in sorted(expected_ids):
                indent_line = request_map[line_id]
                qty = quantities[line_id]
                item = item_by_line[line_id]
                unit = unit_by_item[item.id]
                issue_line = IssueLine(
                    issue_id=issue.id,
                    item_id=item.id,
                    unit_id=unit.id,
                    quantity=qty,
                    remarks=supplied[line_id].remarks,
                )
                issue_lines.append(issue_line)
                self.session.add(issue_line)
                indent_line.issued_quantity = qty

            await self.session.flush()

            for issue_line in issue_lines:
                if issue_line.quantity <= 0:
                    continue
                self.session.add(
                    StockMovement(
                        financial_year_id=indent.financial_year_id,
                        store_id=indent.store_id,
                        item_id=issue_line.item_id,
                        movement_date=issue_date,
                        movement_type="ISSUE",
                        quantity_in=Decimal("0"),
                        quantity_out=issue_line.quantity,
                        reference_type="ISSUE_LINE",
                        reference_id=issue_line.id,
                        reference_no=issue.issue_no,
                        posting_group_id=posting_group_id,
                    )
                )

            indent.status = "FINALIZED"
            await self.session.flush()

        await self.session.commit()

        # Reload the posted issue with its lines eagerly loaded.  This avoids
        # implicit relationship I/O when FastAPI/Pydantic serializes the
        # response from an AsyncSession.
        result = await self.session.execute(
            select(Issue)
            .options(selectinload(Issue.lines))
            .where(Issue.id == issue.id)
        )
        return result.scalar_one()

    async def _next_number(self) -> str:
        from sqlalchemy import text
        value = await self.session.scalar(text("SELECT nextval('issue_no_seq')"))
        return f"ISS-{int(value):06d}"
