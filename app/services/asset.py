from datetime import date
from typing import List

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetDetail, AssetMovement, AssetRepair, ReceiptLineAsset
from app.models.category import Category
from app.models.item import Item
from app.models.role import Role
from app.models.user import User, user_roles
from app.repositories.asset import AssetRepository
from app.schemas.asset import AssetLifecycleRequest, AssetRepairReturnRequest
from app.services.authorization import AuthorizationService


class AssetService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = AssetRepository(session)
        self.auth = AuthorizationService(session)

    async def get(self, asset_id: int, actor_id: int) -> Asset:
        await self.auth.require_permission(actor_id, "ASSET_VIEW")
        asset = await self.repository.get(asset_id)
        if asset is None:
            raise HTTPException(404, "Asset not found")
        await self.auth.require_asset_visibility(actor_id, asset)
        return asset

    async def list(
        self, actor_id: int, store_id: int | None = None, office_id: int | None = None,
        status: str | None = None, item_id: int | None = None
    ) -> List[Asset]:
        await self.auth.require_permission(actor_id, "ASSET_VIEW")
        user = await self.session.get(User, actor_id)
        if user is None or not user.is_active:
            raise HTTPException(403, "User is inactive or not found")
        role_codes = set((await self.session.scalars(
            select(Role.code).join(user_roles, user_roles.c.role_id == Role.id).where(user_roles.c.user_id == actor_id, Role.is_active.is_(True))
        )).all())
        department_wide = "DIRECTOR" in role_codes or "SUPERINTENDENT" in role_codes
        visible_stores = await self.auth.get_visible_stores(actor_id)

        if store_id is not None and not department_wide and (visible_stores is None or store_id not in visible_stores):
            raise HTTPException(403, "User is not authorized to view assets in this store")
        if office_id is not None and not department_wide and user.office_id != office_id:
            raise HTTPException(403, "User is not authorized to view assets in this office")

        allowed_offices = None if department_wide else ([user.office_id] if user.office_id is not None else [])
        return await self.repository.list(
            store_id=store_id, office_id=office_id, status=status, item_id=item_id,
            allowed_store_ids=visible_stores, allowed_office_ids=allowed_offices,
            department_wide=department_wide,
        )

    async def movements(self, asset_id: int, actor_id: int) -> List[AssetMovement]:
        await self.auth.require_permission(actor_id, "ASSET_VIEW")
        asset = await self.repository.get(asset_id)
        if asset is None:
            raise HTTPException(404, "Asset not found")
        await self.auth.require_asset_visibility(actor_id, asset)
        result = await self.session.execute(
            select(AssetMovement).where(AssetMovement.asset_id == asset_id).order_by(AssetMovement.movement_date, AssetMovement.id)
        )
        return list(result.scalars().all())

    async def create_from_receipt(
        self, *, receipt_line_id: int, item_id: int, store_id: int, financial_year_id: int,
        receipt_date, asset_inputs, receipt_no: str, actor_user_id: int
    ) -> List[Asset]:
        item = await self.session.get(Item, item_id)
        if item is None:
            raise HTTPException(404, f"Item {item_id} not found")
        category = await self.session.get(Category, item.category_id)
        if category is None or category.type != "ASSET":
            raise HTTPException(422, f"Item {item.code} is not an asset item")

        serials = [x.serial_no for x in asset_inputs if x.serial_no]
        if len(serials) != len(set(serials)):
            raise HTTPException(422, "Duplicate serial numbers in asset details")

        created: List[Asset] = []
        for data in asset_inputs:
            asset = Asset(
                asset_no=await self._next_asset_number(), item_id=item.id, serial_no=data.serial_no,
                current_store_id=store_id, status="IN_STOCK",
                acquisition_financial_year_id=financial_year_id, created_by=actor_user_id,
                remarks=data.remarks,
            )
            self.session.add(asset)
            await self.session.flush()
            self.session.add(AssetDetail(
                asset_id=asset.id, make=data.make, model=data.model, purchase_date=data.purchase_date,
                purchase_reference=data.purchase_reference, purchase_value=data.purchase_value,
                warranty_expiry_date=data.warranty_expiry_date, technical_specifications=data.technical_specifications,
                remarks=data.remarks,
            ))
            self.session.add(ReceiptLineAsset(receipt_line_id=receipt_line_id, asset_id=asset.id))
            self.session.add(AssetMovement(
                asset_id=asset.id, movement_type="RECEIPT", to_store_id=store_id,
                reference_type="RECEIPT_LINE", reference_id=receipt_line_id,
                reference_document=receipt_no, movement_date=receipt_date, created_by=actor_user_id,
                remarks="Asset received into store",
            ))
            created.append(asset)
        return created

    async def repair(self, asset_id: int, payload: AssetLifecycleRequest, actor_id: int) -> Asset:
        await self.auth.require_permission(actor_id, "ASSET_REPAIR")
        asset = await self._locked(asset_id)
        await self.auth.require_asset_visibility(actor_id, asset)
        if asset.status not in ("IN_STOCK", "ASSIGNED"):
            raise HTTPException(409, f"Asset cannot be sent to repair from status {asset.status}")
        active = await self.session.scalar(select(AssetRepair.id).where(AssetRepair.asset_id == asset.id, AssetRepair.status == "UNDER_REPAIR").limit(1))
        if active is not None:
            raise HTTPException(409, "Asset already has an active repair")
        action_date = payload.date or date.today()
        self.session.add(AssetRepair(
            asset_id=asset.id, previous_store_id=asset.current_store_id, previous_office_id=asset.current_office_id,
            previous_section_id=asset.current_section_id, previous_status=asset.status, sent_date=action_date,
            sent_by=actor_id, reason=payload.reason, status="UNDER_REPAIR"
        ))
        self.session.add(AssetMovement(
            asset_id=asset.id, movement_type="REPAIR", from_store_id=asset.current_store_id,
            from_office_id=asset.current_office_id, from_section_id=asset.current_section_id,
            movement_date=action_date, created_by=actor_id, remarks=payload.reason
        ))
        asset.status = "UNDER_REPAIR"
        asset.updated_by = actor_id
        await self.session.commit()
        return await self.get(asset.id, actor_id)

    async def repair_return(self, asset_id: int, payload: AssetRepairReturnRequest, actor_id: int) -> Asset:
        await self.auth.require_permission(actor_id, "ASSET_REPAIR_RETURN")
        asset = await self._locked(asset_id)
        await self.auth.require_asset_visibility(actor_id, asset)
        if asset.status != "UNDER_REPAIR":
            raise HTTPException(409, "Asset is not under repair")
        repair = await self.session.scalar(
            select(AssetRepair).where(AssetRepair.asset_id == asset.id, AssetRepair.status == "UNDER_REPAIR")
            .order_by(AssetRepair.id.desc()).limit(1).with_for_update()
        )
        if repair is None:
            raise HTTPException(409, "Active repair record not found")
        action_date = payload.date or date.today()
        repair.status = "COMPLETED"
        repair.return_date = action_date
        repair.returned_by = actor_id
        repair.resolution = payload.resolution
        asset.status = repair.previous_status
        asset.current_store_id = repair.previous_store_id
        asset.current_office_id = repair.previous_office_id
        asset.current_section_id = repair.previous_section_id
        asset.updated_by = actor_id
        self.session.add(AssetMovement(
            asset_id=asset.id, movement_type="REPAIR", to_store_id=asset.current_store_id,
            to_office_id=asset.current_office_id, to_section_id=asset.current_section_id,
            movement_date=action_date, created_by=actor_id, remarks=payload.resolution
        ))
        await self.session.commit()
        return await self.get(asset.id, actor_id)

    async def unserviceable(self, asset_id: int, payload: AssetLifecycleRequest, actor_id: int) -> Asset:
        await self.auth.require_permission(actor_id, "ASSET_UNSERVICEABLE")
        asset = await self._locked(asset_id)
        await self.auth.require_asset_visibility(actor_id, asset)
        await self.auth.require_asset_controller(actor_id, asset)
        if asset.status not in ("IN_STOCK", "ASSIGNED"):
            raise HTTPException(409, f"Cannot mark asset unserviceable from status {asset.status}")
        action_date = payload.date or date.today()
        self.session.add(AssetMovement(
            asset_id=asset.id, movement_type="UNSERVICEABLE", from_store_id=asset.current_store_id,
            from_office_id=asset.current_office_id, from_section_id=asset.current_section_id,
            movement_date=action_date, created_by=actor_id, remarks=payload.reason
        ))
        asset.status = "UNSERVICEABLE"
        asset.updated_by = actor_id
        await self.session.commit()
        return await self.get(asset.id, actor_id)

    async def dispose(self, asset_id: int, payload: AssetLifecycleRequest, actor_id: int) -> Asset:
        await self.auth.require_permission(actor_id, "ASSET_DISPOSE")
        asset = await self._locked(asset_id)
        await self.auth.require_asset_visibility(actor_id, asset)
        await self.auth.require_asset_controller(actor_id, asset)
        if asset.status != "UNSERVICEABLE":
            raise HTTPException(409, "Only UNSERVICEABLE assets can be disposed")
        action_date = payload.date or date.today()
        self.session.add(AssetMovement(
            asset_id=asset.id, movement_type="DISPOSAL", from_store_id=asset.current_store_id,
            from_office_id=asset.current_office_id, from_section_id=asset.current_section_id,
            movement_date=action_date, created_by=actor_id, remarks=payload.reason
        ))
        asset.status = "DISPOSED"
        asset.updated_by = actor_id
        await self.session.commit()
        return await self.get(asset.id, actor_id)

    async def lost(self, asset_id: int, payload: AssetLifecycleRequest, actor_id: int) -> Asset:
        await self.auth.require_permission(actor_id, "ASSET_LOST")
        asset = await self._locked(asset_id)
        await self.auth.require_asset_visibility(actor_id, asset)
        await self.auth.require_asset_controller(actor_id, asset)
        if asset.status in ("DISPOSED", "LOST"):
            raise HTTPException(409, f"Asset is already {asset.status}")
        action_date = payload.date or date.today()
        self.session.add(AssetMovement(
            asset_id=asset.id, movement_type="LOST", from_store_id=asset.current_store_id,
            from_office_id=asset.current_office_id, from_section_id=asset.current_section_id,
            movement_date=action_date, created_by=actor_id, remarks=payload.reason
        ))
        asset.status = "LOST"
        asset.updated_by = actor_id
        await self.session.commit()
        return await self.get(asset.id, actor_id)

    async def _locked(self, asset_id: int) -> Asset:
        asset = await self.session.scalar(select(Asset).where(Asset.id == asset_id).with_for_update())
        if asset is None:
            raise HTTPException(404, "Asset not found")
        return asset

    async def _next_asset_number(self) -> str:
        value = await self.session.scalar(text("SELECT nextval('asset_no_seq')"))
        return f"AST-{int(value):06d}"
