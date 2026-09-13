from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import typing

from fastapi import HTTPException

from app.models.asset import Asset, AssetMovement
from app.models.category import Category
from app.models.item import Item
from app.repositories.asset import AssetRepository


class AssetService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = AssetRepository(session)

    async def get(self, asset_id: int) -> Asset:
        asset = await self.repository.get(asset_id)
        if asset is None:
            raise HTTPException(404, "Asset not found")
        return asset

    async def list(self, actor_id: int, store_id: int | None = None, office_id: int | None = None,
                   status: str | None = None, item_id: int | None = None) -> typing.List[Asset]:
        from app.services.authorization import AuthorizationService
        auth = AuthorizationService(self.session)
        await auth.require_permission(actor_id, "ASSET_VIEW")

        visible_stores = await auth.get_visible_stores(actor_id)
        if store_id is not None:
            if visible_stores is not None and store_id not in visible_stores:
                raise HTTPException(403, "User is not authorized to view assets in this store")

        return await self.repository.list(store_id, office_id, status, item_id, visible_stores)

    async def movements(self, asset_id: int) -> typing.List[AssetMovement]:
        asset = await self.repository.get(asset_id)
        if asset is None:
            raise HTTPException(404, "Asset not found")
        result = await self.session.execute(
            select(AssetMovement)
            .where(AssetMovement.asset_id == asset_id)
            .order_by(AssetMovement.movement_date, AssetMovement.id)
        )
        return list(result.scalars().all())

    async def create_from_receipt(
        self,
        *,
        receipt_line_id: int,
        item_id: int,
        store_id: int,
        financial_year_id: int,
        receipt_date,
        asset_inputs,
        receipt_no: str,
        actor_user_id: int,
    ) -> typing.List[Asset]:
        item = await self.session.get(Item, item_id)
        if item is None:
            raise HTTPException(404, f"Item {item_id} not found")
        category = await self.session.get(Category, item.category_id)
        if category is None or category.type != "ASSET":
            raise HTTPException(422, f"Item {item.code} is not an asset item")

        created: list[Asset] = []
        for data in asset_inputs:
            asset = Asset(
                asset_no=await self._next_asset_number(),
                item_id=item.id,
                serial_no=data.serial_no,
                current_store_id=store_id,
                status="IN_STOCK",
                acquisition_financial_year_id=financial_year_id,
                created_by=actor_user_id,
                remarks=data.remarks,
            )
            self.session.add(asset)
            await self.session.flush()

            from app.models.asset import AssetDetail, ReceiptLineAsset
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
                ReceiptLineAsset(receipt_line_id=receipt_line_id, asset_id=asset.id)
            )
            self.session.add(
                AssetMovement(
                    asset_id=asset.id,
                    movement_type="RECEIPT",
                    to_store_id=store_id,
                    reference_type="RECEIPT_LINE",
                    reference_id=receipt_line_id,
                    reference_document=receipt_no,
                    movement_date=receipt_date,
                    created_by=actor_user_id,
                    remarks="Asset received into store",
                )
            )
            created.append(asset)

        return created

    async def _next_asset_number(self) -> str:
        from sqlalchemy import text
        value = await self.session.scalar(text("SELECT nextval('asset_no_seq')"))
        return f"AST-{int(value):06d}"
