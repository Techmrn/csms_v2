from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.user import User
from app.paper_store.models.item import PaperItem
from app.paper_store.schemas.indent_issue import (
    PaperIndentRead,
    PaperIssueRead,
    PaperManualIndentCreate,
    PaperOnlineIndentCreate,
    PaperOnlineIndentIssueRequest,
)
from app.paper_store.schemas.item import PaperItemRead
from app.paper_store.schemas.opening import PaperOpeningStockCreate, PaperOpeningStockRead
from app.paper_store.schemas.receipt import PaperReceiptCreate, PaperReceiptRead
from app.paper_store.schemas.transfer import (
    PaperTransferCreateRequest,
    PaperTransferDispatchRequest,
    PaperTransferRead,
    PaperTransferReceiveRequest,
)
from app.paper_store.services.indent_issue import PaperIndentIssueService
from app.paper_store.services.opening import PaperOpeningService
from app.paper_store.services.receipt import PaperReceiptService
from app.paper_store.services.registers import PaperRegisterService
from app.paper_store.services.stock import PaperStockService
from app.paper_store.services.transfer import PaperTransferService
from app.security.auth import get_current_user
from app.services.authorization import AuthorizationService

router = APIRouter(prefix="/v1/paper", tags=["paper-store"])


@router.get("/items", response_model=list[PaperItemRead])
async def list_paper_items(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "PAPER_VIEW")
    stmt = select(PaperItem).where(PaperItem.is_active.is_(True)).order_by(PaperItem.name)
    return list((await session.scalars(stmt)).all())


@router.get("/opening-stocks", response_model=list[PaperOpeningStockRead])
async def list_paper_openings(
    store_id: int | None = Query(None),
    financial_year_id: int | None = Query(None),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "PAPER_VIEW")
    if store_id is not None:
        await auth.require_paper_warehouse(store_id)
        await auth.require_store_visibility(current_user.id, store_id)
    svc = PaperOpeningService(session)
    return await svc.list(store_id=store_id, financial_year_id=financial_year_id)


@router.post("/opening-stocks", response_model=PaperOpeningStockRead, status_code=201)
async def create_paper_opening(
    payload: PaperOpeningStockCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    svc = PaperOpeningService(session)
    return await svc.create_and_post(payload, actor_id=current_user.id)


@router.get("/receipts", response_model=list[PaperReceiptRead])
async def list_paper_receipts(
    store_id: int | None = Query(None),
    financial_year_id: int | None = Query(None),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "PAPER_VIEW")
    if store_id is not None:
        await auth.require_paper_warehouse(store_id)
        await auth.require_store_visibility(current_user.id, store_id)
    svc = PaperReceiptService(session)
    return await svc.repo.list(store_id=store_id, financial_year_id=financial_year_id)


@router.get("/receipts/{receipt_id}", response_model=PaperReceiptRead)
async def get_paper_receipt(
    receipt_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "PAPER_VIEW")
    svc = PaperReceiptService(session)
    receipt = await svc.repo.get(receipt_id)
    if not receipt:
        raise HTTPException(404, "Paper receipt not found")
    await auth.require_store_visibility(current_user.id, receipt.store_id)
    return receipt


@router.post("/receipts", response_model=PaperReceiptRead, status_code=201)
async def create_paper_receipt(
    payload: PaperReceiptCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    svc = PaperReceiptService(session)
    return await svc.create_and_post(payload, actor_id=current_user.id)


@router.get("/stock")
async def get_paper_stock(
    store_id: int = Query(...),
    financial_year_id: int = Query(...),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "PAPER_VIEW")
    await auth.require_paper_warehouse(store_id)
    await auth.require_store_visibility(current_user.id, store_id)
    svc = PaperStockService(session)
    rows = await svc.current_stock(store_id, financial_year_id)
    return [
        {
            "item_id": r["item"].id,
            "item_code": r["item"].code,
            "item_name": r["item"].name,
            "paper_type": r["item"].paper_type,
            "form_type": r["item"].form_type,
            "gsm": r["item"].gsm,
            "sheets_per_ream": r["item"].sheets_per_ream,
            "unit_id": r["item"].unit_id,
            "opening_sheets": r["opening_sheets"],
            "inward_sheets": r["inward_sheets"],
            "outward_sheets": r["outward_sheets"],
            "balance_sheets": r["balance_sheets"],
            "balance_reams": r["balance_reams"],
            "balance_loose_sheets": r["balance_loose_sheets"],
            "balance_qty": float(r["balance_qty"]),
            "balance_weight_kg": float(r["balance_weight_kg"]),
            "formatted_balance": r["formatted_balance"],
        }
        for r in rows
    ]


@router.get("/indents", response_model=list[PaperIndentRead])
async def list_paper_indents(
    store_id: int | None = Query(None),
    financial_year_id: int | None = Query(None),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "PAPER_VIEW")
    if store_id is not None:
        await auth.require_paper_warehouse(store_id)
        await auth.require_store_visibility(current_user.id, store_id)
    svc = PaperIndentIssueService(session)
    return await svc.list_indents(store_id=store_id, financial_year_id=financial_year_id)


@router.post("/indents/manual", response_model=PaperIndentRead, status_code=201)
async def create_manual_indent_and_issue(
    payload: PaperManualIndentCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    svc = PaperIndentIssueService(session)
    indent, _ = await svc.create_manual_indent_and_issue(payload, actor_id=current_user.id)
    return await svc.get_indent(indent.id)


@router.post("/indents/online", response_model=PaperIndentRead, status_code=201)
async def create_online_paper_indent(
    payload: PaperOnlineIndentCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    svc = PaperIndentIssueService(session)
    return await svc.create_online_indent(payload, actor_id=current_user.id)


@router.post("/indents/{indent_id}/issue", response_model=PaperIssueRead)
async def issue_online_paper_indent(
    indent_id: int,
    payload: PaperOnlineIndentIssueRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    svc = PaperIndentIssueService(session)
    return await svc.issue_from_online_indent(indent_id, payload, actor_id=current_user.id)


@router.get("/transfers", response_model=list[PaperTransferRead])
async def list_paper_transfers(
    store_id: int | None = Query(None),
    financial_year_id: int | None = Query(None),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "PAPER_VIEW")
    if store_id is not None:
        await auth.require_paper_warehouse(store_id)
        await auth.require_store_visibility(current_user.id, store_id)
    svc = PaperTransferService(session)
    return await svc.list(store_id=store_id, financial_year_id=financial_year_id)


@router.post("/transfers", response_model=PaperTransferRead, status_code=201)
async def create_paper_transfer(
    payload: PaperTransferCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    svc = PaperTransferService(session)
    return await svc.create(payload, actor_id=current_user.id)


@router.post("/transfers/{transfer_id}/dispatch", response_model=PaperTransferRead)
async def dispatch_paper_transfer(
    transfer_id: int,
    payload: PaperTransferDispatchRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    svc = PaperTransferService(session)
    return await svc.dispatch(transfer_id, payload, actor_id=current_user.id)


@router.post("/transfers/{transfer_id}/receive", response_model=PaperTransferRead)
async def receive_paper_transfer(
    transfer_id: int,
    payload: PaperTransferReceiveRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_db_session),
):
    svc = PaperTransferService(session)
    return await svc.receive(transfer_id, payload, actor_id=current_user.id)


@router.get("/registers/{kind}")
async def get_paper_register_api(
    kind: str,
    store_id: int | None = Query(None),
    financial_year_id: int | None = Query(None),
    search: str | None = Query(None),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    svc = PaperRegisterService(session)
    if kind == "stock":
        if not store_id or not financial_year_id:
            raise HTTPException(422, "store_id and financial_year_id are required for stock register")
        return await svc.stock_register(current_user.id, store_id, financial_year_id, search=search)
    if kind == "receipts":
        return await svc.receipt_register(current_user.id, store_id, financial_year_id, from_date, to_date, search=search)
    if kind == "issues":
        return await svc.issue_register(current_user.id, store_id, financial_year_id, from_date, to_date, search=search)
    if kind == "transfers":
        return await svc.transfer_register(current_user.id, store_id, financial_year_id, from_date, to_date, search=search)
    if kind == "opening":
        return await svc.opening_register(current_user.id, store_id, financial_year_id, search=search)
    if kind == "ledger":
        return await svc.ledger_register(current_user.id, store_id, financial_year_id, None, from_date, to_date, search=search)
    raise HTTPException(404, f"Unknown paper register kind: {kind}")
