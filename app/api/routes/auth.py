from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db_session
from app.models.role import Role
from app.models.user import User
from app.security.auth import authenticate_user, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/token")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: AsyncSession = Depends(get_db_session),
):
    user = await authenticate_user(session, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    roles = [role.code for role in current_user.roles if role.is_active]
    permissions = sorted(
        {
            permission.code
            for role in current_user.roles
            if role.is_active
            for permission in role.permissions
            if permission.is_active
        }
    )
    stores = [store.code for store in current_user.stores if store.is_active]
    return {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "designation": current_user.designation,
        "office_id": current_user.office_id,
        "section_id": current_user.section_id,
        "roles": roles,
        "permissions": permissions,
        "stores": stores,
    }
