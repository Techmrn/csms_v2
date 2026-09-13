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
from app.models.item import Item
from app.models.office import Office
from app.models.requisition import CentralStoreRequisition
from app.models.stock import StockAccount, StockMovement
from app.models.store import Store
from app.models.transfer import StockTransfer, StockTransferLine, TransferDiscrepancy, TransferLineAsset
from app.models.asset import Asset, AssetMovement
from app.models.unit import Unit
from app.repositories.stock import StockRepository
from app.repositories.transfer import TransferRepository
from app.schemas.transfer import (
    TransferDispatchRequest,
    TransferReceiveRequest,
    TransferDiscrepancyResolutionRequest,
)
from app.services.authorization import AuthorizationService


class TransferService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = TransferRepository(session)
        self.auth = AuthorizationService(session)
        self.stock = StockRepository(session)

    async def dispatch(self, requisition_id: int, payload: TransferDispatchRequest, actor_id: int):
        await self.auth.require_permission(actor_id, "STOCK_TRANSFER_DISPATCH")
        requisition = await self.session.scalar(
            select(CentralStoreRequisition)
            .options(selectinload(CentralStoreRequisition.lines))
            .where(CentralStoreRequisition.id == requisition_id)
            .with_for_update()
        )
        if requisition is None:
            raise HTTPException(404, "Requisition not found")
        if requisition.status != "READY_FOR_TRANSFER":
            raise HTTPException(409, f"Requisition is {requisition.status}; dispatch is not allowed")

        source_store = await self.session.scalar(
            select(Store)
            .join(Office, Office.id == Store.office_id)
            .where(
                Store.store_type == "CENTRAL",
                Store.is_active.is_(True),
                Office.office_type == "DIRECTORATE",
            )
            .order_by(Store.id)
            .limit(1)
        )
        if source_store is None:
            raise HTTPException(409, "Central Store is not configured")
        await self.auth.require_store_assignment(actor_id, source_store.id)

        transfer_date = payload.transfer_date or date.today()
        source_fy = await self.session.get(FinancialYear, requisition.financial_year_id)
        if source_fy is None:
            raise HTTPException(404, "Financial year not found")
        if source_fy.is_closed:
            raise HTTPException(409, "Financial year is closed")
        if not (source_fy.start_date <= transfer_date <= source_fy.end_date):
            raise HTTPException(422, "Transfer date is outside the requisition financial year")

        supplied = {line.requisition_line_id: line for line in payload.lines}
        expected = {line.id: line for line in requisition.lines}
        missing = sorted(set(expected) - set(supplied))
        unknown = sorted(set(supplied) - set(expected))
        if missing or unknown:
            raise HTTPException(
                422,
                f"Dispatch quantities must be supplied for every requisition line; missing={missing}, unknown={unknown}",
            )

        item_ids = sorted({line.item_id for line in requisition.lines})
        item_categories = {}
        for item_id in item_ids:
            item = await self.session.get(Item, item_id)
            cat = await self.session.get(Category, item.category_id)
            item_categories[item_id] = cat.type
            if cat.type != "ASSET":
                await self._lock_stock_account(source_store.id, requisition.financial_year_id, item_id)

        dispatch_lines: list[StockTransferLine] = []
        total_dispatch = Decimal("0")
        locked_assets_by_line = {}
        global_asset_ids = set()
        
        for req_line in requisition.lines:
            supplied_line = supplied[req_line.id]
            qty = supplied_line.dispatch_quantity
            approved = req_line.approved_quantity or Decimal("0")
            if qty < 0:
                raise HTTPException(422, "Dispatch quantity cannot be negative")
            if qty > approved:
                raise HTTPException(
                    422,
                    f"Dispatch quantity {qty} exceeds approved quantity {approved} for item {req_line.item_id}",
                )
            
            cat_type = item_categories[req_line.item_id]
            if qty > 0:
                if cat_type == "ASSET":
                    asset_ids = supplied_line.asset_ids or []
                    if not asset_ids:
                        raise HTTPException(422, f"ASSET transfer requires asset_ids")
                    if len(asset_ids) != int(qty):
                        raise HTTPException(422, f"ASSET transfer quantity mismatch")
                    if len(asset_ids) != len(set(asset_ids)):
                        raise HTTPException(422, f"ASSET transfer contains duplicate asset IDs in the same line")
                    for aid in asset_ids:
                        if aid in global_asset_ids:
                            raise HTTPException(422, f"Asset ID {aid} cannot be transferred multiple times in the same transaction")
                        global_asset_ids.add(aid)
                    
                    locked_assets = []
                    for aid in asset_ids:
                        asset_row = await self.session.scalar(select(Asset).where(Asset.id == aid).with_for_update())
                        if not asset_row:
                            raise HTTPException(404, f"Asset ID {aid} not found")
                        if asset_row.item_id != req_line.item_id:
                            raise HTTPException(422, f"Asset ID {aid} does not match item")
                        if asset_row.current_store_id != source_store.id:
                            raise HTTPException(422, f"Asset ID {aid} is not in source store")
                        if asset_row.status != "IN_STOCK":
                            raise HTTPException(422, f"Asset ID {aid} is not IN_STOCK")
                        locked_assets.append(asset_row)
                    locked_assets_by_line[req_line.id] = locked_assets
                else:
                    if supplied_line.asset_ids:
                        raise HTTPException(422, f"CONSUMABLE transfer must not provide asset_ids")
                    available = await self.stock.current_balance(
                        source_store.id, requisition.financial_year_id, req_line.item_id
                    )
                    if qty > available:
                        raise HTTPException(
                            409,
                            f"Insufficient stock for item {req_line.item_id}: available {available}, requested dispatch {qty}",
                        )
            
            req_line.dispatched_quantity = qty
            total_dispatch += qty
            if qty > 0:
                item = await self.session.get(Item, req_line.item_id)
                unit = await self.session.get(Unit, item.unit_id)
                tline = StockTransferLine(
                    requisition_line_id=req_line.id,
                    item_id=req_line.item_id,
                    unit_id=unit.id,
                    quantity=qty,
                    remarks=req_line.remarks,
                )
                dispatch_lines.append(tline)
                tline._req_line_id = req_line.id

        if total_dispatch == 0:
            requisition.status = "CLOSED"
            requisition.closed_by = actor_id
            requisition.closed_at = datetime.now(timezone.utc)
            await self.session.commit()
            return None

        transfer = StockTransfer(
            transfer_no=await self._next_number(),
            transfer_date=transfer_date,
            financial_year_id=requisition.financial_year_id,
            source_store_id=source_store.id,
            destination_store_id=requisition.requesting_store_id,
            requisition_id=requisition.id,
            status="APPROVED",
            remarks=payload.remarks,
            created_by=actor_id,
            lines=dispatch_lines,
        )
        self.session.add(transfer)
        await self.session.flush()

        posting_group = uuid4()
        for line in transfer.lines:
            cat_type = item_categories[line.item_id]
            if cat_type == "ASSET":
                assets_for_line = locked_assets_by_line[line._req_line_id]
                for asset_row in assets_for_line:
                    self.session.add(TransferLineAsset(transfer_line_id=line.id, asset_id=asset_row.id))
                    asset_row.status = "ASSIGNED"
                    asset_row.current_store_id = None
                    asset_row.updated_by = actor_id
                    self.session.add(
                        AssetMovement(
                            asset_id=asset_row.id,
                            movement_type="TRANSFER",
                            from_store_id=source_store.id,
                            to_store_id=transfer.destination_store_id,
                            reference_type="TRANSFER_LINE",
                            reference_id=line.id,
                            reference_document=transfer.transfer_no,
                            movement_date=transfer_date,
                            created_by=actor_id,
                        )
                    )
            else:
                self.session.add(
                    StockMovement(
                        financial_year_id=requisition.financial_year_id,
                        store_id=source_store.id,
                        item_id=line.item_id,
                        movement_date=transfer_date,
                        movement_type="TRANSFER_OUT",
                        quantity_in=Decimal("0"),
                        quantity_out=line.quantity,
                        reference_type="TRANSFER_LINE",
                        reference_id=line.id,
                        reference_no=transfer.transfer_no,
                        posting_group_id=posting_group,
                        created_by=actor_id,
                    )
                )
        transfer.status = "DISPATCHED"
        transfer.dispatched_by = actor_id
        transfer.dispatched_at = datetime.now(timezone.utc)
        requisition.status = "DISPATCHED"
        if payload.remarks:
            requisition.remarks = payload.remarks
        await self.session.commit()
        return await self.repository.get(transfer.id)

    async def receive(self, transfer_id: int, payload: TransferReceiveRequest, actor_id: int):
        await self.auth.require_permission(actor_id, "STOCK_TRANSFER_RECEIVE")
        transfer = await self.repository.get(transfer_id, for_update=True)
        if transfer is None:
            raise HTTPException(404, "Transfer not found")
        if transfer.status != "DISPATCHED":
            raise HTTPException(409, f"Transfer is {transfer.status}; receipt is not allowed")
        await self.auth.require_store_assignment(actor_id, transfer.destination_store_id)

        destination_fy = await self._financial_year_for_date(payload.receive_date)
        if destination_fy is None:
            raise HTTPException(422, "No financial year matches the transfer receipt date")
        if destination_fy.is_closed:
            raise HTTPException(409, "Destination financial year is closed")

        supplied = {line.transfer_line_id: line.received_quantity for line in payload.lines}
        expected = {line.id: line for line in transfer.lines}
        missing = sorted(set(expected) - set(supplied))
        unknown = sorted(set(supplied) - set(expected))
        if missing or unknown:
            raise HTTPException(
                422,
                f"Receipt quantities must be supplied for every transfer line; missing={missing}, unknown={unknown}",
            )

        requisition = await self.session.scalar(
            select(CentralStoreRequisition)
            .options(selectinload(CentralStoreRequisition.lines))
            .where(CentralStoreRequisition.id == transfer.requisition_id)
            .with_for_update()
        )
        if requisition is None:
            raise HTTPException(409, "Requisition associated with transfer not found")

        posting_group = uuid4()
        discrepancy_found = False
        discrepancy_rows: list[TransferDiscrepancy] = []

        for line in transfer.lines:
            physical_qty = supplied[line.id]
            if physical_qty < 0:
                raise HTTPException(422, "Received quantity cannot be negative")

            posted_qty = min(physical_qty, line.quantity)
            item = await self.session.get(Item, line.item_id)
            cat = await self.session.get(Category, item.category_id)
            
            if cat.type == "ASSET" and physical_qty != line.quantity:
                raise HTTPException(422, "Discrepancy is not supported for ASSET transfers. Received quantity must match dispatched quantity.")

            if posted_qty > 0:
                if cat.type == "ASSET":
                    tlas = await self.session.scalars(select(TransferLineAsset).where(TransferLineAsset.transfer_line_id == line.id))
                    for tla in tlas:
                        asset_row = await self.session.scalar(select(Asset).where(Asset.id == tla.asset_id).with_for_update())
                        asset_row.status = "IN_STOCK"
                        asset_row.current_store_id = transfer.destination_store_id
                        asset_row.current_office_id = None
                        asset_row.current_section_id = None
                        asset_row.updated_by = actor_id
                        self.session.add(
                            AssetMovement(
                                asset_id=asset_row.id,
                                movement_type="TRANSFER",
                                from_store_id=transfer.source_store_id,
                                to_store_id=transfer.destination_store_id,
                                reference_type="TRANSFER_LINE",
                                reference_id=line.id,
                                reference_document=transfer.transfer_no,
                                movement_date=payload.receive_date,
                                created_by=actor_id,
                            )
                        )
                else:
                    self.session.add(
                        StockMovement(
                            financial_year_id=destination_fy.id,
                            store_id=transfer.destination_store_id,
                            item_id=line.item_id,
                            movement_date=payload.receive_date,
                            movement_type="TRANSFER_IN",
                            quantity_in=posted_qty,
                            quantity_out=Decimal("0"),
                            reference_type="TRANSFER_LINE",
                            reference_id=line.id,
                            reference_no=transfer.transfer_no,
                            posting_group_id=posting_group,
                            created_by=actor_id,
                        )
                    )

            req_line = next(
                (x for x in requisition.lines if x.id == line.requisition_line_id),
                None,
            )
            if req_line is not None:
                req_line.received_quantity = posted_qty

            if physical_qty != line.quantity:
                discrepancy_found = True
                discrepancy_rows.append(
                    TransferDiscrepancy(
                        transfer_id=transfer.id,
                        transfer_line_id=line.id,
                        receive_date=payload.receive_date,
                        discrepancy_type=(
                            "SHORT_RECEIPT" if physical_qty < line.quantity else "EXCESS_RECEIPT"
                        ),
                        discrepancy_quantity=abs(line.quantity - physical_qty),
                        reported_by=actor_id,
                        reported_at=datetime.now(timezone.utc),
                        status="OPEN",
                    )
                )

        transfer.received_by = actor_id
        transfer.received_at = datetime.now(timezone.utc)
        self.session.add_all(discrepancy_rows)
        if discrepancy_found:
            transfer.status = "DISCREPANCY"
            requisition.status = "DISCREPANCY"
        else:
            transfer.status = "CLOSED"
            transfer.closed_by = actor_id
            transfer.closed_at = datetime.now(timezone.utc)
            requisition.status = "CLOSED"
            requisition.closed_by = actor_id
            requisition.closed_at = datetime.now(timezone.utc)

        await self.session.commit()
        return await self.repository.get(transfer.id)

    async def resolve_discrepancy(
        self,
        discrepancy_id: int,
        payload: TransferDiscrepancyResolutionRequest,
        actor_id: int,
    ):
        user = await self.auth.require_permission(
            actor_id, "STOCK_TRANSFER_DISCREPANCY_RESOLVE"
        )
        discrepancy = await self.session.get(
            TransferDiscrepancy, discrepancy_id, with_for_update=True
        )
        if discrepancy is None:
            raise HTTPException(404, "Transfer discrepancy not found")
        if discrepancy.status == "CLOSED":
            raise HTTPException(409, "Discrepancy is already closed")

        transfer = await self.repository.get(discrepancy.transfer_id, for_update=True)
        if transfer is None:
            raise HTTPException(404, "Transfer not found")

        source_store = await self.session.get(Store, transfer.source_store_id)
        destination_store = await self.session.get(Store, transfer.destination_store_id)
        allowed_offices = {
            source_store.office_id if source_store else None,
            destination_store.office_id if destination_store else None,
        }
        if user.office_id not in allowed_offices:
            raise HTTPException(403, "User is not authorized to resolve this transfer discrepancy")

        allowed_resolution_types = {
            "CONFIRMED_SHORTAGE",
            "ADDITIONAL_RECEIPT",
            "DAMAGED",
            "WRONG_ITEM",
            "OTHER",
        }
        if payload.resolution_type not in allowed_resolution_types:
            raise HTTPException(422, "Invalid discrepancy resolution type")
        if discrepancy.discrepancy_type == "EXCESS_RECEIPT" and payload.resolution_type == "CONFIRMED_SHORTAGE":
            raise HTTPException(422, "Confirmed shortage is not valid for an excess receipt")

        if payload.resolution_type == "ADDITIONAL_RECEIPT":
            destination_fy = await self._financial_year_for_date(discrepancy.receive_date)
            if destination_fy is None or destination_fy.is_closed:
                raise HTTPException(409, "Destination financial year is unavailable for correction")
            line = await self.session.get(StockTransferLine, discrepancy.transfer_line_id)
            if line is None:
                raise HTTPException(404, "Transfer line not found")
            self.session.add(
                StockMovement(
                    financial_year_id=destination_fy.id,
                    store_id=transfer.destination_store_id,
                    item_id=line.item_id,
                    movement_date=discrepancy.receive_date,
                    movement_type="TRANSFER_IN",
                    quantity_in=discrepancy.discrepancy_quantity,
                    quantity_out=Decimal("0"),
                    reference_type="TRANSFER_DISCREPANCY",
                    reference_id=discrepancy.id,
                    reference_no=transfer.transfer_no,
                    posting_group_id=uuid4(),
                    created_by=actor_id,
                )
            )
            requisition = await self.session.scalar(
                select(CentralStoreRequisition)
                .options(selectinload(CentralStoreRequisition.lines))
                .where(CentralStoreRequisition.id == transfer.requisition_id)
                .with_for_update()
            )
            if requisition is not None:
                req_line = next(
                    (x for x in requisition.lines if x.id == line.requisition_line_id),
                    None,
                )
                if req_line is not None:
                    req_line.received_quantity += discrepancy.discrepancy_quantity

        discrepancy.status = "CLOSED"
        discrepancy.resolution = payload.resolution
        discrepancy.resolved_by = actor_id
        discrepancy.resolved_at = datetime.now(timezone.utc)

        remaining = await self.session.scalar(
            select(TransferDiscrepancy.id)
            .where(
                TransferDiscrepancy.transfer_id == transfer.id,
                TransferDiscrepancy.status != "CLOSED",
            )
            .limit(1)
        )
        if remaining is None:
            transfer.status = "CLOSED"
            transfer.closed_by = actor_id
            transfer.closed_at = datetime.now(timezone.utc)
            requisition = await self.session.scalar(
                select(CentralStoreRequisition)
                .where(CentralStoreRequisition.id == transfer.requisition_id)
                .with_for_update()
            )
            if requisition is not None:
                requisition.status = "CLOSED"
                requisition.closed_by = actor_id
                requisition.closed_at = datetime.now(timezone.utc)

        await self.session.commit()
        return discrepancy

    async def get(self, transfer_id: int):
        result = await self.repository.get(transfer_id)
        if result is None:
            raise HTTPException(404, "Transfer not found")
        return result

    async def list(self, store_id: int | None = None, status: str | None = None):
        return await self.repository.list(store_id, status)

    async def _lock_stock_account(self, store_id: int, fy_id: int, item_id: int):
        await self.session.execute(
            pg_insert(StockAccount)
            .values(store_id=store_id, financial_year_id=fy_id, item_id=item_id)
            .on_conflict_do_nothing(
                index_elements=[
                    StockAccount.store_id,
                    StockAccount.financial_year_id,
                    StockAccount.item_id,
                ]
            )
        )
        await self.session.scalar(
            select(StockAccount)
            .where(
                StockAccount.store_id == store_id,
                StockAccount.financial_year_id == fy_id,
                StockAccount.item_id == item_id,
            )
            .with_for_update()
        )

    async def _financial_year_for_date(self, value: date):
        return await self.session.scalar(
            select(FinancialYear)
            .where(FinancialYear.start_date <= value, FinancialYear.end_date >= value)
            .order_by(FinancialYear.id)
            .limit(1)
        )

    async def _next_number(self) -> str:
        value = await self.session.scalar(text("SELECT nextval('transfer_no_seq')"))
        return f"TRF-{int(value):06d}"
