from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.financial_year import FinancialYear
from app.models.item import Item
from app.models.receipt import Receipt, ReceiptLine
from app.models.stock import StockAccount, StockMovement
from app.models.store import Store
from app.models.unit import Unit
from app.repositories.receipt import ReceiptRepository
from app.schemas.receipt import ReceiptCreate


class ReceiptService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = ReceiptRepository(session)

    async def create(self, payload: ReceiptCreate, actor_id: int | None = None) -> Receipt:
        fy = await self.session.get(FinancialYear, payload.financial_year_id)
        store = await self.session.get(Store, payload.store_id)
        if actor_id is not None:
            from app.services.authorization import AuthorizationService
            auth = AuthorizationService(self.session)
            await auth.require_permission(actor_id, "STOCK_RECEIPT")
            await auth.require_store_assignment(actor_id, payload.store_id)
        if fy is None:
            raise HTTPException(404, "Financial year not found")
        if store is None:
            raise HTTPException(404, "Store not found")
        if fy.is_closed:
            raise HTTPException(409, "Financial year is closed")
        if not (fy.start_date <= payload.receipt_date <= fy.end_date):
            raise HTTPException(422, "Receipt date is outside the financial year")

        seen_items: set[int] = set()
        lines: list[ReceiptLine] = []
        for line in payload.lines:
            if line.item_id in seen_items:
                raise HTTPException(422, f"Duplicate item {line.item_id} in receipt")
            seen_items.add(line.item_id)

            item = await self.session.get(Item, line.item_id)
            if item is None:
                raise HTTPException(404, f"Item {line.item_id} not found")
            category = await self.session.get(Category, item.category_id)
            if category is None:
                raise HTTPException(409, f"Item {item.code} has no valid category")
            if category.type != "CONSUMABLE":
                raise HTTPException(422, f"Receipt stock currently supports consumables only: {item.code}")

            unit = await self.session.get(Unit, line.unit_id)
            if unit is None:
                raise HTTPException(404, f"Unit {line.unit_id} not found")
            if unit.id != item.unit_id:
                raise HTTPException(
                    422, f"Unit {unit.code} is not the master unit for item {item.code}"
                )

            received = Decimal(line.received_quantity)
            accepted = Decimal(line.accepted_quantity)
            rejected = Decimal(line.rejected_quantity)
            if accepted + rejected > received:
                raise HTTPException(
                    422,
                    f"Accepted plus rejected quantity exceeds received quantity for item {item.code}",
                )

            lines.append(
                ReceiptLine(
                    item_id=item.id,
                    received_quantity=received,
                    accepted_quantity=accepted,
                    rejected_quantity=rejected,
                    unit_id=unit.id,
                    unit_price=line.unit_price,
                    remarks=line.remarks,
                )
            )

        receipt = Receipt(
            receipt_no=await self._next_number(),
            receipt_date=payload.receipt_date,
            financial_year_id=payload.financial_year_id,
            store_id=payload.store_id,
            source_type=payload.source_type,
            supplier_name=payload.supplier_name,
            purchase_reference=payload.purchase_reference,
            invoice_reference=payload.invoice_reference,
            challan_reference=payload.challan_reference,
            status="OPEN",
            remarks=payload.remarks,
            lines=lines,
        )
        self.session.add(receipt)
        await self.session.commit()
        result = await self.repository.get(receipt.id)
        if result is None:
            raise HTTPException(500, "Receipt could not be reloaded")
        return result

    async def verify(self, receipt_id: int, actor_id: int | None = None) -> Receipt:
        receipt = await self.repository.get(receipt_id, for_update=True)
        if receipt is None:
            raise HTTPException(404, "Receipt not found")
        if actor_id is not None:
            from app.services.authorization import AuthorizationService
            auth = AuthorizationService(self.session)
            await auth.require_permission(actor_id, "STOCK_RECEIPT")
            await auth.require_store_assignment(actor_id, receipt.store_id)
        if receipt.status != "OPEN":
            raise HTTPException(409, f"Receipt is {receipt.status} and cannot be verified")

        fy = await self.session.get(FinancialYear, receipt.financial_year_id)
        if fy is None or fy.is_closed:
            raise HTTPException(409, "Financial year is missing or closed")
        if not (fy.start_date <= receipt.receipt_date <= fy.end_date):
            raise HTTPException(422, "Receipt date is outside the financial year")

        for line in receipt.lines:
            pending = Decimal(line.received_quantity) - Decimal(line.accepted_quantity) - Decimal(line.rejected_quantity)
            if pending != 0:
                raise HTTPException(
                    422,
                    f"Receipt line {line.id} has {pending} quantity pending inspection",
                )

        receipt.status = "VERIFIED"
        receipt.verified_at = datetime.now(timezone.utc)
        await self.session.commit()
        result = await self.repository.get(receipt.id)
        if result is None:
            raise HTTPException(500, "Receipt could not be reloaded")
        return result

    async def post(self, receipt_id: int, actor_id: int | None = None) -> Receipt:
        receipt = await self.repository.get(receipt_id, for_update=True)
        if receipt is None:
            raise HTTPException(404, "Receipt not found")
        if actor_id is not None:
            from app.services.authorization import AuthorizationService
            auth = AuthorizationService(self.session)
            await auth.require_permission(actor_id, "STOCK_RECEIPT")
            await auth.require_store_assignment(actor_id, receipt.store_id)
        if receipt.status != "VERIFIED":
            raise HTTPException(409, f"Receipt is {receipt.status}; only VERIFIED receipts can be posted")

        fy = await self.session.get(FinancialYear, receipt.financial_year_id)
        if fy is None or fy.is_closed:
            raise HTTPException(409, "Financial year is missing or closed")

        if not (fy.start_date <= receipt.receipt_date <= fy.end_date):
            raise HTTPException(422, "Receipt date is outside the financial year")

        posting_group_id = uuid4()
        now = datetime.now(timezone.utc)

        async with self.session.begin_nested():
            item_ids = sorted({line.item_id for line in receipt.lines})
            for item_id in item_ids:
                await self.session.execute(
                    pg_insert(StockAccount)
                    .values(
                        store_id=receipt.store_id,
                        financial_year_id=receipt.financial_year_id,
                        item_id=item_id,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["store_id", "financial_year_id", "item_id"]
                    )
                )
                account = await self.session.scalar(
                    select(StockAccount)
                    .where(
                        StockAccount.store_id == receipt.store_id,
                        StockAccount.financial_year_id == receipt.financial_year_id,
                        StockAccount.item_id == item_id,
                    )
                    .with_for_update()
                )
                if account is None:
                    raise HTTPException(500, "Unable to lock stock account")

            existing_refs = await self.session.scalars(
                select(StockMovement.id).where(
                    StockMovement.reference_type == "RECEIPT_LINE",
                    StockMovement.reference_id.in_([line.id for line in receipt.lines]),
                    StockMovement.movement_type == "RECEIPT",
                )
            )
            if existing_refs.first() is not None:
                raise HTTPException(409, "Receipt has already been posted")

            for line in receipt.lines:
                accepted = Decimal(line.accepted_quantity)
                if accepted <= 0:
                    continue
                self.session.add(
                    StockMovement(
                        financial_year_id=receipt.financial_year_id,
                        store_id=receipt.store_id,
                        item_id=line.item_id,
                        movement_date=receipt.receipt_date,
                        movement_type="RECEIPT",
                        quantity_in=accepted,
                        quantity_out=Decimal("0"),
                        reference_type="RECEIPT_LINE",
                        reference_id=line.id,
                        reference_no=receipt.receipt_no,
                        posting_group_id=posting_group_id,
                        remarks=line.remarks,
                    )
                )

            receipt.status = "POSTED"
            receipt.posted_at = now
            receipt.posting_group_id = posting_group_id
            await self.session.flush()

        await self.session.commit()
        result = await self.repository.get(receipt.id)
        if result is None:
            raise HTTPException(500, "Receipt could not be reloaded")
        return result

    async def get(self, receipt_id: int) -> Receipt:
        receipt = await self.repository.get(receipt_id)
        if receipt is None:
            raise HTTPException(404, "Receipt not found")
        return receipt

    async def list(self, store_id: int | None = None, status: str | None = None) -> list[Receipt]:
        return await self.repository.list(store_id, status)

    async def _next_number(self) -> str:
        value = await self.session.scalar(text("SELECT nextval('receipt_no_seq')"))
        return f"REC-{int(value):06d}"
