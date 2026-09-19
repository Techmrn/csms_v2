from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.security.auth import get_current_user
from app.models.user import User
from app.schemas.requisition import (
    BranchApprovalRequest,
    CentralApprovalRequest,
    RequisitionCreate,
    RequisitionResponse,
)
from app.services.requisition import RequisitionService
from app.services.authorization import AuthorizationService

router = APIRouter(prefix="/requisitions", tags=["central-store-requisitions"])


@router.post("", response_model=RequisitionResponse, status_code=status.HTTP_201_CREATED)
async def create_requisition(payload: RequisitionCreate, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return await RequisitionService(session).create(payload, current_user.id)


@router.get("", response_model=list[RequisitionResponse])
async def list_requisitions(
    requesting_store_id: int | None = None,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "REQUISITION_VIEW")
    if requesting_store_id is None:
        try:
            await auth.require_permission(current_user.id, "REQUISITION_APPROVE_CENTRAL")
            scoped = None
        except HTTPException:
            scoped = await auth.scoped_store_ids(current_user.id, requesting_store_id)
    else:
        scoped = await auth.scoped_store_ids(current_user.id, requesting_store_id)
    service = RequisitionService(session)
    if scoped is None:
        return await service.list(None, status)
    rows = []
    for sid in scoped:
        rows.extend(await service.list(sid, status))
    return rows


@router.get("/{requisition_id}", response_model=RequisitionResponse)
async def get_requisition(requisition_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "REQUISITION_VIEW")
    requisition = await RequisitionService(session).get(requisition_id)
    try:
        await auth.require_permission(current_user.id, "REQUISITION_APPROVE_CENTRAL")
    except HTTPException:
        await auth.require_store_visibility(current_user.id, requisition.requesting_store_id)
    return requisition


@router.post("/{requisition_id}/approve-branch", response_model=RequisitionResponse)
async def approve_branch(
    requisition_id: int,
    payload: BranchApprovalRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await RequisitionService(session).approve_branch(requisition_id, payload, current_user.id, approve=True)


@router.post("/{requisition_id}/reject-branch", response_model=RequisitionResponse)
async def reject_branch(
    requisition_id: int,
    payload: BranchApprovalRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await RequisitionService(session).reject_branch(requisition_id, payload, current_user.id)


@router.post("/{requisition_id}/approve-central", response_model=RequisitionResponse)
async def approve_central(
    requisition_id: int,
    payload: CentralApprovalRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await RequisitionService(session).approve_central(requisition_id, payload, current_user.id)
