from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.security.auth import get_current_user
from app.models.user import User
from app.schemas.transfer import (
    TransferCreateRequest,
    TransferApproveBranchRequest,
    TransferApproveDirectorateRequest,
    TransferAuthorizeSupplyRequest,
    TransferRejectRequest,
    TransferDispatchRequest,
    TransferGatePassUpdateRequest,
    TransferReceiveRequest,
    TransferResponse,
    TransferDiscrepancyResolutionRequest,
    TransferDiscrepancyResponse,
)
from app.services.transfer import TransferService
from app.services.authorization import AuthorizationService

router = APIRouter(prefix="/transfers", tags=["stock-transfers"])


@router.get("", response_model=list[TransferResponse])
async def list_transfers(
    store_id: int | None = None,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "STOCK_TRANSFER_VIEW")
    scoped = await auth.scoped_store_ids(current_user.id, store_id)
    service = TransferService(session)
    if scoped is None:
        return await service.list(None, status)
    rows = []
    for sid in scoped:
        rows.extend(await service.list(sid, status))
    return rows


@router.post("", response_model=TransferResponse)
async def create_transfer(
    payload: TransferCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await TransferService(session).create(payload, current_user.id)


@router.get("/{transfer_id}", response_model=TransferResponse)
async def get_transfer(
    transfer_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "STOCK_TRANSFER_VIEW")
    transfer = await TransferService(session).get(transfer_id)
    visible = await auth.get_visible_stores(current_user.id)
    if (
        visible is not None
        and transfer.source_store_id not in visible
        and transfer.destination_store_id not in visible
    ):
        raise HTTPException(403, "User is not authorized to access this transfer")
    return transfer


@router.post("/{transfer_id}/approve-branch", response_model=TransferResponse)
async def approve_transfer_branch(
    transfer_id: int,
    payload: TransferApproveBranchRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await TransferService(session).approve_branch(transfer_id, payload, current_user.id)


@router.post("/{transfer_id}/approve-directorate", response_model=TransferResponse)
async def approve_transfer_directorate(
    transfer_id: int,
    payload: TransferApproveDirectorateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await TransferService(session).approve_directorate(transfer_id, payload, current_user.id)


@router.post("/{transfer_id}/authorize-supply", response_model=TransferResponse)
async def authorize_transfer_supply(
    transfer_id: int,
    payload: TransferAuthorizeSupplyRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await TransferService(session).authorize_supplying_branch(transfer_id, payload, current_user.id)


@router.post("/{transfer_id}/reject", response_model=TransferResponse)
async def reject_transfer(
    transfer_id: int,
    payload: TransferRejectRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await TransferService(session).reject(transfer_id, payload, current_user.id)


@router.post("/{transfer_id}/dispatch", response_model=TransferResponse)
async def dispatch_direct_transfer(
    transfer_id: int,
    payload: TransferDispatchRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await TransferService(session).dispatch_transfer(transfer_id, payload, current_user.id)


@router.post("/requisitions/{requisition_id}/dispatch", response_model=TransferResponse | None)
async def dispatch_transfer(
    requisition_id: int,
    payload: TransferDispatchRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await TransferService(session).dispatch(requisition_id, payload, current_user.id)


@router.post("/{transfer_id}/receive", response_model=TransferResponse)
async def receive_transfer(
    transfer_id: int,
    payload: TransferReceiveRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await TransferService(session).receive(transfer_id, payload, current_user.id)


@router.post("/discrepancies/{discrepancy_id}/resolve", response_model=TransferDiscrepancyResponse)
async def resolve_discrepancy(
    discrepancy_id: int,
    payload: TransferDiscrepancyResolutionRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await TransferService(session).resolve_discrepancy(discrepancy_id, payload, current_user.id)


@router.patch("/{transfer_id}/gate-pass", response_model=TransferResponse)
async def update_transfer_gate_pass(
    transfer_id: int,
    payload: TransferGatePassUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await TransferService(session).update_gate_pass_details(
        transfer_id, payload.vehicle_no, payload.received_by_name, current_user.id
    )
