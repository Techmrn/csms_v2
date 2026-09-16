from __future__ import annotations

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.asset import Asset
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
            stmt = stmt.where(or_(Issue.issue_no.ilike(term), Indent.indent_no.ilike(term), Office.name.ilike(term), Section.name.ilike(term)))
        stmt = stmt.order_by(Issue.issue_date.desc(), Issue.id.desc()).limit(5000)
        return [dict(row._mapping) for row in (await self.session.execute(stmt)).all()]

    async def distribution_register(
        self,
        actor_id: int,
        store_id: int | None = None,
        financial_year_id: int | None = None,
        search: str | None = None,
    ) -> list[dict]:
        await self.auth.require_permission(actor_id, "REGISTER_VIEW")
        visible = await self._scope(actor_id, store_id)
        stmt = (
            select(
                Issue.issue_no,
                Issue.issue_date,
                Issue.financial_year_id,
                Store.name.label("store_name"),
                Office.name.label("office_name"),
                Section.name.label("section_name"),
                Item.code.label("item_code"),
                Item.name.label("item_name"),
                Unit.code.label("unit_code"),
                IssueLine.quantity,
                Issue.indent_id,
                Indent.indent_no,
            )
            .join(IssueLine, IssueLine.issue_id == Issue.id)
            .join(Item, Item.id == IssueLine.item_id)
            .join(Unit, Unit.id == IssueLine.unit_id)
            .join(Store, Store.id == Issue.source_store_id)
            .join(Office, Office.id == Issue.destination_office_id)
            .outerjoin(Section, Section.id == Issue.destination_section_id)
            .join(Indent, Indent.id == Issue.indent_id)
            .where(Issue.status == "FINALIZED")
        )
        stmt = self._store_filter(stmt, Issue.source_store_id, visible, store_id)
        if financial_year_id is not None:
            stmt = stmt.where(Issue.financial_year_id == financial_year_id)
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(or_(Issue.issue_no.ilike(term), Item.code.ilike(term), Item.name.ilike(term), Office.name.ilike(term), Section.name.ilike(term)))
        stmt = stmt.order_by(Issue.issue_date.desc(), Issue.id.desc(), IssueLine.id).limit(5000)
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
        """Unified source-document-linked movement register.

        StockMovement remains the sole stock ledger; this view only presents
        its source-document references in chronological form.
        """
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
        return [dict(row._mapping) for row in (await self.session.execute(stmt)).all()]

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
