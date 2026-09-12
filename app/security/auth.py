from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.session import get_db_session
from app.models.role import Role
from app.models.user import User

settings = get_settings()
password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummy-password-for-timing-only")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token")


async def authenticate_user(session: AsyncSession, username: str, password: str) -> User | None:
    stmt = (
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions), selectinload(User.stores))
        .where(User.username == username, User.is_active.is_(True))
    )
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        password_hash.verify(password, DUMMY_HASH)
        return None
    if not password_hash.verify(password, user.password_hash):
        return None
    return user


def create_access_token(user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "exp": expires,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: AsyncSession = Depends(get_db_session),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        subject = payload.get("sub")
        if subject is None:
            raise credentials_exception
        user_id = int(subject)
    except (InvalidTokenError, ValueError, TypeError):
        raise credentials_exception

    stmt = (
        select(User)
        .options(
            selectinload(User.roles).selectinload(Role.permissions),
            selectinload(User.stores),
        )
        .where(User.id == user_id, User.is_active.is_(True))
    )
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


def require_permission(permission_code: str):
    async def dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        allowed = any(
            permission.code == permission_code
            for role in current_user.roles
            if role.is_active
            for permission in role.permissions
            if permission.is_active
        )
        if not allowed:
            raise HTTPException(status_code=403, detail=f"User lacks permission: {permission_code}")
        return current_user

    return dependency
