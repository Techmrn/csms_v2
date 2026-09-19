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
from app.models.issue import Issue, IssueLine, IssueLineAsset
from app.models.stock import StockAccount, StockMovement
from app.models.stock_return import StockReturn, StockReturnLine, StockReturnLineAsset
from app.models.store import Store
from app.models.item import Item
from app.models.user import User
from app.repositories.stock_return import StockReturnRepository
from app.schemas.stock_return import StockReturnCreate
from app.models.asset import Asset, AssetMovement
from app.services.authorization import AuthorizationService


class StockReturnService:
    """Return-to-store workflow for CSMS issues and legacy/manual holdings."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = StockReturnRepository(session)
        self.auth = AuthorizationService(session)

    async def create(self, payload: StockReturnCreate, actor_id: int) -> StockReturn:
        fy = await self.session.get(FinancialYear, payload.financial_year_id)
        store = await self.session.get(Store, payload.store_id)
        # End users may create a return, while verification/posting remain
        # restricted to storekeeper/controller workflow permissions.
        create_permission = "STOCK_RETURN_CREATE" if payload.return_type in {"CSMS_ISSUE", "LEGACY"} else "STOCK_RETURN"
        try:
            await self.auth.require_permission(actor_id, create_permission)
        except HTTPException:
            # Existing storekeeper permission remains backward compatible.
            await self.auth.require_permission(actor_id, "STOCK_RETURN")
        actor = await self.session.get(User, actor_id)
        if actor is None or not actor.is_active:
            raise HTTPException(403, "User is inactive or not found")
        role_codes = {r.code for r in actor.roles if r.is_active}
        if "STOCK_RETURN" in role_codes or "SYSTEM_ADMIN" in role_codes:
            await self.auth.require_store_assignment(actor_id, payload.store_id)
        elif "SECTION_USER" in role_codes:
            if actor.office_id is None or actor.section_id is None:
                raise HTTPException(403, "Section user must have an office and section assignment")
            if payload.returning_office_id not in (None, actor.office_id) or payload.returning_section_id not in (None, actor.section_id):
                raise HTTPException(403, "Section user can return only items from their assigned section")
            if store.office_id != actor.office_id and store.store_type != "CENTRAL":
                raise HTTPException(403, "Section user is not authorized for this return store")
            payload.returning_office_id = actor.office_id
            payload.returning_section_id = actor.section_id
        else:
            await self.auth.require_store_assignment(actor_id, payload.store_id)
        if fy is None:
            raise HTTPException(404, "Financial year not found")
        if store is None:
            raise HTTPException(404, "Store not found")
        if fy.is_closed:
            raise HTTPException(409, "Financial year is closed")
        if not (fy.start_date <= payload.return_date <= fy.end_date):
            raise HTTPException(422, "Return date is outside the financial year")
        if payload.condition not in {"USABLE", "DAMAGED", "UNSERVICEABLE"}:
            raise HTTPException(422, "Invalid return condition")

        if payload.return_type == "CSMS_ISSUE":
            return await self._create_against_issue(payload, actor_id)
        return await self._create_legacy(payload, actor_id)

    async def _create_against_issue(self, payload: StockReturnCreate, actor_id: int) -> StockReturn:
        if payload.original_issue_id is None:
            raise HTTPException(422, "Original issue is required for a CSMS issue return")
        issue = await self.session.scalar(
            select(Issue).options(selectinload(Issue.lines)).where(Issue.id == payload.original_issue_id)
        )
        if issue is None:
            raise HTTPException(404, "Original issue not found")
        if issue.status != "FINALIZED":
            raise HTTPException(409, "Only finalized issues can be returned")
        if payload.store_id != issue.source_store_id:
            raise HTTPException(422, "Return store must be the original issuing store")

        returning_office_id = payload.returning_office_id or issue.destination_office_id
        returning_section_id = payload.returning_section_id if payload.returning_section_id is not None else issue.destination_section_id
        if payload.returning_office_id is not None and payload.returning_office_id != issue.destination_office_id:
            raise HTTPException(422, "Returning office does not match the original issue destination")
        if payload.returning_section_id is not None and payload.returning_section_id != issue.destination_section_id:
            raise HTTPException(422, "Returning section does not match the original issue destination")

        issue_lines = {line.id: line for line in issue.lines}
        supplied_ids = [line.original_issue_line_id for line in payload.lines]
        if any(v is None for v in supplied_ids):
            raise HTTPException(422, "Original issue line is required for every CSMS issue return line")
        if len(supplied_ids) != len(set(supplied_ids)):
            raise HTTPException(422, "Duplicate original issue line in return")

        return_lines: list[StockReturnLine] = []
        global_asset_ids: set[int] = set()
        for request_line in payload.lines:
            issue_line = issue_lines.get(request_line.original_issue_line_id)
            if issue_line is None:
                raise HTTPException(422, f"Issue line {request_line.original_issue_line_id} does not belong to the original issue")
            return_line = await self._build_line_from_issue(request_line, issue_line, returning_office_id, returning_section_id, global_asset_ids)
            return_lines.append(return_line)

        stock_return = StockReturn(
            return_no=await self._next_number(), return_date=payload.return_date,
            financial_year_id=payload.financial_year_id, store_id=payload.store_id,
            original_issue_id=payload.original_issue_id, return_type="CSMS_ISSUE",
            manual_reference=payload.manual_reference, condition=payload.condition,
            returning_user_id=payload.returning_user_id or actor_id,
            returning_office_id=returning_office_id, returning_section_id=returning_section_id,
            status="OPEN", created_by=actor_id, reason=payload.reason, remarks=payload.remarks,
            lines=return_lines,
        )
        self.session.add(stock_return)
        await self.session.commit()
        return await self._reload(stock_return.id)

    async def _create_legacy(self, payload: StockReturnCreate, actor_id: int) -> StockReturn:
        if payload.original_issue_id is not None:
            raise HTTPException(422, "Legacy return must not reference a CSMS issue")
        if not payload.manual_reference and not payload.reason:
            raise HTTPException(422, "Manual return requires a manual reference or reason")
        if not payload.returning_office_id:
            raise HTTPException(422, "Returning office is required for a legacy/manual return")

        return_lines: list[StockReturnLine] = []
        global_asset_ids: set[int] = set()
        for request_line in payload.lines:
            if request_line.original_issue_line_id is not None:
                raise HTTPException(422, "Legacy return lines must not reference CSMS issue lines")
            item = await self.session.get(Item, request_line.item_id) if hasattr(request_line, "item_id") else None
            # Legacy line item_id is supplied through the extended schema field below.
            item_id = getattr(request_line, "item_id", None)
            if item_id is None:
                raise HTTPException(422, "Item is required for a legacy/manual return")
            item = await self.session.get(Item, item_id)
            if item is None or not item.is_active:
                raise HTTPException(404, f"Item {item_id} not found or inactive")
            category = await self.session.get(Category, item.category_id)
            if category is None or category.type not in {"CONSUMABLE", "ASSET"}:
                raise HTTPException(422, f"Unsupported item type for return: {item.code}")
            unit_id = request_line.unit_id
            if unit_id is None:
                raise HTTPException(422, "Unit is required for a legacy/manual return")
            if category.type == "ASSET":
                asset_ids = request_line.asset_ids or []
                if not asset_ids or len(asset_ids) != int(request_line.quantity):
                    raise HTTPException(422, "ASSET legacy return requires asset IDs matching quantity")
                for aid in asset_ids:
                    if aid in global_asset_ids:
                        raise HTTPException(422, f"Asset ID {aid} is duplicated in the return")
                    global_asset_ids.add(aid)
                    asset = await self.session.get(Asset, aid)
                    if asset is None or asset.item_id != item.id:
                        raise HTTPException(422, f"Asset ID {aid} does not belong to item {item.code}")
                    if asset.status != "ASSIGNED":
                        raise HTTPException(422, f"Asset ID {aid} is not currently ASSIGNED")
                    if asset.current_office_id != payload.returning_office_id or asset.current_section_id != payload.returning_section_id:
                        raise HTTPException(422, f"Asset ID {aid} is not assigned to the returning office/section")
            elif request_line.asset_ids:
                raise HTTPException(422, "CONSUMABLE legacy return must not provide asset IDs")

            return_line = StockReturnLine(
                original_issue_line_id=None, item_id=item.id, quantity=Decimal(request_line.quantity),
                unit_id=unit_id, remarks=request_line.remarks,
            )
            if category.type == "ASSET":
                return_line.asset_links = [StockReturnLineAsset(asset_id=aid) for aid in request_line.asset_ids or []]
            return_lines.append(return_line)

        stock_return = StockReturn(
            return_no=await self._next_number(), return_date=payload.return_date,
            financial_year_id=payload.financial_year_id, store_id=payload.store_id,
            original_issue_id=None, return_type="LEGACY", manual_reference=payload.manual_reference,
            condition=payload.condition, returning_user_id=payload.returning_user_id or actor_id,
            returning_office_id=payload.returning_office_id, returning_section_id=payload.returning_section_id,
            status="OPEN", created_by=actor_id, reason=payload.reason, remarks=payload.remarks,
            lines=return_lines,
        )
        self.session.add(stock_return)
        await self.session.commit()
        return await self._reload(stock_return.id)

    async def _build_line_from_issue(self, request_line, issue_line, office_id, section_id, global_asset_ids):
        item = await self.session.get(Item, issue_line.item_id)
        category = await self.session.get(Category, item.category_id) if item else None
        if item is None or category is None or category.type not in ("CONSUMABLE", "ASSET"):
            raise HTTPException(422, "Original issue line has invalid item/category")
        line = StockReturnLine(original_issue_line_id=issue_line.id, item_id=item.id, quantity=Decimal(request_line.quantity), unit_id=issue_line.unit_id, remarks=request_line.remarks)
        if category.type == "ASSET":
            asset_ids = request_line.asset_ids or []
            if len(asset_ids) != int(request_line.quantity):
                raise HTTPException(422, "ASSET return quantity mismatch")
            issued_assets = {x.asset_id for x in await self.session.scalars(select(IssueLineAsset).where(IssueLineAsset.issue_line_id == issue_line.id))}
            for aid in asset_ids:
                if aid in global_asset_ids or aid not in issued_assets:
                    raise HTTPException(422, f"Asset ID {aid} is invalid for this issue line")
                global_asset_ids.add(aid)
                asset = await self.session.get(Asset, aid)
                if asset is None or asset.status != "ASSIGNED" or asset.current_office_id != office_id or asset.current_section_id != section_id:
                    raise HTTPException(422, f"Asset ID {aid} is not currently assigned to the returning office/section")
            line.asset_links = [StockReturnLineAsset(asset_id=aid) for aid in asset_ids]
        elif request_line.asset_ids:
            raise HTTPException(422, "CONSUMABLE return must not provide asset IDs")
        return line

    async def verify(self, return_id: int, actor_id: int) -> StockReturn:
        stock_return = await self.repository.get(return_id, for_update=True)
        if stock_return is None:
            raise HTTPException(404, "Return not found")
        await self.auth.require_permission(actor_id, "STOCK_RETURN")
        await self.auth.require_store_assignment(actor_id, stock_return.store_id)
        if stock_return.status != "OPEN":
            raise HTTPException(409, f"Return is {stock_return.status} and cannot be verified")
        if stock_return.created_by == actor_id:
            raise HTTPException(403, "Return creator cannot verify the same return")
        stock_return.status = "VERIFIED"
        stock_return.verified_by = actor_id
        stock_return.verified_at = datetime.now(timezone.utc)
        await self.session.commit()
        return await self._reload(stock_return.id)

    async def post(self, return_id: int, actor_id: int) -> StockReturn:
        stock_return = await self.repository.get(return_id, for_update=True)
        if stock_return is None:
            raise HTTPException(404, "Return not found")
        await self.auth.require_permission(actor_id, "STOCK_RETURN")
        await self.auth.require_store_assignment(actor_id, stock_return.store_id)
        if stock_return.status != "VERIFIED":
            raise HTTPException(409, f"Return is {stock_return.status}; only VERIFIED returns can be posted")
        if stock_return.verified_by == actor_id:
            raise HTTPException(403, "Return verifier cannot post the same return")

        fy = await self.session.get(FinancialYear, stock_return.financial_year_id)
        if fy is None or fy.is_closed:
            raise HTTPException(409, "Financial year is missing or closed")
        if not (fy.start_date <= stock_return.return_date <= fy.end_date):
            raise HTTPException(422, "Return date is outside the financial year")

        if stock_return.return_type == "CSMS_ISSUE":
            issue_line_ids = sorted(line.original_issue_line_id for line in stock_return.lines if line.original_issue_line_id is not None)
            issue_result = await self.session.execute(select(IssueLine).where(IssueLine.id.in_(issue_line_ids)).with_for_update())
            issue_lines = {line.id: line for line in issue_result.scalars().all()}
            if len(issue_lines) != len(issue_line_ids):
                raise HTTPException(409, "One or more original issue lines no longer exist")
        else:
            issue_lines = {}

        posting_group_id = uuid4()
        now = datetime.now(timezone.utc)
        async with self.session.begin_nested():
            item_ids = sorted({line.item_id for line in stock_return.lines})
            for item_id in item_ids:
                await self.session.execute(pg_insert(StockAccount).values(store_id=stock_return.store_id, financial_year_id=stock_return.financial_year_id, item_id=item_id).on_conflict_do_nothing(index_elements=["store_id", "financial_year_id", "item_id"]))
                account = await self.session.scalar(select(StockAccount).where(StockAccount.store_id == stock_return.store_id, StockAccount.financial_year_id == stock_return.financial_year_id, StockAccount.item_id == item_id).with_for_update())
                if account is None:
                    raise HTTPException(500, "Unable to lock stock account")

            existing = await self.session.scalar(select(StockMovement.id).where(StockMovement.reference_type == "RETURN_LINE", StockMovement.reference_id.in_([line.id for line in stock_return.lines]), StockMovement.movement_type == "RETURN").limit(1))
            if existing is not None:
                raise HTTPException(409, "Return has already been posted")

            for line in stock_return.lines:
                item = await self.session.get(Item, line.item_id)
                category = await self.session.get(Category, item.category_id)
                if category.type == "ASSET":
                    for rla in await self.session.scalars(select(StockReturnLineAsset).where(StockReturnLineAsset.stock_return_line_id == line.id)):
                        asset = await self.session.scalar(select(Asset).where(Asset.id == rla.asset_id).with_for_update())
                        if asset is None or asset.status != "ASSIGNED":
                            raise HTTPException(409, f"Asset ID {rla.asset_id} is no longer ASSIGNED")
                        if stock_return.condition == "USABLE":
                            asset.status = "IN_STOCK"
                            asset.current_store_id = stock_return.store_id
                            asset.current_office_id = None
                            asset.current_section_id = None
                            movement_type = "RETURN"
                        else:
                            asset.status = "UNSERVICEABLE"
                            asset.current_store_id = stock_return.store_id
                            asset.current_office_id = None
                            asset.current_section_id = None
                            movement_type = "UNSERVICEABLE"
                        asset.updated_by = actor_id
                        self.session.add(AssetMovement(asset_id=asset.id, movement_type=movement_type, from_store_id=None, from_office_id=stock_return.returning_office_id, from_section_id=stock_return.returning_section_id, to_store_id=stock_return.store_id, reference_type="RETURN_LINE", reference_id=line.id, reference_document=stock_return.return_no, movement_date=stock_return.return_date, remarks=stock_return.reason, created_by=actor_id))
                elif stock_return.condition == "USABLE":
                    if stock_return.return_type == "CSMS_ISSUE":
                        original = issue_lines[line.original_issue_line_id]
                        already_returned = await self.session.scalar(select(func.coalesce(func.sum(StockReturnLine.quantity), 0)).join(StockReturn, StockReturn.id == StockReturnLine.return_id).where(StockReturnLine.original_issue_line_id == original.id, StockReturn.status == "POSTED"))
                        if Decimal(already_returned or 0) + Decimal(line.quantity) > Decimal(original.quantity):
                            raise HTTPException(422, f"Return quantity exceeds remaining quantity for issue line {original.id}")
                    self.session.add(StockMovement(financial_year_id=stock_return.financial_year_id, store_id=stock_return.store_id, item_id=line.item_id, movement_date=stock_return.return_date, movement_type="RETURN", quantity_in=line.quantity, quantity_out=Decimal("0"), reference_type="RETURN_LINE", reference_id=line.id, reference_no=stock_return.return_no, posting_group_id=posting_group_id, remarks=line.remarks or stock_return.reason, created_by=actor_id))
                # DAMAGED/UNSERVICEABLE consumables are deliberately not added to
                # usable stock. They remain recorded in the return and can later
                # enter the dedicated unserviceable/manual-waste workflow.

            stock_return.status = "POSTED"
            stock_return.posted_by = actor_id
            stock_return.posted_at = now
            stock_return.posting_group_id = posting_group_id
            await self.session.flush()
        await self.session.commit()
        return await self._reload(stock_return.id)

    async def get(self, return_id: int) -> StockReturn:
        result = await self.repository.get(return_id)
        if result is None:
            raise HTTPException(404, "Return not found")
        return result

    async def list(self, store_id: int | None = None, status: str | None = None) -> list[StockReturn]:
        return await self.repository.list(store_id, status)

    async def _reload(self, return_id: int) -> StockReturn:
        result = await self.repository.get(return_id)
        if result is None:
            raise HTTPException(500, "Return could not be reloaded")
        return result

    async def _next_number(self) -> str:
        value = await self.session.scalar(text("SELECT nextval('return_no_seq')"))
        return f"RET-{int(value):06d}"
