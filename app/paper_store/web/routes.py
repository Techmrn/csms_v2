from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db_session
from app.models.financial_year import FinancialYear
from app.models.section import Section
from app.models.store import Store
from app.models.unit import Unit
from app.models.user import User
from app.paper_store.models.item import PaperItem
from app.paper_store.schemas.indent_issue import (
    PaperIndentLineCreate,
    PaperManualIndentCreate,
    PaperOnlineIndentCreate,
    PaperOnlineIndentIssueLine,
    PaperOnlineIndentIssueRequest,
)
from app.paper_store.schemas.opening import (
    PaperOpeningStockCreate,
    PaperOpeningStockLineCreate,
)
from app.paper_store.schemas.receipt import PaperReceiptCreate, PaperReceiptLineCreate
from app.paper_store.schemas.transfer import (
    PaperTransferCreateRequest,
    PaperTransferDispatchLine,
    PaperTransferDispatchRequest,
    PaperTransferLineCreate,
    PaperTransferReceiveLine,
    PaperTransferReceiveRequest,
)
from app.paper_store.services.indent_issue import PaperIndentIssueService
from app.paper_store.services.opening import PaperOpeningService
from app.paper_store.services.receipt import PaperReceiptService
from app.paper_store.services.registers import PaperRegisterService
from app.paper_store.services.stock import PaperStockService
from app.paper_store.services.transfer import PaperTransferService
from app.paper_store.services.units import format_paper_balance, from_total_sheets
from app.services.authorization import AuthorizationService
from app.services.pdf_reports import make_transfer_gate_pass_pdf, make_voucher_pdf
from app.web.auth import get_web_current_user
from app.web.routes import (
    page_window,
    pdf_response,
    permission_codes,
    redirect_with_error,
    redirect_with_success,
    render,
)

router = APIRouter(prefix="/app/paper", tags=["paper-web"])


def _int_val(seq: list, idx: int, default: int = 0) -> int:
    if idx >= len(seq) or not str(seq[idx]).strip():
        return default
    return int(str(seq[idx]).strip())


def _dec_val(seq: list, idx: int, default: Decimal | None = Decimal("0")) -> Decimal | None:
    if idx >= len(seq) or not str(seq[idx]).strip():
        return default
    return Decimal(str(seq[idx]).strip())


async def load_paper_store_context(
    user: User,
    session: AsyncSession,
    requested_store_id: int | None,
    requested_fy_id: int | None,
):
    auth = AuthorizationService(session)
    visible_ids = await auth.get_visible_paper_warehouses(user.id)

    stmt = (
        select(Store)
        .options(selectinload(Store.office))
        .where(
            Store.is_active.is_(True),
            Store.store_type == "PAPER_WAREHOUSE",
            Store.id.in_(visible_ids) if visible_ids else Store.id == -1,
        )
        .order_by(Store.name)
    )
    paper_stores = list((await session.scalars(stmt)).all())
    fys = list(
        (await session.scalars(select(FinancialYear).order_by(FinancialYear.start_date.desc()))).all()
    )

    selected_store = (
        next((s for s in paper_stores if s.id == requested_store_id), None)
        if requested_store_id
        else None
    )
    if selected_store is None and paper_stores:
        assigned_ids = {s.id for s in user.stores if s.is_active}
        selected_store = next((s for s in paper_stores if s.id in assigned_ids), paper_stores[0])

    selected_fy = (
        next((fy for fy in fys if fy.id == requested_fy_id), None)
        if requested_fy_id
        else None
    )
    if selected_fy is None:
        selected_fy = next((fy for fy in fys if fy.is_current), fys[0] if fys else None)

    return paper_stores, fys, selected_store, selected_fy


@router.get("")
async def paper_root(
    current_user: User | RedirectResponse = Depends(get_web_current_user),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    return RedirectResponse(url="/app/paper/stock", status_code=303)


# =========================================================================
# 0. OPENING STOCK ROUTES (FIRST-TIME SETUP & FY CARRY-FORWARD VIEW)
# =========================================================================

@router.get("/opening-stock")
async def paper_opening_list(
    request: Request,
    store_id: int | None = None,
    financial_year_id: int | None = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    auth = AuthorizationService(session)
    try:
        await auth.require_permission(current_user.id, "PAPER_VIEW")
    except HTTPException as exc:
        return redirect_with_error("/app", exc.detail)

    paper_stores, fys, selected_store, selected_fy = await load_paper_store_context(
        current_user, session, store_id, financial_year_id
    )
    svc = PaperOpeningService(session)
    openings = await svc.list(
        store_id=selected_store.id if selected_store else None,
        financial_year_id=selected_fy.id if selected_fy else None,
    )
    return render(
        request,
        "paper/opening.html",
        current_user,
        openings=openings,
        paper_stores=paper_stores,
        financial_years=fys,
        selected_store=selected_store,
        selected_fy=selected_fy,
    )


@router.get("/opening-stock/new")
async def paper_opening_new(
    request: Request,
    store_id: int | None = None,
    financial_year_id: int | None = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    auth = AuthorizationService(session)
    try:
        await auth.require_permission(current_user.id, "PAPER_OPENING_CREATE")
    except HTTPException as exc:
        return redirect_with_error("/app/paper/opening-stock", exc.detail)

    paper_stores, fys, selected_store, selected_fy = await load_paper_store_context(
        current_user, session, store_id, financial_year_id
    )
    if not paper_stores:
        return redirect_with_error("/app", "No Paper Warehouse is assigned to your user.")
    if selected_store:
        try:
            await auth.require_store_assignment(current_user.id, selected_store.id)
        except HTTPException as exc:
            return redirect_with_error("/app/paper/opening-stock", exc.detail)

    paper_items = list(
        (
            await session.scalars(
                select(PaperItem)
                .options(selectinload(PaperItem.unit))
                .where(PaperItem.is_active.is_(True))
                .order_by(PaperItem.name)
            )
        ).all()
    )
    return render(
        request,
        "paper/opening_new.html",
        current_user,
        paper_stores=paper_stores,
        financial_years=fys,
        selected_store=selected_store,
        selected_fy=selected_fy,
        paper_items=paper_items,
        today=(selected_fy.start_date.isoformat() if selected_fy else date.today().isoformat()),
    )


@router.post("/opening-stock/new")
async def paper_opening_submit(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    form_data = await request.form()
    try:
        store_id = int(form_data.get("store_id", "0"))
        financial_year_id = int(form_data.get("financial_year_id", "0"))
        opening_date = date.fromisoformat(str(form_data.get("opening_date", "")))
        remarks = str(form_data.get("remarks", "")).strip() or None

        item_ids = form_data.getlist("paper_item_id")
        reams_list = form_data.getlist("reams")
        sheets_list = form_data.getlist("sheets")
        weights_kg = form_data.getlist("weight_kg")
        reel_counts = form_data.getlist("reel_count")
        line_remarks_list = form_data.getlist("line_remarks")

        lines = []
        for i, raw_id in enumerate(item_ids):
            if not str(raw_id).strip():
                continue
            rc_raw = reel_counts[i] if i < len(reel_counts) else ""
            lines.append(
                PaperOpeningStockLineCreate(
                    paper_item_id=int(str(raw_id)),
                    reams=_int_val(reams_list, i, 0),
                    sheets=_int_val(sheets_list, i, 0),
                    weight_kg=_dec_val(weights_kg, i, Decimal("0")) or Decimal("0"),
                    reel_count=int(str(rc_raw)) if str(rc_raw).strip() else None,
                    remarks=str(line_remarks_list[i]).strip() if i < len(line_remarks_list) and line_remarks_list[i] else None,
                )
            )

        if not lines:
            return redirect_with_error("/app/paper/opening-stock/new", "At least one paper item is required")

        payload = PaperOpeningStockCreate(
            store_id=store_id,
            financial_year_id=financial_year_id,
            opening_date=opening_date,
            remarks=remarks,
            lines=lines,
        )
        opening = await PaperOpeningService(session).create_and_post(payload, actor_id=current_user.id)
        return redirect_with_success(
            f"/app/paper/opening-stock/{opening.id}",
            f"Warehouse opening stock {opening.opening_no} posted successfully.",
        )
    except HTTPException as exc:
        return redirect_with_error("/app/paper/opening-stock/new", exc.detail)
    except Exception as exc:
        return redirect_with_error("/app/paper/opening-stock/new", f"Failed to post opening stock: {str(exc)}")


@router.get("/opening-stock/{opening_id}.pdf")
async def paper_opening_pdf(
    opening_id: int,
    paper_size: str = "auto",
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "PAPER_VIEW")
    opening = await PaperOpeningService(session).get(opening_id)
    if not opening:
        raise HTTPException(404, "Paper opening stock record not found")
    await auth.require_store_visibility(current_user.id, opening.store_id)

    rows = []
    for line in opening.lines:
        item = line.paper_item
        ftype = item.form_type if item else "SHEET"
        spr = item.sheets_per_ream if item else 500
        rows.append({
            "code": item.code if item else str(line.paper_item_id),
            "name": f"{item.name} ({item.gsm} GSM · {item.paper_type})" if item else str(line.paper_item_id),
            "form": ftype,
            "opening": format_paper_balance(ftype, line.total_sheets, line.weight_kg, spr),
            "reels": line.reel_count if line.reel_count is not None else "—",
            "remarks": line.remarks or "—",
        })
    cols = [
        ("code", "Code"),
        ("name", "Paper Specification"),
        ("form", "Form"),
        ("opening", "Opening Balance"),
        ("reels", "Reels"),
        ("remarks", "Remarks"),
    ]
    meta_items = [
        ("Opening No", opening.opening_no),
        ("Opening Date", str(opening.opening_date)),
        ("Entry Mode", opening.opening_type),
        ("Paper Warehouse", opening.store.name if opening.store else str(opening.store_id)),
        ("Financial Year", opening.financial_year.year_name if opening.financial_year else "—"),
        ("Ledger Status", opening.status),
    ]
    pdf = make_voucher_pdf(
        "Paper Opening Stock Voucher",
        cols,
        rows,
        subtitle="Authorized Financial-Year Opening Paper Inventory",
        ref_no=opening.opening_no,
        doc_date=str(opening.opening_date),
        meta_items=meta_items,
        notes=opening.remarks,
        signatures=[
            {"role": "Recorded By", "label": current_user.full_name},
            {"role": "Verified By", "label": "Warehouseman / Officer-in-Charge"},
            {"role": "Approved By", "label": "Head of Press"},
        ],
        paper_size=paper_size,
        domain="paper",
        generated_by=current_user.full_name,
    )
    safe_no = opening.opening_no.lower().replace("/", "_").replace("-", "_")
    return StreamingResponse(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="paper_opening_{safe_no}.pdf"'},
    )


@router.get("/opening-stock/{opening_id}")
async def paper_opening_detail(
    request: Request,
    opening_id: int,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    auth = AuthorizationService(session)
    try:
        await auth.require_permission(current_user.id, "PAPER_VIEW")
    except HTTPException as exc:
        return redirect_with_error("/app/paper/opening-stock", exc.detail)

    opening = await PaperOpeningService(session).get(opening_id)
    if not opening:
        return redirect_with_error("/app/paper/opening-stock", "Opening stock record not found")
    try:
        await auth.require_store_visibility(current_user.id, opening.store_id)
    except HTTPException as exc:
        return redirect_with_error("/app/paper/opening-stock", exc.detail)

    return render(
        request,
        "paper/opening_detail.html",
        current_user,
        opening=opening,
        format_paper=format_paper_balance,
    )


# =========================================================================
# 1. RECEIPT ROUTES (STATIONERY DEPARTMENT)
# =========================================================================

@router.get("/receipts")
async def paper_receipts_list(
    request: Request,
    store_id: int | None = None,
    financial_year_id: int | None = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    auth = AuthorizationService(session)
    try:
        await auth.require_permission(current_user.id, "PAPER_VIEW")
    except HTTPException as exc:
        return redirect_with_error("/app", exc.detail)

    paper_stores, fys, selected_store, selected_fy = await load_paper_store_context(
        current_user, session, store_id, financial_year_id
    )
    svc = PaperReceiptService(session)
    receipts = await svc.repo.list(
        store_id=selected_store.id if selected_store else None,
        financial_year_id=selected_fy.id if selected_fy else None,
    )

    return render(
        request,
        "paper/receipts.html",
        current_user,
        receipts=receipts,
        paper_stores=paper_stores,
        financial_years=fys,
        selected_store=selected_store,
        selected_fy=selected_fy,
    )


@router.get("/receipts/new")
async def paper_receipt_new(
    request: Request,
    store_id: int | None = None,
    financial_year_id: int | None = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    auth = AuthorizationService(session)
    try:
        await auth.require_permission(current_user.id, "PAPER_RECEIPT_CREATE")
    except HTTPException as exc:
        return redirect_with_error("/app/paper/receipts", exc.detail)

    paper_stores, fys, selected_store, selected_fy = await load_paper_store_context(
        current_user, session, store_id, financial_year_id
    )
    if not paper_stores:
        return redirect_with_error("/app", "No Paper Warehouse is configured or assigned to your user.")

    paper_items = list(
        (
            await session.scalars(
                select(PaperItem)
                .options(selectinload(PaperItem.unit))
                .where(PaperItem.is_active.is_(True))
                .order_by(PaperItem.name)
            )
        ).all()
    )
    units = list((await session.scalars(select(Unit).order_by(Unit.code))).all())

    return render(
        request,
        "paper/receipt_new.html",
        current_user,
        paper_stores=paper_stores,
        financial_years=fys,
        selected_store=selected_store,
        selected_fy=selected_fy,
        paper_items=paper_items,
        units=units,
        today=date.today().isoformat(),
    )


@router.post("/receipts/new")
async def paper_receipt_submit(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    form_data = await request.form()

    try:
        store_id = int(form_data.get("store_id", "0"))
        financial_year_id = int(form_data.get("financial_year_id", "0")) or None
        receipt_date = date.fromisoformat(str(form_data.get("receipt_date", "")))
        source_depot = str(form_data.get("source_depot", "")).strip()
        allotment_no = str(form_data.get("allotment_no", "")).strip() or None
        allotment_date_raw = form_data.get("allotment_date", "")
        allotment_date = date.fromisoformat(str(allotment_date_raw)) if allotment_date_raw else None
        challan_no = str(form_data.get("challan_no", "")).strip() or None
        challan_date_raw = form_data.get("challan_date", "")
        challan_date = date.fromisoformat(str(challan_date_raw)) if challan_date_raw else None
        vehicle_no = str(form_data.get("vehicle_no", "")).strip() or None
        carrier_name = str(form_data.get("carrier_name", "")).strip() or None
        lorry_receipt_no = str(form_data.get("lorry_receipt_no", "")).strip() or None
        remarks = str(form_data.get("remarks", "")).strip() or None

        paper_item_ids = form_data.getlist("paper_item_id")
        unit_ids = form_data.getlist("unit_id")
        challan_reams = form_data.getlist("challan_reams")
        challan_sheets = form_data.getlist("challan_sheets")
        received_reams = form_data.getlist("received_reams")
        received_sheets = form_data.getlist("received_sheets")
        accepted_reams = form_data.getlist("accepted_reams")
        accepted_sheets = form_data.getlist("accepted_sheets")
        damaged_reams = form_data.getlist("damaged_reams")
        damaged_sheets = form_data.getlist("damaged_sheets")

        challan_quantities = form_data.getlist("challan_quantity")
        received_quantities = form_data.getlist("received_quantity")
        accepted_quantities = form_data.getlist("accepted_quantity")
        damaged_quantities = form_data.getlist("damaged_quantity")

        weights_kg = form_data.getlist("weight_kg")
        reel_counts = form_data.getlist("reel_count")
        reel_numbers_list = form_data.getlist("reel_numbers")
        line_remarks_list = form_data.getlist("line_remarks")

        lines = []
        for i, raw_item_id in enumerate(paper_item_ids):
            if not str(raw_item_id).strip():
                continue

            rc_raw = reel_counts[i] if i < len(reel_counts) else ""
            lines.append(
                PaperReceiptLineCreate(
                    paper_item_id=int(str(raw_item_id)),
                    unit_id=_int_val(unit_ids, i, 0) or None,
                    challan_reams=_int_val(challan_reams, i, 0),
                    challan_sheets=_int_val(challan_sheets, i, 0),
                    received_reams=_int_val(received_reams, i, 0),
                    received_sheets=_int_val(received_sheets, i, 0),
                    accepted_reams=_int_val(accepted_reams, i, 0),
                    accepted_sheets=_int_val(accepted_sheets, i, 0),
                    damaged_reams=_int_val(damaged_reams, i, 0),
                    damaged_sheets=_int_val(damaged_sheets, i, 0),
                    challan_quantity=_dec_val(challan_quantities, i, None),
                    received_quantity=_dec_val(received_quantities, i, None),
                    accepted_quantity=_dec_val(accepted_quantities, i, None),
                    damaged_quantity=_dec_val(damaged_quantities, i, None),
                    weight_kg=_dec_val(weights_kg, i, Decimal("0")) or Decimal("0"),
                    reel_count=int(str(rc_raw)) if str(rc_raw).strip() else None,
                    reel_numbers=str(reel_numbers_list[i]).strip() if i < len(reel_numbers_list) and reel_numbers_list[i] else None,
                    remarks=str(line_remarks_list[i]).strip() if i < len(line_remarks_list) and line_remarks_list[i] else None,
                )
            )

        if not lines:
            return redirect_with_error("/app/paper/receipts/new", "At least one paper line item is required")

        payload = PaperReceiptCreate(
            store_id=store_id,
            financial_year_id=financial_year_id,
            receipt_date=receipt_date,
            source_depot=source_depot,
            allotment_no=allotment_no,
            allotment_date=allotment_date,
            challan_no=challan_no,
            challan_date=challan_date,
            vehicle_no=vehicle_no,
            carrier_name=carrier_name,
            lorry_receipt_no=lorry_receipt_no,
            remarks=remarks,
            lines=lines,
        )

        svc = PaperReceiptService(session)
        receipt = await svc.create_and_post(payload, actor_id=current_user.id)
        return redirect_with_success(
            f"/app/paper/receipts/{receipt.id}",
            f"Paper receipt {receipt.receipt_no} verified and posted to warehouse stock.",
        )

    except HTTPException as exc:
        return redirect_with_error("/app/paper/receipts/new", exc.detail)
    except Exception as exc:
        return redirect_with_error("/app/paper/receipts/new", f"Failed to save paper receipt: {str(exc)}")


@router.get("/receipts/{receipt_id}.pdf")
async def paper_receipt_pdf(
    receipt_id: int,
    paper_size: str = "auto",
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "PAPER_VIEW")
    receipt = await PaperReceiptService(session).repo.get(receipt_id)
    if not receipt:
        raise HTTPException(404, "Paper receipt not found")
    await auth.require_store_visibility(current_user.id, receipt.store_id)

    total_wt = Decimal("0")
    rows = []
    for line in receipt.lines:
        item = line.paper_item
        ftype = item.form_type if item else "SHEET"
        spr = item.sheets_per_ream if item else 500
        wt = Decimal(str(line.weight_kg or 0))
        total_wt += wt
        rows.append({
            "item": f"{item.code} — {item.name}" if item else str(line.paper_item_id),
            "form": ftype,
            "challan": format_paper_balance(ftype, line.challan_sheets, line.challan_quantity, spr),
            "received": format_paper_balance(ftype, line.received_sheets, line.received_quantity, spr),
            "accepted": format_paper_balance(ftype, line.accepted_sheets, line.weight_kg, spr),
            "damaged": format_paper_balance(ftype, line.damaged_sheets, line.damaged_quantity, spr),
            "weight_kg": f"{wt:.3f}",
        })
    cols = [
        ("item", "Paper Item Specification"),
        ("form", "Form"),
        ("challan", "Challan Qty"),
        ("received", "Received Qty"),
        ("accepted", "Accepted Stock IN"),
        ("damaged", "Damaged / Short"),
        ("weight_kg", "Weight (KG)"),
    ]
    meta_items = [
        ("Receipt No", receipt.receipt_no),
        ("Receipt Date", str(receipt.receipt_date)),
        ("Financial Year", receipt.financial_year.year_name if receipt.financial_year else "—"),
        ("Receiving Warehouse", receipt.store.name if receipt.store else str(receipt.store_id)),
        ("Supplying Department", receipt.source_depot or "Stationery Department"),
        ("Challan / Waybill", receipt.challan_no or "—"),
    ]
    if receipt.allotment_no:
        meta_items.append(("Allotment Ref", receipt.allotment_no))
    if receipt.vehicle_no or receipt.carrier_name:
        meta_items.append(("Vehicle / Carrier", f"{receipt.vehicle_no or '—'} / {receipt.carrier_name or '—'}"))

    pdf = make_voucher_pdf(
        "Stationery Paper Receipt Voucher",
        cols,
        rows,
        subtitle="Accepted Paper Stock Verification & Ledger Receipt",
        ref_no=receipt.receipt_no,
        doc_date=str(receipt.receipt_date),
        meta_items=meta_items,
        totals_row={"item": "Total Accepted Weight (KG)", "form": "", "challan": "", "received": "", "accepted": "", "damaged": "", "weight_kg": f"{total_wt:.3f}"},
        notes=receipt.remarks,
        signatures=[
            {"role": "Posted By", "label": receipt.poster.full_name if receipt.poster else current_user.full_name},
            {"role": "Inspected By", "label": "Warehouseman / Receiving Officer"},
            {"role": "Verified By", "label": "Head of Press"},
        ],
        paper_size=paper_size,
        domain="paper",
        generated_by=current_user.full_name,
    )
    safe_no = receipt.receipt_no.lower().replace("/", "_").replace("-", "_")
    return StreamingResponse(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="paper_receipt_{safe_no}.pdf"'},
    )


@router.get("/receipts/{receipt_id}")
async def paper_receipt_detail(
    request: Request,
    receipt_id: int,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    auth = AuthorizationService(session)
    try:
        await auth.require_permission(current_user.id, "PAPER_VIEW")
    except HTTPException as exc:
        return redirect_with_error("/app/paper/receipts", exc.detail)

    receipt = await PaperReceiptService(session).repo.get(receipt_id)
    if not receipt:
        return redirect_with_error("/app/paper/receipts", "Paper receipt not found")

    try:
        await auth.require_store_visibility(current_user.id, receipt.store_id)
    except HTTPException as exc:
        return redirect_with_error("/app/paper/receipts", exc.detail)

    return render(
        request,
        "paper/receipt_detail.html",
        current_user,
        receipt=receipt,
        format_paper=format_paper_balance,
    )


# =========================================================================
# 2. SECTION INDENTS & ISSUES (MANUAL ISSUE + ONLINE SECTION REQUEST)
# =========================================================================

@router.get("/indents")
async def paper_indents_list(
    request: Request,
    store_id: int | None = None,
    financial_year_id: int | None = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    auth = AuthorizationService(session)
    try:
        await auth.require_permission(current_user.id, "PAPER_VIEW")
    except HTTPException as exc:
        return redirect_with_error("/app", exc.detail)

    paper_stores, fys, selected_store, selected_fy = await load_paper_store_context(
        current_user, session, store_id, financial_year_id
    )

    user_roles = {r.code for r in current_user.roles if r.is_active}
    section_filter = current_user.section_id if ("SECTION_USER" in user_roles and "WAREHOUSEMAN" not in user_roles) else None

    svc = PaperIndentIssueService(session)
    indents = await svc.list_indents(
        store_id=selected_store.id if selected_store else None,
        financial_year_id=selected_fy.id if selected_fy else None,
        section_id=section_filter,
    )

    return render(
        request,
        "paper/indents.html",
        current_user,
        indents=indents,
        paper_stores=paper_stores,
        financial_years=fys,
        selected_store=selected_store,
        selected_fy=selected_fy,
    )


@router.get("/indents/new")
async def paper_indent_new(
    request: Request,
    store_id: int | None = None,
    financial_year_id: int | None = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    auth = AuthorizationService(session)
    perms = permission_codes(current_user)
    if "PAPER_ISSUE" not in perms:
        if "PAPER_INDENT_CREATE" in perms:
            return RedirectResponse(url="/app/paper/online-indents/new", status_code=303)
        return redirect_with_error("/app/paper/indents", "User lacks PAPER_ISSUE permission")

    paper_stores, fys, selected_store, selected_fy = await load_paper_store_context(
        current_user, session, store_id, financial_year_id
    )
    if not paper_stores:
        return redirect_with_error("/app", "No Paper Warehouse is available.")

    target_office_id = selected_store.office_id if selected_store else paper_stores[0].office_id
    sections = list(
        (
            await session.scalars(
                select(Section)
                .where(Section.office_id == target_office_id, Section.is_active.is_(True))
                .order_by(Section.name)
            )
        ).all()
    )
    paper_items = list(
        (
            await session.scalars(
                select(PaperItem)
                .options(selectinload(PaperItem.unit))
                .where(PaperItem.is_active.is_(True))
                .order_by(PaperItem.name)
            )
        ).all()
    )

    # Fetch live stock balances per item for the selected warehouse so Warehouseman sees exact available balance
    stock_map = {}
    if selected_store and selected_fy:
        stock_rows = await PaperStockService(session).current_stock(selected_store.id, selected_fy.id)
        stock_map = {r["item"].id: r["formatted_balance"] for r in stock_rows}

    return render(
        request,
        "paper/indent_new.html",
        current_user,
        paper_stores=paper_stores,
        sections=sections,
        financial_years=fys,
        selected_store=selected_store,
        selected_fy=selected_fy,
        paper_items=paper_items,
        stock_map=stock_map,
        today=date.today().isoformat(),
    )


@router.post("/indents/new")
async def paper_indent_submit(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    form_data = await request.form()

    try:
        store_id = int(form_data.get("store_id", "0"))
        section_id = int(form_data.get("section_id", "0"))
        indent_date = date.fromisoformat(str(form_data.get("indent_date", "")))
        financial_year_id = int(form_data.get("financial_year_id", "0")) or None
        job_no = str(form_data.get("job_no", "")).strip() or None
        remarks = str(form_data.get("remarks", "")).strip() or None

        paper_item_ids = form_data.getlist("paper_item_id")
        requested_reams = form_data.getlist("requested_reams")
        requested_sheets = form_data.getlist("requested_sheets")
        issued_reams = form_data.getlist("issued_reams")
        issued_sheets = form_data.getlist("issued_sheets")
        requested_quantities = form_data.getlist("requested_quantity")
        issued_quantities = form_data.getlist("issued_quantity")
        weights_kg = form_data.getlist("weight_kg")

        lines = []
        for i, raw_item_id in enumerate(paper_item_ids):
            if not str(raw_item_id).strip():
                continue

            has_iss_split = (i < len(issued_reams) and str(issued_reams[i]).strip() != "") or (
                i < len(issued_sheets) and str(issued_sheets[i]).strip() != ""
            )
            lines.append(
                PaperIndentLineCreate(
                    paper_item_id=int(str(raw_item_id)),
                    requested_reams=_int_val(requested_reams, i, 0),
                    requested_sheets=_int_val(requested_sheets, i, 0),
                    issued_reams=_int_val(issued_reams, i, 0) if has_iss_split else None,
                    issued_sheets=_int_val(issued_sheets, i, 0) if has_iss_split else None,
                    requested_quantity=_dec_val(requested_quantities, i, None),
                    issued_quantity=_dec_val(issued_quantities, i, None),
                    weight_kg=_dec_val(weights_kg, i, None),
                )
            )

        if not lines:
            return redirect_with_error("/app/paper/indents/new", "At least one paper line item is required")

        payload = PaperManualIndentCreate(
            store_id=store_id,
            section_id=section_id,
            indent_date=indent_date,
            financial_year_id=financial_year_id,
            job_no=job_no,
            remarks=remarks,
            lines=lines,
        )

        svc = PaperIndentIssueService(session)
        indent, issue = await svc.create_manual_indent_and_issue(payload, actor_id=current_user.id)
        return redirect_with_success(
            f"/app/paper/indents/{indent.id}",
            f"Paper issued to section under Issue Voucher {issue.issue_no}.",
        )

    except HTTPException as exc:
        return redirect_with_error("/app/paper/indents/new", exc.detail)
    except Exception as exc:
        return redirect_with_error("/app/paper/indents/new", f"Failed to issue paper: {str(exc)}")


@router.get("/online-indents/new")
async def paper_online_indent_new(
    request: Request,
    store_id: int | None = None,
    financial_year_id: int | None = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Online paper request screen for Press Section Users (balances stay hidden)."""
    if isinstance(current_user, RedirectResponse):
        return current_user

    auth = AuthorizationService(session)
    try:
        await auth.require_permission(current_user.id, "PAPER_INDENT_CREATE")
    except HTTPException as exc:
        return redirect_with_error("/app", exc.detail)

    paper_stores, fys, selected_store, selected_fy = await load_paper_store_context(
        current_user, session, store_id, financial_year_id
    )
    if not paper_stores:
        return redirect_with_error(
            "/app",
            "No Paper Warehouse is configured for your office. Ask Administration to set up a Press Paper Warehouse.",
        )

    paper_items = list(
        (
            await session.scalars(
                select(PaperItem)
                .options(selectinload(PaperItem.unit))
                .where(PaperItem.is_active.is_(True))
                .order_by(PaperItem.name)
            )
        ).all()
    )
    return render(
        request,
        "paper/online_indent_new.html",
        current_user,
        paper_stores=paper_stores,
        financial_years=fys,
        selected_store=selected_store,
        selected_fy=selected_fy,
        paper_items=paper_items,
        today=date.today().isoformat(),
    )


@router.post("/online-indents/new")
async def paper_online_indent_submit(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    form_data = await request.form()
    try:
        store_id = int(form_data.get("store_id", "0"))
        indent_date = date.fromisoformat(str(form_data.get("indent_date", "")))
        financial_year_id = int(form_data.get("financial_year_id", "0")) or None
        job_no = str(form_data.get("job_no", "")).strip() or None
        remarks = str(form_data.get("remarks", "")).strip() or None

        paper_item_ids = form_data.getlist("paper_item_id")
        requested_reams = form_data.getlist("requested_reams")
        requested_sheets = form_data.getlist("requested_sheets")
        weights_kg = form_data.getlist("weight_kg")

        lines = []
        for i, raw_id in enumerate(paper_item_ids):
            if not str(raw_id).strip():
                continue
            lines.append(
                PaperIndentLineCreate(
                    paper_item_id=int(str(raw_id)),
                    requested_reams=_int_val(requested_reams, i, 0),
                    requested_sheets=_int_val(requested_sheets, i, 0),
                    weight_kg=_dec_val(weights_kg, i, None),
                )
            )
        if not lines:
            return redirect_with_error("/app/paper/online-indents/new", "At least one paper item is required")

        payload = PaperOnlineIndentCreate(
            store_id=store_id,
            section_id=current_user.section_id,
            indent_date=indent_date,
            financial_year_id=financial_year_id,
            job_no=job_no,
            remarks=remarks,
            lines=lines,
        )
        indent = await PaperIndentIssueService(session).create_online_indent(payload, actor_id=current_user.id)
        return redirect_with_success(
            f"/app/paper/indents/{indent.id}",
            f"Paper request {indent.indent_no} submitted to Paper Warehouse.",
        )
    except HTTPException as exc:
        return redirect_with_error("/app/paper/online-indents/new", exc.detail)
    except Exception as exc:
        return redirect_with_error("/app/paper/online-indents/new", f"Failed to submit request: {str(exc)}")


@router.get("/indents/{indent_id}.pdf")
async def paper_indent_pdf(
    indent_id: int,
    paper_size: str = "auto",
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "PAPER_VIEW")
    indent = await PaperIndentIssueService(session).get_indent(indent_id)
    if not indent:
        raise HTTPException(404, "Paper indent not found")

    perms = permission_codes(current_user)
    is_section_owner = current_user.section_id == indent.section_id and "PAPER_INDENT_CREATE" in perms
    if not is_section_owner:
        await auth.require_store_visibility(current_user.id, indent.store_id)

    total_wt = Decimal("0")
    rows = []
    for line in indent.lines:
        item = line.paper_item
        ftype = item.form_type if item else "SHEET"
        spr = item.sheets_per_ream if item else 500
        wt = Decimal(str(line.issued_weight_kg or line.requested_weight_kg or 0))
        total_wt += wt
        if line.issued_sheets is not None or (line.issued_weight_kg is not None and line.issued_weight_kg > 0) or indent.status == "FINALIZED":
            issued_disp = format_paper_balance(ftype, line.issued_sheets or 0, line.issued_weight_kg or 0, spr)
        else:
            issued_disp = "Pending issue"
        rows.append({
            "item": f"{item.code} — {item.name}" if item else str(line.paper_item_id),
            "form": ftype,
            "requested": format_paper_balance(ftype, line.requested_sheets, line.requested_weight_kg or line.requested_quantity, spr),
            "issued": issued_disp,
            "weight_kg": f"{wt:.3f}",
        })
    cols = [
        ("item", "Paper Item Specification"),
        ("form", "Form"),
        ("requested", "Requested Qty"),
        ("issued", "Issued Qty"),
        ("weight_kg", "Weight (KG)"),
    ]
    meta_items = [
        ("Indent No", indent.indent_no),
        ("Indent Date", str(indent.indent_date)),
        ("Issue Ref", indent.issue.issue_no if indent.issue else "Pending Issue"),
        ("Paper Warehouse", indent.store.name if indent.store else str(indent.store_id)),
        ("Requesting Section", indent.section.name if indent.section else str(indent.section_id)),
        ("Job / Work Order", indent.job_no or "General Production Run"),
        ("Mode / Status", f"{indent.request_source} · {indent.status}"),
    ]
    pdf = make_voucher_pdf(
        "Paper Section Indent & Issue Voucher",
        cols,
        rows,
        subtitle=f"Section Paper Requisition & Press Production Issue Slip",
        ref_no=indent.indent_no,
        doc_date=str(indent.indent_date),
        meta_items=meta_items,
        totals_row={"item": "Total Weight (KG)", "form": "", "requested": "", "issued": "", "weight_kg": f"{total_wt:.3f}"},
        notes=indent.remarks,
        signatures=[
            {"role": "Section Requisitioner", "label": indent.section.name if indent.section else "Section Official"},
            {"role": "Issued By", "label": current_user.full_name},
            {"role": "Received By", "label": "Section Supervisor"},
        ],
        paper_size=paper_size,
        domain="paper",
        generated_by=current_user.full_name,
    )
    safe_no = indent.indent_no.lower().replace("/", "_").replace("-", "_")
    return StreamingResponse(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="paper_indent_{safe_no}.pdf"'},
    )


@router.get("/indents/{indent_id}")
async def paper_indent_detail(
    request: Request,
    indent_id: int,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    auth = AuthorizationService(session)
    try:
        await auth.require_permission(current_user.id, "PAPER_VIEW")
    except HTTPException as exc:
        return redirect_with_error("/app/paper/indents", exc.detail)

    indent = await PaperIndentIssueService(session).get_indent(indent_id)
    if not indent:
        return redirect_with_error("/app/paper/indents", "Paper indent not found")

    perms = permission_codes(current_user)
    user_stores = {s.id for s in current_user.stores if s.is_active}
    is_section_owner = current_user.section_id == indent.section_id and "PAPER_INDENT_CREATE" in perms
    if not is_section_owner:
        try:
            await auth.require_store_visibility(current_user.id, indent.store_id)
        except HTTPException as exc:
            return redirect_with_error("/app/paper/indents", exc.detail)

    can_issue = (
        indent.status in ("SUBMITTED", "APPROVED")
        and "PAPER_ISSUE" in perms
        and indent.store_id in user_stores
    )

    avail_map = {}
    if can_issue:
        stock_svc = PaperStockService(session)
        for line in indent.lines:
            sh, wt = await stock_svc.balance_for_item(indent.store_id, indent.financial_year_id, line.paper_item_id)
            spr = line.paper_item.sheets_per_ream or 500
            avail_map[line.id] = format_paper_balance(line.paper_item.form_type, sh, wt, spr)

    return render(
        request,
        "paper/indent_detail.html",
        current_user,
        indent=indent,
        can_issue=can_issue,
        avail_map=avail_map,
        format_paper=format_paper_balance,
        from_total_sheets=from_total_sheets,
        today=date.today().isoformat(),
    )


@router.post("/indents/{indent_id}/issue")
async def paper_online_indent_issue(
    indent_id: int,
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    form_data = await request.form()
    try:
        line_ids = form_data.getlist("indent_line_id")
        iss_reams = form_data.getlist("issued_reams")
        iss_sheets = form_data.getlist("issued_sheets")
        weights_kg = form_data.getlist("weight_kg")
        remarks_list = form_data.getlist("line_remarks")

        lines = []
        for i, lid in enumerate(line_ids):
            lines.append(
                PaperOnlineIndentIssueLine(
                    indent_line_id=int(str(lid)),
                    issued_reams=_int_val(iss_reams, i, 0),
                    issued_sheets=_int_val(iss_sheets, i, 0),
                    weight_kg=_dec_val(weights_kg, i, None),
                    remarks=str(remarks_list[i]).strip() if i < len(remarks_list) and remarks_list[i] else None,
                )
            )
        issue_date_raw = form_data.get("issue_date")
        payload = PaperOnlineIndentIssueRequest(
            issue_date=date.fromisoformat(str(issue_date_raw)) if issue_date_raw else date.today(),
            remarks=str(form_data.get("remarks", "")).strip() or None,
            lines=lines,
        )
        issue = await PaperIndentIssueService(session).issue_from_online_indent(
            indent_id, payload, actor_id=current_user.id
        )
        return redirect_with_success(
            f"/app/paper/indents/{indent_id}",
            f"Paper issued against request under voucher {issue.issue_no}.",
        )
    except HTTPException as exc:
        return redirect_with_error(f"/app/paper/indents/{indent_id}", exc.detail)
    except Exception as exc:
        return redirect_with_error(f"/app/paper/indents/{indent_id}", f"Failed to issue paper: {str(exc)}")


# =========================================================================
# 3. INTER-PRESS TRANSFERS & DIRECTORATE DIRECTIVES
# =========================================================================

@router.get("/transfers")
async def paper_transfers_list(
    request: Request,
    store_id: int | None = None,
    financial_year_id: int | None = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    auth = AuthorizationService(session)
    try:
        await auth.require_permission(current_user.id, "PAPER_VIEW")
    except HTTPException as exc:
        return redirect_with_error("/app", exc.detail)

    paper_stores, fys, selected_store, selected_fy = await load_paper_store_context(
        current_user, session, store_id, financial_year_id
    )

    svc = PaperTransferService(session)
    transfers = await svc.list(
        store_id=selected_store.id if selected_store else None,
        financial_year_id=selected_fy.id if selected_fy else None,
    )

    return render(
        request,
        "paper/transfers.html",
        current_user,
        transfers=transfers,
        paper_stores=paper_stores,
        financial_years=fys,
        selected_store=selected_store,
        selected_fy=selected_fy,
    )


@router.get("/transfers/new")
async def paper_transfer_new(
    request: Request,
    store_id: int | None = None,
    financial_year_id: int | None = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    auth = AuthorizationService(session)
    perms = permission_codes(current_user)
    is_directorate = "PAPER_TRANSFER_DIRECTIVE" in perms

    if not is_directorate:
        try:
            await auth.require_permission(current_user.id, "PAPER_TRANSFER_CREATE")
        except HTTPException as exc:
            return redirect_with_error("/app/paper/transfers", exc.detail)

    stmt = (
        select(Store)
        .options(selectinload(Store.office))
        .where(Store.is_active.is_(True), Store.store_type == "PAPER_WAREHOUSE")
        .order_by(Store.name)
    )
    paper_stores = list((await session.scalars(stmt)).all())
    fys = list((await session.scalars(select(FinancialYear).order_by(FinancialYear.start_date.desc()))).all())
    selected_fy = next((fy for fy in fys if fy.is_current), fys[0] if fys else None)

    paper_items = list(
        (
            await session.scalars(
                select(PaperItem)
                .options(selectinload(PaperItem.unit))
                .where(PaperItem.is_active.is_(True))
                .order_by(PaperItem.name)
            )
        ).all()
    )
    user_stores = {s.id for s in current_user.stores if s.is_active}

    return render(
        request,
        "paper/transfer_new.html",
        current_user,
        paper_stores=paper_stores,
        financial_years=fys,
        selected_fy=selected_fy,
        paper_items=paper_items,
        is_directorate=is_directorate,
        user_stores=user_stores,
        today=date.today().isoformat(),
    )


@router.post("/transfers/new")
async def paper_transfer_submit(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    form_data = await request.form()

    try:
        source_store_id = int(form_data.get("source_store_id", "0"))
        destination_store_id = int(form_data.get("destination_store_id", "0"))
        transfer_mode = str(form_data.get("transfer_mode", "PULL")).upper()
        transfer_date = date.fromisoformat(str(form_data.get("transfer_date", "")))
        financial_year_id = int(form_data.get("financial_year_id", "0")) or None
        remarks = str(form_data.get("remarks", "")).strip() or None

        paper_item_ids = form_data.getlist("paper_item_id")
        requested_reams = form_data.getlist("requested_reams")
        requested_sheets = form_data.getlist("requested_sheets")
        requested_quantities = form_data.getlist("requested_quantity")
        weights_kg = form_data.getlist("weight_kg")
        line_remarks_list = form_data.getlist("line_remarks")

        lines = []
        for i, raw_item_id in enumerate(paper_item_ids):
            if not str(raw_item_id).strip():
                continue

            lines.append(
                PaperTransferLineCreate(
                    paper_item_id=int(str(raw_item_id)),
                    requested_reams=_int_val(requested_reams, i, 0),
                    requested_sheets=_int_val(requested_sheets, i, 0),
                    requested_quantity=_dec_val(requested_quantities, i, None),
                    weight_kg=_dec_val(weights_kg, i, None),
                    remarks=str(line_remarks_list[i]).strip() if i < len(line_remarks_list) and line_remarks_list[i] else None,
                )
            )

        if not lines:
            return redirect_with_error("/app/paper/transfers/new", "At least one paper line item is required")

        payload = PaperTransferCreateRequest(
            source_store_id=source_store_id,
            destination_store_id=destination_store_id,
            transfer_date=transfer_date,
            financial_year_id=financial_year_id,
            transfer_mode=transfer_mode,
            remarks=remarks,
            lines=lines,
        )

        transfer = await PaperTransferService(session).create(payload, actor_id=current_user.id)
        return redirect_with_success(
            f"/app/paper/transfers/{transfer.id}",
            f"Inter-press transfer {transfer.transfer_no} initiated.",
        )

    except HTTPException as exc:
        return redirect_with_error("/app/paper/transfers/new", exc.detail)
    except Exception as exc:
        return redirect_with_error("/app/paper/transfers/new", f"Failed to create transfer: {str(exc)}")


@router.get("/transfers/{transfer_id}/gate-pass.pdf")
async def paper_transfer_gate_pass_pdf(
    transfer_id: int,
    paper_size: str = "auto",
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "PAPER_VIEW")
    transfer = await PaperTransferService(session).get(transfer_id)
    if not transfer:
        raise HTTPException(404, "Paper transfer not found")
    visible = await auth.get_visible_stores(current_user.id)
    if visible is not None and transfer.source_store_id not in visible and transfer.destination_store_id not in visible:
        raise HTTPException(403, "User is not authorized to view this paper transfer gate pass")

    info = {
        "transfer_no": transfer.transfer_no,
        "transfer_date": str(transfer.transfer_date),
        "requisition_no": transfer.gate_pass_no or transfer.transfer_no,
        "requisition_date": str(transfer.transfer_date),
        "source_store": transfer.source_store.name if transfer.source_store else str(transfer.source_store_id),
        "source_office": transfer.source_store.office.name if transfer.source_store and transfer.source_store.office else "Printing Department",
        "destination_store": transfer.destination_store.name if transfer.destination_store else str(transfer.destination_store_id),
        "destination_office": transfer.destination_store.office.name if transfer.destination_store and transfer.destination_store.office else "—",
        "vehicle_no": transfer.vehicle_no,
        "received_by_name": transfer.carrier_name,
        "status": transfer.status,
        "fy_name": transfer.financial_year.year_name if transfer.financial_year else "—",
        "dispatched_by_name": current_user.full_name,
    }
    items = []
    for line in transfer.lines:
        item = line.paper_item
        ftype = item.form_type if item else "SHEET"
        spr = item.sheets_per_ream if item else 500
        disp_sheets = line.dispatched_sheets if line.dispatched_sheets is not None else line.requested_sheets
        disp_wt = line.dispatched_weight_kg if line.dispatched_weight_kg is not None else (line.requested_weight_kg or 0)
        qty_disp = format_paper_balance(ftype, disp_sheets, disp_wt, spr)
        ledger_val = f"{Decimal(str(disp_wt or 0)):.3f} KG" if ftype == "REEL" else f"{int(disp_sheets or 0)} SH"
        items.append({
            "item_code": item.code if item else str(line.paper_item_id),
            "item_name": f"{item.name} ({item.gsm} GSM)" if item else str(line.paper_item_id),
            "unit_code": ftype,
            "paper_qty_display": qty_disp,
            "quantity": ledger_val,
            "remarks": line.remarks or "—",
            "asset_numbers": "",
        })
    pdf_buffer = make_transfer_gate_pass_pdf(
        info,
        items,
        paper_size=paper_size,
        domain="paper",
        generated_by=current_user.full_name,
    )
    safe_no = transfer.transfer_no.lower().replace("/", "_").replace("-", "_")
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="paper_gate_pass_{safe_no}.pdf"'},
    )


@router.get("/transfers/{transfer_id}")
async def paper_transfer_detail(
    request: Request,
    transfer_id: int,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    auth = AuthorizationService(session)
    try:
        await auth.require_permission(current_user.id, "PAPER_VIEW")
    except HTTPException as exc:
        return redirect_with_error("/app/paper/transfers", exc.detail)

    transfer = await PaperTransferService(session).get(transfer_id)
    if not transfer:
        return redirect_with_error("/app/paper/transfers", "Transfer not found")

    user_stores = {s.id for s in current_user.stores if s.is_active}
    user_roles = {r.code for r in current_user.roles if r.is_active}
    perms = permission_codes(current_user)

    can_approve_branch = (
        "PAPER_TRANSFER_APPROVE" in perms
        and "BRANCH_HEAD" in user_roles
        and current_user.office_id == transfer.source_store.office_id
    )
    can_dispatch = "PAPER_TRANSFER_DISPATCH" in perms and transfer.source_store_id in user_stores
    can_receive = "PAPER_TRANSFER_RECEIVE" in perms and transfer.destination_store_id in user_stores

    return render(
        request,
        "paper/transfer_detail.html",
        current_user,
        transfer=transfer,
        can_approve_branch=can_approve_branch,
        can_dispatch=can_dispatch,
        can_receive=can_receive,
        format_paper=format_paper_balance,
        from_total_sheets=from_total_sheets,
    )


@router.post("/transfers/{transfer_id}/approve-branch")
async def paper_transfer_approve_branch(
    transfer_id: int,
    remarks: Annotated[str | None, Form()] = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    try:
        await PaperTransferService(session).approve_branch(transfer_id, actor_id=current_user.id, remarks=remarks)
        return redirect_with_success(f"/app/paper/transfers/{transfer_id}", "Transfer approved by Branch Head.")
    except HTTPException as exc:
        return redirect_with_error(f"/app/paper/transfers/{transfer_id}", exc.detail)


@router.post("/transfers/{transfer_id}/dispatch")
async def paper_transfer_dispatch(
    request: Request,
    transfer_id: int,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    form_data = await request.form()
    try:
        vehicle_no = str(form_data.get("vehicle_no", "")).strip() or None
        driver_name = str(form_data.get("driver_name", "")).strip() or None
        carrier_name = str(form_data.get("carrier_name", "")).strip() or None
        gate_pass_no = str(form_data.get("gate_pass_no", "")).strip() or None
        remarks = str(form_data.get("remarks", "")).strip() or None

        line_ids = form_data.getlist("line_id")
        disp_reams = form_data.getlist("dispatch_reams")
        disp_sheets = form_data.getlist("dispatch_sheets")
        dispatch_quantities = form_data.getlist("dispatch_quantity")
        weights_kg = form_data.getlist("weight_kg")

        d_lines = []
        for i in range(len(line_ids)):
            d_lines.append(
                PaperTransferDispatchLine(
                    line_id=int(str(line_ids[i])),
                    dispatch_reams=_int_val(disp_reams, i, 0),
                    dispatch_sheets=_int_val(disp_sheets, i, 0),
                    dispatch_quantity=_dec_val(dispatch_quantities, i, None),
                    weight_kg=_dec_val(weights_kg, i, Decimal("0")) or Decimal("0"),
                )
            )

        payload = PaperTransferDispatchRequest(
            vehicle_no=vehicle_no,
            driver_name=driver_name,
            carrier_name=carrier_name,
            gate_pass_no=gate_pass_no,
            remarks=remarks,
            lines=d_lines,
        )

        await PaperTransferService(session).dispatch(transfer_id, payload, actor_id=current_user.id)
        return redirect_with_success(
            f"/app/paper/transfers/{transfer_id}",
            "Paper dispatched with Gate Pass. Stock deducted from supplying warehouse.",
        )
    except HTTPException as exc:
        return redirect_with_error(f"/app/paper/transfers/{transfer_id}", exc.detail)


@router.post("/transfers/{transfer_id}/receive")
async def paper_transfer_receive(
    request: Request,
    transfer_id: int,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    form_data = await request.form()
    try:
        remarks = str(form_data.get("remarks", "")).strip() or None
        line_ids = form_data.getlist("line_id")
        recv_reams = form_data.getlist("received_reams")
        recv_sheets = form_data.getlist("received_sheets")
        received_quantities = form_data.getlist("received_quantity")
        weights_kg = form_data.getlist("weight_kg")

        r_lines = []
        for i in range(len(line_ids)):
            r_lines.append(
                PaperTransferReceiveLine(
                    line_id=int(str(line_ids[i])),
                    received_reams=_int_val(recv_reams, i, 0),
                    received_sheets=_int_val(recv_sheets, i, 0),
                    received_quantity=_dec_val(received_quantities, i, None),
                    weight_kg=_dec_val(weights_kg, i, Decimal("0")) or Decimal("0"),
                )
            )

        payload = PaperTransferReceiveRequest(
            remarks=remarks,
            lines=r_lines,
        )

        await PaperTransferService(session).receive(transfer_id, payload, actor_id=current_user.id)
        return redirect_with_success(
            f"/app/paper/transfers/{transfer_id}",
            "Paper received and posted to destination warehouse stock.",
        )
    except HTTPException as exc:
        return redirect_with_error(f"/app/paper/transfers/{transfer_id}", exc.detail)


# =========================================================================
# 4. PAPER STOCK BALANCES (FY-WISE OPENING + IN - OUT = CLOSING)
# =========================================================================

@router.get("/stock")
async def paper_stock_view(
    request: Request,
    store_id: int | None = None,
    financial_year_id: int | None = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    auth = AuthorizationService(session)
    try:
        await auth.require_permission(current_user.id, "PAPER_VIEW")
    except HTTPException as exc:
        return redirect_with_error("/app", exc.detail)

    paper_stores, fys, selected_store, selected_fy = await load_paper_store_context(
        current_user, session, store_id, financial_year_id
    )

    stock_rows = []
    sheet_specs_count = 0
    reel_specs_count = 0
    total_reel_kg = Decimal("0")

    if selected_store and selected_fy:
        stock_rows = await PaperStockService(session).current_stock(selected_store.id, selected_fy.id)
        for row in stock_rows:
            if row["item"].form_type == "REEL":
                reel_specs_count += 1
                total_reel_kg += Decimal(row["balance_weight_kg"])
            else:
                sheet_specs_count += 1

    return render(
        request,
        "paper/stock.html",
        current_user,
        paper_stores=paper_stores,
        financial_years=fys,
        selected_store=selected_store,
        selected_fy=selected_fy,
        stock_rows=stock_rows,
        sheet_specs_count=sheet_specs_count,
        reel_specs_count=reel_specs_count,
        total_reel_kg=total_reel_kg,
    )


# =========================================================================
# 5. DEDICATED PAPER WAREHOUSE REGISTERS (HUB + 6 REGISTERS + PDF EXPORT)
# =========================================================================

@router.get("/registers")
async def paper_registers_hub(
    request: Request,
    store_id: int | None = None,
    financial_year_id: int | None = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    auth = AuthorizationService(session)
    try:
        await auth.require_permission(current_user.id, "PAPER_REGISTER_VIEW")
    except HTTPException as exc:
        return redirect_with_error("/app", exc.detail)

    paper_stores, fys, selected_store, selected_fy = await load_paper_store_context(
        current_user, session, store_id, financial_year_id
    )
    return render(
        request,
        "paper/registers.html",
        current_user,
        paper_stores=paper_stores,
        financial_years=fys,
        selected_store=selected_store,
        selected_fy=selected_fy,
    )


@router.get("/registers/{kind}.pdf")
async def paper_register_pdf(
    kind: str,
    store_id: int | None = None,
    financial_year_id: int | None = None,
    search: str | None = None,
    paper_size: str = "auto",
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    auth = AuthorizationService(session)
    await auth.require_permission(current_user.id, "PAPER_REGISTER_VIEW")

    paper_stores, fys, selected_store, selected_fy = await load_paper_store_context(
        current_user, session, store_id, financial_year_id
    )
    svc = PaperRegisterService(session)
    wh_label = selected_store.name if selected_store else "All Permitted Warehouses"
    fy_label = selected_fy.year_name if selected_fy else "All Financial Years"
    sub = f"{wh_label} | FY {fy_label}"
    meta = [("Paper Warehouse", wh_label), ("Financial Year", fy_label)]

    if kind == "stock":
        if not selected_store or not selected_fy:
            raise HTTPException(422, "Paper Warehouse and Financial Year are required")
        rows = await svc.stock_register(current_user.id, selected_store.id, selected_fy.id, search=search)
        cols = [
            ("code", "Code"),
            ("name", "Paper Specification"),
            ("form_type", "Format"),
            ("opening", "Opening"),
            ("inward", "Receipts In"),
            ("outward", "Issues Out"),
            ("closing", "Closing Balance"),
            ("weight_kg", "Weight (KG)"),
        ]
        return pdf_response(
            "Paper Stock Register",
            cols,
            rows,
            sub,
            paper_size=paper_size,
            domain="paper",
            meta_items=meta,
            generated_by=current_user.full_name,
            search_term=search,
        )

    if kind == "receipts":
        rows = await svc.receipt_register(current_user.id, store_id, financial_year_id, search=search)
        cols = [
            ("receipt_date", "Date"),
            ("receipt_no", "Receipt No"),
            ("warehouse_name", "Warehouse"),
            ("source_depot", "Depot"),
            ("challan_no", "Challan"),
            ("item_name", "Paper Item"),
            ("accepted", "Accepted"),
            ("damaged", "Damaged"),
            ("weight_kg", "Wt (KG)"),
        ]
        return pdf_response(
            "Paper Stationery Receipt Register",
            cols,
            rows,
            sub,
            paper_size=paper_size,
            domain="paper",
            meta_items=meta,
            generated_by=current_user.full_name,
            search_term=search,
        )

    if kind == "issues":
        rows = await svc.issue_register(current_user.id, store_id, financial_year_id, search=search)
        cols = [
            ("issue_date", "Date"),
            ("issue_no", "Issue No"),
            ("warehouse_name", "Warehouse"),
            ("section_name", "Section"),
            ("job_no", "Job No"),
            ("item_name", "Paper Item"),
            ("issued", "Issued Qty"),
            ("weight_kg", "Wt (KG)"),
        ]
        return pdf_response(
            "Paper Section Issue Register",
            cols,
            rows,
            sub,
            paper_size=paper_size,
            domain="paper",
            meta_items=meta,
            generated_by=current_user.full_name,
            search_term=search,
        )

    if kind == "transfers":
        rows = await svc.transfer_register(current_user.id, store_id, financial_year_id, search=search)
        cols = [
            ("transfer_date", "Date"),
            ("transfer_no", "Transfer No"),
            ("transfer_mode", "Mode"),
            ("source_warehouse", "From"),
            ("destination_warehouse", "To"),
            ("item_name", "Paper Item"),
            ("dispatched", "Dispatched"),
            ("received", "Received"),
            ("status", "Status"),
        ]
        return pdf_response(
            "Inter-Press Paper Transfer Register",
            cols,
            rows,
            sub,
            paper_size=paper_size,
            domain="paper",
            meta_items=meta,
            generated_by=current_user.full_name,
            search_term=search,
        )

    if kind == "opening":
        rows = await svc.opening_register(current_user.id, store_id, financial_year_id, search=search)
        cols = [
            ("opening_date", "Date"),
            ("opening_no", "Doc No"),
            ("opening_type", "Type"),
            ("warehouse_name", "Warehouse"),
            ("fy_name", "FY"),
            ("item_name", "Paper Item"),
            ("opening_qty", "Opening Balance"),
            ("weight_kg", "Wt (KG)"),
        ]
        return pdf_response(
            "Paper Opening Stock Register",
            cols,
            rows,
            sub,
            paper_size=paper_size,
            domain="paper",
            meta_items=meta,
            generated_by=current_user.full_name,
            search_term=search,
        )

    if kind == "ledger":
        rows = await svc.ledger_register(current_user.id, store_id, financial_year_id, search=search)
        cols = [
            ("movement_date", "Date"),
            ("movement_type", "Type"),
            ("warehouse_name", "Warehouse"),
            ("item_name", "Paper Item"),
            ("inward", "Inward"),
            ("outward", "Outward"),
            ("reference_no", "Reference"),
        ]
        return pdf_response(
            "Paper Transaction Ledger",
            cols,
            rows,
            sub,
            paper_size=paper_size,
            domain="paper",
            meta_items=meta,
            generated_by=current_user.full_name,
            search_term=search,
        )

    raise HTTPException(404, f"Unknown paper register: {kind}")


@router.get("/registers/{kind}")
async def paper_register_detail(
    kind: str,
    request: Request,
    store_id: int | None = None,
    financial_year_id: int | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    auth = AuthorizationService(session)
    try:
        await auth.require_permission(current_user.id, "PAPER_REGISTER_VIEW")
    except HTTPException as exc:
        return redirect_with_error("/app", exc.detail)

    paper_stores, fys, selected_store, selected_fy = await load_paper_store_context(
        current_user, session, store_id, financial_year_id
    )

    svc = PaperRegisterService(session)
    titles = {
        "stock": ("Paper Stock Register", "FY Opening, Receipts, Issues, and Closing Balances in Reams+Sheets / KG"),
        "receipts": ("Stationery Inward Register", "All paper receipts received from the Stationery Department"),
        "issues": ("Section & Job Issue Register", "Paper issued to press sections against jobs & work orders"),
        "transfers": ("Inter-Press Paper Transfer Register", "Transfers & Directorate Push Directives between press warehouses"),
        "opening": ("Warehouse Opening Stock Register", "First-time physical opening & FY carry-forward documents"),
        "ledger": ("Paper Transaction Ledger", "Chronological paper movement audit trail (PaperStockMovement)"),
    }
    if kind not in titles:
        raise HTTPException(404, f"Unknown paper register: {kind}")

    raw = []
    if kind == "stock":
        if selected_store and selected_fy:
            raw = await svc.stock_register(current_user.id, selected_store.id, selected_fy.id, search=search)
    elif kind == "receipts":
        raw = await svc.receipt_register(current_user.id, selected_store.id if store_id else None, selected_fy.id if financial_year_id else None, search=search)
    elif kind == "issues":
        raw = await svc.issue_register(current_user.id, selected_store.id if store_id else None, selected_fy.id if financial_year_id else None, search=search)
    elif kind == "transfers":
        raw = await svc.transfer_register(current_user.id, selected_store.id if store_id else None, selected_fy.id if financial_year_id else None, search=search)
    elif kind == "opening":
        raw = await svc.opening_register(current_user.id, selected_store.id if store_id else None, selected_fy.id if financial_year_id else None, search=search)
    elif kind == "ledger":
        raw = await svc.ledger_register(current_user.id, selected_store.id if store_id else None, selected_fy.id if financial_year_id else None, search=search)

    total = len(raw)
    page, page_size, pages, offset = page_window(total, page, page_size)
    rows = raw[offset : offset + page_size]

    title, subtitle = titles[kind]
    return render(
        request,
        "paper/register_list.html",
        current_user,
        title=title,
        subtitle=subtitle,
        kind=kind,
        rows=rows,
        paper_stores=paper_stores,
        financial_years=fys,
        selected_store=selected_store,
        selected_fy=selected_fy,
        search=search or "",
        page=page,
        page_size=page_size,
        pages=pages,
        total=total,
    )
