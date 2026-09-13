from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.financial_year import FinancialYear
from app.models.issue import Issue, IssueLine
from app.models.stock import StockAccount, StockMovement
from app.models.stock_return import StockReturn, StockReturnLine
from app.models.store import Store
from app.models.unit import Unit
from app.models.item import Item
from app.repositories.stock_return import StockReturnRepository
from app.schemas.stock_return import StockReturnCreate


class StockReturnService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = StockReturnRepository(session)

    async def create(self, payload: StockReturnCreate, actor_id: int | None = None) -> StockReturn:
        fy = await self.session.get(FinancialYear, payload.financial_year_id)
        store = await self.session.get(Store, payload.store_id)
        if actor_id is not None:
            from app.services.authorization import AuthorizationService
            auth = AuthorizationService(self.session)
            await auth.require_permission(actor_id, "STOCK_RETURN")
            await auth.require_store_assignment(actor_id, payload.store_id)
        if fy is None:
            raise HTTPException(404, "Financial year not found")
        if store is None:
            raise HTTPException(404, "Store not found")
        if fy.is_closed:
            raise HTTPException(409, "Financial year is closed")
        if not (fy.start_date <= payload.return_date <= fy.end_date):
            raise HTTPException(422, "Return date is outside the financial year")

        issue_result = await self.session.execute(
            select(Issue)
            .options(selectinload(Issue.lines))
            .where(Issue.id == payload.original_issue_id)
        )
        issue = issue_result.scalar_one_or_none()
        if issue is None:
            raise HTTPException(404, "Original issue not found")
        if issue.status != "FINALIZED":
            raise HTTPException(409, "Only finalized issues can be returned")
        if payload.store_id != issue.source_store_id:
            raise HTTPException(422, "Return store must be the original issuing store")

        if payload.returning_office_id is None:
            returning_office_id = issue.destination_office_id
        else:
            returning_office_id = payload.returning_office_id
            if returning_office_id != issue.destination_office_id:
                raise HTTPException(422, "Returning office does not match the original issue destination")

        if payload.returning_section_id is None:
            returning_section_id = issue.destination_section_id
        else:
            returning_section_id = payload.returning_section_id
            if returning_section_id != issue.destination_section_id:
                raise HTTPException(422, "Returning section does not match the original issue destination")

        issue_lines = {line.id: line for line in issue.lines}
        supplied_ids = [line.original_issue_line_id for line in payload.lines]
        if len(supplied_ids) != len(set(supplied_ids)):
            raise HTTPException(422, "Duplicate original issue line in return")

        return_lines: list[StockReturnLine] = []
        for request_line in payload.lines:
            issue_line = issue_lines.get(request_line.original_issue_line_id)
            if issue_line is None:
                raise HTTPException(
                    422,
                    f"Issue line {request_line.original_issue_line_id} does not belong to the original issue",
                )
            item = await self.session.get(Item, issue_line.item_id)
            unit = await self.session.get(Unit, issue_line.unit_id)
            if item is None or unit is None:
                raise HTTPException(409, "Original issue line has invalid item or unit")
            category = await self.session.get(Category, item.category_id)
            if category is None or category.type != "CONSUMABLE":
                raise HTTPException(422, f"Only consumable returns are supported: {item.code}")
            return_lines.append(
                StockReturnLine(
                    original_issue_line_id=issue_line.id,
                    item_id=issue_line.item_id,
                    quantity=Decimal(request_line.quantity),
                    unit_id=issue_line.unit_id,
                    remarks=request_line.remarks,
                )
            )

        stock_return = StockReturn(
            return_no=await self._next_number(),
            return_date=payload.return_date,
            financial_year_id=payload.financial_year_id,
            store_id=payload.store_id,
            original_issue_id=payload.original_issue_id,
            returning_office_id=returning_office_id,
            returning_section_id=returning_section_id,
            status="OPEN",
            reason=payload.reason,
            remarks=payload.remarks,
            lines=return_lines,
        )
        self.session.add(stock_return)
        await self.session.commit()
        result = await self.repository.get(stock_return.id)
        if result is None:
            raise HTTPException(500, "Return could not be reloaded")
        return result

    async def verify(self, return_id: int, actor_id: int | None = None) -> StockReturn:
        stock_return = await self.repository.get(return_id, for_update=True)
        if stock_return is None:
            raise HTTPException(404, "Return not found")
        if actor_id is not None:
            from app.services.authorization import AuthorizationService
            auth = AuthorizationService(self.session)
            await auth.require_permission(actor_id, "STOCK_RETURN")
            await auth.require_store_assignment(actor_id, stock_return.store_id)
        if stock_return.status != "OPEN":
            raise HTTPException(409, f"Return is {stock_return.status} and cannot be verified")
        stock_return.status = "VERIFIED"
        stock_return.verified_at = datetime.now(timezone.utc)
        await self.session.commit()
        result = await self.repository.get(stock_return.id)
        if result is None:
            raise HTTPException(500, "Return could not be reloaded")
        return result

    async def post(self, return_id: int, actor_id: int | None = None) -> StockReturn:
        stock_return = await self.repository.get(return_id, for_update=True)
        if stock_return is None:
            raise HTTPException(404, "Return not found")
        if actor_id is not None:
            from app.services.authorization import AuthorizationService
            auth = AuthorizationService(self.session)
            await auth.require_permission(actor_id, "STOCK_RETURN")
            await auth.require_store_assignment(actor_id, stock_return.store_id)
        if stock_return.status != "VERIFIED":
            raise HTTPException(409, f"Return is {stock_return.status}; only VERIFIED returns can be posted")

        fy = await self.session.get(FinancialYear, stock_return.financial_year_id)
        if fy is None or fy.is_closed:
            raise HTTPException(409, "Financial year is missing or closed")
        if not (fy.start_date <= stock_return.return_date <= fy.end_date):
            raise HTTPException(422, "Return date is outside the financial year")

        # Lock original issue lines before calculating cumulative returns so two
        # concurrent returns cannot return more than was originally issued.
        issue_line_ids = sorted(line.original_issue_line_id for line in stock_return.lines)
        issue_result = await self.session.execute(
            select(IssueLine)
            .where(IssueLine.id.in_(issue_line_ids))
            .order_by(IssueLine.id)
            .with_for_update()
        )
        issue_lines = {line.id: line for line in issue_result.scalars().all()}
        if len(issue_lines) != len(issue_line_ids):
            raise HTTPException(409, "One or more original issue lines no longer exist")

        posting_group_id = uuid4()
        now = datetime.now(timezone.utc)

        async with self.session.begin_nested():
            item_ids = sorted({line.item_id for line in stock_return.lines})
            for item_id in item_ids:
                await self.session.execute(
                    pg_insert(StockAccount)
                    .values(
                        store_id=stock_return.store_id,
                        financial_year_id=stock_return.financial_year_id,
                        item_id=item_id,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["store_id", "financial_year_id", "item_id"]
                    )
                )
                account = await self.session.scalar(
                    select(StockAccount)
                    .where(
                        StockAccount.store_id == stock_return.store_id,
                        StockAccount.financial_year_id == stock_return.financial_year_id,
                        StockAccount.item_id == item_id,
                    )
                    .with_for_update()
                )
                if account is None:
                    raise HTTPException(500, "Unable to lock stock account")

            existing = await self.session.scalar(
                select(StockMovement.id).where(
                    StockMovement.reference_type == "RETURN_LINE",
                    StockMovement.reference_id.in_([line.id for line in stock_return.lines]),
                    StockMovement.movement_type == "RETURN",
                ).limit(1)
            )
            if existing is not None:
                raise HTTPException(409, "Return has already been posted")

            for line in stock_return.lines:
                original = issue_lines[line.original_issue_line_id]
                already_returned = await self.session.scalar(
                    select(func.coalesce(func.sum(StockReturnLine.quantity), 0))
                    .join(StockReturn, StockReturn.id == StockReturnLine.return_id)
                    .where(
                        StockReturnLine.original_issue_line_id == original.id,
                        StockReturn.status == "POSTED",
                    )
                )
                already_returned = Decimal(already_returned or 0)
                new_total = already_returned + Decimal(line.quantity)
                issued_quantity = Decimal(original.quantity)
                if new_total > issued_quantity:
                    raise HTTPException(
                        422,
                        f"Return quantity {line.quantity} exceeds remaining returnable quantity "
                        f"{issued_quantity - already_returned} for issue line {original.id}",
                    )

                self.session.add(
                    StockMovement(
                        financial_year_id=stock_return.financial_year_id,
                        store_id=stock_return.store_id,
                        item_id=line.item_id,
                        movement_date=stock_return.return_date,
                        movement_type="RETURN",
                        quantity_in=line.quantity,
                        quantity_out=Decimal("0"),
                        reference_type="RETURN_LINE",
                        reference_id=line.id,
                        reference_no=stock_return.return_no,
                        posting_group_id=posting_group_id,
                        remarks=line.remarks,
                    )
                )

            stock_return.status = "POSTED"
            stock_return.posted_at = now
            stock_return.posting_group_id = posting_group_id
            await self.session.flush()

        await self.session.commit()
        result = await self.repository.get(stock_return.id)
        if result is None:
            raise HTTPException(500, "Return could not be reloaded")
        return result

    async def get(self, return_id: int) -> StockReturn:
        stock_return = await self.repository.get(return_id)
        if stock_return is None:
            raise HTTPException(404, "Return not found")
        return stock_return

    async def list(self, store_id: int | None = None, status: str | None = None) -> list[StockReturn]:
        return await self.repository.list(store_id, status)

    async def _next_number(self) -> str:
        value = await self.session.scalar(text("SELECT nextval('return_no_seq')"))
        return f"RET-{int(value):06d}"
