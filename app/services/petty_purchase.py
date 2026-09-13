from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.financial_year import FinancialYear
from app.models.indent import Indent, IndentLine
from app.models.issue import Issue, IssueLine
from app.models.item import Item
from app.models.petty_purchase import PettyPurchase, PettyPurchaseLine
from app.models.stock import StockAccount, StockMovement
from app.models.store import Store
from app.models.unit import Unit
from app.repositories.petty_purchase import PettyPurchaseRepository
from app.repositories.stock import StockRepository
from app.schemas.petty_purchase import (
    PettyPurchaseCreate,
    PettyPurchasePostRequest,
    PettyPurchaseVerifyRequest,
)
from app.services.authorization import AuthorizationService


class PettyPurchaseService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = PettyPurchaseRepository(session)
        self.stock = StockRepository(session)
        self.auth = AuthorizationService(session)

    async def create(self, payload: PettyPurchaseCreate, actor_id: int) -> PettyPurchase:
        await self.auth.require_permission(actor_id, "PETTY_PURCHASE_CREATE")
        await self.auth.require_store_assignment(actor_id, payload.store_id)

        fy = await self.session.get(FinancialYear, payload.financial_year_id)
        store = await self.session.get(Store, payload.store_id)
        if fy is None:
            raise HTTPException(404, "Financial year not found")
        if store is None:
            raise HTTPException(404, "Store not found")
        if fy.is_closed:
            raise HTTPException(409, "Financial year is closed")
        if not (fy.start_date <= payload.purchase_date <= fy.end_date):
            raise HTTPException(422, "Petty purchase date is outside the financial year")

        if payload.indent_id is not None:
            # Immediate issue is explicitly tied to this indent.  Detailed line
            # compatibility is validated below.
            result = await self.session.execute(
                select(Indent)
                .options(selectinload(Indent.lines))
                .where(Indent.id == payload.indent_id)
            )
            indent = result.scalar_one_or_none()
            if indent is None:
                raise HTTPException(404, "Indent not found")
            if indent.store_id != payload.store_id:
                raise HTTPException(422, "Petty purchase indent must belong to the same store")
            if indent.status not in {"RECORDED", "PROCESSING"}:
                raise HTTPException(409, f"Indent is {indent.status} and cannot receive an immediate petty-purchase issue")
            existing = await self.session.scalar(select(Issue.id).where(Issue.indent_id == indent.id).limit(1))
            if existing is not None:
                raise HTTPException(409, "The linked indent already has an issue")
            if not (fy.start_date <= indent.indent_date <= fy.end_date):
                raise HTTPException(422, "Linked indent is outside the selected financial year")
        else:
            indent = None

        seen: set[int] = set()
        lines: list[PettyPurchaseLine] = []
        total_immediate_issue = Decimal("0")
        indent_lines_by_item = {line.item_id: line for line in indent.lines} if indent is not None else {}

        for line in payload.lines:
            if line.item_id is not None:
                item = await self.session.get(Item, line.item_id)
                if item is None or not item.is_active:
                    raise HTTPException(404, f"Item {line.item_id} not found or inactive")
            else:
                # Create an explicit temporary consumable Item so the stock ledger
                # can keep a normal Item identity even for a one-off purchase.
                if not line.temporary_item_name:
                    raise HTTPException(422, "Temporary item name is required")
                unit = await self.session.get(Unit, line.unit_id)
                if unit is None:
                    raise HTTPException(404, f"Unit {line.unit_id} not found")
                consumable_category = await self.session.scalar(
                    select(Category).where(Category.type == "CONSUMABLE", Category.is_active.is_(True)).order_by(Category.id).limit(1)
                )
                if consumable_category is None:
                    raise HTTPException(409, "No active CONSUMABLE category is configured")

                item = await self.session.scalar(
                    select(Item).where(
                        Item.name == line.temporary_item_name,
                        Item.category_id == consumable_category.id,
                        Item.is_temporary.is_(True),
                        Item.is_active.is_(True),
                    ).limit(1)
                )
                if item is None:
                    seq_value = await self.session.scalar(text("SELECT nextval('temp_item_no_seq')"))
                    item = Item(
                        code=f"TEMP-{int(seq_value):06d}",
                        name=line.temporary_item_name,
                        category_id=consumable_category.id,
                        unit_id=unit.id,
                        specification=line.temporary_specification,
                        remarks="Created from petty purchase as temporary item",
                        is_active=True,
                        is_temporary=True,
                    )
                    self.session.add(item)
                    await self.session.flush()
                elif item.unit_id != unit.id:
                    raise HTTPException(422, f"Temporary item {item.code} already uses a different master unit")

            if item.id in seen:
                raise HTTPException(422, f"Duplicate item {item.code} in petty purchase")
            seen.add(item.id)

            category = await self.session.get(Category, item.category_id)
            if category is None or category.type != "CONSUMABLE":
                raise HTTPException(422, f"Petty purchase supports consumables only: {item.code}")
            unit = await self.session.get(Unit, line.unit_id)
            if unit is None:
                raise HTTPException(404, f"Unit {line.unit_id} not found")
            if unit.id != item.unit_id:
                raise HTTPException(422, f"Unit {unit.code} is not the master unit for item {item.code}")

            immediate = Decimal(line.immediate_issue_quantity)
            total_immediate_issue += immediate
            if immediate > 0:
                if indent is None:
                    raise HTTPException(422, "An indent is required when any petty-purchase quantity is issued immediately")
                indent_line = indent_lines_by_item.get(item.id)
                if indent_line is None:
                    raise HTTPException(422, f"Immediate issue item {item.code} is not present on the linked indent")
                if immediate > Decimal(indent_line.requested_quantity):
                    raise HTTPException(
                        422,
                        f"Immediate issue quantity {immediate} exceeds requested quantity {indent_line.requested_quantity} for item {item.code}",
                    )

            lines.append(
                PettyPurchaseLine(
                    item_id=item.id,
                    temporary_item_name=line.temporary_item_name,
                    temporary_specification=line.temporary_specification,
                    quantity=Decimal(line.quantity),
                    unit_id=unit.id,
                    unit_price=line.unit_price,
                    immediate_issue_quantity=immediate,
                    remarks=line.remarks,
                )
            )

        if total_immediate_issue <= 0 and payload.indent_id is not None:
            raise HTTPException(422, "Linked indent is allowed only when at least one line is for immediate issue")

        petty_purchase = PettyPurchase(
            petty_purchase_no=await self._next_number(),
            purchase_date=payload.purchase_date,
            financial_year_id=payload.financial_year_id,
            store_id=payload.store_id,
            indent_id=payload.indent_id,
            vendor_name=payload.vendor_name,
            reference_no=payload.reference_no,
            invoice_no=payload.invoice_no,
            status="OPEN",
            remarks=payload.remarks,
            created_by=actor_id,
            lines=lines,
        )
        self.session.add(petty_purchase)
        await self.session.commit()
        return await self.repository.get(petty_purchase.id)

    async def verify(self, petty_purchase_id: int, payload: PettyPurchaseVerifyRequest, actor_id: int) -> PettyPurchase:
        purchase = await self.repository.get(petty_purchase_id, for_update=True)
        if purchase is None:
            raise HTTPException(404, "Petty purchase not found")
        if purchase.status != "OPEN":
            raise HTTPException(409, f"Petty purchase is {purchase.status} and cannot be verified")

        await self.auth.require_permission(actor_id, "PETTY_PURCHASE_VERIFY")
        await self.auth.require_store_controller(actor_id, purchase.store_id)

        fy = await self.session.get(FinancialYear, purchase.financial_year_id)
        if fy is None or fy.is_closed:
            raise HTTPException(409, "Financial year is missing or closed")
        if not (fy.start_date <= purchase.purchase_date <= fy.end_date):
            raise HTTPException(422, "Petty purchase date is outside the financial year")

        purchase.status = "VERIFIED"
        purchase.verified_by = actor_id
        purchase.verified_at = datetime.now(timezone.utc)
        if payload.remarks:
            purchase.remarks = payload.remarks
        await self.session.commit()
        return await self.repository.get(purchase.id)

    async def post(self, petty_purchase_id: int, payload: PettyPurchasePostRequest, actor_id: int) -> PettyPurchase:
        await self.auth.require_permission(actor_id, "PETTY_PURCHASE_POST")
        purchase = await self.repository.get(petty_purchase_id, for_update=True)
        if purchase is None:
            raise HTTPException(404, "Petty purchase not found")
        if purchase.status != "VERIFIED":
            raise HTTPException(409, f"Petty purchase is {purchase.status}; only VERIFIED purchases can be posted")
        await self.auth.require_store_assignment(actor_id, purchase.store_id)

        fy = await self.session.get(FinancialYear, purchase.financial_year_id)
        if fy is None or fy.is_closed:
            raise HTTPException(409, "Financial year is missing or closed")
        if not (fy.start_date <= purchase.purchase_date <= fy.end_date):
            raise HTTPException(422, "Petty purchase date is outside the financial year")

        indent = None
        if purchase.indent_id is not None:
            result = await self.session.execute(
                select(Indent)
                .options(selectinload(Indent.lines))
                .where(Indent.id == purchase.indent_id)
                .with_for_update()
            )
            indent = result.scalar_one_or_none()
            if indent is None:
                raise HTTPException(404, "Linked indent not found")
            if indent.store_id != purchase.store_id:
                raise HTTPException(422, "Linked indent store does not match petty purchase store")
            if indent.status not in {"RECORDED", "PROCESSING"}:
                raise HTTPException(409, f"Linked indent is {indent.status} and cannot be finalized")
            existing_issue = await self.session.scalar(select(Issue.id).where(Issue.indent_id == indent.id).limit(1))
            if existing_issue is not None:
                raise HTTPException(409, "Linked indent already has an issue")

        item_ids = sorted({line.item_id for line in purchase.lines})
        purchase_by_item = {line.item_id: line for line in purchase.lines}
        current_before_purchase: dict[int, Decimal] = {}
        async with self.session.begin_nested():
            for item_id in item_ids:
                await self.session.execute(
                    pg_insert(StockAccount)
                    .values(
                        store_id=purchase.store_id,
                        financial_year_id=purchase.financial_year_id,
                        item_id=item_id,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["store_id", "financial_year_id", "item_id"]
                    )
                )
                account = await self.session.scalar(
                    select(StockAccount)
                    .where(
                        StockAccount.store_id == purchase.store_id,
                        StockAccount.financial_year_id == purchase.financial_year_id,
                        StockAccount.item_id == item_id,
                    )
                    .with_for_update()
                )
                if account is None:
                    raise HTTPException(500, "Unable to lock stock account")
                current_before_purchase[item_id] = await self.stock.current_balance(
                    purchase.store_id, purchase.financial_year_id, item_id
                )

            existing_movement = await self.session.scalar(
                select(StockMovement.id)
                .where(
                    StockMovement.reference_type == "PETTY_PURCHASE_LINE",
                    StockMovement.reference_id.in_([line.id for line in purchase.lines]),
                    StockMovement.movement_type == "PETTY_PURCHASE",
                )
                .limit(1)
            )
            if existing_movement is not None:
                raise HTTPException(409, "Petty purchase has already been posted")

            # If there is an immediate issue, the just-purchased quantity can be
            # used even when stock before the purchase is zero.
            for line in purchase.lines:
                available_after_purchase = current_before_purchase[line.item_id] + Decimal(line.quantity)
                immediate = Decimal(line.immediate_issue_quantity)
                if immediate > available_after_purchase:
                    raise HTTPException(
                        409,
                        f"Insufficient stock after petty purchase for item {line.item_id}: available {available_after_purchase}, requested immediate issue {immediate}",
                    )

            posting_group_id = uuid4()
            now = datetime.now(timezone.utc)
            for line in purchase.lines:
                qty = Decimal(line.quantity)
                self.session.add(
                    StockMovement(
                        financial_year_id=purchase.financial_year_id,
                        store_id=purchase.store_id,
                        item_id=line.item_id,
                        movement_date=purchase.purchase_date,
                        movement_type="PETTY_PURCHASE",
                        quantity_in=qty,
                        quantity_out=Decimal("0"),
                        reference_type="PETTY_PURCHASE_LINE",
                        reference_id=line.id,
                        reference_no=purchase.petty_purchase_no,
                        posting_group_id=posting_group_id,
                        remarks=line.remarks,
                    )
                )

            if purchase.indent_id is not None and any(Decimal(line.immediate_issue_quantity) > 0 for line in purchase.lines):
                if indent is None:
                    raise HTTPException(500, "Immediate-issue indent could not be loaded")
                request_map = {line.id: line for line in indent.lines}
                immediate_by_item = {line.item_id: Decimal(line.immediate_issue_quantity) for line in purchase.lines}
                quantities: dict[int, Decimal] = {}
                for indent_line in indent.lines:
                    quantities[indent_line.id] = immediate_by_item.get(indent_line.item_id, Decimal("0"))
                    if quantities[indent_line.id] > Decimal(indent_line.requested_quantity):
                        raise HTTPException(422, f"Immediate issue exceeds requested quantity for item line {indent_line.id}")

                issue = Issue(
                    issue_no=await self._next_issue_number(),
                    issue_date=purchase.purchase_date,
                    financial_year_id=purchase.financial_year_id,
                    indent_id=indent.id,
                    source_store_id=purchase.store_id,
                    destination_office_id=indent.office_id,
                    destination_section_id=indent.section_id,
                    destination_type="SECTION" if indent.section_id else "OFFICE",
                    reference_no=purchase.petty_purchase_no,
                    status="FINALIZED",
                    remarks=purchase.remarks,
                    created_by=purchase.created_by,
                    posted_by=actor_id,
                    posted_at=now,
                    posting_group_id=posting_group_id,
                )
                self.session.add(issue)
                await self.session.flush()

                issue_lines: list[IssueLine] = []
                for indent_line in sorted(indent.lines, key=lambda item: item.id):
                    qty = quantities[indent_line.id]
                    issue_line = IssueLine(
                        issue_id=issue.id,
                        item_id=indent_line.item_id,
                        unit_id=await self._item_unit_id(indent_line.item_id),
                        quantity=qty,
                        remarks=None,
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
                            financial_year_id=purchase.financial_year_id,
                            store_id=purchase.store_id,
                            item_id=issue_line.item_id,
                            movement_date=purchase.purchase_date,
                            movement_type="ISSUE",
                            quantity_in=Decimal("0"),
                            quantity_out=issue_line.quantity,
                            reference_type="ISSUE_LINE",
                            reference_id=issue_line.id,
                            reference_no=issue.issue_no,
                            posting_group_id=posting_group_id,
                            remarks=issue_line.remarks,
                        )
                    )
                indent.status = "FINALIZED"

            purchase.status = "POSTED"
            purchase.posted_by = actor_id
            purchase.posted_at = now
            purchase.posting_group_id = posting_group_id
            if payload.remarks:
                purchase.remarks = payload.remarks
            await self.session.flush()

        await self.session.commit()
        return await self.repository.get(purchase.id)

    async def get(self, petty_purchase_id: int) -> PettyPurchase:
        purchase = await self.repository.get(petty_purchase_id)
        if purchase is None:
            raise HTTPException(404, "Petty purchase not found")
        return purchase

    async def list(self, store_id: int | None = None, status: str | None = None) -> list[PettyPurchase]:
        return await self.repository.list(store_id, status)

    async def _next_number(self) -> str:
        value = await self.session.scalar(text("SELECT nextval('petty_purchase_no_seq')"))
        return f"PP-{int(value):06d}"

    async def _next_issue_number(self) -> str:
        value = await self.session.scalar(text("SELECT nextval('issue_no_seq')"))
        return f"ISS-{int(value):06d}"

    async def _item_unit_id(self, item_id: int) -> int:
        item = await self.session.get(Item, item_id)
        if item is None:
            raise HTTPException(404, f"Item {item_id} not found")
        return item.unit_id
