from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permission import Permission, role_permissions
from app.models.role import Role
from app.models.user import User, user_roles, user_stores
from app.models.store import Store
from app.models.office import Office


class AuthorizationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def require_permission(self, user_id: int, permission_code: str) -> User:
        user = await self.session.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(403, "User is inactive or not found")

        stmt = (
            select(User.id)
            .join(user_roles, user_roles.c.user_id == User.id)
            .join(Role, Role.id == user_roles.c.role_id)
            .join(role_permissions, role_permissions.c.role_id == Role.id)
            .join(Permission, Permission.id == role_permissions.c.permission_id)
            .where(
                User.id == user_id,
                User.is_active.is_(True),
                Role.is_active.is_(True),
                Permission.is_active.is_(True),
                Permission.code == permission_code,
            )
        )
        allowed = await self.session.scalar(stmt)
        if allowed is None:
            raise HTTPException(403, f"User lacks permission: {permission_code}")
        return user

    async def require_store_assignment(self, user_id: int, store_id: int) -> User:
        user = await self.session.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(403, "User is inactive or not found")
        stmt = select(user_stores.c.user_id).where(
            user_stores.c.user_id == user_id,
            user_stores.c.store_id == store_id,
        )
        if await self.session.scalar(stmt) is None:
            raise HTTPException(403, "User is not assigned to this store")
        return user


    async def require_store_controller(self, user_id: int, store_id: int) -> User:
        """Require the business controlling officer for a store.

        Central Store: Deputy Superintendent, Stock & Stores.
        Branch Store: Branch Head of the store's office.
        System administration does not automatically confer business authority.
        """
        user = await self.session.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(403, "User is inactive or not found")

        store = await self.session.get(Store, store_id)
        if store is None or not store.is_active:
            raise HTTPException(404, "Store not found or inactive")

        stmt = (
            select(Role.code)
            .join(user_roles, user_roles.c.role_id == Role.id)
            .where(
                user_roles.c.user_id == user_id,
                Role.is_active.is_(True),
            )
        )
        role_codes = set((await self.session.scalars(stmt)).all())

        if store.store_type == "CENTRAL":
            if "DEPUTY_SUPDT_STORES" not in role_codes:
                raise HTTPException(403, "Only the Deputy Superintendent, Stock & Stores can control the Central Store")
            return user

        if store.store_type in ("BRANCH", "PAPER_WAREHOUSE"):
            if "BRANCH_HEAD" not in role_codes or user.office_id != store.office_id:
                raise HTTPException(403, "Only the Branch Head can control this branch store")
            return user

        raise HTTPException(403, "No controlling officer is configured for this store")


    async def require_store_visibility(self, user_id: int, store_id: int) -> User:
        """Require that the user may view/work with a specific store."""
        visible = await self.get_visible_stores(user_id)
        if visible is not None and store_id not in visible:
            raise HTTPException(403, "User is not authorized to access this store")
        user = await self.session.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(403, "User is inactive or not found")
        return user

    async def scoped_store_ids(self, user_id: int, store_id: int | None = None) -> list[int] | None:
        """Return stores visible to the user, validating an optional requested store."""
        visible = await self.get_visible_stores(user_id)
        if store_id is not None:
            if visible is not None and store_id not in visible:
                raise HTTPException(403, "User is not authorized to access this store")
            return [store_id]
        return visible

    async def require_asset_visibility(self, user_id: int, asset) -> User:
        """Require view/access to an individual asset by store or office scope."""
        user = await self.session.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(403, "User is inactive or not found")

        role_stmt = (
            select(Role.code)
            .join(user_roles, user_roles.c.role_id == Role.id)
            .where(user_roles.c.user_id == user_id, Role.is_active.is_(True))
        )
        role_codes = set((await self.session.scalars(role_stmt)).all())
        if "SYSTEM_ADMIN" in role_codes or "DIRECTOR" in role_codes:
            return user

        current_store_id = getattr(asset, "current_store_id", None)
        current_office_id = getattr(asset, "current_office_id", None)
        if current_store_id is not None:
            visible = await self.get_visible_stores(user_id)
            if visible is None or current_store_id in visible:
                return user
        if current_office_id is not None and user.office_id == current_office_id:
            return user
        raise HTTPException(403, "User is not authorized to access this asset")

    async def require_asset_controller(self, user_id: int, asset) -> User:
        """Require the controlling officer for the asset's current custody location."""
        user = await self.session.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(403, "User is inactive or not found")

        if asset.current_store_id is not None:
            return await self.require_store_controller(user_id, asset.current_store_id)

        if asset.current_office_id is None:
            raise HTTPException(403, "Asset has no current custody location")

        role_stmt = (
            select(Role.code)
            .join(user_roles, user_roles.c.role_id == Role.id)
            .where(user_roles.c.user_id == user_id, Role.is_active.is_(True))
        )
        role_codes = set((await self.session.scalars(role_stmt)).all())
        office = await self.session.get(Office, asset.current_office_id)
        if office is None or not office.is_active:
            raise HTTPException(404, "Asset office not found or inactive")
        if office.office_type == "DIRECTORATE":
            if "DEPUTY_SUPDT_STORES" not in role_codes:
                raise HTTPException(403, "Only the Deputy Superintendent, Stock & Stores can control Directorate assets")
            return user
        if office.office_type == "BRANCH":
            if "BRANCH_HEAD" not in role_codes or user.office_id != office.id:
                raise HTTPException(403, "Only the Branch Head can control branch assets")
            return user
        raise HTTPException(403, "No controlling officer is configured for this asset location")

    async def get_visible_stores(self, user_id: int) -> list[int] | None:
        """Return a list of store IDs visible to the user, or None for department-wide visibility."""
        user = await self.session.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(403, "User is inactive or not found")

        stmt = (
            select(Role.code)
            .join(user_roles, user_roles.c.role_id == Role.id)
            .where(
                user_roles.c.user_id == user_id,
                Role.is_active.is_(True),
            )
        )
        role_codes = set((await self.session.scalars(stmt)).all())

        # Department-wide visibility
        if "SYSTEM_ADMIN" in role_codes or "DIRECTOR" in role_codes:
            return None

        visible_store_ids = set()

        # Central store visibility
        if "DEPUTY_SUPDT_STORES" in role_codes:
            central_stores = await self.session.scalars(select(Store.id).where(Store.store_type == "CENTRAL"))
            visible_store_ids.update(central_stores.all())

        # Branch head visibility
        if "BRANCH_HEAD" in role_codes and user.office_id is not None:
            branch_stores = await self.session.scalars(
                select(Store.id).where(Store.office_id == user.office_id, Store.store_type.in_(["BRANCH", "PAPER_WAREHOUSE"]))
            )
            visible_store_ids.update(branch_stores.all())

        # Assigned stores visibility
        assigned_stores = await self.session.scalars(
            select(user_stores.c.store_id).where(user_stores.c.user_id == user_id)
        )
        visible_store_ids.update(assigned_stores.all())

        return list(visible_store_ids)

    async def get_visible_general_stores(self, user_id: int) -> list[int]:
        """Return active General Store IDs (excluding PAPER_WAREHOUSE) visible to the user."""
        visible = await self.get_visible_stores(user_id)
        stmt = select(Store.id).where(Store.is_active.is_(True), Store.store_type != "PAPER_WAREHOUSE")
        if visible is not None:
            if not visible:
                return []
            stmt = stmt.where(Store.id.in_(visible))
        return list((await self.session.scalars(stmt)).all())

    async def get_visible_paper_warehouses(self, user_id: int) -> list[int]:
        """Return active PAPER_WAREHOUSE IDs visible to the user."""
        user = await self.session.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(403, "User is inactive or not found")

        stmt = (
            select(Role.code)
            .join(user_roles, user_roles.c.role_id == Role.id)
            .where(user_roles.c.user_id == user_id, Role.is_active.is_(True))
        )
        role_codes = set((await self.session.scalars(stmt)).all())

        if role_codes.intersection({"SYSTEM_ADMIN", "DIRECTOR", "DEPUTY_SUPDT_STORES"}):
            all_wh = await self.session.scalars(
                select(Store.id).where(Store.is_active.is_(True), Store.store_type == "PAPER_WAREHOUSE")
            )
            return list(all_wh.all())

        visible_wh_ids: set[int] = set()
        if ("BRANCH_HEAD" in role_codes or "SECTION_USER" in role_codes) and user.office_id is not None:
            office_wh = await self.session.scalars(
                select(Store.id).where(
                    Store.is_active.is_(True),
                    Store.store_type == "PAPER_WAREHOUSE",
                    Store.office_id == user.office_id,
                )
            )
            visible_wh_ids.update(office_wh.all())

        assigned_wh = await self.session.scalars(
            select(Store.id)
            .join(user_stores, user_stores.c.store_id == Store.id)
            .where(
                user_stores.c.user_id == user_id,
                Store.is_active.is_(True),
                Store.store_type == "PAPER_WAREHOUSE",
            )
        )
        visible_wh_ids.update(assigned_wh.all())
        return list(visible_wh_ids)

    async def require_general_store(self, store_id: int) -> Store:
        """Ensure the store is an active non-warehouse General Store."""
        store = await self.session.get(Store, store_id)
        if store is None or not store.is_active:
            raise HTTPException(404, "Store not found or inactive")
        if store.store_type == "PAPER_WAREHOUSE":
            raise HTTPException(422, "Paper Warehouses cannot process General Store transactions")
        return store

    async def require_paper_warehouse(self, store_id: int) -> Store:
        """Ensure the store is an active Paper Warehouse."""
        store = await self.session.get(Store, store_id)
        if store is None or not store.is_active:
            raise HTTPException(404, "Paper Warehouse not found or inactive")
        if store.store_type != "PAPER_WAREHOUSE":
            raise HTTPException(422, "Store must be of type PAPER_WAREHOUSE")
        return store
