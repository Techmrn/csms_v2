from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.transfer import (
    TransferDispatchRequest,
    TransferReceiveRequest,
    TransferResponse,
    TransferDiscrepancyResolutionRequest,
    TransferDiscrepancyResponse,
)
from app.services.transfer import TransferService

router = APIRouter(prefix="/transfers", tags=["stock-transfers"])


@router.get("", response_model=list[TransferResponse])
async def list_transfers(
    store_id: int | None = None,
    status: str | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    return await TransferService(session).list(store_id, status)


@router.get("/{transfer_id}", response_model=TransferResponse)
async def get_transfer(transfer_id: int, session: AsyncSession = Depends(get_db_session)):
    return await TransferService(session).get(transfer_id)


@router.post("/requisitions/{requisition_id}/dispatch", response_model=TransferResponse | None)
async def dispatch_transfer(
    requisition_id: int,
    payload: TransferDispatchRequest,
    session: AsyncSession = Depends(get_db_session),
):
    return await TransferService(session).dispatch(requisition_id, payload)


@router.post("/{transfer_id}/receive", response_model=TransferResponse)
async def receive_transfer(
    transfer_id: int,
    payload: TransferReceiveRequest,
    session: AsyncSession = Depends(get_db_session),
):
    return await TransferService(session).receive(transfer_id, payload)


@router.post("/discrepancies/{discrepancy_id}/resolve", response_model=TransferDiscrepancyResponse)
async def resolve_discrepancy(
    discrepancy_id: int,
    payload: TransferDiscrepancyResolutionRequest,
    session: AsyncSession = Depends(get_db_session),
):
    return await TransferService(session).resolve_discrepancy(discrepancy_id, payload)
