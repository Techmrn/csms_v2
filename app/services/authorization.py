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

        if store.store_type == "BRANCH":
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
        if "DIRECTOR" in role_codes or "SUPERINTENDENT" in role_codes:
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
        if "DIRECTOR" in role_codes or "SUPERINTENDENT" in role_codes:
            return None

        visible_store_ids = set()

        # Central store visibility
        if "DEPUTY_SUPDT_STORES" in role_codes:
            central_stores = await self.session.scalars(select(Store.id).where(Store.store_type == "CENTRAL"))
            visible_store_ids.update(central_stores.all())

        # Branch head visibility
        if "BRANCH_HEAD" in role_codes and user.office_id is not None:
            branch_stores = await self.session.scalars(
                select(Store.id).where(Store.office_id == user.office_id, Store.store_type == "BRANCH")
            )
            visible_store_ids.update(branch_stores.all())

        # Assigned stores visibility
        assigned_stores = await self.session.scalars(
            select(user_stores.c.store_id).where(user_stores.c.user_id == user_id)
        )
        visible_store_ids.update(assigned_stores.all())

        return list(visible_store_ids)
