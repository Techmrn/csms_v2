from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permission import Permission, role_permissions
from app.models.role import Role
from app.models.user import User, user_roles, user_stores


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
