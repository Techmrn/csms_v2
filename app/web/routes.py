from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.asset import Asset
from app.models.financial_year import FinancialYear
from app.models.item import Item
from app.models.office import Office
from app.models.store import Store
from app.models.user import User
from app.security.auth import authenticate_user, create_access_token
from app.services.authorization import AuthorizationService
from app.services.stock import StockService
from app.web.auth import get_web_current_user

WEB_ROOT = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(WEB_ROOT / "templates"))

router = APIRouter(tags=["web"])


MENU = [
    ("Dashboard", "/app", None),
    ("Stock", "/app/stock", "STOCK_VIEW"),
    ("Items", "/app/items", "STOCK_VIEW"),
    ("Assets", "/app/assets", "ASSET_VIEW"),
    ("Manual Indents", "/app", "INDENT_CREATE"),
    ("Receipts", "/app", "STOCK_RECEIPT"),
    ("Returns", "/app", "STOCK_RETURN"),
    ("Requisitions", "/app", "REQUISITION_CREATE"),
    ("Transfers", "/app", "STOCK_TRANSFER_RECEIVE"),
    ("Petty Purchase", "/app", "PETTY_PURCHASE_CREATE"),
    ("Stock Control", "/app", "STOCK_VERIFY"),
]


def role_label(user: User) -> str:
    active_roles = [r.code for r in user.roles if r.is_active]
    labels = []
    for code in active_roles:
        labels.append(code.replace("_", " ").title())
    return " / ".join(labels) or "User"


def permission_codes(user: User) -> set[str]:
    return {
        permission.code
        for role in user.roles
        if role.is_active
        for permission in role.permissions
        if permission.is_active
    }


def visible_menu(user: User) -> list[dict[str, str | None]]:
    perms = permission_codes(user)
    return [
        {"label": label, "href": href}
        for label, href, permission in MENU
        if permission is None or permission in perms
    ]


def base_context(user: User) -> dict:
    roles = [r.code for r in user.roles if r.is_active]
    return {
        "user": user,
        "role_label": role_label(user),
        "roles": roles,
        "menu": visible_menu(user),
        "permissions": permission_codes(user),
    }


async def load_store_context(
    user: User,
    session: AsyncSession,
    requested_store_id: int | None,
    requested_fy_id: int | None,
) -> tuple[list[Store], list[FinancialYear], Store | None, FinancialYear | None]:
    auth = AuthorizationService(session)
    visible = await auth.get_visible_stores(user.id)

    store_stmt = select(Store).where(Store.is_active.is_(True)).order_by(Store.name)
    if visible is not None:
        if not visible:
            store_stmt = store_stmt.where(Store.id == -1)
        else:
            store_stmt = store_stmt.where(Store.id.in_(visible))
    stores = list((await session.scalars(store_stmt)).all())

    fys = list(
        (
            await session.scalars(
                select(FinancialYear)
                .order_by(FinancialYear.start_date.desc())
            )
        ).all()
    )

    selected_store: Store | None = None
    if requested_store_id is not None:
        selected_store = next((s for s in stores if s.id == requested_store_id), None)
    if selected_store is None and stores:
        primary_ids = {store.id for store in user.stores if store.is_active}
        selected_store = next((s for s in stores if s.id in primary_ids), stores[0])

    selected_fy: FinancialYear | None = None
    if requested_fy_id is not None:
        selected_fy = next((fy for fy in fys if fy.id == requested_fy_id), None)
    if selected_fy is None:
        selected_fy = next((fy for fy in fys if fy.is_current), fys[0] if fys else None)

    return stores, fys, selected_store, selected_fy


def context_query(store: Store | None, fy: FinancialYear | None) -> str:
    if store is None or fy is None:
        return ""
    return f"?store_id={store.id}&financial_year_id={fy.id}"


@router.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/app", status_code=303)


@router.get("/login", include_in_schema=False)
async def login_page(request: Request):
    return TEMPLATES.TemplateResponse(request=request, name="login.html", context={"error": None})


@router.post("/login", include_in_schema=False)
async def login_submit(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    session: AsyncSession = Depends(get_db_session),
):
    user = await authenticate_user(session, username, password)
    if user is None:
        return TEMPLATES.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Incorrect username or password"},
            status_code=401,
        )

    token = create_access_token(user)
    response = RedirectResponse(url="/app", status_code=303)
    response.set_cookie(
        "csms_access_token",
        token,
        httponly=True,
        secure=not __import__("app.core.config", fromlist=["get_settings"]).get_settings().debug,
        samesite="lax",
        max_age=60 * __import__("app.core.config", fromlist=["get_settings"]).get_settings().access_token_expire_minutes,
        path="/",
    )
    return response


@router.get("/logout", include_in_schema=False)
async def logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("csms_access_token", path="/")
    return response


@router.get("/app", include_in_schema=False)
async def dashboard(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    store_id: int | None = None,
    financial_year_id: int | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    stores, fys, selected_store, selected_fy = await load_store_context(
        current_user, session, store_id, financial_year_id
    )
    stock_rows = []
    total_units = Decimal("0")
    if selected_store and selected_fy:
        await AuthorizationService(session).require_store_visibility(
            current_user.id, selected_store.id
        )
        rows = await StockService(session).current_stock(
            selected_store.id, selected_fy.id, None
        )
        stock_rows = rows[:8]
        total_units = sum((Decimal(str(row.balance or 0)) for row in rows), Decimal("0"))

    item_count = await session.scalar(
        select(func.count(Item.id)).where(Item.is_active.is_(True))
    )
    visible_asset_count = 0
    if selected_store and selected_fy:
        try:
            visible_assets = await session.execute(
                select(func.count(Asset.id)).where(Asset.is_active.is_(True), Asset.current_store_id == selected_store.id)
            )
            visible_asset_count = int(visible_assets.scalar_one())
        except Exception:
            visible_asset_count = 0

    context = base_context(current_user)
    context.update(
        {
            "request": request,
            "stores": stores,
            "financial_years": fys,
            "selected_store": selected_store,
            "selected_fy": selected_fy,
            "stock_rows": stock_rows,
            "stock_count": len(rows) if selected_store and selected_fy else 0,
            "total_units": total_units,
            "item_count": int(item_count or 0),
            "asset_count": visible_asset_count,
        }
    )
    return TEMPLATES.TemplateResponse(request=request, name="dashboard.html", context=context)


@router.get("/app/stock", include_in_schema=False)
async def stock_page(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    store_id: int | None = None,
    financial_year_id: int | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    stores, fys, selected_store, selected_fy = await load_store_context(
        current_user, session, store_id, financial_year_id
    )
    rows = []
    if selected_store and selected_fy:
        await AuthorizationService(session).require_permission(current_user.id, "STOCK_VIEW")
        await AuthorizationService(session).require_store_visibility(current_user.id, selected_store.id)
        rows = await StockService(session).current_stock(selected_store.id, selected_fy.id, None)
    context = base_context(current_user)
    context.update(
        {
            "request": request,
            "stores": stores,
            "financial_years": fys,
            "selected_store": selected_store,
            "selected_fy": selected_fy,
            "rows": rows,
        }
    )
    return TEMPLATES.TemplateResponse(request=request, name="stock.html", context=context)


@router.get("/app/items", include_in_schema=False)
async def items_page(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    await AuthorizationService(session).require_permission(current_user.id, "STOCK_VIEW")
    items = list((await session.scalars(select(Item).where(Item.is_active.is_(True)).order_by(Item.name))).all())
    offices = list((await session.scalars(select(Office).where(Office.is_active.is_(True)).order_by(Office.name))).all())
    context = base_context(current_user)
    context.update({"request": request, "items": items, "offices": offices})
    return TEMPLATES.TemplateResponse(request=request, name="items.html", context=context)


@router.get("/app/assets", include_in_schema=False)
async def assets_page(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    store_id: int | None = None,
    status: str | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    await AuthorizationService(session).require_permission(current_user.id, "ASSET_VIEW")
    stores, fys, selected_store, selected_fy = await load_store_context(
        current_user, session, store_id, None
    )
    # For the Asset Register, an omitted store_id means "all visible stores".
    # load_store_context normally chooses a default store for dashboard context,
    # so restore the explicit all-store semantic here.
    if store_id is None:
        selected_store = None

    assets = []
    visible_store_ids = await AuthorizationService(session).get_visible_stores(current_user.id)
    stmt = select(Asset).where(Asset.is_active.is_(True))
    if selected_store is not None:
        await AuthorizationService(session).require_store_visibility(current_user.id, selected_store.id)
        stmt = stmt.where(Asset.current_store_id == selected_store.id)
    elif visible_store_ids is not None:
        stmt = stmt.where(Asset.current_store_id.in_(visible_store_ids))
    if status:
        stmt = stmt.where(Asset.status == status)
    assets = list((await session.scalars(stmt.order_by(Asset.asset_no))).all())
    context = base_context(current_user)
    context.update(
        {
            "request": request,
            "stores": stores,
            "financial_years": fys,
            "selected_store": selected_store,
            "assets": assets,
            "status_filter": status or "",
        }
    )
    return TEMPLATES.TemplateResponse(request=request, name="assets.html", context=context)
