from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.petty_purchase import (
    PettyPurchaseCreate,
    PettyPurchasePostRequest,
    PettyPurchaseResponse,
    PettyPurchaseVerifyRequest,
)
from app.services.petty_purchase import PettyPurchaseService

router = APIRouter(prefix="/petty-purchases", tags=["petty-purchases"])


@router.post("", response_model=PettyPurchaseResponse, status_code=status.HTTP_201_CREATED)
async def create_petty_purchase(
    payload: PettyPurchaseCreate,
    session: AsyncSession = Depends(get_db_session),
):
    return await PettyPurchaseService(session).create(payload)


@router.get("", response_model=list[PettyPurchaseResponse])
async def list_petty_purchases(
    store_id: int | None = None,
    status: str | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    return await PettyPurchaseService(session).list(store_id, status)


@router.get("/{petty_purchase_id}", response_model=PettyPurchaseResponse)
async def get_petty_purchase(
    petty_purchase_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    return await PettyPurchaseService(session).get(petty_purchase_id)


@router.post("/{petty_purchase_id}/verify", response_model=PettyPurchaseResponse)
async def verify_petty_purchase(
    petty_purchase_id: int,
    payload: PettyPurchaseVerifyRequest,
    session: AsyncSession = Depends(get_db_session),
):
    return await PettyPurchaseService(session).verify(petty_purchase_id, payload)


@router.post("/{petty_purchase_id}/post", response_model=PettyPurchaseResponse)
async def post_petty_purchase(
    petty_purchase_id: int,
    payload: PettyPurchasePostRequest,
    session: AsyncSession = Depends(get_db_session),
):
    return await PettyPurchaseService(session).post(petty_purchase_id, payload)
