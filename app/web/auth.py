from typing import Annotated

import jwt
from fastapi import Cookie, Depends, Request
from fastapi.responses import RedirectResponse
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.session import get_db_session
from app.models.role import Role
from app.models.user import User

settings = get_settings()


async def get_user_from_token(session: AsyncSession, token: str) -> User | None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        subject = payload.get("sub")
        if subject is None:
            return None
        user_id = int(subject)
    except (InvalidTokenError, ValueError, TypeError):
        return None

    stmt = (
        select(User)
        .options(
            selectinload(User.roles).selectinload(Role.permissions),
            selectinload(User.stores),
        )
        .where(User.id == user_id, User.is_active.is_(True))
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_web_current_user(
    request: Request,
    csms_access_token: Annotated[str | None, Cookie()] = None,
    session: AsyncSession = Depends(get_db_session),
) -> User | RedirectResponse:
    if not csms_access_token:
        return RedirectResponse(url="/login", status_code=303)

    user = await get_user_from_token(session, csms_access_token)
    if user is None:
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie("csms_access_token")
        return response
    return user
