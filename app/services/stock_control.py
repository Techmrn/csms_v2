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
from app.models.stock import StockAccount, StockMovement
from app.models.stock_control import (
    Adjustment,
    AdjustmentLine,
    StockVerification,
    StockVerificationLine,
    UnserviceableLine,
    UnserviceableMaterial,
)
from app.models.store import Store
from app.models.unit import Unit
from app.repositories.stock import StockRepository
from app.repositories.stock_control import (
    AdjustmentRepository,
    StockVerificationRepository,
    UnserviceableRepository,
)
from app.schemas.stock_control import (
    AdjustmentAuthorizeRequest,
    AdjustmentCreateFromVerificationRequest,
    AdjustmentPostRequest,
    StockVerificationAuthorizeRequest,
    StockVerificationCreate,
    UnserviceableActionRequest,
    UnserviceableCreate,
)
from app.services.authorization import AuthorizationService


def _now():
    return datetime.now(timezone.utc)


class StockVerificationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = StockVerificationRepository(session)
        self.stock = StockRepository(session)
        self.auth = AuthorizationService(session)

    async def create(self, payload: StockVerificationCreate, actor_id: int) -> StockVerification:
        await self.auth.require_permission(actor_id, "STOCK_VERIFICATION_CREATE")
        await self.auth.require_store_assignment(actor_id, payload.store_id)

        fy = await self.session.get(FinancialYear, payload.financial_year_id)
        store = await self.session.get(Store, payload.store_id)
        if fy is None:
            raise HTTPException(404, "Financial year not found")
        if store is None:
            raise HTTPException(404, "Store not found")
        if fy.is_closed:
            raise HTTPException(409, "Financial year is closed")
        if not (fy.start_date <= payload.verification_date <= fy.end_date):
            raise HTTPException(422, "Verification date is outside the financial year")

        seen_items: set[int] = set()
        item_ids: list[int] = []
        for line in payload.lines:
            if line.item_id in seen_items:
                raise HTTPException(422, f"Duplicate item {line.item_id} in stock verification")
            seen_items.add(line.item_id)
            item_ids.append(line.item_id)
        item_ids.sort()
        lines_by_item = {line.item_id: line for line in payload.lines}

        existing_verification = await self.session.scalar(
            select(StockVerification.id)
            .where(
                StockVerification.store_id == payload.store_id,
                StockVerification.status.in_(["COUNTED", "AUTHORIZED"]),
            )
            .limit(1)
        )
        if existing_verification is not None:
            raise HTTPException(409, "A stock verification is already open for this store")

        rows: list[StockVerificationLine] = []
        for item_id in item_ids:
            line = lines_by_item[item_id]
            item = await self.session.get(Item, item_id)
            if item is None or not item.is_active:
                raise HTTPException(404, f"Item {item_id} not found or inactive")
            category = await self.session.get(Category, item.category_id)
            if category is None or category.type != "CONSUMABLE":
                raise HTTPException(422, f"Stock verification supports consumables only: {item.code}")

            await self._ensure_account(payload.store_id, payload.financial_year_id, item_id)
            await self.session.scalar(
                select(StockAccount)
                .where(
                    StockAccount.store_id == payload.store_id,
                    StockAccount.financial_year_id == payload.financial_year_id,
                    StockAccount.item_id == item_id,
                )
                .with_for_update()
            )
            system_quantity = await self.stock.current_balance(
                payload.store_id, payload.financial_year_id, item_id
            )
            physical_quantity = Decimal(line.physical_quantity)
            rows.append(
                StockVerificationLine(
                    item_id=item_id,
                    system_quantity=system_quantity,
                    physical_quantity=physical_quantity,
                    variance_quantity=physical_quantity - system_quantity,
                    remarks=line.remarks,
                )
            )

        verification = StockVerification(
            verification_no=await self._next_number(),
            verification_date=payload.verification_date,
            financial_year_id=payload.financial_year_id,
            store_id=payload.store_id,
            status="COUNTED",
            remarks=payload.remarks,
            created_by=actor_id,
            counted_by=actor_id,
            counted_at=_now(),
            lines=rows,
        )
        self.session.add(verification)
        await self.session.commit()
        return await self.repository.get(verification.id)

    async def authorize(self, verification_id: int, payload: StockVerificationAuthorizeRequest, actor_id: int) -> StockVerification:
        await self.auth.require_permission(actor_id, "STOCK_VERIFY")
        verification = await self.repository.get(verification_id, for_update=True)
        if verification is None:
            raise HTTPException(404, "Stock verification not found")
        if verification.status != "COUNTED":
            raise HTTPException(409, f"Verification is {verification.status} and cannot be authorized")
        if verification.created_by == actor_id:
            raise HTTPException(403, "The person who recorded the verification cannot authorize it")
        await self.auth.require_store_controller(actor_id, verification.store_id)

        # A verification snapshot is only valid if stock has not changed after it
        # was captured. This prevents authorizing a variance against stale system data.
        for line in verification.lines:
            await self._ensure_account(verification.store_id, verification.financial_year_id, line.item_id)
            await self.session.scalar(
                select(StockAccount)
                .where(
                    StockAccount.store_id == verification.store_id,
                    StockAccount.financial_year_id == verification.financial_year_id,
                    StockAccount.item_id == line.item_id,
                )
                .with_for_update()
            )
            current = await self.stock.current_balance(
                verification.store_id, verification.financial_year_id, line.item_id
            )
            if current != Decimal(line.system_quantity):
                raise HTTPException(
                    409,
                    f"Stock for item {line.item_id} changed after verification snapshot; create a new verification",
                )

        verification.authorized_by = actor_id
        verification.authorized_at = _now()
        verification.remarks = payload.remarks or verification.remarks
        has_variance = any(Decimal(line.variance_quantity) != 0 for line in verification.lines)
        verification.status = "AUTHORIZED" if has_variance else "CLOSED"
        if not has_variance:
            verification.closed_by = actor_id
            verification.closed_at = _now()
        await self.session.commit()
        return await self.repository.get(verification.id)

    async def get(self, verification_id: int):
        value = await self.repository.get(verification_id)
        if value is None:
            raise HTTPException(404, "Stock verification not found")
        return value

    async def list(self, store_id=None, status=None):
        return await self.repository.list(store_id, status)

    async def _ensure_account(self, store_id: int, fy_id: int, item_id: int):
        await self.session.execute(
            pg_insert(StockAccount)
            .values(store_id=store_id, financial_year_id=fy_id, item_id=item_id)
            .on_conflict_do_nothing(
                index_elements=[StockAccount.store_id, StockAccount.financial_year_id, StockAccount.item_id]
            )
        )

    async def _next_number(self):
        value = await self.session.scalar(text("SELECT nextval('stock_verification_no_seq')"))
        return f"VER-{int(value):06d}"


class AdjustmentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = AdjustmentRepository(session)
        self.stock = StockRepository(session)
        self.auth = AuthorizationService(session)

    async def create_from_verification(self, payload: AdjustmentCreateFromVerificationRequest, actor_id: int) -> Adjustment:
        await self.auth.require_permission(actor_id, "STOCK_ADJUST_CREATE")
        verification = await self.session.scalar(
            select(StockVerification)
            .options(selectinload(StockVerification.lines))
            .where(StockVerification.id == payload.verification_id)
            .with_for_update()
        )
        if verification is None:
            raise HTTPException(404, "Stock verification not found")
        if verification.status != "AUTHORIZED":
            raise HTTPException(409, "Stock verification must be authorized before creating an adjustment")
        await self.auth.require_store_assignment(actor_id, verification.store_id)

        if payload.adjustment_type not in {"ADJUSTMENT_IN", "ADJUSTMENT_OUT"}:
            raise HTTPException(422, "Invalid adjustment type")

        expected_lines = [
            line for line in verification.lines
            if (Decimal(line.variance_quantity) > 0 and payload.adjustment_type == "ADJUSTMENT_IN")
            or (Decimal(line.variance_quantity) < 0 and payload.adjustment_type == "ADJUSTMENT_OUT")
        ]
        if not expected_lines:
            raise HTTPException(422, "No variance exists for the requested adjustment direction")

        existing = await self.session.scalar(
            select(Adjustment.id).where(
                Adjustment.verification_id == verification.id,
                Adjustment.adjustment_type == payload.adjustment_type,
            )
        )
        if existing is not None:
            raise HTTPException(409, "An adjustment of this type already exists for the verification")

        lines = [
            AdjustmentLine(
                item_id=line.item_id,
                quantity=abs(Decimal(line.variance_quantity)),
                unit_id=(await self.session.get(Item, line.item_id)).unit_id,
                remarks=line.remarks,
            )
            for line in expected_lines
        ]
        adjustment = Adjustment(
            adjustment_no=await self._next_number(),
            adjustment_date=verification.verification_date,
            financial_year_id=verification.financial_year_id,
            store_id=verification.store_id,
            verification_id=verification.id,
            adjustment_type=payload.adjustment_type,
            reason=payload.reason,
            reference_no=verification.verification_no,
            status="OPEN",
            remarks=payload.remarks,
            created_by=actor_id,
            lines=lines,
        )
        self.session.add(adjustment)
        await self.session.commit()
        return await self.repository.get(adjustment.id)

    async def authorize(self, adjustment_id: int, payload: AdjustmentAuthorizeRequest, actor_id: int) -> Adjustment:
        await self.auth.require_permission(actor_id, "STOCK_ADJUST_AUTHORIZE")
        adjustment = await self.repository.get(adjustment_id, for_update=True)
        if adjustment is None:
            raise HTTPException(404, "Adjustment not found")
        if adjustment.status != "OPEN":
            raise HTTPException(409, f"Adjustment is {adjustment.status} and cannot be authorized")
        if adjustment.created_by == actor_id:
            raise HTTPException(403, "The person who created the adjustment cannot authorize it")
        await self.auth.require_store_controller(actor_id, adjustment.store_id)
        adjustment.status = "AUTHORIZED"
        adjustment.authorized_by = actor_id
        adjustment.authorized_at = _now()
        adjustment.remarks = payload.remarks or adjustment.remarks
        await self.session.commit()
        return await self.repository.get(adjustment.id)

    async def post(self, adjustment_id: int, payload: AdjustmentPostRequest, actor_id: int) -> Adjustment:
        await self.auth.require_permission(actor_id, "STOCK_ADJUST_POST")
        adjustment = await self.repository.get(adjustment_id, for_update=True)
        if adjustment is None:
            raise HTTPException(404, "Adjustment not found")
        if adjustment.status != "AUTHORIZED":
            raise HTTPException(409, f"Adjustment is {adjustment.status} and cannot be posted")
        await self.auth.require_store_assignment(actor_id, adjustment.store_id)
        if adjustment.authorized_by == actor_id:
            raise HTTPException(403, "The authorizing officer cannot post the adjustment")

        verification = await self.session.scalar(
            select(StockVerification)
            .options(selectinload(StockVerification.lines))
            .where(StockVerification.id == adjustment.verification_id)
            .with_for_update()
        )
        if verification is None or verification.status != "AUTHORIZED":
            raise HTTPException(409, "The adjustment's verification is no longer authorized")

        verification_lines = {line.item_id: line for line in verification.lines}

        posting_group_id = uuid4()
        for line in sorted(adjustment.lines, key=lambda x: x.item_id):
            verification_line = verification_lines.get(line.item_id)
            if verification_line is None:
                raise HTTPException(409, f"Adjustment item {line.item_id} is not present in its verification")
            await self._ensure_account(adjustment.store_id, adjustment.financial_year_id, line.item_id)
            await self.session.scalar(
                select(StockAccount)
                .where(
                    StockAccount.store_id == adjustment.store_id,
                    StockAccount.financial_year_id == adjustment.financial_year_id,
                    StockAccount.item_id == line.item_id,
                )
                .with_for_update()
            )
            current = await self.stock.current_balance(
                adjustment.store_id, adjustment.financial_year_id, line.item_id
            )
            if current != Decimal(verification_line.system_quantity):
                raise HTTPException(
                    409,
                    f"Stock for item {line.item_id} changed after verification; create a new verification before posting the adjustment",
                )
            qty = Decimal(line.quantity)
            if adjustment.adjustment_type == "ADJUSTMENT_OUT" and current < qty:
                raise HTTPException(409, f"Insufficient stock for adjustment item {line.item_id}: available {current}, requested {qty}")
            duplicate = await self.session.scalar(
                select(StockMovement.id).where(
                    StockMovement.reference_type == "ADJUSTMENT_LINE",
                    StockMovement.reference_id == line.id,
                    StockMovement.item_id == line.item_id,
                    StockMovement.movement_type == adjustment.adjustment_type,
                ).limit(1)
            )
            if duplicate is not None:
                raise HTTPException(409, "Adjustment has already been posted")

            self.session.add(
                StockMovement(
                    financial_year_id=adjustment.financial_year_id,
                    store_id=adjustment.store_id,
                    item_id=line.item_id,
                    movement_date=adjustment.adjustment_date,
                    movement_type=adjustment.adjustment_type,
                    quantity_in=qty if adjustment.adjustment_type == "ADJUSTMENT_IN" else Decimal("0"),
                    quantity_out=qty if adjustment.adjustment_type == "ADJUSTMENT_OUT" else Decimal("0"),
                    reference_type="ADJUSTMENT_LINE",
                    reference_id=line.id,
                    reference_no=adjustment.adjustment_no,
                    posting_group_id=posting_group_id,
                    remarks=line.remarks,
                    created_by=actor_id,
                )
            )
        adjustment.status = "POSTED"
        adjustment.posted_by = actor_id
        adjustment.posted_at = _now()
        adjustment.posting_group_id = posting_group_id
        adjustment.remarks = payload.remarks or adjustment.remarks

        verification = await self.session.get(StockVerification, adjustment.verification_id, with_for_update=True)
        if verification is not None:
            posted_types = set((await self.session.scalars(
                select(Adjustment.adjustment_type)
                .where(Adjustment.verification_id == verification.id, Adjustment.status == "POSTED")
            )).all())
            needs_in = any(Decimal(line.variance_quantity) > 0 for line in verification.lines)
            needs_out = any(Decimal(line.variance_quantity) < 0 for line in verification.lines)
            if (not needs_in or "ADJUSTMENT_IN" in posted_types) and (not needs_out or "ADJUSTMENT_OUT" in posted_types):
                verification.status = "CLOSED"
                verification.closed_by = actor_id
                verification.closed_at = _now()

        await self.session.commit()
        return await self.repository.get(adjustment.id)

    async def get(self, adjustment_id: int):
        value = await self.repository.get(adjustment_id)
        if value is None:
            raise HTTPException(404, "Adjustment not found")
        return value

    async def list(self, store_id=None, status=None):
        return await self.repository.list(store_id, status)

    async def _ensure_account(self, store_id: int, fy_id: int, item_id: int):
        await self.session.execute(
            pg_insert(StockAccount)
            .values(store_id=store_id, financial_year_id=fy_id, item_id=item_id)
            .on_conflict_do_nothing(index_elements=[StockAccount.store_id, StockAccount.financial_year_id, StockAccount.item_id])
        )

    async def _next_number(self):
        value = await self.session.scalar(text("SELECT nextval('adjustment_no_seq')"))
        return f"ADJ-{int(value):06d}"


class UnserviceableService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = UnserviceableRepository(session)
        self.stock = StockRepository(session)
        self.auth = AuthorizationService(session)

    async def create(self, payload: UnserviceableCreate, actor_id: int) -> UnserviceableMaterial:
        await self.auth.require_permission(actor_id, "STOCK_UNSERVICEABLE_CREATE")
        await self.auth.require_store_assignment(actor_id, payload.store_id)

        fy = await self.session.get(FinancialYear, payload.financial_year_id)
        store = await self.session.get(Store, payload.store_id)
        if fy is None:
            raise HTTPException(404, "Financial year not found")
        if store is None:
            raise HTTPException(404, "Store not found")
        if fy.is_closed:
            raise HTTPException(409, "Financial year is closed")
        if not (fy.start_date <= payload.date <= fy.end_date):
            raise HTTPException(422, "Unserviceable date is outside the financial year")

        seen: set[int] = set()
        lines: list[UnserviceableLine] = []
        for line in payload.lines:
            if line.item_id in seen:
                raise HTTPException(422, f"Duplicate item {line.item_id} in unserviceable record")
            seen.add(line.item_id)
            item = await self.session.get(Item, line.item_id)
            if item is None or not item.is_active:
                raise HTTPException(404, f"Item {line.item_id} not found or inactive")
            category = await self.session.get(Category, item.category_id)
            if category is None or category.type != "CONSUMABLE":
                raise HTTPException(422, f"Unserviceable stock supports consumables only: {item.code}")
            unit = await self.session.get(Unit, line.unit_id)
            if unit is None:
                raise HTTPException(404, f"Unit {line.unit_id} not found")
            if unit.id != item.unit_id:
                raise HTTPException(422, f"Unit {unit.code} is not the master unit for item {item.code}")
            lines.append(
                UnserviceableLine(
                    item_id=line.item_id,
                    quantity=Decimal(line.quantity),
                    unit_id=line.unit_id,
                    reason=line.reason,
                    remarks=line.remarks,
                )
            )

        record = UnserviceableMaterial(
            reference_no=await self._next_number(),
            date=payload.date,
            financial_year_id=payload.financial_year_id,
            store_id=payload.store_id,
            status="REPORTED",
            reason=payload.reason,
            remarks=payload.remarks,
            reported_by=actor_id,
            lines=lines,
        )
        self.session.add(record)
        await self.session.commit()
        return await self.repository.get(record.id)

    async def verify(self, record_id: int, payload: UnserviceableActionRequest, actor_id: int) -> UnserviceableMaterial:
        await self.auth.require_permission(actor_id, "STOCK_VERIFY")
        record = await self.repository.get(record_id, for_update=True)
        if record is None:
            raise HTTPException(404, "Unserviceable record not found")
        if record.status != "REPORTED":
            raise HTTPException(409, f"Unserviceable record is {record.status} and cannot be verified")
        if record.reported_by == actor_id:
            raise HTTPException(403, "The person reporting unserviceable stock cannot verify it")
        await self.auth.require_store_controller(actor_id, record.store_id)
        record.status = "VERIFIED"
        record.verified_by = actor_id
        record.verified_at = _now()
        record.remarks = payload.remarks or record.remarks
        await self.session.commit()
        return await self.repository.get(record.id)

    async def authorize(self, record_id: int, payload: UnserviceableActionRequest, actor_id: int) -> UnserviceableMaterial:
        await self.auth.require_permission(actor_id, "STOCK_UNSERVICEABLE_AUTHORIZE")
        record = await self.repository.get(record_id, for_update=True)
        if record is None:
            raise HTTPException(404, "Unserviceable record not found")
        if record.status != "VERIFIED":
            raise HTTPException(409, f"Unserviceable record is {record.status} and cannot be authorized")
        await self.auth.require_store_controller(actor_id, record.store_id)
        if record.reported_by == actor_id:
            raise HTTPException(403, "The person reporting unserviceable stock cannot authorize it")
        record.status = "AUTHORIZED"
        record.authorized_by = actor_id
        record.authorized_at = _now()
        record.remarks = payload.remarks or record.remarks
        await self.session.commit()
        return await self.repository.get(record.id)

    async def post(self, record_id: int, payload: UnserviceableActionRequest, actor_id: int) -> UnserviceableMaterial:
        await self.auth.require_permission(actor_id, "STOCK_UNSERVICEABLE_POST")
        record = await self.repository.get(record_id, for_update=True)
        if record is None:
            raise HTTPException(404, "Unserviceable record not found")
        if record.status != "AUTHORIZED":
            raise HTTPException(409, f"Unserviceable record is {record.status} and cannot be posted")
        await self.auth.require_store_assignment(actor_id, record.store_id)
        if record.authorized_by == actor_id:
            raise HTTPException(403, "The authorizing officer cannot post unserviceable stock")

        posting_group_id = uuid4()
        for line in sorted(record.lines, key=lambda x: x.item_id):
            await self.session.execute(
                pg_insert(StockAccount)
                .values(store_id=record.store_id, financial_year_id=record.financial_year_id, item_id=line.item_id)
                .on_conflict_do_nothing(index_elements=[StockAccount.store_id, StockAccount.financial_year_id, StockAccount.item_id])
            )
            await self.session.scalar(
                select(StockAccount)
                .where(
                    StockAccount.store_id == record.store_id,
                    StockAccount.financial_year_id == record.financial_year_id,
                    StockAccount.item_id == line.item_id,
                )
                .with_for_update()
            )
            current = await self.stock.current_balance(record.store_id, record.financial_year_id, line.item_id)
            qty = Decimal(line.quantity)
            if current < qty:
                raise HTTPException(409, f"Insufficient stock for unserviceable item {line.item_id}: available {current}, requested {qty}")
            duplicate = await self.session.scalar(
                select(StockMovement.id).where(
                    StockMovement.reference_type == "UNSERVICEABLE_LINE",
                    StockMovement.reference_id == line.id,
                    StockMovement.item_id == line.item_id,
                    StockMovement.movement_type == "UNSERVICEABLE",
                ).limit(1)
            )
            if duplicate is not None:
                raise HTTPException(409, "Unserviceable record has already been posted")
            self.session.add(
                StockMovement(
                    financial_year_id=record.financial_year_id,
                    store_id=record.store_id,
                    item_id=line.item_id,
                    movement_date=record.date,
                    movement_type="UNSERVICEABLE",
                    quantity_in=Decimal("0"),
                    quantity_out=qty,
                    reference_type="UNSERVICEABLE_LINE",
                    reference_id=line.id,
                    reference_no=record.reference_no,
                    posting_group_id=posting_group_id,
                    remarks=line.reason or line.remarks or record.reason,
                    created_by=actor_id,
                )
            )
        record.status = "POSTED"
        record.posted_by = actor_id
        record.posted_at = _now()
        record.posting_group_id = posting_group_id
        record.remarks = payload.remarks or record.remarks
        await self.session.commit()
        return await self.repository.get(record.id)

    async def get(self, record_id: int):
        value = await self.repository.get(record_id)
        if value is None:
            raise HTTPException(404, "Unserviceable record not found")
        return value

    async def list(self, store_id=None, status=None):
        return await self.repository.list(store_id, status)

    async def _next_number(self):
        value = await self.session.scalar(text("SELECT nextval('unserviceable_no_seq')"))
        return f"UNS-{int(value):06d}"
