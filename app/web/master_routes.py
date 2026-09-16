from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db_session
from app.models.category import Category
from app.models.financial_year import FinancialYear
from app.models.inventory_policy import InventoryPolicy
from app.models.item import Item
from app.models.office import Office
from app.models.permission import Permission
from app.models.role import Role
from app.models.section import Section
from app.models.store import Store
from app.models.unit import Unit
from app.models.user import User
from app.security.auth import password_hash
from app.services.authorization import AuthorizationService
from app.services.master_admin import MasterAdminService
from app.web.auth import get_web_current_user
from app.web.routes import redirect_with_error, render

router = APIRouter(tags=["web-admin"])


def current_user_or_redirect(current_user):
    return current_user if isinstance(current_user, User) else current_user


async def require_master_user(user: User, session: AsyncSession) -> None:
    await MasterAdminService(session).require_master(user.id)


async def require_org_user(user: User, session: AsyncSession) -> None:
    await MasterAdminService(session).require_org(user.id)


async def require_user_admin(user: User, session: AsyncSession) -> None:
    await MasterAdminService(session).require_user_admin(user.id)


@router.get("/app/admin", include_in_schema=False)
async def admin_home(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    service = MasterAdminService(session)
    perms = {
        "MASTER_DATA_MANAGE",
        "ORGANIZATION_MANAGE",
        "USER_MANAGE",
    }
    user_perms = {
        permission.code
        for role in current_user.roles
        if role.is_active
        for permission in role.permissions
        if permission.is_active
    }
    if not user_perms.intersection(perms):
        raise HTTPException(403, "User lacks administration access")
    counts = await service.get_dashboard_counts()
    return render(request, "admin_home.html", current_user, counts=counts)


@router.get("/app/admin/organization", include_in_schema=False)
async def organization_home(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    await require_org_user(current_user, session)
    return render(request, "admin_organization.html", current_user)


@router.get("/app/admin/views", include_in_schema=False)
async def admin_views_home(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    await require_user_admin(current_user, session)
    return render(request, "admin_views.html", current_user)


@router.get("/app/admin/views/requisitions", include_in_schema=False)
async def admin_requisitions_view(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    await require_user_admin(current_user, session)
    rows = await MasterAdminService(session).list_admin_views_requisitions()
    return render(request, "admin_requisitions.html", current_user, rows=rows)


@router.get("/app/admin/views/transfers", include_in_schema=False)
async def admin_transfers_view(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    await require_user_admin(current_user, session)
    rows = await MasterAdminService(session).list_admin_views_transfers()
    return render(request, "admin_transfers.html", current_user, rows=rows)


@router.get("/app/admin/views/stock-control", include_in_schema=False)
async def admin_stock_control_view(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    await require_user_admin(current_user, session)
    data = await MasterAdminService(session).get_admin_stock_control_views()
    return render(request, "admin_stock_control.html", current_user, **data)


@router.get("/app/admin/masters", include_in_schema=False)
async def masters_home(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    await require_master_user(current_user, session)
    return render(request, "masters_home.html", current_user)


@router.get("/app/admin/offices", include_in_schema=False)
async def offices_page(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_org_user(current_user, session)
    offices = await MasterAdminService(session).list_offices()
    edit_id = request.query_params.get("edit")
    edit_office = await session.get(Office, int(edit_id)) if edit_id else None
    return render(request, "master_offices.html", current_user, offices=offices, edit_office=edit_office)


@router.post("/app/admin/offices/new", include_in_schema=False)
async def create_office_web(
    request: Request,
    code: Annotated[str, Form()],
    name: Annotated[str, Form()],
    office_type: Annotated[str, Form()],
    parent_office_id: Annotated[str | None, Form()] = None,
    display_order: Annotated[str | None, Form()] = None,
    remarks: Annotated[str | None, Form()] = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await require_org_user(current_user, session)
        await MasterAdminService(session).create_office({
            "code": code.strip().upper(), "name": name.strip(), "office_type": office_type,
            "parent_office_id": int(parent_office_id) if parent_office_id else None,
            "display_order": int(display_order) if display_order else None,
            "remarks": remarks.strip() if remarks else None,
        })
        await session.commit()
        return RedirectResponse(url="/app/admin/offices?success=Office%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError) as exc:
        await session.rollback()
        return redirect_with_error("/app/admin/offices", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.post("/app/admin/offices/{office_id}/save", include_in_schema=False)
async def update_office_web(
    office_id: int,
    request: Request,
    name: Annotated[str, Form()],
    office_type: Annotated[str, Form()],
    parent_office_id: Annotated[str | None, Form()] = None,
    display_order: Annotated[str | None, Form()] = None,
    remarks: Annotated[str | None, Form()] = None,
    is_active: Annotated[str | None, Form()] = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await require_org_user(current_user, session)
        await MasterAdminService(session).update_office(office_id, {
            "name": name.strip(), "office_type": office_type,
            "parent_office_id": int(parent_office_id) if parent_office_id else None,
            "display_order": int(display_order) if display_order else None,
            "remarks": remarks.strip() if remarks else None,
            "is_active": is_active == "on",
        })
        await session.commit()
        return RedirectResponse(url="/app/admin/offices?success=Office%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError) as exc:
        await session.rollback()
        return redirect_with_error(f"/app/admin/offices?edit={office_id}", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.get("/app/admin/stores", include_in_schema=False)
async def stores_page(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_org_user(current_user, session)
    service = MasterAdminService(session)
    stores = await service.list_stores()
    offices = await service.list_offices()
    edit_id = request.query_params.get("edit")
    edit_store = await session.get(Store, int(edit_id)) if edit_id else None
    return render(request, "master_stores.html", current_user, stores=stores, offices=offices, edit_store=edit_store)


@router.post("/app/admin/stores/new", include_in_schema=False)
async def create_store_web(
    request: Request,
    office_id: Annotated[int, Form()],
    code: Annotated[str, Form()],
    name: Annotated[str, Form()],
    store_type: Annotated[str, Form()],
    is_primary: Annotated[str | None, Form()] = None,
    remarks: Annotated[str | None, Form()] = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await require_org_user(current_user, session)
        await MasterAdminService(session).create_store({
            "office_id": office_id, "code": code.strip().upper(), "name": name.strip(),
            "store_type": store_type, "is_primary": is_primary == "on", "remarks": remarks.strip() if remarks else None,
        })
        await session.commit()
        return RedirectResponse(url="/app/admin/stores?success=Store%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError) as exc:
        await session.rollback()
        return redirect_with_error("/app/admin/stores", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.post("/app/admin/stores/{store_id}/save", include_in_schema=False)
async def update_store_web(
    store_id: int,
    request: Request,
    office_id: Annotated[int, Form()],
    name: Annotated[str, Form()],
    store_type: Annotated[str, Form()],
    is_primary: Annotated[str | None, Form()] = None,
    remarks: Annotated[str | None, Form()] = None,
    is_active: Annotated[str | None, Form()] = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await require_org_user(current_user, session)
        await MasterAdminService(session).update_store(store_id, {
            "office_id": office_id, "name": name.strip(), "store_type": store_type,
            "is_primary": is_primary == "on", "remarks": remarks.strip() if remarks else None, "is_active": is_active == "on",
        })
        await session.commit()
        return RedirectResponse(url="/app/admin/stores?success=Store%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError) as exc:
        await session.rollback()
        return redirect_with_error(f"/app/admin/stores?edit={store_id}", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.get("/app/admin/sections", include_in_schema=False)
async def sections_page(
    request: Request,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_org_user(current_user, session)
    service = MasterAdminService(session)
    sections = await service.list_sections(); offices = await service.list_offices()
    edit_id = request.query_params.get("edit")
    edit_section = await session.get(Section, int(edit_id)) if edit_id else None
    return render(request, "master_sections.html", current_user, sections=sections, offices=offices, edit_section=edit_section)


@router.post("/app/admin/sections/new", include_in_schema=False)
async def create_section_web(
    office_id: Annotated[int, Form()], code: Annotated[str, Form()], name: Annotated[str, Form()],
    remarks: Annotated[str | None, Form()] = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await require_org_user(current_user, session)
        await MasterAdminService(session).create_section({"office_id": office_id, "code": code.strip().upper(), "name": name.strip(), "remarks": remarks.strip() if remarks else None})
        await session.commit(); return RedirectResponse(url="/app/admin/sections?success=Section%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error("/app/admin/sections", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.post("/app/admin/sections/{section_id}/save", include_in_schema=False)
async def update_section_web(
    section_id: int, office_id: Annotated[int, Form()], name: Annotated[str, Form()],
    remarks: Annotated[str | None, Form()] = None, is_active: Annotated[str | None, Form()] = None,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await require_org_user(current_user, session)
        await MasterAdminService(session).update_section(section_id, {"office_id": office_id, "name": name.strip(), "remarks": remarks.strip() if remarks else None, "is_active": is_active == "on"})
        await session.commit(); return RedirectResponse(url="/app/admin/sections?success=Section%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error(f"/app/admin/sections?edit={section_id}", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.get("/app/admin/categories", include_in_schema=False)
async def categories_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_master_user(current_user, session)
    categories = await MasterAdminService(session).list_categories()
    edit_id = request.query_params.get("edit")
    edit_category = await session.get(Category, int(edit_id)) if edit_id else None
    return render(request, "master_categories.html", current_user, categories=categories, edit_category=edit_category)


@router.post("/app/admin/categories/new", include_in_schema=False)
async def create_category_web(code: Annotated[str, Form()], name: Annotated[str, Form()], type: Annotated[str, Form()], description: Annotated[str | None, Form()] = None, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await require_master_user(current_user, session)
        await MasterAdminService(session).create_category({"code": code.strip().upper(), "name": name.strip(), "type": type, "description": description.strip() if description else None})
        await session.commit(); return RedirectResponse(url="/app/admin/categories?success=Category%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error("/app/admin/categories", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.post("/app/admin/categories/{category_id}/save", include_in_schema=False)
async def update_category_web(category_id: int, name: Annotated[str, Form()], type: Annotated[str, Form()], description: Annotated[str | None, Form()] = None, is_active: Annotated[str | None, Form()] = None, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await require_master_user(current_user, session)
        await MasterAdminService(session).update_category(category_id, {"name": name.strip(), "type": type, "description": description.strip() if description else None, "is_active": is_active == "on"})
        await session.commit(); return RedirectResponse(url="/app/admin/categories?success=Category%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error(f"/app/admin/categories?edit={category_id}", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.get("/app/admin/units", include_in_schema=False)
async def units_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_master_user(current_user, session); units = await MasterAdminService(session).list_units()
    edit_id = request.query_params.get("edit")
    edit_unit = await session.get(Unit, int(edit_id)) if edit_id else None
    return render(request, "master_units.html", current_user, units=units, edit_unit=edit_unit)


@router.post("/app/admin/units/new", include_in_schema=False)
async def create_unit_web(code: Annotated[str, Form()], name: Annotated[str, Form()], symbol: Annotated[str | None, Form()] = None, decimal_allowed: Annotated[str | None, Form()] = None, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await require_master_user(current_user, session); await MasterAdminService(session).create_unit({"code": code.strip().upper(), "name": name.strip(), "symbol": symbol.strip() if symbol else None, "decimal_allowed": decimal_allowed == "on"})
        await session.commit(); return RedirectResponse(url="/app/admin/units?success=Unit%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error("/app/admin/units", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.post("/app/admin/units/{unit_id}/save", include_in_schema=False)
async def update_unit_web(unit_id: int, name: Annotated[str, Form()], symbol: Annotated[str | None, Form()] = None, decimal_allowed: Annotated[str | None, Form()] = None, is_active: Annotated[str | None, Form()] = None, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await require_master_user(current_user, session); await MasterAdminService(session).update_unit(unit_id, {"name": name.strip(), "symbol": symbol.strip() if symbol else None, "decimal_allowed": decimal_allowed == "on", "is_active": is_active == "on"})
        await session.commit(); return RedirectResponse(url="/app/admin/units?success=Unit%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error(f"/app/admin/units?edit={unit_id}", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.get("/app/admin/items", include_in_schema=False)
async def admin_items_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_master_user(current_user, session); service=MasterAdminService(session); items=await service.list_items(); categories=await service.list_categories(); units=await service.list_units()
    edit_id=request.query_params.get("edit")
    edit_item=await session.get(Item,int(edit_id)) if edit_id else None
    return render(request, "master_items.html", current_user, items=items, categories=categories, units=units, edit_item=edit_item)


@router.post("/app/admin/items/new", include_in_schema=False)
async def create_item_web(code: Annotated[str, Form()], name: Annotated[str, Form()], category_id: Annotated[int, Form()], unit_id: Annotated[int, Form()], specification: Annotated[str | None, Form()] = None, remarks: Annotated[str | None, Form()] = None, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await require_master_user(current_user, session); await MasterAdminService(session).create_item({"code": code.strip().upper(), "name": name.strip(), "category_id": category_id, "unit_id": unit_id, "specification": specification.strip() if specification else None, "remarks": remarks.strip() if remarks else None})
        await session.commit(); return RedirectResponse(url="/app/admin/items?success=Item%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error("/app/admin/items", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.post("/app/admin/items/{item_id}/save", include_in_schema=False)
async def update_item_web(item_id: int, name: Annotated[str, Form()], category_id: Annotated[int, Form()], unit_id: Annotated[int, Form()], specification: Annotated[str | None, Form()] = None, remarks: Annotated[str | None, Form()] = None, is_active: Annotated[str | None, Form()] = None, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await require_master_user(current_user, session); await MasterAdminService(session).update_item(item_id, {"name": name.strip(), "category_id": category_id, "unit_id": unit_id, "specification": specification.strip() if specification else None, "remarks": remarks.strip() if remarks else None, "is_active": is_active == "on"})
        await session.commit(); return RedirectResponse(url="/app/admin/items?success=Item%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error(f"/app/admin/items?edit={item_id}", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.get("/app/admin/financial-years", include_in_schema=False)
async def financial_years_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_master_user(current_user, session); years=await MasterAdminService(session).list_financial_years()
    edit_id=request.query_params.get("edit")
    edit_year=await session.get(FinancialYear,int(edit_id)) if edit_id else None
    return render(request, "master_financial_years.html", current_user, years=years, edit_year=edit_year)


@router.post("/app/admin/financial-years/new", include_in_schema=False)
async def create_financial_year_web(year_name: Annotated[str, Form()], start_date: Annotated[date, Form()], end_date: Annotated[date, Form()], is_current: Annotated[str | None, Form()] = None, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await require_master_user(current_user, session); await MasterAdminService(session).create_financial_year({"year_name": year_name.strip(), "start_date": start_date, "end_date": end_date, "is_current": is_current == "on"})
        await session.commit(); return RedirectResponse(url="/app/admin/financial-years?success=Financial%20year%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error("/app/admin/financial-years", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.post("/app/admin/financial-years/{fy_id}/save", include_in_schema=False)
async def update_financial_year_web(fy_id: int, start_date: Annotated[date, Form()], end_date: Annotated[date, Form()], is_current: Annotated[str | None, Form()] = None, is_closed: Annotated[str | None, Form()] = None, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    try:
        await require_master_user(current_user, session); await MasterAdminService(session).update_financial_year(fy_id, {"start_date": start_date, "end_date": end_date, "is_current": is_current == "on", "is_closed": is_closed == "on"})
        await session.commit(); return RedirectResponse(url="/app/admin/financial-years?success=Financial%20year%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error(f"/app/admin/financial-years?edit={fy_id}", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.get("/app/admin/policies", include_in_schema=False)
async def policies_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_master_user(current_user, session); service=MasterAdminService(session); policies=await service.list_inventory_policies(); stores=await service.list_stores(); items=await service.list_items()
    edit_id=request.query_params.get("edit")
    edit_policy=await session.get(InventoryPolicy,int(edit_id)) if edit_id else None
    return render(request, "master_policies.html", current_user, policies=policies, stores=stores, items=items, edit_policy=edit_policy)


@router.post("/app/admin/policies/new", include_in_schema=False)
async def create_policy_web(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    form=await request.form()
    try:
        await require_master_user(current_user, session)
        def dec(name):
            value=str(form.get(name) or "").strip()
            return Decimal(value) if value else None
        await MasterAdminService(session).create_inventory_policy({
            "store_id": int(form["store_id"]), "item_id": int(form["item_id"]),
            "reorder_level": dec("reorder_level"), "reorder_quantity": dec("reorder_quantity"),
            "maximum_stock_level": dec("maximum_stock_level"), "low_stock_level": dec("low_stock_level"),
            "issue_method": str(form.get("issue_method") or "NONE"),
            "batch_tracking": form.get("batch_tracking") == "on", "expiry_tracking": form.get("expiry_tracking") == "on",
            "expiry_alert_days": int(form["expiry_alert_days"]) if str(form.get("expiry_alert_days") or "").strip() else None,
            "is_active": True,
        }, current_user.id)
        await session.commit(); return RedirectResponse(url="/app/admin/policies?success=Inventory%20policy%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError, InvalidOperation) as exc:
        await session.rollback(); return redirect_with_error("/app/admin/policies", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.post("/app/admin/policies/{policy_id}/save", include_in_schema=False)
async def update_policy_web(policy_id: int, request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    form=await request.form()
    try:
        await require_master_user(current_user, session)
        def dec(name):
            value=str(form.get(name) or "").strip(); return Decimal(value) if value else None
        await MasterAdminService(session).update_inventory_policy(policy_id, {
            "reorder_level": dec("reorder_level"), "reorder_quantity": dec("reorder_quantity"),
            "maximum_stock_level": dec("maximum_stock_level"), "low_stock_level": dec("low_stock_level"),
            "issue_method": str(form.get("issue_method") or "NONE"),
            "batch_tracking": form.get("batch_tracking") == "on", "expiry_tracking": form.get("expiry_tracking") == "on",
            "expiry_alert_days": int(form["expiry_alert_days"]) if str(form.get("expiry_alert_days") or "").strip() else None,
            "is_active": form.get("is_active") == "on",
        }, current_user.id)
        await session.commit(); return RedirectResponse(url="/app/admin/policies?success=Inventory%20policy%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError, InvalidOperation) as exc:
        await session.rollback(); return redirect_with_error(f"/app/admin/policies?edit={policy_id}", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.get("/app/admin/roles", include_in_schema=False)
async def roles_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_user_admin(current_user, session)
    roles=await MasterAdminService(session).get_roles_permissions()
    return render(request, "master_roles.html", current_user, roles=roles)


@router.get("/app/admin/users", include_in_schema=False)
async def users_page(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_user_admin(current_user, session)
    service=MasterAdminService(session); users=await service.list_users(); offices,stores,sections,roles=await service.user_form_data()
    edit_id=request.query_params.get("edit")
    edit_user=None
    if edit_id:
        edit_user=await session.scalar(select(User).options(selectinload(User.roles), selectinload(User.stores)).where(User.id==int(edit_id)))
    return render(request, "master_users.html", current_user, users=users, offices=offices, stores=stores, sections=sections, roles=roles, edit_user=edit_user)


@router.post("/app/admin/users/new", include_in_schema=False)
async def create_user_web(request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    form=await request.form()
    try:
        await require_user_admin(current_user, session)
        role_ids=[int(x) for x in form.getlist("role_ids")]
        store_ids=[int(x) for x in form.getlist("store_ids")]
        data={"code":str(form["code"]).strip().upper(), "username":str(form["username"]).strip(), "full_name":str(form["full_name"]).strip(), "designation":str(form.get("designation") or "").strip() or None, "office_id":int(form["office_id"]) if form.get("office_id") else None, "section_id":int(form["section_id"]) if form.get("section_id") else None, "email":str(form.get("email") or "").strip() or None, "mobile":str(form.get("mobile") or "").strip() or None, "is_active":True, "remarks":str(form.get("remarks") or "").strip() or None}
        password=str(form.get("password") or "")
        if len(password)<8: raise HTTPException(422,"Password must contain at least 8 characters")
        await MasterAdminService(session).create_user(data, role_ids, store_ids, password)
        await session.commit(); return RedirectResponse(url="/app/admin/users?success=User%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error("/app/admin/users", exc.detail if isinstance(exc, HTTPException) else str(exc))


@router.post("/app/admin/users/{user_id}/save", include_in_schema=False)
async def update_user_web(user_id: int, request: Request, current_user: User | RedirectResponse = Depends(get_web_current_user), session: AsyncSession = Depends(get_db_session)):
    if isinstance(current_user, RedirectResponse): return current_user
    form=await request.form()
    try:
        await require_user_admin(current_user, session)
        role_ids=[int(x) for x in form.getlist("role_ids")]
        store_ids=[int(x) for x in form.getlist("store_ids")]
        data={"full_name":str(form["full_name"]).strip(), "designation":str(form.get("designation") or "").strip() or None, "office_id":int(form["office_id"]) if form.get("office_id") else None, "section_id":int(form["section_id"]) if form.get("section_id") else None, "email":str(form.get("email") or "").strip() or None, "mobile":str(form.get("mobile") or "").strip() or None, "is_active":form.get("is_active")=="on", "remarks":str(form.get("remarks") or "").strip() or None}
        password=str(form.get("password") or "").strip() or None
        if password and len(password)<8: raise HTTPException(422,"Password must contain at least 8 characters")
        await MasterAdminService(session).update_user(user_id,data,role_ids,store_ids,current_user.id,password)
        await session.commit(); return RedirectResponse(url="/app/admin/users?success=User%20saved%20successfully.", status_code=303)
    except (HTTPException, ValueError) as exc:
        await session.rollback(); return redirect_with_error(f"/app/admin/users?edit={user_id}", exc.detail if isinstance(exc,HTTPException) else str(exc))


@router.get("/app/admin/users/{user_id}", include_in_schema=False)
async def user_detail_page(
    request: Request,
    user_id: int,
    current_user: User | RedirectResponse = Depends(get_web_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    if isinstance(current_user, RedirectResponse): return current_user
    await require_user_admin(current_user, session)
    user = await session.scalar(
        select(User)
        .options(selectinload(User.roles), selectinload(User.stores))
        .where(User.id == user_id)
    )
    if user is None:
        raise HTTPException(404, "User not found")
    return render(request, "user_detail.html", current_user, target_user=user)
