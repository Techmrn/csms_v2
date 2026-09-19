from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.security.auth import get_current_user
from app.models.user import User
from app.schemas.petty_purchase import (
    PettyPurchaseCreate,
    PettyPurchasePostRequest,
    PettyPurchaseResponse,
    PettyPurchaseVerifyRequest,
)
from app.services.petty_purchase import PettyPurchaseService
from app.services.authorization import AuthorizationService

router = APIRouter(prefix="/petty-purchases", tags=["petty-purchases"])


@router.post("", response_model=PettyPurchaseResponse, status_code=status.HTTP_201_CREATED)
async def create_petty_purchase(
    payload: PettyPurchaseCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await PettyPurchaseService(session).create(payload, current_user.id)


@router.get("", response_model=list[PettyPurchaseResponse])
async def list_petty_purchases(
    store_id: int | None = None,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "PETTY_PURCHASE_VIEW")
    scoped = await auth.scoped_store_ids(current_user.id, store_id)
    service = PettyPurchaseService(session)
    if scoped is None:
        return await service.list(None, status)
    rows = []
    for sid in scoped:
        rows.extend(await service.list(sid, status))
    return rows


@router.get("/{petty_purchase_id}", response_model=PettyPurchaseResponse)
async def get_petty_purchase(
    petty_purchase_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    await AuthorizationService(session).require_permission(current_user.id, "PETTY_PURCHASE_VIEW")
    purchase = await PettyPurchaseService(session).get(petty_purchase_id)
    await AuthorizationService(session).require_store_visibility(current_user.id, purchase.store_id)
    return purchase


@router.post("/{petty_purchase_id}/verify", response_model=PettyPurchaseResponse)
async def verify_petty_purchase(
    petty_purchase_id: int,
    payload: PettyPurchaseVerifyRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await PettyPurchaseService(session).verify(petty_purchase_id, payload, current_user.id)


@router.post("/{petty_purchase_id}/post", response_model=PettyPurchaseResponse)
async def post_petty_purchase(
    petty_purchase_id: int,
    payload: PettyPurchasePostRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await PettyPurchaseService(session).post(petty_purchase_id, payload, current_user.id)
