from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.security.auth import get_current_user
from app.models.user import User
from app.schemas.stock_control import (
    AdjustmentAuthorizeRequest,
    AdjustmentCreateFromVerificationRequest,
    AdjustmentPostRequest,
    AdjustmentResponse,
    StockVerificationAuthorizeRequest,
    StockVerificationCreate,
    StockVerificationResponse,
    UnserviceableActionRequest,
    UnserviceableCreate,
    UnserviceableResponse,
)
from app.services.stock_control import AdjustmentService, StockVerificationService, UnserviceableService
from app.services.authorization import AuthorizationService


verification_router = APIRouter(prefix="/stock/verifications", tags=["stock-verification"])
adjustment_router = APIRouter(prefix="/stock/adjustments", tags=["stock-adjustments"])
unserviceable_router = APIRouter(prefix="/stock/unserviceable", tags=["unserviceable-stock"])


@verification_router.post("", response_model=StockVerificationResponse, status_code=status.HTTP_201_CREATED)
async def create_verification(
    payload: StockVerificationCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await StockVerificationService(session).create(payload, current_user.id)


@verification_router.get("", response_model=list[StockVerificationResponse])
async def list_verifications(
    store_id: int | None = None,
    status_value: str | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "STOCK_VIEW")
    scoped = await auth.scoped_store_ids(current_user.id, store_id)
    service = StockVerificationService(session)
    if scoped is None:
        return await service.list(None, status_value)
    rows = []
    for sid in scoped:
        rows.extend(await service.list(sid, status_value))
    return rows


@verification_router.get("/{verification_id}", response_model=StockVerificationResponse)
async def get_verification(verification_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return await StockVerificationService(session).get(verification_id)


@verification_router.post("/{verification_id}/authorize", response_model=StockVerificationResponse)
async def authorize_verification(
    verification_id: int,
    payload: StockVerificationAuthorizeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await StockVerificationService(session).authorize(verification_id, payload, current_user.id)


@adjustment_router.post("/from-verification", response_model=AdjustmentResponse, status_code=status.HTTP_201_CREATED)
async def create_adjustment_from_verification(
    payload: AdjustmentCreateFromVerificationRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await AdjustmentService(session).create_from_verification(payload, current_user.id)


@adjustment_router.get("", response_model=list[AdjustmentResponse])
async def list_adjustments(
    store_id: int | None = None,
    status_value: str | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "STOCK_VIEW")
    scoped = await auth.scoped_store_ids(current_user.id, store_id)
    service = AdjustmentService(session)
    if scoped is None:
        return await service.list(None, status_value)
    rows = []
    for sid in scoped:
        rows.extend(await service.list(sid, status_value))
    return rows


@adjustment_router.get("/{adjustment_id}", response_model=AdjustmentResponse)
async def get_adjustment(adjustment_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return await AdjustmentService(session).get(adjustment_id)


@adjustment_router.post("/{adjustment_id}/authorize", response_model=AdjustmentResponse)
async def authorize_adjustment(
    adjustment_id: int,
    payload: AdjustmentAuthorizeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await AdjustmentService(session).authorize(adjustment_id, payload, current_user.id)


@adjustment_router.post("/{adjustment_id}/post", response_model=AdjustmentResponse)
async def post_adjustment(
    adjustment_id: int,
    payload: AdjustmentPostRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await AdjustmentService(session).post(adjustment_id, payload, current_user.id)


@unserviceable_router.post("", response_model=UnserviceableResponse, status_code=status.HTTP_201_CREATED)
async def create_unserviceable(
    payload: UnserviceableCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await UnserviceableService(session).create(payload, current_user.id)


@unserviceable_router.get("", response_model=list[UnserviceableResponse])
async def list_unserviceable(
    store_id: int | None = None,
    status_value: str | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "STOCK_VIEW")
    scoped = await auth.scoped_store_ids(current_user.id, store_id)
    service = UnserviceableService(session)
    if scoped is None:
        return await service.list(None, status_value)
    rows = []
    for sid in scoped:
        rows.extend(await service.list(sid, status_value))
    return rows


@unserviceable_router.get("/{record_id}", response_model=UnserviceableResponse)
async def get_unserviceable(record_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return await UnserviceableService(session).get(record_id)


@unserviceable_router.post("/{record_id}/verify", response_model=UnserviceableResponse)
async def verify_unserviceable(
    record_id: int,
    payload: UnserviceableActionRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await UnserviceableService(session).verify(record_id, payload, current_user.id)


@unserviceable_router.post("/{record_id}/authorize", response_model=UnserviceableResponse)
async def authorize_unserviceable(
    record_id: int,
    payload: UnserviceableActionRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await UnserviceableService(session).authorize(record_id, payload, current_user.id)


@unserviceable_router.post("/{record_id}/post", response_model=UnserviceableResponse)
async def post_unserviceable(
    record_id: int,
    payload: UnserviceableActionRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await UnserviceableService(session).post(record_id, payload, current_user.id)
