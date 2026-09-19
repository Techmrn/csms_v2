from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.asset import Asset, AssetMovement
from app.models.financial_year import FinancialYear
from app.models.indent import Indent
from app.models.issue import Issue, IssueLine
from app.models.item import Item
from app.models.office import Office
from app.models.section import Section
from app.models.stock import StockMovement
from app.models.store import Store
from app.models.unit import Unit
from app.services.authorization import AuthorizationService


class RegisterService:
    """Read-only operational registers derived from authoritative documents."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.auth = AuthorizationService(session)

    async def _scope(self, actor_id: int, store_id: int | None = None) -> list[int] | None:
        visible = await self.auth.get_visible_stores(actor_id)
        if store_id is not None:
            await self.auth.require_store_visibility(actor_id, store_id)
        return visible

    @staticmethod
    def _store_filter(stmt, column, visible: list[int] | None, store_id: int | None):
        if store_id is not None:
            return stmt.where(column == store_id)
        if visible is not None:
            return stmt.where(column.in_(visible)) if visible else stmt.where(column == -1)
        return stmt

    async def issue_register(
        self,
        actor_id: int,
        store_id: int | None = None,
        financial_year_id: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        search: str | None = None,
    ) -> list[dict]:
        await self.auth.require_permission(actor_id, "REGISTER_VIEW")
        visible = await self._scope(actor_id, store_id)
        stmt = (
            select(
                Issue.id,
                Issue.issue_no,
                Issue.issue_date,
                Issue.financial_year_id,
                Issue.source_store_id,
                Store.name.label("store_name"),
                Issue.destination_office_id,
                Office.name.label("office_name"),
                Issue.destination_section_id,
                Section.name.label("section_name"),
                Issue.destination_type,
                Issue.status,
                Issue.indent_id,
                Indent.indent_no,
                Issue.remarks,
            )
            .join(Store, Store.id == Issue.source_store_id)
            .join(Office, Office.id == Issue.destination_office_id)
            .join(Indent, Indent.id == Issue.indent_id)
            .outerjoin(Section, Section.id == Issue.destination_section_id)
        )
        stmt = self._store_filter(stmt, Issue.source_store_id, visible, store_id)
        if financial_year_id is not None:
            stmt = stmt.where(Issue.financial_year_id == financial_year_id)
        if from_date is not None:
            stmt = stmt.where(Issue.issue_date >= from_date)
        if to_date is not None:
            stmt = stmt.where(Issue.issue_date <= to_date)
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(or_(Issue.issue_no.ilike(term), Indent.indent_no.ilike(term), Office.name.ilike(term)))
        stmt = stmt.order_by(Issue.issue_date.desc(), Issue.id.desc()).limit(1000)
        return [dict(row._mapping) for row in (await self.session.execute(stmt)).all()]

    async def distribution_register(
        self,
        actor_id: int,
        store_id: int | None = None,
        financial_year_id: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        search: str | None = None,
    ) -> list[dict]:
        await self.auth.require_permission(actor_id, "REGISTER_VIEW")
        visible = await self._scope(actor_id, store_id)
        stmt = (
            select(
                IssueLine.id,
                Issue.issue_no,
                Issue.issue_date,
                Store.name.label("store_name"),
                Office.name.label("office_name"),
                Section.name.label("section_name"),
                Item.code.label("item_code"),
                Item.name.label("item_name"),
                Unit.code.label("unit_code"),
                IssueLine.quantity,
                IssueLine.remarks,
            )
            .join(Issue, Issue.id == IssueLine.issue_id)
            .join(Store, Store.id == Issue.source_store_id)
            .join(Office, Office.id == Issue.destination_office_id)
            .join(Item, Item.id == IssueLine.item_id)
            .join(Unit, Unit.id == IssueLine.unit_id)
            .outerjoin(Section, Section.id == Issue.destination_section_id)
            .where(Issue.status == "FINALIZED")
        )
        stmt = self._store_filter(stmt, Issue.source_store_id, visible, store_id)
        if financial_year_id is not None:
            stmt = stmt.where(Issue.financial_year_id == financial_year_id)
        if from_date is not None:
            stmt = stmt.where(Issue.issue_date >= from_date)
        if to_date is not None:
            stmt = stmt.where(Issue.issue_date <= to_date)
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(or_(Issue.issue_no.ilike(term), Office.name.ilike(term), Item.code.ilike(term), Item.name.ilike(term)))
        stmt = stmt.order_by(Issue.issue_date.desc(), IssueLine.id.desc()).limit(1000)
        return [dict(row._mapping) for row in (await self.session.execute(stmt)).all()]

    async def transaction_register(
        self,
        actor_id: int,
        store_id: int | None = None,
        financial_year_id: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        search: str | None = None,
    ) -> list[dict]:
        """Unified source-document-linked movement register."""
        await self.auth.require_permission(actor_id, "REGISTER_VIEW")
        visible = await self._scope(actor_id, store_id)
        stmt = (
            select(
                StockMovement.id,
                StockMovement.movement_date,
                StockMovement.movement_type,
                Store.name.label("store_name"),
                Item.code.label("item_code"),
                Item.name.label("item_name"),
                Unit.code.label("unit_code"),
                StockMovement.quantity_in,
                StockMovement.quantity_out,
                StockMovement.reference_type,
                StockMovement.reference_id,
                StockMovement.reference_no,
                StockMovement.remarks,
            )
            .join(Store, Store.id == StockMovement.store_id)
            .join(Item, Item.id == StockMovement.item_id)
            .join(Unit, Unit.id == Item.unit_id)
        )
        stmt = self._store_filter(stmt, StockMovement.store_id, visible, store_id)
        if financial_year_id is not None:
            stmt = stmt.where(StockMovement.financial_year_id == financial_year_id)
        if from_date is not None:
            stmt = stmt.where(StockMovement.movement_date >= from_date)
        if to_date is not None:
            stmt = stmt.where(StockMovement.movement_date <= to_date)
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(or_(StockMovement.reference_no.ilike(term), StockMovement.reference_type.ilike(term), Item.code.ilike(term), Item.name.ilike(term), StockMovement.movement_type.ilike(term)))
        stmt = stmt.order_by(StockMovement.movement_date.desc(), StockMovement.id.desc()).limit(1000)
        rows = [dict(row._mapping) for row in (await self.session.execute(stmt)).all()]

        # Include physical asset movements
        stmt_asset = (
            select(
                AssetMovement.id,
                AssetMovement.movement_date,
                AssetMovement.movement_type,
                Item.code.label("item_code"),
                Item.name.label("item_name"),
                Unit.code.label("unit_code"),
                AssetMovement.from_store_id,
                AssetMovement.to_store_id,
                AssetMovement.reference_type,
                AssetMovement.reference_id,
                AssetMovement.reference_document,
                Asset.asset_no,
                AssetMovement.remarks,
            )
            .join(Asset, Asset.id == AssetMovement.asset_id)
            .join(Item, Item.id == Asset.item_id)
            .join(Unit, Unit.id == Item.unit_id)
        )
        if store_id is not None:
            stmt_asset = stmt_asset.where(
                or_(AssetMovement.from_store_id == store_id, AssetMovement.to_store_id == store_id)
            )
        elif visible is not None:
            if visible:
                stmt_asset = stmt_asset.where(
                    or_(AssetMovement.from_store_id.in_(visible), AssetMovement.to_store_id.in_(visible))
                )
            else:
                stmt_asset = stmt_asset.where(AssetMovement.id == -1)

        if financial_year_id is not None:
            fy = await self.session.get(FinancialYear, financial_year_id)
            if fy:
                stmt_asset = stmt_asset.where(
                    AssetMovement.movement_date >= fy.start_date,
                    AssetMovement.movement_date <= fy.end_date,
                )
        if from_date is not None:
            stmt_asset = stmt_asset.where(AssetMovement.movement_date >= from_date)
        if to_date is not None:
            stmt_asset = stmt_asset.where(AssetMovement.movement_date <= to_date)
        if search:
            term = f"%{search.strip()}%"
            stmt_asset = stmt_asset.where(
                or_(
                    Asset.asset_no.ilike(term),
                    AssetMovement.reference_document.ilike(term),
                    AssetMovement.reference_type.ilike(term),
                    Item.code.ilike(term),
                    Item.name.ilike(term),
                    AssetMovement.movement_type.ilike(term),
                )
            )
        asset_raw = (await self.session.execute(stmt_asset.limit(1000))).all()
        stores_map = {s.id: s.name for s in (await self.session.scalars(select(Store))).all()}
        for r in asset_raw:
            ref_store_id = store_id if store_id is not None else (r.to_store_id or r.from_store_id)
            qty_in = Decimal("1") if r.to_store_id == ref_store_id else Decimal("0")
            qty_out = Decimal("1") if r.from_store_id == ref_store_id else Decimal("0")
            s_name = stores_map.get(ref_store_id, "Store")
            rows.append({
                "id": r.id,
                "movement_date": r.movement_date,
                "movement_type": r.movement_type,
                "store_name": s_name,
                "item_code": r.item_code,
                "item_name": f"{r.item_name} [{r.asset_no}]",
                "unit_code": r.unit_code,
                "quantity_in": qty_in,
                "quantity_out": qty_out,
                "reference_type": r.reference_type or "ASSET",
                "reference_id": r.reference_id,
                "reference_no": r.reference_document or r.asset_no,
                "remarks": r.remarks,
            })

        rows.sort(key=lambda x: (x["movement_date"] is not None, x["movement_date"], x["id"]), reverse=True)
        return rows[:1000]

    async def asset_register(self, actor_id: int, store_id: int | None = None) -> list[Asset]:
        await self.auth.require_permission(actor_id, "REGISTER_VIEW")
        visible = await self._scope(actor_id, store_id)
        stmt = select(Asset).options(selectinload(Asset.item)).order_by(Asset.asset_no)
        if store_id is not None:
            stmt = stmt.where(Asset.current_store_id == store_id)
        elif visible is not None:
            stmt = stmt.where(Asset.current_store_id.in_(visible)) if visible else stmt.where(Asset.id == -1)
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(or_(Asset.asset_no.ilike(term), Asset.serial_no.ilike(term), Item.code.ilike(term), Item.name.ilike(term)))
        return list((await self.session.scalars(stmt)).all())

    async def computer_register(self, actor_id: int, store_id: int | None = None, search: str | None = None) -> list[Asset]:
        await self.auth.require_permission(actor_id, "REGISTER_VIEW")
        visible = await self._scope(actor_id, store_id)
        terms = ("computer", "desktop", "laptop", "printer")
        conditions = [func.lower(Item.name).like(f"%{term}%") for term in terms]
        stmt = (
            select(Asset)
            .options(selectinload(Asset.item))
            .join(Item, Item.id == Asset.item_id)
            .where(or_(*conditions))
            .order_by(Asset.asset_no)
        )
        if store_id is not None:
            stmt = stmt.where(Asset.current_store_id == store_id)
        elif visible is not None:
            stmt = stmt.where(Asset.current_store_id.in_(visible)) if visible else stmt.where(Asset.id == -1)
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(or_(Asset.asset_no.ilike(term), Asset.serial_no.ilike(term), Item.code.ilike(term), Item.name.ilike(term)))
        return list((await self.session.scalars(stmt)).all())

    async def e_waste_register(self, actor_id: int, store_id: int | None = None, search: str | None = None) -> list[Asset]:
        """Current asset records relevant to the e-waste lifecycle.

        The current schema has no separate e-waste entity; UNSERVICEABLE and
        DISPOSED assets are therefore presented as the lifecycle register.
        """
        await self.auth.require_permission(actor_id, "REGISTER_VIEW")
        visible = await self._scope(actor_id, store_id)
        stmt = select(Asset).options(selectinload(Asset.item)).where(Asset.status.in_(("UNSERVICEABLE", "DISPOSED")))
        if store_id is not None:
            stmt = stmt.where(Asset.current_store_id == store_id)
        elif visible is not None:
            stmt = stmt.where(Asset.current_store_id.in_(visible)) if visible else stmt.where(Asset.id == -1)
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(or_(Asset.asset_no.ilike(term), Asset.serial_no.ilike(term), Item.code.ilike(term), Item.name.ilike(term)))
        stmt = stmt.order_by(Asset.asset_no)
        return list((await self.session.scalars(stmt)).all())
