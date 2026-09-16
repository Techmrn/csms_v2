from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.security.auth import get_current_user
from app.models.user import User
from app.schemas.receipt import ReceiptCreate, ReceiptResponse
from app.services.receipt import ReceiptService
from app.services.authorization import AuthorizationService

router = APIRouter(prefix="/receipts", tags=["receipts"])


@router.post("", response_model=ReceiptResponse, status_code=status.HTTP_201_CREATED)
async def create_receipt(
    payload: ReceiptCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await ReceiptService(session).create(payload, current_user.id)


@router.get("", response_model=list[ReceiptResponse])
async def list_receipts(
    store_id: int | None = None,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "STOCK_RECEIPT_VIEW")
    scoped = await auth.scoped_store_ids(current_user.id, store_id)
    service = ReceiptService(session)
    if scoped is None:
        return await service.list(None, status)
    rows = []
    for sid in scoped:
        rows.extend(await service.list(sid, status))
    return rows


@router.get("/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(receipt_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return await ReceiptService(session).get(receipt_id)


@router.post("/{receipt_id}/verify", response_model=ReceiptResponse)
async def verify_receipt(receipt_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return await ReceiptService(session).verify(receipt_id, current_user.id)


@router.post("/{receipt_id}/post", response_model=ReceiptResponse)
async def post_receipt(receipt_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return await ReceiptService(session).post(receipt_id, current_user.id)
