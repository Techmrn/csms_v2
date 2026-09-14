from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.asset import Asset, AssetDetail, AssetMovement
from app.models.category import Category
from app.models.financial_year import FinancialYear
from app.models.item import Item
from app.models.stock import OpeningStock, OpeningStockLine, StockAccount, StockMovement
from app.models.store import Store
from app.models.unit import Unit
from app.repositories.stock import StockRepository
from app.schemas.stock import OpeningStockCreate, OpeningAssetInput


class StockService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = StockRepository(session)

    async def _validate_opening_payload(self, payload: OpeningStockCreate, actor_id: int):
        from app.services.authorization import AuthorizationService

        auth = AuthorizationService(self.session)
        await auth.require_permission(actor_id, "STOCK_OPENING_CREATE")
        await auth.require_store_assignment(actor_id, payload.store_id)

        fy = await self.session.get(FinancialYear, payload.financial_year_id)
        store = await self.session.get(Store, payload.store_id)
        if fy is None:
            raise HTTPException(status_code=404, detail="Financial year not found")
        if store is None:
            raise HTTPException(status_code=404, detail="Store not found")
        if fy.is_closed:
            raise HTTPException(status_code=409, detail="Financial year is closed")
        if not (fy.start_date <= payload.opening_date <= fy.end_date):
            raise HTTPException(status_code=422, detail="Opening date is outside the financial year")

        existing_items = await self.session.scalars(
            select(OpeningStockLine.item_id)
            .join(OpeningStock, OpeningStock.id == OpeningStockLine.opening_stock_id)
            .where(
                OpeningStock.store_id == payload.store_id,
                OpeningStock.financial_year_id == payload.financial_year_id,
                OpeningStockLine.item_id.in_([line.item_id for line in payload.lines]),
            )
        )
        existing_item_ids = set(existing_items.all())
        if existing_item_ids:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Opening stock already exists for item(s) "
                    + ", ".join(str(item_id) for item_id in sorted(existing_item_ids))
                    + " for this store and financial year. Each item can be opened only once."
                ),
            )

        seen_items: set[int] = set()
        asset_nos: set[str] = set()
        serial_nos: set[str] = set()
        prepared: list[tuple[OpeningStockLine, Item, Category, Unit, list[OpeningAssetInput]]] = []

        for line in payload.lines:
            if line.item_id in seen_items:
                raise HTTPException(status_code=422, detail=f"Duplicate item {line.item_id} in opening stock")
            seen_items.add(line.item_id)

            item = await self.session.get(Item, line.item_id)
            unit = await self.session.get(Unit, line.unit_id)
            if item is None or not item.is_active:
                raise HTTPException(status_code=404, detail=f"Item {line.item_id} not found or inactive")
            if unit is None:
                raise HTTPException(status_code=404, detail=f"Unit {line.unit_id} not found")
            if unit.id != item.unit_id:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unit {unit.code} is not the master unit for item {item.code}",
                )

            category = await self.session.get(Category, item.category_id)
            if category is None or category.type not in ("CONSUMABLE", "ASSET"):
                raise HTTPException(status_code=422, detail=f"Unsupported category for item {item.code}")

            asset_inputs = line.asset_details or []
            if category.type == "CONSUMABLE":
                if asset_inputs:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Consumable item {item.code} cannot contain asset details",
                    )
            else:
                if line.quantity != line.quantity.to_integral_value():
                    raise HTTPException(
                        status_code=422,
                        detail=f"Asset opening quantity must be a whole number for {item.code}",
                    )
                expected = int(line.quantity)
                if len(asset_inputs) != expected:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"Asset opening for {item.code} requires exactly {expected} asset records; "
                            f"received {len(asset_inputs)}"
                        ),
                    )
                for data in asset_inputs:
                    if data.asset_no in asset_nos:
                        raise HTTPException(status_code=422, detail=f"Duplicate asset number {data.asset_no}")
                    asset_nos.add(data.asset_no)
                    if data.serial_no:
                        normalized = data.serial_no.strip()
                        if normalized in serial_nos:
                            raise HTTPException(status_code=422, detail=f"Duplicate serial number {data.serial_no}")
                        serial_nos.add(normalized)

                    existing_asset = await self.session.scalar(
                        select(Asset.id).where(Asset.asset_no == data.asset_no).limit(1)
                    )
                    if existing_asset is not None:
                        raise HTTPException(
                            status_code=422,
                            detail=f"Asset number {data.asset_no} already exists",
                        )
                    if data.serial_no:
                        existing_serial = await self.session.scalar(
                            select(Asset.id).where(Asset.serial_no == data.serial_no).limit(1)
                        )
                        if existing_serial is not None:
                            raise HTTPException(
                                status_code=422,
                                detail=f"Serial number {data.serial_no} already exists",
                            )

            prepared.append(
                (
                    OpeningStockLine(
                        store_id=payload.store_id,
                        financial_year_id=payload.financial_year_id,
                        item_id=item.id,
                        quantity=line.quantity,
                        unit_id=unit.id,
                        asset_details=[x.model_dump(mode="json") for x in asset_inputs] or None,
                        remarks=line.remarks,
                    ),
                    item,
                    category,
                    unit,
                    asset_inputs,
                )
            )

        return fy, store, prepared

    async def _build_opening(self, payload: OpeningStockCreate, actor_id: int) -> OpeningStock:
        _, _, prepared = await self._validate_opening_payload(payload, actor_id)
        opening_no = await self._next_opening_number(payload.financial_year_id)
        opening = OpeningStock(
            opening_no=opening_no,
            opening_date=payload.opening_date,
            financial_year_id=payload.financial_year_id,
            store_id=payload.store_id,
            status="OPEN",
            remarks=payload.remarks,
            created_by=actor_id,
            lines=[row[0] for row in prepared],
        )
        self.session.add(opening)
        await self.session.flush()
        return opening

    async def create_opening(self, payload: OpeningStockCreate, actor_id: int) -> OpeningStock:
        opening = await self._build_opening(payload, actor_id)
        await self.session.commit()
        await self.session.refresh(opening)
        return opening

    async def create_and_post_opening(self, payload: OpeningStockCreate, actor_id: int) -> OpeningStock:
        opening = await self._build_opening(payload, actor_id)
        return await self.post_opening(opening.id, actor_id)

    async def post_opening(self, opening_id: int, actor_id: int) -> OpeningStock:
        from app.services.authorization import AuthorizationService

        auth = AuthorizationService(self.session)
        await auth.require_permission(actor_id, "STOCK_OPENING_CREATE")

        result = await self.session.execute(
            select(OpeningStock)
            .options(selectinload(OpeningStock.lines))
            .where(OpeningStock.id == opening_id)
            .with_for_update()
        )
        opening = result.scalar_one_or_none()
        if opening is None:
            raise HTTPException(status_code=404, detail="Opening stock not found")
        await auth.require_store_assignment(actor_id, opening.store_id)

        if opening.status != "OPEN":
            raise HTTPException(status_code=409, detail=f"Opening stock is {opening.status}, not OPEN")

        fy = await self.session.get(FinancialYear, opening.financial_year_id)
        if fy is None or fy.is_closed:
            raise HTTPException(status_code=409, detail="Financial year is missing or closed")
        if not (fy.start_date <= opening.opening_date <= fy.end_date):
            raise HTTPException(status_code=422, detail="Opening date is outside the financial year")

        async with self.session.begin_nested():
            posting_group_id = uuid4()

            for line in opening.lines:
                item = await self.session.get(Item, line.item_id)
                if item is None:
                    raise HTTPException(status_code=404, detail=f"Item {line.item_id} not found")
                category = await self.session.get(Category, item.category_id)
                if category is None:
                    raise HTTPException(status_code=409, detail=f"Item {item.id} has no valid category")

                if category.type == "CONSUMABLE":
                    await self.session.execute(
                        pg_insert(StockAccount)
                        .values(
                            store_id=opening.store_id,
                            financial_year_id=opening.financial_year_id,
                            item_id=line.item_id,
                        )
                        .on_conflict_do_nothing(
                            index_elements=["store_id", "financial_year_id", "item_id"]
                        )
                    )
                    account = await self.session.scalar(
                        select(StockAccount)
                        .where(
                            StockAccount.store_id == opening.store_id,
                            StockAccount.financial_year_id == opening.financial_year_id,
                            StockAccount.item_id == line.item_id,
                        )
                        .with_for_update()
                    )
                    if account is None:
                        raise HTTPException(status_code=500, detail="Unable to lock stock account")

                    duplicate = await self.session.scalar(
                        select(StockMovement.id)
                        .where(
                            StockMovement.reference_type == "OPENING_STOCK_LINE",
                            StockMovement.reference_id == line.id,
                            StockMovement.item_id == line.item_id,
                            StockMovement.movement_type == "OPENING",
                        )
                        .limit(1)
                    )
                    if duplicate is not None:
                        raise HTTPException(status_code=409, detail="Opening stock is already posted")

                    self.session.add(
                        StockMovement(
                            financial_year_id=opening.financial_year_id,
                            store_id=opening.store_id,
                            item_id=line.item_id,
                            movement_date=opening.opening_date,
                            movement_type="OPENING",
                            quantity_in=line.quantity,
                            quantity_out=Decimal("0"),
                            reference_type="OPENING_STOCK_LINE",
                            reference_id=line.id,
                            reference_no=opening.opening_no,
                            posting_group_id=posting_group_id,
                            remarks=line.remarks,
                            created_by=actor_id,
                        )
                    )
                else:
                    details = line.asset_details or []
                    if int(line.quantity) != len(details):
                        raise HTTPException(
                            status_code=422,
                            detail=f"Asset opening details do not match quantity for item {item.code}",
                        )

                    for raw in details:
                        data = OpeningAssetInput.model_validate(raw)
                        existing = await self.session.scalar(
                            select(Asset.id).where(Asset.asset_no == data.asset_no).limit(1)
                        )
                        if existing is not None:
                            raise HTTPException(
                                status_code=409,
                                detail=f"Asset number {data.asset_no} already exists",
                            )
                        if data.serial_no:
                            existing_serial = await self.session.scalar(
                                select(Asset.id).where(Asset.serial_no == data.serial_no).limit(1)
                            )
                            if existing_serial is not None:
                                raise HTTPException(
                                    status_code=409,
                                    detail=f"Serial number {data.serial_no} already exists",
                                )

                        asset = Asset(
                            asset_no=data.asset_no,
                            item_id=item.id,
                            serial_no=data.serial_no,
                            current_store_id=opening.store_id,
                            status="IN_STOCK",
                            acquisition_financial_year_id=opening.financial_year_id,
                            created_by=actor_id,
                            updated_by=actor_id,
                            remarks=data.remarks,
                        )
                        self.session.add(asset)
                        await self.session.flush()

                        self.session.add(
                            AssetDetail(
                                asset_id=asset.id,
                                make=data.make,
                                model=data.model,
                                purchase_date=data.purchase_date,
                                purchase_reference=data.purchase_reference,
                                purchase_value=data.purchase_value,
                                warranty_expiry_date=data.warranty_expiry_date,
                                technical_specifications=data.technical_specifications,
                                remarks=data.remarks,
                            )
                        )
                        self.session.add(
                            AssetMovement(
                                asset_id=asset.id,
                                movement_type="OPENING",
                                to_store_id=opening.store_id,
                                reference_type="OPENING_STOCK_LINE",
                                reference_id=line.id,
                                reference_document=opening.opening_no,
                                movement_date=opening.opening_date,
                                created_by=actor_id,
                                remarks="Existing asset entered as opening stock",
                            )
                        )

            opening.status = "POSTED"
            opening.posted_by = actor_id
            opening.posting_group_id = posting_group_id
            opening.posted_at = datetime.now(timezone.utc)

        await self.session.commit()
        result = await self.session.execute(
            select(OpeningStock)
            .options(selectinload(OpeningStock.lines))
            .where(OpeningStock.id == opening.id)
        )
        return result.scalar_one()

    async def current_stock(self, store_id: int, financial_year_id: int, item_id: int | None = None):
        return await self.repository.balances(store_id, financial_year_id, item_id)

    async def current_balance(self, store_id: int, financial_year_id: int, item_id: int):
        return await self.repository.current_balance(store_id, financial_year_id, item_id)

    async def stock_register(
        self,
        store_id: int,
        financial_year_id: int,
        item_id: int,
        from_date: date | None = None,
        to_date: date | None = None,
    ):
        return await self.repository.register(
            store_id, financial_year_id, item_id, from_date, to_date
        )

    async def _next_opening_number(self, financial_year_id: int) -> str:
        prefix = f"OPN-{financial_year_id}"
        existing = await self.session.scalars(
            select(OpeningStock.opening_no)
            .where(OpeningStock.opening_no.like(f"{prefix}-%"))
            .order_by(OpeningStock.opening_no.desc())
        )
        last = existing.first()
        next_number = 1
        if last:
            try:
                next_number = int(last.rsplit("-", 1)[1]) + 1
            except (ValueError, IndexError):
                next_number = 1
        return f"{prefix}-{next_number:05d}"
