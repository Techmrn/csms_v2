from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permission import Permission, role_permissions
from app.models.role import Role
from app.models.user import User, user_roles, user_stores
from app.models.store import Store


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
