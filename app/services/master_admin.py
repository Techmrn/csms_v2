from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from pwdlib import PasswordHash
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.asset import Asset
from app.models.category import Category
from app.models.financial_year import FinancialYear
from app.models.inventory_policy import InventoryPolicy
from app.models.item import Item
from app.models.office import Office
from app.models.permission import Permission, role_permissions
from app.models.role import Role
from app.models.section import Section
from app.models.stock import StockMovement
from app.models.store import Store
from app.models.unit import Unit
from app.models.user import User, user_roles, user_stores


class MasterAdminService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.password_hash = PasswordHash.recommended()

    async def require_master(self, user_id: int):
        from app.services.authorization import AuthorizationService
        return await AuthorizationService(self.session).require_permission(user_id, "MASTER_DATA_MANAGE")

    async def require_org(self, user_id: int):
        from app.services.authorization import AuthorizationService
        return await AuthorizationService(self.session).require_permission(user_id, "ORGANIZATION_MANAGE")

    async def require_user_admin(self, user_id: int):
        from app.services.authorization import AuthorizationService
        return await AuthorizationService(self.session).require_permission(user_id, "USER_MANAGE")

    async def _ensure_unique(self, model, field, value, current_id: int | None = None):
        stmt = select(model.id).where(field == value)
        if current_id is not None:
            stmt = stmt.where(model.id != current_id)
        if await self.session.scalar(stmt.limit(1)) is not None:
            raise HTTPException(409, f"{model.__tablename__}: value already exists")

    async def list_offices(self):
        return list((await self.session.scalars(select(Office).order_by(Office.display_order, Office.name))).all())

    async def create_office(self, data: dict):
        await self._ensure_unique(Office, Office.code, data["code"])
        if data.get("parent_office_id") == 0:
            data["parent_office_id"] = None
        if data.get("parent_office_id") is not None:
            parent = await self.session.get(Office, data["parent_office_id"])
            if parent is None:
                raise HTTPException(404, "Parent office not found")
        office = Office(**data)
        self.session.add(office)
        await self.session.flush()
        return office

    async def update_office(self, office_id: int, data: dict):
        office = await self.session.get(Office, office_id)
        if office is None:
            raise HTTPException(404, "Office not found")
        if "code" in data and data["code"] != office.code:
            raise HTTPException(422, "Office code cannot be changed after creation")
        if data.get("parent_office_id") == office.id:
            raise HTTPException(422, "Office cannot be its own parent")
        if data.get("parent_office_id") is not None:
            parent = await self.session.get(Office, data["parent_office_id"])
            if parent is None:
                raise HTTPException(404, "Parent office not found")
        for key, value in data.items():
            if key != "code":
                setattr(office, key, value)
        await self.session.flush()
        return office

    async def list_stores(self):
        stmt = select(Store).options(selectinload(Store.office)).order_by(Store.name)
        return list((await self.session.scalars(stmt)).all())

    async def create_store(self, data: dict):
        await self._ensure_unique(Store, Store.code, data["code"])
        office = await self.session.get(Office, data["office_id"])
        if office is None or not office.is_active:
            raise HTTPException(404, "Office not found or inactive")
        if data["store_type"] == "CENTRAL" and office.office_type != "DIRECTORATE":
            raise HTTPException(422, "Central Store must belong to a Directorate office")
        if data["store_type"] == "BRANCH" and office.office_type != "BRANCH":
            raise HTTPException(422, "Branch Store must belong to a Branch office")
        if data["store_type"] == "CENTRAL":
            existing = await self.session.scalar(select(Store.id).where(Store.store_type == "CENTRAL", Store.is_active.is_(True)).limit(1))
            if existing is not None:
                raise HTTPException(409, "An active Central Store already exists")
        store = Store(**data)
        self.session.add(store)
        await self.session.flush()
        return store

    async def update_store(self, store_id: int, data: dict):
        store = await self.session.get(Store, store_id)
        if store is None:
            raise HTTPException(404, "Store not found")
        if data.get("code") and data["code"] != store.code:
            raise HTTPException(422, "Store code cannot be changed after creation")
        office = await self.session.get(Office, data.get("office_id", store.office_id))
        if office is None:
            raise HTTPException(404, "Office not found")
        if data.get("store_type", store.store_type) == "CENTRAL" and office.office_type != "DIRECTORATE":
            raise HTTPException(422, "Central Store must belong to a Directorate office")
        if data.get("store_type", store.store_type) == "BRANCH" and office.office_type != "BRANCH":
            raise HTTPException(422, "Branch Store must belong to a Branch office")
        if data.get("store_type", store.store_type) == "CENTRAL" and store.store_type != "CENTRAL":
            existing = await self.session.scalar(select(Store.id).where(Store.store_type == "CENTRAL", Store.id != store.id, Store.is_active.is_(True)).limit(1))
            if existing is not None:
                raise HTTPException(409, "An active Central Store already exists")
        for key, value in data.items():
            if key != "code":
                setattr(store, key, value)
        await self.session.flush()
        return store

    async def list_sections(self):
        stmt = select(Section).options(selectinload(Section.office)).order_by(Section.name)
        return list((await self.session.scalars(stmt)).all())

    async def create_section(self, data: dict):
        office = await self.session.get(Office, data["office_id"])
        if office is None:
            raise HTTPException(404, "Office not found")
        existing = await self.session.scalar(select(Section.id).where(Section.office_id == data["office_id"], Section.code == data["code"]).limit(1))
        if existing is not None:
            raise HTTPException(409, "Section code already exists in this office")
        section = Section(**data)
        self.session.add(section)
        await self.session.flush()
        return section

    async def update_section(self, section_id: int, data: dict):
        section = await self.session.get(Section, section_id)
        if section is None:
            raise HTTPException(404, "Section not found")
        if data.get("code") and data["code"] != section.code:
            raise HTTPException(422, "Section code cannot be changed after creation")
        office_id = data.get("office_id", section.office_id)
        if await self.session.get(Office, office_id) is None:
            raise HTTPException(404, "Office not found")
        for key, value in data.items():
            if key != "code":
                setattr(section, key, value)
        await self.session.flush()
        return section

    async def list_categories(self):
        return list((await self.session.scalars(select(Category).order_by(Category.name))).all())

    async def create_category(self, data: dict):
        data["type"] = data["type"].upper()
        if data["type"] not in {"CONSUMABLE", "ASSET"}:
            raise HTTPException(422, "Category type must be CONSUMABLE or ASSET")
        await self._ensure_unique(Category, Category.code, data["code"])
        category = Category(**data)
        self.session.add(category)
        await self.session.flush()
        return category

    async def update_category(self, category_id: int, data: dict):
        category = await self.session.get(Category, category_id)
        if category is None:
            raise HTTPException(404, "Category not found")
        if data.get("code") and data["code"] != category.code:
            raise HTTPException(422, "Category code cannot be changed")
        if data.get("type") and data["type"] != category.type:
            used = await self.session.scalar(select(Item.id).where(Item.category_id == category.id).limit(1))
            if used is not None:
                raise HTTPException(409, "Category type cannot change after the category is used")
        for key, value in data.items():
            if key != "code":
                setattr(category, key, value)
        await self.session.flush()
        return category

    async def list_units(self):
        return list((await self.session.scalars(select(Unit).order_by(Unit.name))).all())

    async def create_unit(self, data: dict):
        await self._ensure_unique(Unit, Unit.code, data["code"])
        unit = Unit(**data)
        self.session.add(unit)
        await self.session.flush()
        return unit

    async def update_unit(self, unit_id: int, data: dict):
        unit = await self.session.get(Unit, unit_id)
        if unit is None:
            raise HTTPException(404, "Unit not found")
        if data.get("code") and data["code"] != unit.code:
            raise HTTPException(422, "Unit code cannot be changed")
        for key, value in data.items():
            if key != "code":
                setattr(unit, key, value)
        await self.session.flush()
        return unit

    async def list_items(self, search: str | None = None, category_id: int | None = None, limit: int | None = None):
        stmt = select(Item).options(selectinload(Item.category), selectinload(Item.unit)).order_by(Item.name)
        if category_id:
            stmt = stmt.where(Item.category_id == category_id)
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(or_(Item.name.ilike(pattern), Item.code.ilike(pattern)))
        if limit:
            stmt = stmt.limit(limit)
        return list((await self.session.scalars(stmt)).all())

    async def create_item(self, data: dict):
        await self._ensure_unique(Item, Item.code, data["code"])
        category = await self.session.get(Category, data["category_id"])
        unit = await self.session.get(Unit, data["unit_id"])
        if category is None or not category.is_active:
            raise HTTPException(404, "Category not found or inactive")
        if unit is None or not unit.is_active:
            raise HTTPException(404, "Unit not found or inactive")
        duplicate = await self.session.scalar(select(Item.id).where(Item.name == data["name"], Item.category_id == data["category_id"]).limit(1))
        if duplicate is not None:
            raise HTTPException(409, "An item with this name already exists in this category")
        item = Item(**data, is_temporary=False)
        self.session.add(item)
        await self.session.flush()
        return item

    async def update_item(self, item_id: int, data: dict):
        item = await self.session.get(Item, item_id)
        if item is None:
            raise HTTPException(404, "Item not found")
        if data.get("code") and data["code"] != item.code:
            raise HTTPException(422, "Item code cannot be changed")
        if "category_id" in data and data["category_id"] != item.category_id:
            used = await self.session.scalar(select(StockMovement.id).where(StockMovement.item_id == item.id).limit(1))
            asset_used = await self.session.scalar(select(Asset.id).where(Asset.item_id == item.id).limit(1))
            if used is not None or asset_used is not None:
                raise HTTPException(409, "Category cannot change after the item is used")
        if "unit_id" in data and data["unit_id"] != item.unit_id:
            used = await self.session.scalar(select(StockMovement.id).where(StockMovement.item_id == item.id).limit(1))
            if used is not None:
                raise HTTPException(409, "Unit cannot change after stock history exists")
        for key, value in data.items():
            if key != "code":
                setattr(item, key, value)
        await self.session.flush()
        return item

    async def list_financial_years(self):
        return list((await self.session.scalars(select(FinancialYear).order_by(FinancialYear.start_date.desc()))).all())

    async def create_financial_year(self, data: dict):
        if data["start_date"] >= data["end_date"]:
            raise HTTPException(422, "Start date must be before end date")
        overlap = await self.session.scalar(
            select(FinancialYear.id).where(
                and_(FinancialYear.start_date <= data["end_date"], FinancialYear.end_date >= data["start_date"])
            ).limit(1)
        )
        if overlap is not None:
            raise HTTPException(409, "Financial year overlaps an existing financial year")
        if data.get("is_current"):
            await self.session.execute(update(FinancialYear).values(is_current=False))
        fy = FinancialYear(**data, is_closed=False)
        self.session.add(fy)
        await self.session.flush()
        return fy

    async def update_financial_year(self, fy_id: int, data: dict):
        fy = await self.session.get(FinancialYear, fy_id)
        if fy is None:
            raise HTTPException(404, "Financial year not found")
        if data.get("year_name") and data["year_name"] != fy.year_name:
            raise HTTPException(422, "Financial year name cannot be changed")
        start = data.get("start_date", fy.start_date)
        end = data.get("end_date", fy.end_date)
        if start >= end:
            raise HTTPException(422, "Start date must be before end date")
        if data.get("is_current"):
            await self.session.execute(update(FinancialYear).where(FinancialYear.id != fy.id).values(is_current=False))
        for key, value in data.items():
            if key != "year_name":
                setattr(fy, key, value)
        await self.session.flush()
        return fy

    async def list_inventory_policies(self):
        stmt = select(InventoryPolicy).options(selectinload(InventoryPolicy.store), selectinload(InventoryPolicy.item)).order_by(InventoryPolicy.id.desc())
        return list((await self.session.scalars(stmt)).all())

    async def create_inventory_policy(self, data: dict, actor_id: int):
        item = await self.session.get(Item, data["item_id"])
        store = await self.session.get(Store, data["store_id"])
        if item is None or store is None:
            raise HTTPException(404, "Store or item not found")
        category = await self.session.get(Category, item.category_id)
        if category is None or category.type != "CONSUMABLE":
            raise HTTPException(422, "Inventory policy is only applicable to consumable items")
        duplicate = await self.session.scalar(select(InventoryPolicy.id).where(InventoryPolicy.store_id == data["store_id"], InventoryPolicy.item_id == data["item_id"]).limit(1))
        if duplicate is not None:
            raise HTTPException(409, "An inventory policy already exists for this Store and Item")
        policy = InventoryPolicy(**data, created_by=actor_id, updated_by=actor_id)
        self.session.add(policy)
        await self.session.flush()
        return policy

    async def update_inventory_policy(self, policy_id: int, data: dict, actor_id: int):
        policy = await self.session.get(InventoryPolicy, policy_id)
        if policy is None:
            raise HTTPException(404, "Inventory policy not found")
        if data.get("store_id", policy.store_id) != policy.store_id or data.get("item_id", policy.item_id) != policy.item_id:
            duplicate = await self.session.scalar(select(InventoryPolicy.id).where(InventoryPolicy.store_id == data.get("store_id", policy.store_id), InventoryPolicy.item_id == data.get("item_id", policy.item_id), InventoryPolicy.id != policy.id).limit(1))
            if duplicate is not None:
                raise HTTPException(409, "An inventory policy already exists for this Store and Item")
        for key, value in data.items():
            setattr(policy, key, value)
        policy.updated_by = actor_id
        await self.session.flush()
        return policy

    async def list_users(self):
        stmt = (
            select(User)
            .options(selectinload(User.roles), selectinload(User.stores), selectinload(User.office), selectinload(User.section))
            .order_by(User.full_name)
        )
        return list((await self.session.scalars(stmt)).all())

    async def user_form_data(self):
        offices = list((await self.session.scalars(select(Office).where(Office.is_active.is_(True)).order_by(Office.name))).all())
        stores = list((await self.session.scalars(select(Store).where(Store.is_active.is_(True)).order_by(Store.name))).all())
        sections = list((await self.session.scalars(select(Section).where(Section.is_active.is_(True)).order_by(Section.name))).all())
        roles = list((await self.session.scalars(select(Role).where(Role.is_active.is_(True)).order_by(Role.name))).all())
        return offices, stores, sections, roles

    async def create_user(self, data: dict, role_ids: list[int], store_ids: list[int], password: str):
        await self._ensure_unique(User, User.code, data["code"])
        await self._ensure_unique(User, User.username, data["username"])
        office = await self.session.get(Office, data.get("office_id")) if data.get("office_id") else None
        if data.get("office_id") and office is None:
            raise HTTPException(404, "Office not found")
        if data.get("section_id"):
            section = await self.session.get(Section, data["section_id"])
            if section is None:
                raise HTTPException(404, "Section not found")
            if data.get("office_id") != section.office_id:
                raise HTTPException(422, "Section does not belong to selected office")
        roles = list((await self.session.scalars(select(Role).where(Role.id.in_(role_ids), Role.is_active.is_(True)))).all()) if role_ids else []
        if not roles:
            raise HTTPException(422, "At least one active role is required")
        stores = list((await self.session.scalars(select(Store).where(Store.id.in_(store_ids), Store.is_active.is_(True)))).all()) if store_ids else []
        user = User(**data, password_hash=self.password_hash.hash(password))
        user.roles = roles
        user.stores = stores
        self.session.add(user)
        await self.session.flush()
        return user

    async def update_user(self, user_id: int, data: dict, role_ids: list[int], store_ids: list[int], actor_id: int, password: str | None = None):
        user = await self.session.scalar(
            select(User)
            .options(selectinload(User.roles), selectinload(User.stores))
            .where(User.id == user_id)
        )
        if user is None:
            raise HTTPException(404, "User not found")
        if user.id == actor_id and data.get("is_active") is False:
            raise HTTPException(422, "You cannot deactivate your own account")
        if "code" in data and data["code"] != user.code:
            raise HTTPException(422, "User code cannot be changed")
        if "username" in data and data["username"] != user.username:
            raise HTTPException(422, "Username cannot be changed")
        if data.get("office_id"):
            if await self.session.get(Office, data["office_id"]) is None:
                raise HTTPException(404, "Office not found")
        if data.get("section_id"):
            section = await self.session.get(Section, data["section_id"])
            if section is None:
                raise HTTPException(404, "Section not found")
            if data.get("office_id", user.office_id) != section.office_id:
                raise HTTPException(422, "Section does not belong to selected office")
        roles = list((await self.session.scalars(select(Role).where(Role.id.in_(role_ids), Role.is_active.is_(True)))).all()) if role_ids else []
        if not roles:
            raise HTTPException(422, "At least one active role is required")
        stores = list((await self.session.scalars(select(Store).where(Store.id.in_(store_ids), Store.is_active.is_(True)))).all()) if store_ids else []
        for key, value in data.items():
            if key not in {"code", "username"}:
                setattr(user, key, value)
        user.roles = roles
        user.stores = stores
        if password:
            user.password_hash = self.password_hash.hash(password)
        await self.session.flush()
        return user

    async def get_roles_permissions(self):
        stmt = select(Role).options(selectinload(Role.permissions)).order_by(Role.name)
        return list((await self.session.scalars(stmt)).all())

    async def get_dashboard_counts(self):
        models = [Office, Store, Section, Category, Unit, Item, FinancialYear, User, InventoryPolicy]
        result = {}
        for model in models:
            result[model.__tablename__] = int((await self.session.scalar(select(func.count()).select_from(model))) or 0)
        for model in [Office, Store, Section, Item, User]:
            result[f"active_{model.__tablename__}"] = int(
                (await self.session.scalar(
                    select(func.count()).select_from(model).where(model.is_active.is_(True))
                )) or 0
            )
        current_fy = await self.session.scalar(
            select(FinancialYear.year_name).where(FinancialYear.is_current.is_(True)).limit(1)
        )
        result["current_financial_year"] = current_fy
        return result

    async def list_admin_views_requisitions(self):
        from app.models.requisition import CentralStoreRequisition
        stmt = select(CentralStoreRequisition).options(
            selectinload(CentralStoreRequisition.lines)
        ).order_by(CentralStoreRequisition.requisition_date.desc(), CentralStoreRequisition.id.desc()).limit(100)
        return list((await self.session.scalars(stmt)).all())

    async def list_admin_views_transfers(self):
        from app.models.transfer import StockTransfer
        stmt = select(StockTransfer).options(
            selectinload(StockTransfer.lines)
        ).order_by(StockTransfer.transfer_date.desc(), StockTransfer.id.desc()).limit(100)
        return list((await self.session.scalars(stmt)).all())

    async def get_admin_stock_control_views(self):
        from app.models.stock_control import StockVerification, Adjustment, UnserviceableMaterial
        verification_stmt = select(StockVerification).order_by(StockVerification.verification_date.desc(), StockVerification.id.desc()).limit(50)
        adjustment_stmt = select(Adjustment).order_by(Adjustment.adjustment_date.desc(), Adjustment.id.desc()).limit(50)
        unserviceable_stmt = select(UnserviceableMaterial).order_by(UnserviceableMaterial.date.desc(), UnserviceableMaterial.id.desc()).limit(50)
        verification_rows = list((await self.session.scalars(verification_stmt)).all())
        adjustment_rows = list((await self.session.scalars(adjustment_stmt)).all())
        unserviceable_rows = list((await self.session.scalars(unserviceable_stmt)).all())
        return {
            "counts": {
                "verifications": int((await self.session.scalar(select(func.count()).select_from(StockVerification))) or 0),
                "adjustments": int((await self.session.scalar(select(func.count()).select_from(Adjustment))) or 0),
                "unserviceable": int((await self.session.scalar(select(func.count()).select_from(UnserviceableMaterial))) or 0),
            },
            "verification_rows": verification_rows,
            "adjustment_rows": adjustment_rows,
            "unserviceable_rows": unserviceable_rows,
        }
