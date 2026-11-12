import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.office import Office
from app.models.store import Store
from app.models.user import User
from app.services.master_admin import MasterAdminService
from app.web.routes import grouped_nav


@pytest.mark.asyncio
async def test_paper_warehouse_creation_validation():
    async with AsyncSessionLocal() as session:
        admin_svc = MasterAdminService(session)
        directorate = await session.scalar(select(Office).where(Office.office_type == "DIRECTORATE"))
        press = await session.scalar(select(Office).where(Office.office_type == "BRANCH"))

        # 1. Attempting to create PAPER_WAREHOUSE under DIRECTORATE must be rejected with 422
        with pytest.raises(HTTPException) as exc_info:
            await admin_svc.create_store({
                "office_id": directorate.id,
                "code": "DIR-WH-INVALID",
                "name": "Invalid Directorate Paper Warehouse",
                "store_type": "PAPER_WAREHOUSE",
                "is_primary": False,
            })
        assert exc_info.value.status_code == 422
        assert "Branch office (Press)" in exc_info.value.detail

        # 2. Creating under a Press (Branch) is allowed
        # (Roll back any pending transaction state)
        await session.rollback()


@pytest.mark.asyncio
async def test_grouped_nav_structure_for_different_roles():
    from sqlalchemy.orm import selectinload
    from app.models.role import Role

    async with AsyncSessionLocal() as session:
        user_stmt = select(User).options(selectinload(User.roles).selectinload(Role.permissions))
        admin_user = await session.scalar(user_stmt.where(User.username == "dev_admin"))
        press_head = await session.scalar(user_stmt.where(User.username == "dev_press_head"))
        press_sk = await session.scalar(user_stmt.where(User.username == "dev_press_sk"))
        cp_whman = await session.scalar(user_stmt.where(User.username == "dev_cp_whman"))
        foreman = await session.scalar(user_stmt.where(User.username == "dev_foreman1"))

        # Admin nav
        admin_groups = grouped_nav(admin_user)
        admin_titles = [g["title"] for g in admin_groups if g["title"]]
        assert "Administration" in admin_titles
        assert "Paper Warehouse" in admin_titles

        # Press Head nav (supervises both General Store and Paper Warehouse)
        head_groups = grouped_nav(press_head)
        head_titles = [g["title"] for g in head_groups if g["title"]]
        assert "General Store" in head_titles
        assert "Paper Warehouse" in head_titles
        paper_group = next(g for g in head_groups if g["title"] == "Paper Warehouse")
        paper_links = [link["label"] for link in paper_group["links"]]
        assert "Inter-Press Transfers" in paper_links
        assert "Warehouse Registers" in paper_links

        # Storekeeper nav (General Store ONLY — isolated from Paper Warehouse)
        sk_groups = grouped_nav(press_sk)
        sk_titles = [g["title"] for g in sk_groups if g["title"]]
        assert "General Store" in sk_titles
        assert "Paper Warehouse" not in sk_titles

        # Warehouseman nav (Paper Warehouse ONLY — isolated from General Store)
        assert cp_whman is not None
        wh_groups = grouped_nav(cp_whman)
        wh_titles = [g["title"] for g in wh_groups if g["title"]]
        assert "Paper Warehouse" in wh_titles
        assert "General Store" not in wh_titles

        # Section User nav
        foreman_groups = grouped_nav(foreman)
        foreman_titles = [g["title"] for g in foreman_groups if g["title"]]
        assert "General Store" in foreman_titles
        assert "Administration" not in foreman_titles


@pytest.mark.asyncio
async def test_ui_modernization_web_views(client):
    from app.security.auth import create_access_token
    from sqlalchemy.orm import selectinload
    from app.models.role import Role

    async with AsyncSessionLocal() as session:
        user_stmt = select(User).options(selectinload(User.roles).selectinload(Role.permissions))
        admin = await session.scalar(user_stmt.where(User.username == "dev_admin"))
        press_head = await session.scalar(user_stmt.where(User.username == "dev_press_head"))
        foreman = await session.scalar(user_stmt.where(User.username == "dev_foreman1"))
        cp_whman = await session.scalar(user_stmt.where(User.username == "dev_cp_whman"))

        admin_token = create_access_token(admin)
        press_head_token = create_access_token(press_head)
        foreman_token = create_access_token(foreman)
        whman_token = create_access_token(cp_whman)

    # 1. Admin Stores page shows Paper Warehouse filter and option
    resp = await client.get("/app/admin/stores", cookies={"csms_access_token": admin_token})
    assert resp.status_code == 200
    html = resp.text
    assert "Paper Warehouse (Press)" in html
    assert "📰 Paper Warehouses" in html
    assert "General Stores" in html

    # 1b. Admin Paper Catalog page
    resp_pi = await client.get("/app/admin/paper-items", cookies={"csms_access_token": admin_token})
    assert resp_pi.status_code == 200
    assert "Paper Catalog" in resp_pi.text

    # 2. Admin Users page separates General Stores and Paper Warehouses
    resp = await client.get("/app/admin/users", cookies={"csms_access_token": admin_token})
    assert resp.status_code == 200
    html = resp.text
    assert "📦 General Stores Access" in html
    assert "📰 Paper Warehouses Access" in html

    # 3. Section User dashboard shows the 2-Card Chooser linking to online-indents
    resp = await client.get("/app", cookies={"csms_access_token": foreman_token})
    assert resp.status_code == 200
    html = resp.text
    assert "Request Paper for Print Job" in html
    assert "/app/paper/online-indents/new" in html
    assert "Request General Consumables" in html
    assert "/app/online-indents/new" in html

    # 4. Press Head dashboard shows Executive Approvals Hub
    resp = await client.get("/app", cookies={"csms_access_token": press_head_token})
    assert resp.status_code == 200
    html = resp.text
    assert "Executive Approvals Hub" in html

    # 5. Warehouseman dashboard, Opening Stock, and Registers Hub
    for path in ("/app", "/app/paper/opening-stock", "/app/paper/registers"):
        r_wh = await client.get(path, cookies={"csms_access_token": whman_token})
        assert r_wh.status_code == 200, f"Unexpected {r_wh.status_code} on {path}"

