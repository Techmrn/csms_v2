from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated

from pydantic import ValidationError

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.exc import IntegrityError
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db_session
from app.models.asset import Asset
from app.models.category import Category
from app.models.financial_year import FinancialYear
from app.models.indent import Indent, IndentLine
from app.models.issue import Issue, IssueLine
from app.models.item import Item
from app.models.office import Office
from app.models.receipt import Receipt
from app.models.section import Section
from app.models.stock_return import StockReturn
from app.models.petty_purchase import PettyPurchase
from app.models.requisition import CentralStoreRequisition, CentralStoreRequisitionLine
from app.models.stock import OpeningStock, StockMovement
from app.models.role import Role
from app.models.store import Store
from app.models.unit import Unit
from app.models.user import User, user_roles
from app.models.transfer import StockTransfer
from app.security.auth import authenticate_user, create_access_token
from app.schemas.indent import (
    IndentCreate,
    IndentLineCreate,
    IssueFinalizeLine,
    IssueFinalizeRequest,
    ManualIndentCreate,
    ManualIndentLineCreate,
)
from app.schemas.petty_purchase import PettyPurchaseCreate, PettyPurchaseLineCreate, PettyPurchasePostRequest, PettyPurchaseVerifyRequest
from app.schemas.requisition import RequisitionCreate, RequisitionLineCreate, BranchApprovalRequest, BranchApprovalLine, CentralApprovalRequest, RequisitionApprovalLine
from app.schemas.transfer import TransferDispatchRequest, TransferDispatchLine, TransferReceiveRequest, TransferReceiveLine
from app.schemas.receipt import ReceiptCreate, ReceiptLineCreate, AssetReceiptInput
from app.schemas.stock_return import StockReturnCreate, StockReturnLineCreate
from app.schemas.stock import OpeningStockCreate, OpeningStockLineCreate, OpeningAssetInput
from app.services.authorization import AuthorizationService
from app.services.indent import IndentService
from app.services.issue import IssueService
from app.services.petty_purchase import PettyPurchaseService
from app.services.receipt import ReceiptService
from app.services.requisition import RequisitionService
from app.services.transfer import TransferService
from app.services.stock import StockService
from app.services.stock_return import StockReturnService
from app.services.registers import RegisterService
from app.web.auth import get_web_current_user
from app.services.pdf_reports import make_register_pdf

WEB_ROOT = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(WEB_ROOT / "templates"))
router = APIRouter(tags=["web"])

MENU = [
    ("Dashboard", "/app", None),
    ("Stock", "/app/stock", "STOCK_VIEW"),
    ("Opening Stock", "/app/opening-stock", "STOCK_OPENING_CREATE"),
    ("Items", "/app/items", "MASTER_DATA_MANAGE"),
    ("Assets", "/app/assets", "ASSET_VIEW"),
    ("Online Indents", "/app/online-indents", "INDENT_VIEW"),
    ("Manual Indents", "/app/indents", "INDENT_PROCESS"),
    ("Requisitions", "/app/requisitions", "REQUISITION_VIEW"),
    ("Transfers", "/app/transfers", "STOCK_TRANSFER_VIEW"),
    ("Receipts", "/app/receipts", "STOCK_RECEIPT_VIEW"),
    ("Returns", "/app/returns", "STOCK_RETURN_VIEW"),
    ("Petty Purchase", "/app/petty-purchases", "PETTY_PURCHASE_VIEW"),
    ("Registers", "/app/registers", "REGISTER_VIEW"),
    ("My Activity", "/app/my-activity", None),
    ("Administration", "/app/admin", None),
]

def role_label(user: User) -> str:
    active_roles = [r.code for r in user.roles if r.is_active]
    return " / ".join(code.replace("_", " ").title() for code in active_roles) or "User"


def permission_codes(user: User) -> set[str]:
    return {
        permission.code
        for role in user.roles
        if role.is_active
        for permission in role.permissions
        if permission.is_active
    }


def is_system_admin(user: User) -> bool:
    return any(role.is_active and role.code == "SYSTEM_ADMIN" for role in user.roles)


ADMIN_MENU = [
    ("Administration", "/app/admin", {"MASTER_DATA_MANAGE", "ORGANIZATION_MANAGE", "USER_MANAGE"}),
    ("Master Data", "/app/admin/masters", {"MASTER_DATA_MANAGE"}),
    ("Organization", "/app/admin/organization", {"ORGANIZATION_MANAGE"}),
    ("Users", "/app/admin/users", {"USER_MANAGE"}),
    ("Roles & Permissions", "/app/admin/roles", {"USER_MANAGE"}),
    ("All Views", "/app/admin/views", {"USER_MANAGE"}),
]


def visible_menu(user: User) -> list[dict[str, str | None]]:
    perms = permission_codes(user)
    menu = []
    for label, href, permission in MENU:
        if label == "Dashboard":
            menu.append({"label": label, "href": href})
            continue
        if label == "Administration":
            admin_permissions = {"MASTER_DATA_MANAGE", "ORGANIZATION_MANAGE", "USER_MANAGE"}
            if perms.intersection(admin_permissions):
                menu.append({"label": label, "href": href})
            continue
        if label == "Requisitions":
            requisition_permissions = {
                "REQUISITION_VIEW",
                "REQUISITION_CREATE",
                "REQUISITION_APPROVE_BRANCH",
                "REQUISITION_APPROVE_CENTRAL",
                "STOCK_TRANSFER_DISPATCH",
            }
            if perms.intersection(requisition_permissions):
                menu.append({"label": label, "href": href})
            continue
        if permission and permission in perms:
            menu.append({"label": label, "href": href})

    # Administration has its own permission-scoped submenu.  Do not expose
    # links the current role cannot actually open.
    for label, href, required_permissions in ADMIN_MENU[1:]:
        if perms.intersection(required_permissions):
            menu.append({"label": label, "href": href})
    return menu


def base_context(user: User) -> dict:
    return {
        "user": user,
        "role_label": role_label(user),
        "roles": [r.code for r in user.roles if r.is_active],
        "permissions": permission_codes(user),
        "is_system_admin": is_system_admin(user),
        "menu": visible_menu(user),
    }


async def load_store_context(
    user: User,
    session: AsyncSession,
    requested_store_id: int | None,
    requested_fy_id: int | None,
):
    auth = AuthorizationService(session)
    visible = await auth.get_visible_stores(user.id)
    stmt = select(Store).where(Store.is_active.is_(True)).order_by(Store.name)
    if visible is not None:
        stmt = stmt.where(Store.id.in_(visible)) if visible else stmt.where(Store.id == -1)
    elif any(role.is_active and role.code == "SECTION_USER" for role in user.roles):
        # Section users are not storekeepers and therefore normally have no
        # user_stores assignment. They still need a source store for an online
        # indent. Expose the Central Store plus their own branch store only.
        central = select(Store.id).where(Store.store_type == "CENTRAL", Store.is_active.is_(True))
        stmt = select(Store).where(
            Store.is_active.is_(True),
            (Store.id.in_(central) | (Store.office_id == user.office_id)),
        ).order_by(Store.name)
    stores = list((await session.scalars(stmt)).all())
    fys = list((await session.scalars(select(FinancialYear).order_by(FinancialYear.start_date.desc()))).all())

    selected_store = next((s for s in stores if s.id == requested_store_id), None) if requested_store_id else None
    if selected_store is None and stores:
        primary_ids = {s.id for s in user.stores if s.is_active}
        selected_store = next((s for s in stores if s.id in primary_ids), stores[0])

    selected_fy = next((fy for fy in fys if fy.id == requested_fy_id), None) if requested_fy_id else None
    if selected_fy is None:
        selected_fy = next((fy for fy in fys if fy.is_current), fys[0] if fys else None)
    return stores, fys, selected_store, selected_fy


def render(request: Request, template: str, user: User, **context):
    merged = base_context(user)
    merged.update({
        "request": request,
        "success": request.query_params.get("success"),
        "error": request.query_params.get("error"),
        **context,
    })
    return TEMPLATES.TemplateResponse(request=request, name=template, context=merged)


def redirect_with_error(path: str, message: str) -> RedirectResponse:
    from urllib.parse import quote
    return RedirectResponse(url=f"{path}?error={quote(message)}", status_code=303)


def redirect_with_success(path: str, message: str) -> RedirectResponse:
    from urllib.parse import quote
    return RedirectResponse(url=f"{path}?success={quote(message)}", status_code=303)


async def require_view_permission(session: AsyncSession, user_id: int, permission_code: str) -> None:
    """Enforce the same explicit view permission used by the navigation matrix.

    System administration does not implicitly grant business-view permissions;
    SYSTEM_ADMIN receives only the view permissions explicitly listed in the
    centralized role matrix.
    """
    await AuthorizationService(session).require_permission(user_id, permission_code)


def form_decimal(value: str | None, default: Decimal = Decimal("0")) -> Decimal:
    if value is None or not value.strip():
        return default
    try:
        return Decimal(value.strip())
    except InvalidOperation as exc:
        raise HTTPException(422, f"Invalid quantity: {value}") from exc


def repeated(form, name: str) -> list[str]:
    return [str(v).strip() for v in form.getlist(name)]


async def permitted_destination_offices(session: AsyncSession, user: User, selected_store: Store | None) -> list[Office]:
    if selected_store is None:
        return []
    if selected_store.store_type == "CENTRAL":
        stmt = select(Office).where(Office.is_active.is_(True)).order_by(Office.office_type, Office.name)
        return list((await session.scalars(stmt)).all())
    office = await session.get(Office, selected_store.office_id)
    return [office] if office and office.is_active else []


async def sections_for_offices(session: AsyncSession, offices: list[Office]) -> list[Section]:
    office_ids = [o.id for o in offices]
    if not office_ids:
        return []
    stmt = select(Section).where(Section.is_active.is_(True), Section.office_id.in_(office_ids)).order_by(Section.name)
    return list((await session.scalars(stmt)).all())


async def build_item_availability(
    session: AsyncSession, store_id: int, financial_year_id: int
) -> dict[int, Decimal]:
    availability: dict[int, Decimal] = {}

    rows = await StockService(session).current_stock(store_id, financial_year_id, None)
    for row in rows:
        availability[int(row.item_id)] = Decimal(str(row.balance or 0))

    asset_rows = await session.execute(
        select(Asset.item_id, func.count(Asset.id))
        .where(
            Asset.current_store_id == store_id,
            Asset.status == "IN_STOCK",
        )
        .group_by(Asset.item_id)
    )
    for item_id, count in asset_rows.all():
        availability[int(item_id)] = Decimal(int(count))

    return availability


@router.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/app", status_code=303)


@router.get("/login", include_in_schema=False)
async def login_page(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="login.html", context={"error": request.query_params.get("error")})


@router.post("/login", include_in_schema=False)
async def login_submit(request: Request, username: Annotated[str, Form()], password: Annotated[str, Form()], session: AsyncSession = Depends(get_db_session)):
    user = await authenticate_user(session, username, password)
    if user is None:
        return TEMPLATES.TemplateResponse(request=request, name="login.html", context={"error": "Incorrect username or password"}, status_code=401)
    token = create_access_token(user)
    response = RedirectResponse(url="/app", status_code=303)
    response.set_cookie("csms_access_token", token, httponly=True, secure=False, samesite="lax", max_age=60 * 60, path="/")
    return response


@router.get("/logout", include_in_schema=False)
async def logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("csms_access_token", path="/")
    return response


@router.get("/app", include_in_schema=False)
async def dashboard(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, financial_year_id: int | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    if is_system_admin(current_user):
        return RedirectResponse(url="/app/admin", status_code=303)
    stores, fys, selected_store, selected_fy = await load_store_context(current_user, session, store_id, financial_year_id)
    stock_rows, total_units = [], Decimal("0")
    if selected_store and selected_fy:
        await AuthorizationService(session).require_store_visibility(current_user.id, selected_store.id)
        rows = await StockService(session).current_stock(selected_store.id, selected_fy.id, None)
        stock_rows = rows[:8]
        total_units = sum((Decimal(str(row.balance or 0)) for row in rows), Decimal("0"))
    item_count = await session.scalar(select(func.count(Item.id)).where(Item.is_active.is_(True)))
    visible_asset_count = 0
    if selected_store:
        visible_asset_count = int((await session.scalar(select(func.count(Asset.id)).where(Asset.current_store_id == selected_store.id))) or 0)
    return render(request, "dashboard.html", current_user, stores=stores, financial_years=fys, selected_store=selected_store, selected_fy=selected_fy, stock_rows=stock_rows, stock_count=len(stock_rows), total_units=total_units, item_count=int(item_count or 0), asset_count=visible_asset_count)


@router.get("/app/opening-stock", include_in_schema=False)
async def opening_stock_page(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    store_id: int | None = None,
    financial_year_id: int | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    await require_view_permission(session, current_user.id, "STOCK_OPENING_CREATE")
    stores, fys, selected_store, selected_fy = await load_store_context(
        current_user, session, store_id, financial_year_id
    )

    visible = await AuthorizationService(session).get_visible_stores(current_user.id)
    stmt = select(OpeningStock).order_by(
        OpeningStock.opening_date.desc(), OpeningStock.id.desc()
    )
    if visible is not None:
        stmt = stmt.where(OpeningStock.store_id.in_(visible))
    if store_id is not None:
        await AuthorizationService(session).require_store_visibility(
            current_user.id, store_id
        )
        stmt = stmt.where(OpeningStock.store_id == store_id)

    openings = list(
        (await session.scalars(stmt.limit(100))).all()
    )
    return render(
        request,
        "opening_stock.html",
        current_user,
        openings=openings,
        stores=stores,
        financial_years=fys,
        selected_store=selected_store,
        selected_fy=selected_fy,
        error=request.query_params.get("error"),
    )


@router.get("/app/opening-stock/new", include_in_schema=False)
async def new_opening_stock_page(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    store_id: int | None = None,
    financial_year_id: int | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    await AuthorizationService(session).require_permission(
        current_user.id, "STOCK_OPENING_CREATE"
    )
    stores, fys, selected_store, selected_fy = await load_store_context(
        current_user, session, store_id, financial_year_id
    )
    if selected_store:
        await AuthorizationService(session).require_store_assignment(
            current_user.id, selected_store.id
        )

    items = list(
        (
            await session.scalars(
                select(Item)
                .options(selectinload(Item.category), selectinload(Item.unit))
                .where(Item.is_active.is_(True))
                .order_by(Item.name)
            )
        ).all()
    )

    return render(
        request,
        "opening_stock_new.html",
        current_user,
        stores=stores,
        financial_years=fys,
        selected_store=selected_store,
        selected_fy=selected_fy,
        items=items,
        error=request.query_params.get("error"),
    )


@router.post("/app/opening-stock/new", include_in_schema=False)
async def create_opening_stock_web(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    form = await request.form()

    try:
        item_ids = repeated(form, "item_id")
        unit_ids = repeated(form, "unit_id")
        qtys = repeated(form, "quantity")
        line_remarks = repeated(form, "line_remarks")

        # Asset details are submitted as individual fields. Each asset row carries
        # the parent opening-line index so multiple opening lines can coexist.
        asset_line_indices = repeated(form, "asset_line_index")
        asset_nos = repeated(form, "asset_no")
        asset_serials = repeated(form, "asset_serial_no")
        asset_makes = repeated(form, "asset_make")
        asset_models = repeated(form, "asset_model")
        asset_purchase_dates = repeated(form, "asset_purchase_date")
        asset_purchase_refs = repeated(form, "asset_purchase_reference")
        asset_values = repeated(form, "asset_purchase_value")
        asset_warranty_dates = repeated(form, "asset_warranty_expiry_date")
        asset_remarks = repeated(form, "asset_remarks")

        grouped_assets: dict[int, list[OpeningAssetInput]] = {}
        for aidx, raw_parent in enumerate(asset_line_indices):
            if raw_parent is None or str(raw_parent).strip() == "":
                continue
            parent_idx = int(raw_parent)
            asset_no = asset_nos[aidx].strip() if aidx < len(asset_nos) else ""
            if not asset_no:
                raise HTTPException(422, f"Asset number is required for asset row {aidx + 1}")
            pd = asset_purchase_dates[aidx].strip() if aidx < len(asset_purchase_dates) else ""
            wd = asset_warranty_dates[aidx].strip() if aidx < len(asset_warranty_dates) else ""
            pv = asset_values[aidx].strip() if aidx < len(asset_values) else ""
            grouped_assets.setdefault(parent_idx, []).append(
                OpeningAssetInput(
                    asset_no=asset_no,
                    serial_no=(asset_serials[aidx].strip() if aidx < len(asset_serials) and asset_serials[aidx].strip() else None),
                    make=(asset_makes[aidx].strip() if aidx < len(asset_makes) and asset_makes[aidx].strip() else None),
                    model=(asset_models[aidx].strip() if aidx < len(asset_models) and asset_models[aidx].strip() else None),
                    purchase_date=date.fromisoformat(pd) if pd else None,
                    purchase_reference=(asset_purchase_refs[aidx].strip() if aidx < len(asset_purchase_refs) and asset_purchase_refs[aidx].strip() else None),
                    purchase_value=form_decimal(pv, Decimal("0")) if pv else None,
                    warranty_expiry_date=date.fromisoformat(wd) if wd else None,
                    remarks=(asset_remarks[aidx].strip() if aidx < len(asset_remarks) and asset_remarks[aidx].strip() else None),
                )
            )

        lines: list[OpeningStockLineCreate] = []
        for idx, raw_item_id in enumerate(item_ids):
            if not raw_item_id:
                continue
            qty = form_decimal(qtys[idx] if idx < len(qtys) else "")
            unit_id = int(unit_ids[idx]) if idx < len(unit_ids) and unit_ids[idx] else 0
            lines.append(
                OpeningStockLineCreate(
                    item_id=int(raw_item_id),
                    quantity=qty,
                    unit_id=unit_id,
                    asset_details=grouped_assets.get(idx),
                    remarks=(
                        line_remarks[idx].strip()
                        if idx < len(line_remarks) and line_remarks[idx].strip()
                        else None
                    ),
                )
            )

        payload = OpeningStockCreate(
            opening_date=date.fromisoformat(str(form["opening_date"])),
            financial_year_id=int(form["financial_year_id"]),
            store_id=int(form["store_id"]),
            remarks=str(form.get("remarks") or "").strip() or None,
            lines=lines,
        )

        await StockService(session).create_and_post_opening(payload, current_user.id)
        return redirect_with_success("/app/opening-stock", "Opening stock posted successfully.")

    except (HTTPException, ValueError, ValidationError) as exc:
        await session.rollback()
        return redirect_with_error(
            "/app/opening-stock/new",
            exc.detail if isinstance(exc, HTTPException) else str(exc),
        )


@router.get("/app/stock", include_in_schema=False)
async def stock_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, financial_year_id: int | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_view_permission(session, current_user.id, "STOCK_VIEW")
    stores, fys, selected_store, selected_fy = await load_store_context(current_user, session, store_id, financial_year_id)
    rows = []
    if selected_store and selected_fy:
        await AuthorizationService(session).require_store_visibility(current_user.id, selected_store.id)
        rows = await StockService(session).current_stock(selected_store.id, selected_fy.id, None)
    return render(request, "stock.html", current_user, stores=stores, financial_years=fys, selected_store=selected_store, selected_fy=selected_fy, rows=rows)


@router.get("/app/items", include_in_schema=False)
async def items_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_view_permission(session, current_user.id, "MASTER_DATA_MANAGE")
    items = list((await session.scalars(select(Item).options(selectinload(Item.category), selectinload(Item.unit)).where(Item.is_active.is_(True)).order_by(Item.name))).all())
    return render(request, "items.html", current_user, items=items)


@router.get("/app/assets", include_in_schema=False)
async def assets_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, status: str | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_view_permission(session, current_user.id, "ASSET_VIEW")
    stores, fys, selected_store, selected_fy = await load_store_context(current_user, session, store_id, None)
    if store_id is None: selected_store = None
    visible_store_ids = await AuthorizationService(session).get_visible_stores(current_user.id)
    stmt = select(Asset).options(selectinload(Asset.item))
    if selected_store is not None:
        await AuthorizationService(session).require_store_visibility(current_user.id, selected_store.id)
        stmt = stmt.where(Asset.current_store_id == selected_store.id)
    elif visible_store_ids is not None:
        stmt = stmt.where(Asset.current_store_id.in_(visible_store_ids))
    if status: stmt = stmt.where(Asset.status == status)
    assets = list((await session.scalars(stmt.order_by(Asset.asset_no))).all())
    return render(request, "assets.html", current_user, stores=stores, financial_years=fys, selected_store=selected_store, assets=assets, status_filter=status or "")


@router.get("/app/online-indents", include_in_schema=False)
async def online_indents_page(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    store_id: int | None = None,
    status: str | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    await require_view_permission(session, current_user.id, "INDENT_VIEW")
    visible = await AuthorizationService(session).get_visible_stores(current_user.id)
    stmt = select(Indent).options(selectinload(Indent.lines).selectinload(IndentLine.item)).where(Indent.request_source == "ONLINE")
    if visible is not None:
        stmt = stmt.where(Indent.store_id.in_(visible))
    if store_id is not None:
        await AuthorizationService(session).require_store_visibility(current_user.id, store_id)
        stmt = stmt.where(Indent.store_id == store_id)
    if status:
        stmt = stmt.where(Indent.status == status)
    indents = list((await session.scalars(stmt.order_by(Indent.indent_date.desc(), Indent.id.desc()).limit(100))).all())
    stores, _, selected_store, _ = await load_store_context(current_user, session, store_id, None)
    return render(request, "indents.html", current_user, stores=stores, financial_years=[], selected_store=selected_store, selected_fy=None, indents=indents, status_filter=status or "", page_mode="ONLINE", error=request.query_params.get("error"), success=request.query_params.get("success"))


@router.get("/app/online-indents/new", include_in_schema=False)
async def new_online_indent_page(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    store_id: int | None = None,
    financial_year_id: int | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    await AuthorizationService(session).require_permission(current_user.id, "INDENT_CREATE")
    stores, fys, selected_store, selected_fy = await load_store_context(current_user, session, store_id, financial_year_id)
    items = list((await session.scalars(select(Item).options(selectinload(Item.category), selectinload(Item.unit)).where(Item.is_active.is_(True)).order_by(Item.name))).all())
    destination_offices = await permitted_destination_offices(session, current_user, selected_store)
    sections = await sections_for_offices(session, destination_offices)
    availability = await build_item_availability(session, selected_store.id, selected_fy.id) if selected_store and selected_fy else {}
    return render(request, "online_indent_new.html", current_user, stores=stores, financial_years=fys, selected_store=selected_store, selected_fy=selected_fy, destination_offices=destination_offices, sections=sections, items=items, availability=availability, error=request.query_params.get("error"))


@router.post("/app/online-indents/new", include_in_schema=False)
async def create_online_indent_web(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    form = await request.form()
    try:
        await AuthorizationService(session).require_permission(current_user.id, "INDENT_CREATE")
        item_ids, qtys, remarks = (repeated(form, n) for n in ("item_id", "requested_quantity", "line_remarks"))
        lines = [IndentLineCreate(item_id=int(item_ids[i]), requested_quantity=form_decimal(qtys[i]), remarks=(remarks[i] if i < len(remarks) else None) or None) for i in range(len(item_ids)) if item_ids[i] and qtys[i]]
        payload = IndentCreate(
            indent_date=date.fromisoformat(str(form["indent_date"])),
            financial_year_id=int(form["financial_year_id"]),
            store_id=int(form["store_id"]),
            office_id=int(form["office_id"]),
            section_id=int(form["section_id"]) if form.get("section_id") else None,
            request_source="ONLINE",
            request_type=str(form.get("request_type") or "GENERAL"),
            reference_no=str(form.get("reference_no") or "") or None,
            reference_date=date.fromisoformat(str(form["reference_date"])) if form.get("reference_date") else None,
            remarks=str(form.get("remarks") or "") or None,
            lines=lines,
        )
        indent = await IndentService(session).create(payload, current_user.id)
        return redirect_with_success("/app/online-indents", f"Online indent {indent.indent_no} created successfully.")
    except (HTTPException, ValueError) as exc:
        await session.rollback()
        return redirect_with_error("/app/online-indents/new", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.post("/app/indents/{indent_id}/approve", include_in_schema=False)
async def approve_online_indent_web(indent_id: int, request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    try:
        indent = await IndentService(session).approve_online(indent_id, current_user.id)
        return redirect_with_success(f"/app/indents/{indent_id}", f"Indent {indent.indent_no} approved for processing.")
    except HTTPException as exc:
        await session.rollback()
        return redirect_with_error(f"/app/indents/{indent_id}", exc.detail)


@router.get("/app/indents", include_in_schema=False)
async def indents_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, status: str | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_view_permission(session, current_user.id, "INDENT_VIEW")
    stores, fys, selected_store, selected_fy = await load_store_context(current_user, session, store_id, None)
    visible = await AuthorizationService(session).get_visible_stores(current_user.id)
    stmt = select(Indent).options(selectinload(Indent.lines))
    if visible is not None: stmt = stmt.where(Indent.store_id.in_(visible))
    if store_id is not None:
        await AuthorizationService(session).require_store_visibility(current_user.id, store_id)
        stmt = stmt.where(Indent.store_id == store_id)
        selected_store = next((s for s in stores if s.id == store_id), selected_store)
    if status: stmt = stmt.where(Indent.status == status)
    indents = list((await session.scalars(stmt.order_by(Indent.indent_date.desc(), Indent.id.desc()).limit(100))).all())
    return render(request, "indents.html", current_user, stores=stores, financial_years=fys, selected_store=selected_store, selected_fy=selected_fy, indents=indents, status_filter=status or "", error=request.query_params.get("error"))


@router.get("/app/indents/new", include_in_schema=False)
async def new_indent_page(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    store_id: int | None = None,
    financial_year_id: int | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    await AuthorizationService(session).require_permission(current_user.id, "INDENT_PROCESS")
    stores, fys, selected_store, selected_fy = await load_store_context(
        current_user, session, store_id, financial_year_id
    )
    if selected_store:
        await AuthorizationService(session).require_store_assignment(
            current_user.id, selected_store.id
        )

    items = list(
        (
            await session.scalars(
                select(Item)
                .options(selectinload(Item.category), selectinload(Item.unit))
                .where(Item.is_active.is_(True))
                .order_by(Item.name)
            )
        ).all()
    )
    destination_offices = await permitted_destination_offices(session, current_user, selected_store)
    sections = await sections_for_offices(session, destination_offices)

    available_assets_by_item: dict[int, list[dict]] = {}
    if selected_store:
        asset_stmt = (
            select(Asset)
            .options(selectinload(Asset.detail))
            .where(
                Asset.current_store_id == selected_store.id,
                Asset.status == "IN_STOCK",
            )
            .order_by(Asset.item_id, Asset.asset_no)
        )
        assets = (await session.scalars(asset_stmt)).all()
        for a in assets:
            detail_str = ""
            if a.detail:
                parts = [p for p in [a.detail.make, a.detail.model] if p]
                if parts:
                    detail_str = f" ({' '.join(parts)})"
            label = f"{a.asset_no}"
            if a.serial_no:
                label += f" — SN: {a.serial_no}"
            if detail_str:
                label += detail_str
            available_assets_by_item.setdefault(a.item_id, []).append({
                "id": a.id,
                "asset_no": a.asset_no,
                "serial_no": a.serial_no or "",
                "label": label,
            })

    availability = {}
    if selected_store and selected_fy:
        availability = await build_item_availability(
            session, selected_store.id, selected_fy.id
        )
    for it in items:
        if it.category and it.category.type == "ASSET":
            availability[it.id] = Decimal(len(available_assets_by_item.get(it.id, [])))

    return render(
        request,
        "indent_new.html",
        current_user,
        stores=stores,
        financial_years=fys,
        selected_store=selected_store,
        selected_fy=selected_fy,
        items=items,
        sections=sections,
        destination_offices=destination_offices,
        availability=availability,
        store_assets_json=json.dumps(available_assets_by_item),
        error=request.query_params.get("error"),
    )


@router.post("/app/indents/new", include_in_schema=False)
async def create_indent_web(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    form = await request.form()

    try:
        item_ids = repeated(form, "item_id")
        unit_ids = repeated(form, "unit_id")
        requested_values = repeated(form, "requested_quantity")
        issued_values = repeated(form, "issued_quantity")
        line_remarks = repeated(form, "line_remarks")
        asset_values = repeated(form, "asset_ids")

        lines: list[ManualIndentLineCreate] = []

        for idx, raw_item_id in enumerate(item_ids):
            if not raw_item_id:
                continue

            requested = form_decimal(
                requested_values[idx] if idx < len(requested_values) else ""
            )
            issued = form_decimal(
                issued_values[idx] if idx < len(issued_values) else ""
            )
            unit_id = int(unit_ids[idx]) if idx < len(unit_ids) and unit_ids[idx] else 0

            parsed_assets = None
            if idx < len(asset_values) and asset_values[idx].strip():
                parsed_assets = [
                    int(x.strip())
                    for x in asset_values[idx].split(",")
                    if x.strip()
                ]

            lines.append(
                ManualIndentLineCreate(
                    item_id=int(raw_item_id),
                    unit_id=unit_id,
                    requested_quantity=requested,
                    issued_quantity=issued,
                    asset_ids=parsed_assets,
                    remarks=(
                        line_remarks[idx].strip()
                        if idx < len(line_remarks) and line_remarks[idx].strip()
                        else None
                    ),
                )
            )

        payload = ManualIndentCreate(
            indent_date=date.fromisoformat(str(form["indent_date"])),
            financial_year_id=int(form["financial_year_id"]),
            store_id=int(form["store_id"]),
            office_id=int(form["office_id"]),
            section_id=(
                int(form["section_id"])
                if form.get("section_id")
                else None
            ),
            remarks=str(form.get("remarks") or "").strip() or None,
            lines=lines,
        )

        indent, issue = await IndentService(session).create_manual_and_issue(
            payload, current_user.id
        )

        return redirect_with_success(f"/app/indents/{indent.id}", f"Indent {indent.indent_no} and issue {issue.issue_no} saved successfully.")
    except (HTTPException, ValueError, ValidationError) as exc:
        await session.rollback()
        return redirect_with_error(
            "/app/indents/new",
            exc.detail if isinstance(exc, HTTPException) else str(exc),
        )


@router.post("/app/indents/{indent_id}/issue", include_in_schema=False)
async def issue_online_indent_web(indent_id: int, request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse):
        return current_user
    form = await request.form()
    try:
        await AuthorizationService(session).require_permission(current_user.id, "INDENT_PROCESS")
        indent = await session.scalar(select(Indent).options(selectinload(Indent.lines)).where(Indent.id == indent_id, Indent.request_source == "ONLINE"))
        if indent is None:
            raise HTTPException(404, "Online indent not found")
        line_ids = repeated(form, "indent_line_id")
        qtys = repeated(form, "issued_quantity")
        remarks = repeated(form, "issue_line_remarks")
        payload = IssueFinalizeRequest(
            issue_date=date.today(),
            remarks=None,
            lines=[IssueFinalizeLine(indent_line_id=int(line_ids[i]), issued_quantity=form_decimal(qtys[i]), asset_ids=None, remarks=remarks[i] if i < len(remarks) and remarks[i] else None) for i in range(len(line_ids))],
        )
        await IssueService(session).finalize_from_indent(indent_id, payload, current_user.id)
        return redirect_with_success(f"/app/indents/{indent_id}", "Issue posted successfully.")
    except (HTTPException, ValueError) as exc:
        await session.rollback()
        return redirect_with_error(f"/app/indents/{indent_id}", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.get("/app/indents/{indent_id}", include_in_schema=False)
async def indent_detail_page(
    request: Request,
    indent_id: int,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    await require_view_permission(session, current_user.id, "INDENT_VIEW")

    indent = (
        await session.execute(
            select(Indent)
            .options(selectinload(Indent.lines).selectinload(IndentLine.item))
            .where(Indent.id == indent_id)
        )
    ).scalar_one_or_none()

    if indent is None:
        raise HTTPException(404, "Indent not found")

    await AuthorizationService(session).require_store_visibility(
        current_user.id, indent.store_id
    )

    issue = await session.scalar(
        select(Issue).where(Issue.indent_id == indent.id)
    )

    availability = {}
    for line in indent.lines:
        availability[line.id] = await StockService(session).current_balance(
            indent.store_id,
            indent.financial_year_id,
            line.item_id,
        )

    return render(
        request,
        "indent_detail.html",
        current_user,
        indent=indent,
        issue=issue,
        available=availability,
        error=request.query_params.get("error"),
    )


@router.get("/app/receipts", include_in_schema=False)
async def receipts_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, status: str | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_view_permission(session, current_user.id, "STOCK_RECEIPT_VIEW")
    visible = await AuthorizationService(session).get_visible_stores(current_user.id)
    stmt = select(Receipt).options(selectinload(Receipt.lines))
    if visible is not None: stmt = stmt.where(Receipt.store_id.in_(visible))
    if store_id is not None:
        await AuthorizationService(session).require_store_visibility(current_user.id, store_id)
        stmt = stmt.where(Receipt.store_id == store_id)
    if status: stmt = stmt.where(Receipt.status == status)
    receipts = list((await session.scalars(stmt.order_by(Receipt.receipt_date.desc(), Receipt.id.desc()).limit(100))).all())
    stores, fys, selected_store, selected_fy = await load_store_context(current_user, session, store_id, None)
    return render(request, "receipts.html", current_user, receipts=receipts, stores=stores, financial_years=fys, selected_store=selected_store, error=request.query_params.get("error"))


@router.get("/app/receipts/new", include_in_schema=False)
async def new_receipt_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, financial_year_id: int | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await AuthorizationService(session).require_permission(current_user.id, "STOCK_RECEIPT")
    stores, fys, selected_store, selected_fy = await load_store_context(current_user, session, store_id, financial_year_id)
    if selected_store: await AuthorizationService(session).require_store_assignment(current_user.id, selected_store.id)
    items = list((await session.scalars(select(Item).options(selectinload(Item.category), selectinload(Item.unit)).where(Item.is_active.is_(True)).order_by(Item.name))).all())
    units = list((await session.scalars(select(Unit).where(Unit.is_active.is_(True)).order_by(Unit.name))).all())
    return render(request, "receipt_new.html", current_user, stores=stores, financial_years=fys, selected_store=selected_store, selected_fy=selected_fy, items=items, units=units, error=request.query_params.get("error"))


@router.post("/app/receipts/new", include_in_schema=False)
async def create_receipt_web(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    form = await request.form()
    try:
        item_ids, recv, acc, rej, unit_ids, prices, remarks = (repeated(form, n) for n in ("item_id", "received_quantity", "accepted_quantity", "rejected_quantity", "unit_id", "unit_price", "line_remarks"))
        asset_line_indices = repeated(form, "asset_line_index")
        asset_serials = repeated(form, "asset_serial_no")
        asset_makes = repeated(form, "asset_make")
        asset_models = repeated(form, "asset_model")
        asset_purchase_dates = repeated(form, "asset_purchase_date")
        asset_purchase_refs = repeated(form, "asset_purchase_reference")
        asset_values = repeated(form, "asset_purchase_value")
        asset_warranty_dates = repeated(form, "asset_warranty_expiry_date")
        asset_specs = repeated(form, "asset_technical_specifications")
        asset_remarks = repeated(form, "asset_remarks")
        grouped_assets: dict[int, list[AssetReceiptInput]] = {}
        for aidx, raw_parent in enumerate(asset_line_indices):
            if raw_parent is None or str(raw_parent).strip() == "":
                continue
            parent_idx = int(raw_parent)
            pd = asset_purchase_dates[aidx].strip() if aidx < len(asset_purchase_dates) else ""
            wd = asset_warranty_dates[aidx].strip() if aidx < len(asset_warranty_dates) else ""
            pv = asset_values[aidx].strip() if aidx < len(asset_values) else ""
            grouped_assets.setdefault(parent_idx, []).append(
                AssetReceiptInput(
                    serial_no=(asset_serials[aidx].strip() if aidx < len(asset_serials) and asset_serials[aidx].strip() else None),
                    make=(asset_makes[aidx].strip() if aidx < len(asset_makes) and asset_makes[aidx].strip() else None),
                    model=(asset_models[aidx].strip() if aidx < len(asset_models) and asset_models[aidx].strip() else None),
                    purchase_date=date.fromisoformat(pd) if pd else None,
                    purchase_reference=(asset_purchase_refs[aidx].strip() if aidx < len(asset_purchase_refs) and asset_purchase_refs[aidx].strip() else None),
                    purchase_value=form_decimal(pv, Decimal("0")) if pv else None,
                    warranty_expiry_date=date.fromisoformat(wd) if wd else None,
                    technical_specifications=(asset_specs[aidx].strip() if aidx < len(asset_specs) and asset_specs[aidx].strip() else None),
                    remarks=(asset_remarks[aidx].strip() if aidx < len(asset_remarks) and asset_remarks[aidx].strip() else None),
                )
            )
        lines = []
        for idx, i in enumerate(item_ids):
            if not i or idx >= len(recv) or not recv[idx]:
                continue
            lines.append(ReceiptLineCreate(
                item_id=int(i),
                received_quantity=form_decimal(recv[idx]),
                accepted_quantity=form_decimal(acc[idx]),
                rejected_quantity=form_decimal(rej[idx]),
                unit_id=int(unit_ids[idx]),
                unit_price=form_decimal(prices[idx], default=Decimal("0")) if prices[idx] else None,
                remarks=(remarks[idx] if idx < len(remarks) else None) or None,
                asset_details=grouped_assets.get(idx),
            ))
        if not lines:
            raise HTTPException(422, "Add at least one receipt line.")
        for line in lines:
            if line.accepted_quantity + line.rejected_quantity != line.received_quantity:
                raise HTTPException(
                    422,
                    "For each receipt line, Accepted + Rejected must equal Received before the receipt can be posted to stock.",
                )

        payload = ReceiptCreate(receipt_date=date.fromisoformat(str(form["receipt_date"])), financial_year_id=int(form["financial_year_id"]), store_id=int(form["store_id"]), supplier_name=str(form.get("supplier_name") or "") or None, purchase_reference=str(form.get("purchase_reference") or "") or None, invoice_reference=str(form.get("invoice_reference") or "") or None, challan_reference=str(form.get("challan_reference") or "") or None, remarks=str(form.get("remarks") or "") or None, lines=lines)
        service = ReceiptService(session)
        receipt = await service.create(payload, current_user.id)
        await service.verify(receipt.id, current_user.id)
        await service.post(receipt.id, current_user.id)
        return redirect_with_success("/app/receipts", "Receipt saved and accepted quantity posted to stock.")
    except (HTTPException, ValueError, ValidationError) as exc:
        await session.rollback()
        return redirect_with_error("/app/receipts/new", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.post("/app/receipts/{receipt_id}/verify", include_in_schema=False)
async def verify_receipt_web(receipt_id: int, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await ReceiptService(session).verify(receipt_id, current_user.id)
        return redirect_with_success("/app/receipts", "Receipt action completed successfully.")
    except HTTPException as exc: return redirect_with_error("/app/receipts", exc.detail)


@router.post("/app/receipts/{receipt_id}/post", include_in_schema=False)
async def post_receipt_web(receipt_id: int, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await ReceiptService(session).post(receipt_id, current_user.id)
        return redirect_with_success("/app/receipts", "Receipt action completed successfully.")
    except HTTPException as exc: return redirect_with_error("/app/receipts", exc.detail)


@router.get("/app/requisitions", include_in_schema=False)
async def requisitions_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), status: str | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    perms = permission_codes(current_user)
    allowed = {"REQUISITION_VIEW", "REQUISITION_CREATE", "REQUISITION_APPROVE_BRANCH", "REQUISITION_APPROVE_CENTRAL", "STOCK_TRANSFER_DISPATCH"}
    if not perms.intersection(allowed): raise HTTPException(403, "User lacks requisition access")
    auth = AuthorizationService(session)
    visible = await auth.get_visible_stores(current_user.id)
    central_store_ids = set((await session.scalars(select(Store.id).where(Store.store_type == "CENTRAL"))).all())
    is_central_user = (
        "REQUISITION_APPROVE_CENTRAL" in perms
        or "STOCK_TRANSFER_DISPATCH" in perms
        or (visible is not None and any(sid in central_store_ids for sid in visible))
    )
    stmt = select(CentralStoreRequisition).options(
        selectinload(CentralStoreRequisition.lines).selectinload(CentralStoreRequisitionLine.item)
    ).order_by(CentralStoreRequisition.requisition_date.desc(), CentralStoreRequisition.id.desc())
    if visible is not None and not is_central_user:
        stmt = stmt.where(CentralStoreRequisition.requesting_store_id.in_(visible))
    if status: stmt = stmt.where(CentralStoreRequisition.status == status)
    rows = list((await session.scalars(stmt.limit(100))).all())
    all_stores = list((await session.scalars(select(Store).where(Store.is_active.is_(True)).order_by(Store.name))).all())
    stores, fys, selected_store, selected_fy = await load_store_context(current_user, session, None, None)
    return render(request, "requisitions.html", current_user, requisitions=rows, stores=all_stores, financial_years=fys, selected_fy=selected_fy, error=request.query_params.get("error"), success=request.query_params.get("success"))


@router.get("/app/requisitions/new", include_in_schema=False)
async def new_requisition_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await AuthorizationService(session).require_permission(current_user.id, "REQUISITION_CREATE")
    stores, fys, _, selected_fy = await load_store_context(current_user, session, None, None)
    branch_stores = [s for s in stores if s.store_type == "BRANCH"]
    if len(branch_stores) == 1: selected_store = branch_stores[0]
    else: selected_store = branch_stores[0] if branch_stores else None
    if selected_store: await AuthorizationService(session).require_store_assignment(current_user.id, selected_store.id)
    items = list((await session.scalars(select(Item).options(selectinload(Item.category), selectinload(Item.unit)).where(Item.is_active.is_(True)).order_by(Item.name))).all())
    return render(request, "requisition_new.html", current_user, stores=branch_stores, financial_years=fys, selected_store=selected_store, selected_fy=selected_fy, items=items, error=request.query_params.get("error"))


@router.get("/app/requisitions/{requisition_id}", include_in_schema=False)
async def requisition_detail_page(requisition_id: int, request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    perms = permission_codes(current_user)
    if not perms.intersection({"REQUISITION_VIEW", "STOCK_TRANSFER_DISPATCH"}):
        raise HTTPException(403, "User lacks requisition access")
    auth = AuthorizationService(session)
    requisition = await session.scalar(
        select(CentralStoreRequisition)
        .options(selectinload(CentralStoreRequisition.lines).selectinload(CentralStoreRequisitionLine.item))
        .where(CentralStoreRequisition.id == requisition_id)
    )
    if requisition is None: raise HTTPException(404, "Requisition not found")
    visible = await auth.get_visible_stores(current_user.id)
    central_store_ids = set((await session.scalars(select(Store.id).where(Store.store_type == "CENTRAL"))).all())
    is_central_user = (
        "REQUISITION_APPROVE_CENTRAL" in perms
        or "STOCK_TRANSFER_DISPATCH" in perms
        or (visible is not None and any(sid in central_store_ids for sid in visible))
    )
    if visible is not None and not is_central_user:
        await auth.require_store_visibility(current_user.id, requisition.requesting_store_id)

    service = RequisitionService(session)
    fulfilling_store = await service.get_fulfilling_store(requisition)
    fulfilling_available = {}
    branch_available = {}
    for line in requisition.lines:
        # Available shown to the current approval authority is always from the
        # store that fulfils the current requisition workflow.
        stmt = select(func.coalesce(func.sum(StockMovement.quantity_in - StockMovement.quantity_out), 0)).where(
            StockMovement.store_id == fulfilling_store.id,
            StockMovement.financial_year_id == requisition.financial_year_id,
            StockMovement.item_id == line.item_id,
        )
        fulfilling_available[line.item_id] = (await session.scalar(stmt)) or Decimal("0")
        stmt2 = select(func.coalesce(func.sum(StockMovement.quantity_in - StockMovement.quantity_out), 0)).where(
            StockMovement.store_id == requisition.requesting_store_id,
            StockMovement.financial_year_id == requisition.financial_year_id,
            StockMovement.item_id == line.item_id,
        )
        branch_available[line.item_id] = (await session.scalar(stmt2)) or Decimal("0")

    requesting_store = await session.get(Store, requisition.requesting_store_id)
    transfer = await session.scalar(
        select(StockTransfer)
        .options(selectinload(StockTransfer.lines))
        .where(StockTransfer.requisition_id == requisition_id)
        .order_by(StockTransfer.id.desc())
    )
    return render(
        request, "requisition_detail.html", current_user, requisition=requisition,
        fulfilling_store=fulfilling_store, fulfilling_available=fulfilling_available,
        branch_available=branch_available, requesting_store=requesting_store,
        transfer=transfer, today=date.today(),
        is_central_user=is_central_user, error=request.query_params.get("error"),
        success=request.query_params.get("success"),
    )


@router.post("/app/requisitions/new", include_in_schema=False)
async def create_requisition_web(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    form = await request.form()
    try:
        item_ids, qtys, remarks = (repeated(form, n) for n in ("item_id", "requested_quantity", "line_remarks"))
        store_id = int(form["requesting_store_id"])
        store = await session.get(Store, store_id)
        if store is None: raise HTTPException(404, "Store not found")
        payload = RequisitionCreate(requisition_date=date.fromisoformat(str(form["requisition_date"])), financial_year_id=int(form["financial_year_id"]), requesting_office_id=store.office_id, requesting_store_id=store_id, reference_no=str(form.get("reference_no") or "") or None, remarks=str(form.get("remarks") or "") or None, lines=[RequisitionLineCreate(item_id=int(item_ids[i]), requested_quantity=form_decimal(qtys[i]), remarks=remarks[i] if i < len(remarks) else None) for i in range(len(item_ids)) if item_ids[i] and qtys[i]])
        req = await RequisitionService(session).create(payload, current_user.id)
        return redirect_with_success("/app/requisitions", f"Requisition {req.requisition_no} created successfully.")
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error("/app/requisitions/new", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.post("/app/requisitions/{requisition_id}/approve-branch", include_in_schema=False)
async def approve_requisition_branch_web(requisition_id: int, request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    form = await request.form()
    try:
        ids = repeated(form, "requisition_line_id")
        qtys = repeated(form, "requested_quantity")
        lines = [
            BranchApprovalLine(requisition_line_id=int(ids[i]), requested_quantity=form_decimal(qtys[i]))
            for i in range(len(ids))
            if ids[i] and qtys[i]
        ] if ids and qtys else None
        remarks = form.get("remarks")
        await RequisitionService(session).approve_branch(
            requisition_id,
            BranchApprovalRequest(remarks=str(remarks) if remarks else None, lines=lines),
            current_user.id,
            approve=True,
        )
        return redirect_with_success(f"/app/requisitions/{requisition_id}", "Branch approval completed.")
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error(f"/app/requisitions/{requisition_id}", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.post("/app/requisitions/{requisition_id}/approve-central", include_in_schema=False)
async def approve_requisition_central_web(requisition_id: int, request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    form = await request.form()
    try:
        ids, qtys = repeated(form, "requisition_line_id"), repeated(form, "approved_quantity")
        payload = CentralApprovalRequest(remarks=None, lines=[RequisitionApprovalLine(requisition_line_id=int(ids[i]), approved_quantity=form_decimal(qtys[i])) for i in range(len(ids))])
        await RequisitionService(session).approve_central(requisition_id, payload, current_user.id)
        return redirect_with_success(f"/app/requisitions/{requisition_id}", "Central approval completed.")
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error("/app/requisitions", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.post("/app/requisitions/{requisition_id}/dispatch", include_in_schema=False)
async def dispatch_requisition_web(requisition_id: int, request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    form = await request.form()
    try:
        ids, qtys = repeated(form, "requisition_line_id"), repeated(form, "dispatch_quantity")
        payload = TransferDispatchRequest(transfer_date=date.fromisoformat(str(form["transfer_date"])), remarks=None, lines=[TransferDispatchLine(requisition_line_id=int(ids[i]), dispatch_quantity=form_decimal(qtys[i])) for i in range(len(ids))])
        await TransferService(session).dispatch(requisition_id, payload, current_user.id)
        return redirect_with_success(f"/app/requisitions/{requisition_id}", "Transfer dispatched successfully.")
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error(f"/app/requisitions/{requisition_id}", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.post("/app/requisitions/{requisition_id}/receive", include_in_schema=False)
async def receive_requisition_web(requisition_id: int, request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    form = await request.form()
    try:
        transfer = await session.scalar(
            select(StockTransfer)
            .options(selectinload(StockTransfer.lines))
            .where(StockTransfer.requisition_id == requisition_id, StockTransfer.status == "DISPATCHED")
            .order_by(StockTransfer.id.desc())
        )
        if transfer is None:
            raise HTTPException(404, "No dispatched stock transfer found for this requisition")

        req_line_ids = repeated(form, "requisition_line_id")
        qtys = repeated(form, "received_quantity")
        req_to_transfer = {tl.requisition_line_id: tl.id for tl in transfer.lines if tl.requisition_line_id}

        lines_payload = []
        if req_line_ids and qtys:
            for i in range(len(req_line_ids)):
                rid = int(req_line_ids[i])
                if rid in req_to_transfer and i < len(qtys):
                    lines_payload.append(TransferReceiveLine(transfer_line_id=req_to_transfer[rid], received_quantity=form_decimal(qtys[i])))
        else:
            for tl in transfer.lines:
                lines_payload.append(TransferReceiveLine(transfer_line_id=tl.id, received_quantity=tl.quantity))

        receive_date_str = form.get("receive_date")
        receive_date = date.fromisoformat(str(receive_date_str)) if receive_date_str else date.today()
        remarks = str(form.get("remarks")) if form.get("remarks") else None

        payload = TransferReceiveRequest(receive_date=receive_date, remarks=remarks, lines=lines_payload)
        await TransferService(session).receive(transfer.id, payload, current_user.id)
        return redirect_with_success(f"/app/requisitions/{requisition_id}", "Stock received and accepted into branch store successfully.")
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error(f"/app/requisitions/{requisition_id}", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.get("/app/transfers", include_in_schema=False)
async def transfers_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), status: str | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_view_permission(session, current_user.id, "STOCK_TRANSFER_VIEW")
    visible = await AuthorizationService(session).get_visible_stores(current_user.id)
    all_rows = []
    if visible is None:
        all_rows = await TransferService(session).list(None, status)
    else:
        seen=set()
        for sid in visible:
            for row in await TransferService(session).list(sid, status):
                if row.id not in seen: all_rows.append(row); seen.add(row.id)
    stores = list((await session.scalars(select(Store).where(Store.is_active.is_(True)).order_by(Store.name))).all())
    return render(request, "transfers.html", current_user, transfers=all_rows, stores=stores, error=request.query_params.get("error"), success=request.query_params.get("success"))


@router.post("/app/transfers/{transfer_id}/receive", include_in_schema=False)
async def receive_transfer_web(transfer_id: int, request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    form = await request.form()
    try:
        ids, qtys = repeated(form, "transfer_line_id"), repeated(form, "received_quantity")
        payload = TransferReceiveRequest(receive_date=date.fromisoformat(str(form["receive_date"])), remarks=None, lines=[TransferReceiveLine(transfer_line_id=int(ids[i]), received_quantity=form_decimal(qtys[i])) for i in range(len(ids))])
        await TransferService(session).receive(transfer_id, payload, current_user.id)
        return redirect_with_success("/app/transfers", "Transfer received successfully.")
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error("/app/transfers", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.get("/app/my-activity", include_in_schema=False)
async def my_activity_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user

    # Every authenticated active user may see their own activity. This does not
    # grant access to anybody else's history or to the department-wide register.
    rows: list[dict] = []

    async def add_rows(model, label: str, number_attr: str, date_attr: str = "created_at", action: str = "Created"):
        number_col = getattr(model, number_attr)
        date_col = getattr(model, date_attr)
        stmt = select(model).where(getattr(model, "created_by") == current_user.id).order_by(date_col.desc()).limit(100)
        for obj in (await session.scalars(stmt)).all():
            rows.append({"date": getattr(obj, date_attr), "type": label, "document": getattr(obj, number_attr), "status": getattr(obj, "status", ""), "action": action, "id": obj.id})

    await add_rows(Indent, "Indent", "indent_no")
    await add_rows(CentralStoreRequisition, "Requisition", "requisition_no")
    await add_rows(Issue, "Issue", "issue_no", "created_at")
    await add_rows(StockReturn, "Return", "return_no", "created_at")
    await add_rows(PettyPurchase, "Petty Purchase", "petty_purchase_no")
    await add_rows(StockTransfer, "Transfer", "transfer_no")
    await add_rows(Receipt, "Receipt", "receipt_no")

    rows.sort(key=lambda x: (x["date"] is not None, x["date"]), reverse=True)
    return render(request, "my_activity.html", current_user, activities=rows[:200])


@router.get("/app/petty-purchases", include_in_schema=False)
async def petty_purchases_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, status: str | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_view_permission(session, current_user.id, "PETTY_PURCHASE_VIEW")
    visible = await AuthorizationService(session).get_visible_stores(current_user.id)
    stmt = select(PettyPurchase).options(selectinload(PettyPurchase.lines))
    if visible is not None: stmt = stmt.where(PettyPurchase.store_id.in_(visible))
    if store_id is not None:
        await AuthorizationService(session).require_store_visibility(current_user.id, store_id)
        stmt = stmt.where(PettyPurchase.store_id == store_id)
    if status: stmt = stmt.where(PettyPurchase.status == status)
    purchases = list((await session.scalars(stmt.order_by(PettyPurchase.purchase_date.desc(), PettyPurchase.id.desc()).limit(100))).all())
    stores, fys, selected_store, selected_fy = await load_store_context(current_user, session, store_id, None)
    return render(request, "petty_purchases.html", current_user, purchases=purchases, stores=stores, financial_years=fys, selected_store=selected_store, error=request.query_params.get("error"))


@router.get("/app/petty-purchases/new", include_in_schema=False)
async def new_petty_purchase_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, financial_year_id: int | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await AuthorizationService(session).require_permission(current_user.id, "PETTY_PURCHASE_CREATE")
    stores, fys, selected_store, selected_fy = await load_store_context(current_user, session, store_id, financial_year_id)
    if selected_store: await AuthorizationService(session).require_store_assignment(current_user.id, selected_store.id)
    items = list((await session.scalars(select(Item).options(selectinload(Item.category), selectinload(Item.unit)).where(Item.is_active.is_(True)).order_by(Item.name))).all())
    units = list((await session.scalars(select(Unit).where(Unit.is_active.is_(True)).order_by(Unit.name))).all())
    destination_offices = await permitted_destination_offices(session, current_user, selected_store)
    sections = await sections_for_offices(session, destination_offices)
    approved_indents = []
    if selected_store is not None:
        approved_stmt = select(Indent).options(selectinload(Indent.lines).selectinload(IndentLine.item)).where(Indent.store_id == selected_store.id, Indent.status.in_(("RECORDED", "PROCESSING"))).where(~select(Issue.id).where(Issue.indent_id == Indent.id).exists()).order_by(Indent.indent_date.desc(), Indent.id.desc()).limit(100)
        approved_indents = list((await session.scalars(approved_stmt)).all())
    return render(request, "petty_purchase_new.html", current_user, stores=stores, financial_years=fys, selected_store=selected_store, selected_fy=selected_fy, items=items, units=units, destination_offices=destination_offices, sections=sections, approved_indents=approved_indents, error=request.query_params.get("error"))


@router.post("/app/petty-purchases/new", include_in_schema=False)
async def create_petty_purchase_web(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    form = await request.form()
    try:
        item_ids, names, qtys, unit_ids, prices, immediate, remarks = (repeated(form, n) for n in ("item_id", "temporary_item_name", "quantity", "unit_id", "unit_price", "immediate_issue_quantity", "line_remarks"))
        lines=[]
        for idx, qty in enumerate(qtys):
            if not qty: continue
            iid = int(item_ids[idx]) if idx < len(item_ids) and item_ids[idx] else None
            tname = (names[idx] if idx < len(names) else "").strip() or None
            lines.append(PettyPurchaseLineCreate(item_id=iid, temporary_item_name=tname, quantity=form_decimal(qty), unit_id=int(unit_ids[idx]), unit_price=form_decimal(prices[idx], default=Decimal("0")) if idx < len(prices) and prices[idx] else None, immediate_issue_quantity=form_decimal(immediate[idx] if idx < len(immediate) else "0"), remarks=(remarks[idx] if idx < len(remarks) else None) or None))
        payload = PettyPurchaseCreate(
            purchase_date=date.fromisoformat(str(form["purchase_date"])),
            financial_year_id=int(form["financial_year_id"]),
            store_id=int(form["store_id"]),
            indent_id=int(form["indent_id"]) if form.get("indent_id") else None,
            issue_office_id=int(form["issue_office_id"]) if form.get("issue_office_id") else None,
            issue_section_id=int(form["issue_section_id"]) if form.get("issue_section_id") else None,
            vendor_name=str(form.get("vendor_name") or "") or None,
            reference_no=str(form.get("reference_no") or "") or None,
            invoice_no=str(form.get("invoice_no") or "") or None,
            remarks=str(form.get("remarks") or "") or None,
            lines=lines,
        )
        await PettyPurchaseService(session).create(payload, current_user.id)
        return redirect_with_success("/app/petty-purchases", "Petty purchase action completed successfully.")
    except (HTTPException, ValueError) as exc:
        return redirect_with_error("/app/petty-purchases/new", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.post("/app/petty-purchases/{purchase_id}/verify", include_in_schema=False)
async def verify_petty_web(purchase_id: int, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await PettyPurchaseService(session).verify(purchase_id, PettyPurchaseVerifyRequest(), current_user.id)
        return redirect_with_success("/app/petty-purchases", "Petty purchase action completed successfully.")
    except HTTPException as exc: return redirect_with_error("/app/petty-purchases", exc.detail)


@router.post("/app/petty-purchases/{purchase_id}/post", include_in_schema=False)
async def post_petty_web(purchase_id: int, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await PettyPurchaseService(session).post(purchase_id, PettyPurchasePostRequest(), current_user.id)
        return redirect_with_success("/app/petty-purchases", "Petty purchase action completed successfully.")
    except HTTPException as exc: return redirect_with_error("/app/petty-purchases", exc.detail)


def page_window(total: int, page: int, page_size: int) -> tuple[int, int, int, int]:
    page_size = max(10, min(page_size, 200))
    pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, pages))
    return page, page_size, pages, (page - 1) * page_size


def pdf_response(title: str, columns: list[tuple[str, str]], rows: list[dict], subtitle: str = ""):
    pdf = make_register_pdf(title, columns, rows, subtitle)
    filename = title.lower().replace(" ", "_").replace("/", "-") + ".pdf"
    return StreamingResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/app/registers", include_in_schema=False)
async def registers_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, financial_year_id: int | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_view_permission(session, current_user.id, "REGISTER_VIEW")
    stores, fys, selected_store, selected_fy = await load_store_context(current_user, session, store_id, financial_year_id)
    return render(request, "registers.html", current_user, stores=stores, financial_years=fys, selected_store=selected_store, selected_fy=selected_fy)


@router.get("/app/registers/item-stock", include_in_schema=False)
async def item_stock_register_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, financial_year_id: int | None = None, search: str | None = None, page: int = 1, page_size: int = 50, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_view_permission(session, current_user.id, "REGISTER_VIEW")
    stores, fys, selected_store, selected_fy = await load_store_context(current_user, session, store_id, financial_year_id)
    rows = []
    if selected_store and selected_fy:
        await AuthorizationService(session).require_store_visibility(current_user.id, selected_store.id)
        raw = await StockService(session).all_item_balances(selected_store.id, selected_fy.id, search)
        total = len(raw); page, page_size, pages, offset = page_window(total, page, page_size)
        rows = [dict(r._mapping) for r in raw[offset:offset + page_size]]
    else:
        total = 0; pages = 1; offset = 0
    return render(request, "item_stock_register.html", current_user, rows=rows, stores=stores, financial_years=fys, selected_store=selected_store, selected_fy=selected_fy, search=search or "", page=page, page_size=page_size, pages=pages, total=total)


@router.get("/app/registers/issues", include_in_schema=False)
async def issue_register_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, financial_year_id: int | None = None, search: str | None = None, page: int = 1, page_size: int = 50, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_view_permission(session, current_user.id, "REGISTER_VIEW")
    stores, fys, selected_store, selected_fy = await load_store_context(current_user, session, store_id, financial_year_id)
    raw = await RegisterService(session).issue_register(current_user.id, store_id, financial_year_id, search=search)
    total=len(raw); page,page_size,pages,offset=page_window(total,page,page_size); rows=raw[offset:offset+page_size]
    return render(request, "register_list.html", current_user, title="Issue Register", subtitle="Posted issues derived from Issue documents", kind="issues", rows=rows, stores=stores, financial_years=fys, selected_store=selected_store, selected_fy=selected_fy, search=search or "", page=page, page_size=page_size, pages=pages, total=total)


@router.get("/app/registers/distribution", include_in_schema=False)
async def distribution_register_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, financial_year_id: int | None = None, search: str | None = None, page: int = 1, page_size: int = 50, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_view_permission(session, current_user.id, "REGISTER_VIEW")
    stores, fys, selected_store, selected_fy = await load_store_context(current_user, session, store_id, financial_year_id)
    raw=await RegisterService(session).distribution_register(current_user.id,store_id,financial_year_id,search=search); total=len(raw); page,page_size,pages,offset=page_window(total,page,page_size); rows=raw[offset:offset+page_size]
    return render(request,"register_list.html",current_user,title="Distribution Register",subtitle="Distribution derived from finalized Issues",kind="distribution",rows=rows,stores=stores,financial_years=fys,selected_store=selected_store,selected_fy=selected_fy,search=search or "",page=page,page_size=page_size,pages=pages,total=total)


@router.get("/app/registers/transactions", include_in_schema=False)
async def transaction_register_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, financial_year_id: int | None = None, search: str | None = None, page: int = 1, page_size: int = 50, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_view_permission(session,current_user.id,"REGISTER_VIEW"); stores,fys,selected_store,selected_fy=await load_store_context(current_user,session,store_id,financial_year_id)
    raw=await RegisterService(session).transaction_register(current_user.id,store_id,financial_year_id,search=search); total=len(raw); page,page_size,pages,offset=page_window(total,page,page_size); rows=raw[offset:offset+page_size]
    return render(request,"register_list.html",current_user,title="Transaction Register",subtitle="Unified source-document-linked stock movement history",kind="transactions",rows=rows,stores=stores,financial_years=fys,selected_store=selected_store,selected_fy=selected_fy,search=search or "",page=page,page_size=page_size,pages=pages,total=total)


@router.get("/app/registers/computers", include_in_schema=False)
async def computer_register_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, search: str | None = None, page: int = 1, page_size: int = 50, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    stores,fys,selected_store,selected_fy=await load_store_context(current_user,session,store_id,None); raw=await RegisterService(session).computer_register(current_user.id,store_id,search=search); total=len(raw); page,page_size,pages,offset=page_window(total,page,page_size)
    return render(request,"register_assets.html",current_user,title="Computer Register",subtitle="Computer/printer assets filtered from the Asset Register",assets=raw[offset:offset+page_size],stores=stores,financial_years=fys,selected_store=selected_store,selected_fy=selected_fy,search=search or "",page=page,page_size=page_size,pages=pages,total=total)


@router.get("/app/registers/e-waste", include_in_schema=False)
async def e_waste_register_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, search: str | None = None, page: int = 1, page_size: int = 50, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    stores,fys,selected_store,selected_fy=await load_store_context(current_user,session,store_id,None); raw=await RegisterService(session).e_waste_register(current_user.id,store_id,search=search); total=len(raw); page,page_size,pages,offset=page_window(total,page,page_size)
    return render(request,"register_assets.html",current_user,title="E-Waste Register",subtitle="Unserviceable/disposed asset lifecycle view",assets=raw[offset:offset+page_size],stores=stores,financial_years=fys,selected_store=selected_store,selected_fy=selected_fy,search=search or "",page=page,page_size=page_size,pages=pages,total=total)

@router.get("/app/outward-pass/{issue_id}", include_in_schema=False)
async def outward_pass_page(issue_id: int, request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_view_permission(session, current_user.id, "REGISTER_VIEW")
    issue = await session.scalar(select(Issue).options(selectinload(Issue.lines).selectinload(IssueLine.item), selectinload(Issue.lines).selectinload(IssueLine.unit)).where(Issue.id == issue_id))
    if issue is None: raise HTTPException(404, "Issue not found")
    await AuthorizationService(session).require_store_visibility(current_user.id, issue.source_store_id)
    store = await session.get(Store, issue.source_store_id); office = await session.get(Office, issue.destination_office_id)
    section = await session.get(Section, issue.destination_section_id) if issue.destination_section_id else None
    if issue.status != "FINALIZED": raise HTTPException(409, "Only finalized issues can generate an outward pass")
    return render(request,"outward_pass.html",current_user,issue=issue,store=store,office=office,section=section)


@router.get("/app/outward-pass/{issue_id}.pdf", include_in_schema=False)
async def outward_pass_pdf(issue_id: int, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_view_permission(session, current_user.id, "REGISTER_VIEW")
    issue = await session.scalar(select(Issue).options(selectinload(Issue.lines).selectinload(IssueLine.item), selectinload(Issue.lines).selectinload(IssueLine.unit)).where(Issue.id == issue_id))
    if issue is None: raise HTTPException(404,"Issue not found")
    await AuthorizationService(session).require_store_visibility(current_user.id, issue.source_store_id)
    if issue.status != "FINALIZED": raise HTTPException(409,"Only finalized issues can generate an outward pass")
    store=await session.get(Store,issue.source_store_id); office=await session.get(Office,issue.destination_office_id); section=await session.get(Section,issue.destination_section_id) if issue.destination_section_id else None
    rows=[{"item":f"{line.item.code} — {line.item.name}" if line.item else line.item_id,"unit":line.unit.code if line.unit else line.unit_id,"quantity":line.quantity} for line in issue.lines]
    cols=[("item","Item"),("unit","Unit"),("quantity","Quantity")]
    subtitle=f"Pass reference: {issue.issue_no} | Date: {issue.issue_date} | From: {store.name if store else issue.source_store_id} | To: {office.name if office else issue.destination_office_id}{(' / '+section.name) if section else ''}"
    return pdf_response("Outward Pass",cols,rows,subtitle)


@router.get("/app/registers/item-stock.pdf", include_in_schema=False)
async def item_stock_register_pdf(current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, financial_year_id: int | None = None, search: str | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_view_permission(session, current_user.id, "REGISTER_VIEW")
    stores,fys,selected_store,selected_fy=await load_store_context(current_user,session,store_id,financial_year_id)
    if not selected_store or not selected_fy: raise HTTPException(422,"Store and financial year are required")
    await AuthorizationService(session).require_store_visibility(current_user.id, selected_store.id)
    raw=await StockService(session).all_item_balances(selected_store.id,selected_fy.id,search)
    rows=[dict(r._mapping) for r in raw]
    cols=[("item_code","Code"),("item_name","Item"),("unit_code","Unit"),("balance","Balance")]
    return pdf_response("Item Stock Register",cols,rows,f"{selected_store.name} | FY {selected_fy.year_name}")


@router.get("/app/registers/issues.pdf", include_in_schema=False)
async def issue_register_pdf(current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, financial_year_id: int | None = None, search: str | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    rows=await RegisterService(session).issue_register(current_user.id,store_id,financial_year_id,search=search)
    cols=[("issue_no","Issue"),("issue_date","Date"),("store_name","Store"),("office_name","Destination Office"),("section_name","Section"),("indent_no","Indent"),("status","Status")]
    return pdf_response("Issue Register",cols,rows)


@router.get("/app/registers/distribution.pdf", include_in_schema=False)
async def distribution_register_pdf(current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, financial_year_id: int | None = None, search: str | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    rows=await RegisterService(session).distribution_register(current_user.id,store_id,financial_year_id,search=search)
    cols=[("issue_date","Date"),("issue_no","Issue"),("office_name","Destination"),("section_name","Section"),("item_code","Item Code"),("item_name","Item"),("quantity","Quantity")]
    return pdf_response("Distribution Register",cols,rows)


@router.get("/app/registers/transactions.pdf", include_in_schema=False)
async def transaction_register_pdf(current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, financial_year_id: int | None = None, search: str | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    rows=await RegisterService(session).transaction_register(current_user.id,store_id,financial_year_id,search=search)
    cols=[("movement_date","Date"),("movement_type","Movement"),("store_name","Store"),("item_code","Item Code"),("item_name","Item"),("quantity_in","In"),("quantity_out","Out"),("reference_no","Document")]
    return pdf_response("Transaction Register",cols,rows)


@router.get("/app/registers/computers.pdf", include_in_schema=False)
async def computer_register_pdf(current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, search: str | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    assets=await RegisterService(session).computer_register(current_user.id,store_id,search=search)
    rows=[{"asset_no":a.asset_no,"item":f"{a.item.code} — {a.item.name}" if a.item else a.item_id,"serial":a.serial_no or "","status":a.status,"store":a.current_store_id or "","office":a.current_office_id or "","section":a.current_section_id or ""} for a in assets]
    cols=[("asset_no","Asset No"),("item","Item"),("serial","Serial"),("status","Status"),("store","Store"),("office","Office"),("section","Section")]
    return pdf_response("Computer Register",cols,rows)


@router.get("/app/registers/e-waste.pdf", include_in_schema=False)
async def e_waste_register_pdf(current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, search: str | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    assets=await RegisterService(session).e_waste_register(current_user.id,store_id,search=search)
    rows=[{"asset_no":a.asset_no,"item":f"{a.item.code} — {a.item.name}" if a.item else a.item_id,"serial":a.serial_no or "","status":a.status,"store":a.current_store_id or "","office":a.current_office_id or "","section":a.current_section_id or ""} for a in assets]
    cols=[("asset_no","Asset No"),("item","Item"),("serial","Serial"),("status","Status"),("store","Store"),("office","Office"),("section","Section")]
    return pdf_response("E-Waste Register",cols,rows)


@router.get("/app/returns", include_in_schema=False)
async def returns_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, status: str | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_view_permission(session, current_user.id, "STOCK_RETURN_VIEW")
    auth = AuthorizationService(session)
    perms = permission_codes(current_user)
    visible = await auth.get_visible_stores(current_user.id)
    stmt = select(StockReturn).options(selectinload(StockReturn.lines))
    is_section_user = "STOCK_RETURN_CREATE" in perms and "STOCK_RETURN" not in perms
    if visible is not None and not is_section_user: stmt = stmt.where(StockReturn.store_id.in_(visible))
    if store_id is not None:
        await auth.require_store_visibility(current_user.id, store_id)
        stmt = stmt.where(StockReturn.store_id == store_id)
    if is_section_user and current_user.section_id is not None:
        stmt = stmt.where(StockReturn.returning_section_id == current_user.section_id)
    if status: stmt = stmt.where(StockReturn.status == status)
    returns = list((await session.scalars(stmt.order_by(StockReturn.return_date.desc(), StockReturn.id.desc()).limit(100))).all())
    stores, fys, selected_store, selected_fy = await load_store_context(current_user, session, store_id, None)
    return render(request, "returns.html", current_user, returns=returns, stores=stores, financial_years=fys, selected_store=selected_store, error=request.query_params.get("error"), success=request.query_params.get("success"))

@router.get("/app/returns/new", include_in_schema=False)
async def new_return_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), store_id: int | None = None, session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    perms = permission_codes(current_user)
    if "STOCK_RETURN_CREATE" not in perms and "STOCK_RETURN" not in perms: raise HTTPException(403, "User lacks return creation permission")
    auth = AuthorizationService(session)
    stores, fys, selected_store, selected_fy = await load_store_context(current_user, session, store_id, None)
    is_section_user = "STOCK_RETURN_CREATE" in perms and "STOCK_RETURN" not in perms
    if selected_store is None and stores: selected_store = stores[0]
    if is_section_user and selected_store is None and current_user.office_id is not None:
        selected_store = await session.scalar(select(Store).where(Store.office_id == current_user.office_id, Store.is_active.is_(True)).order_by(Store.id))
        if selected_store is not None:
            stores = [selected_store]
    if selected_store is not None and not is_section_user: await auth.require_store_assignment(current_user.id, selected_store.id)
    issues_stmt = select(Issue).options(selectinload(Issue.lines).selectinload(IssueLine.item)).where(Issue.status == "FINALIZED")
    if is_section_user:
        issues_stmt = issues_stmt.where(Issue.destination_office_id == current_user.office_id, Issue.destination_section_id == current_user.section_id)
    else:
        visible = await auth.get_visible_stores(current_user.id)
        if visible is not None: issues_stmt = issues_stmt.where(Issue.source_store_id.in_(visible))
    issues = list((await session.scalars(issues_stmt.order_by(Issue.issue_date.desc(), Issue.id.desc()).limit(100))).all())
    items = list((await session.scalars(select(Item).options(selectinload(Item.category), selectinload(Item.unit)).where(Item.is_active.is_(True)).order_by(Item.name))).all())
    units = list((await session.scalars(select(Unit).where(Unit.is_active.is_(True)).order_by(Unit.name))).all())
    return render(request, "return_new.html", current_user, stores=stores, financial_years=fys, selected_store=selected_store, selected_fy=selected_fy, issues=issues, items=items, units=units, is_section_user=is_section_user, error=request.query_params.get("error"))

@router.post("/app/returns/new", include_in_schema=False)
async def create_return_web(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    form = await request.form()
    try:
        return_type = str(form.get("return_type") or "CSMS_ISSUE")
        issue_id = int(form["original_issue_id"]) if form.get("original_issue_id") else None
        item_ids, issue_line_ids, qtys, unit_ids, asset_ids, line_remarks = (repeated(form, n) for n in ("item_id", "original_issue_line_id", "quantity", "unit_id", "asset_ids", "line_remarks"))
        lines=[]
        for idx, qty in enumerate(qtys):
            if not qty: continue
            parsed_assets=[int(x.strip()) for x in (asset_ids[idx] if idx < len(asset_ids) else "").split(",") if x.strip()] or None
            lines.append(StockReturnLineCreate(original_issue_line_id=int(issue_line_ids[idx]) if idx < len(issue_line_ids) and issue_line_ids[idx] else None, item_id=int(item_ids[idx]) if idx < len(item_ids) and item_ids[idx] else None, unit_id=int(unit_ids[idx]) if idx < len(unit_ids) and unit_ids[idx] else None, quantity=form_decimal(qty), asset_ids=parsed_assets, remarks=(line_remarks[idx] if idx < len(line_remarks) else None) or None))
        payload=StockReturnCreate(return_date=date.fromisoformat(str(form["return_date"])), financial_year_id=int(form["financial_year_id"]), store_id=int(form["store_id"]), original_issue_id=issue_id, return_type=return_type, manual_reference=str(form.get("manual_reference") or "") or None, condition=str(form.get("condition") or "USABLE"), returning_user_id=current_user.id, returning_office_id=int(form["returning_office_id"]) if form.get("returning_office_id") else current_user.office_id, returning_section_id=int(form["returning_section_id"]) if form.get("returning_section_id") else current_user.section_id, reason=str(form["reason"]), remarks=str(form.get("remarks") or "") or None, lines=lines)
        await StockReturnService(session).create(payload, current_user.id)
        return redirect_with_success("/app/returns", "Return recorded successfully.")
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error("/app/returns/new", exc.detail if isinstance(exc, HTTPException) else str(exc))

@router.post("/app/returns/{return_id}/verify", include_in_schema=False)
async def verify_return_web(return_id: int, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await StockReturnService(session).verify(return_id, current_user.id)
        return redirect_with_success("/app/returns", "Return verified successfully.")
    except HTTPException as exc: return redirect_with_error("/app/returns", exc.detail)

@router.post("/app/returns/{return_id}/post", include_in_schema=False)
async def post_return_web(return_id: int, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await StockReturnService(session).post(return_id, current_user.id)
        return redirect_with_success("/app/returns", "Return posted successfully.")
    except HTTPException as exc: return redirect_with_error("/app/returns", exc.detail)

