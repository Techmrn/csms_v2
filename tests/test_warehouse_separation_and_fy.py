"""End-to-end verification of Store vs Paper Warehouse separation, exact Ream+Sheet/KG arithmetic,
Section User paper indents, Warehouseman opening stock, FY closing carry-forward, and isolated registers."""
import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.category import Category
from app.models.financial_year import FinancialYear
from app.models.item import Item
from app.models.office import Office
from app.models.role import Role
from app.models.section import Section
from app.models.stock import OpeningStock, StockMovement
from app.models.store import Store
from app.models.unit import Unit
from app.models.user import User
from app.paper_store.models.item import PaperItem
from app.paper_store.models.stock import PaperOpeningStock
from app.paper_store.schemas.indent_issue import PaperIndentLineCreate, PaperManualIndentCreate
from app.paper_store.schemas.opening import PaperOpeningStockCreate, PaperOpeningStockLineCreate
from app.paper_store.services.indent_issue import PaperIndentIssueService
from app.paper_store.services.opening import PaperOpeningService
from app.paper_store.services.stock import PaperStockService
from app.paper_store.services.units import from_total_sheets
from app.schemas.stock import OpeningStockCreate, OpeningStockLineCreate
from app.security.auth import create_access_token
from app.services.fy_rollover import FinancialYearRolloverService
from app.services.master_admin import MasterAdminService
from app.services.registers import RegisterService
from app.services.stock import StockService


@pytest.mark.asyncio
async def test_storekeeper_blocked_from_paper_and_warehouseman_blocked_from_general_store():
    async with AsyncSessionLocal() as session:
        fy = await session.scalar(select(FinancialYear).where(FinancialYear.is_current.is_(True)))
        press_sk = await session.scalar(select(User).where(User.username == "dev_press_sk"))
        cp_whman = await session.scalar(select(User).where(User.username == "dev_cp_whman"))
        paper_wh = await session.scalar(select(Store).where(Store.code == "PRESS-PAPER-WH"))
        general_store = await session.scalar(select(Store).where(Store.code == "CENTRAL"))
        press_office = await session.scalar(select(Office).where(Office.code == "PRESS"))
        section = await session.scalar(select(Section).where(Section.office_id == press_office.id))
        paper_item = await session.scalar(select(PaperItem).where(PaperItem.is_active.is_(True)).limit(1))
        consumable_item = await session.scalar(
            select(Item)
            .join(Category, Category.id == Item.category_id)
            .where(Category.type == "CONSUMABLE", Item.is_active.is_(True))
            .limit(1)
        )
        assert fy and press_sk and cp_whman and paper_wh and general_store and press_office and section and paper_item and consumable_item

        sk_token = create_access_token(press_sk)
        wh_token = create_access_token(cp_whman)

        # Service-level guard: Storekeeper cannot post General Store opening onto a PAPER_WAREHOUSE
        general_sk = await session.scalar(select(User).where(User.username == "dev_general_sk"))
        stock_svc = StockService(session)
        with pytest.raises(Exception) as exc_store_guard:
            await stock_svc.create_opening(
                OpeningStockCreate(
                    opening_date=date.today(),
                    financial_year_id=fy.id,
                    store_id=paper_wh.id,
                    lines=[
                        OpeningStockLineCreate(
                            item_id=consumable_item.id,
                            quantity=Decimal("10"),
                            unit_id=consumable_item.unit_id,
                        )
                    ],
                ),
                actor_id=general_sk.id,
            )
        assert "403" in str(exc_store_guard.value) or "Paper Warehouse" in str(exc_store_guard.value)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sk_headers = {"Authorization": f"Bearer {sk_token}"}
        wh_headers = {"Authorization": f"Bearer {wh_token}"}

        # 1. Storekeeper blocked (403) from all /api/v1/paper/* write operations
        res_open = await client.post(
            "/api/v1/paper/opening-stocks",
            headers=sk_headers,
            json={
                "store_id": paper_wh.id,
                "financial_year_id": fy.id,
                "opening_date": date.today().isoformat(),
                "lines": [{"paper_item_id": paper_item.id, "reams": 1, "sheets": 0}],
            },
        )
        assert res_open.status_code == 403

        res_rcpt = await client.post(
            "/api/v1/paper/receipts",
            headers=sk_headers,
            json={
                "store_id": paper_wh.id,
                "receipt_date": date.today().isoformat(),
                "financial_year_id": fy.id,
                "source_depot": "Stationery Depot",
                "lines": [{"paper_item_id": paper_item.id, "received_reams": 2, "accepted_reams": 2}],
            },
        )
        assert res_rcpt.status_code == 403

        res_ind = await client.post(
            "/api/v1/paper/indents/manual",
            headers=sk_headers,
            json={
                "store_id": paper_wh.id,
                "section_id": section.id,
                "indent_date": date.today().isoformat(),
                "financial_year_id": fy.id,
                "lines": [{"paper_item_id": paper_item.id, "requested_reams": 1, "issued_reams": 1}],
            },
        )
        assert res_ind.status_code == 403

        bp_wh_resp = None
        async with AsyncSessionLocal() as s2:
            bp_wh = await s2.scalar(select(Store).where(Store.code == "BP-PAPER-WH"))
            bp_wh_resp = bp_wh.id

        res_trf = await client.post(
            "/api/v1/paper/transfers",
            headers=sk_headers,
            json={
                "source_store_id": bp_wh_resp,
                "destination_store_id": paper_wh.id,
                "transfer_date": date.today().isoformat(),
                "financial_year_id": fy.id,
                "transfer_mode": "PULL",
                "lines": [{"paper_item_id": paper_item.id, "requested_reams": 1}],
            },
        )
        assert res_trf.status_code == 403

        # Storekeeper blocked from /app/paper/* create pages (redirected with error)
        for path in ("/app/paper/opening-stock/new", "/app/paper/receipts/new", "/app/paper/indents/new"):
            r_web = await client.get(path, cookies={"csms_access_token": sk_token}, follow_redirects=False)
            assert r_web.status_code == 303

        # 2. Warehouseman blocked (403) from General Store endpoints
        r_gen_ind = await client.post(
            "/api/indents",
            headers=wh_headers,
            json={
                "indent_date": date.today().isoformat(),
                "financial_year_id": fy.id,
                "store_id": general_store.id,
                "office_id": press_office.id,
                "section_id": section.id,
                "lines": [{"item_id": consumable_item.id, "requested_quantity": "1"}],
            },
        )
        assert r_gen_ind.status_code == 403

        r_gen_rcpt = await client.post(
            "/api/receipts",
            headers=wh_headers,
            json={
                "receipt_date": date.today().isoformat(),
                "financial_year_id": fy.id,
                "store_id": general_store.id,
                "supplier_name": "Test Supplier",
                "lines": [
                    {
                        "item_id": consumable_item.id,
                        "received_quantity": "5",
                        "accepted_quantity": "5",
                        "rejected_quantity": "0",
                        "unit_id": consumable_item.unit_id,
                    }
                ],
            },
        )
        assert r_gen_rcpt.status_code == 403

        r_gen_open = await client.post(
            "/api/stock/openings/manual",
            headers=wh_headers,
            json={
                "opening_date": date.today().isoformat(),
                "financial_year_id": fy.id,
                "store_id": general_store.id,
                "lines": [
                    {
                        "item_id": consumable_item.id,
                        "quantity": "5",
                        "unit_id": consumable_item.unit_id,
                    }
                ],
            },
        )
        assert r_gen_open.status_code == 403


@pytest.mark.asyncio
async def test_paper_reams_sheets_and_reel_kg_opening_and_issue():
    suffix = uuid.uuid4().hex[:6]
    async with AsyncSessionLocal() as session:
        fy = await session.scalar(select(FinancialYear).where(FinancialYear.is_current.is_(True)))
        cp_whman = await session.scalar(select(User).where(User.username == "dev_cp_whman"))
        paper_wh = await session.scalar(select(Store).where(Store.code == "PRESS-PAPER-WH"))
        section = await session.scalar(select(Section).where(Section.office_id == paper_wh.office_id))
        unit_ream = await session.scalar(select(Unit).where(Unit.code == "REAM"))
        unit_kg = await session.scalar(select(Unit).where(Unit.code == "KG")) or unit_ream

        sheet_item = PaperItem(
            code=f"PPR-SH-{suffix}",
            name=f"Exact Sheet Paper {suffix}",
            paper_type="Maplitho",
            form_type="SHEET",
            gsm=80,
            sheets_per_ream=500,
            weight_per_ream_kg=Decimal("20.000"),
            unit_id=unit_ream.id,
            is_active=True,
        )
        reel_item = PaperItem(
            code=f"PPR-RL-{suffix}",
            name=f"Exact Reel Newsprint {suffix}",
            paper_type="Newsprint",
            form_type="REEL",
            gsm=48,
            sheets_per_ream=500,
            unit_id=unit_kg.id,
            is_active=True,
        )
        session.add_all([sheet_item, reel_item])
        await session.flush()

        # First-time opening stock by Warehouseman (no Branch Head approval required)
        open_svc = PaperOpeningService(session)
        opening = await open_svc.create_and_post(
            PaperOpeningStockCreate(
                store_id=paper_wh.id,
                financial_year_id=fy.id,
                opening_date=fy.start_date,
                remarks="First-time warehouse setup",
                lines=[
                    PaperOpeningStockLineCreate(
                        paper_item_id=sheet_item.id,
                        unit_id=unit_ream.id,
                        reams=10,
                        sheets=250,
                    ),
                    PaperOpeningStockLineCreate(
                        paper_item_id=reel_item.id,
                        unit_id=unit_kg.id,
                        weight_kg=Decimal("500.500"),
                        reel_count=2,
                    ),
                ],
            ),
            actor_id=cp_whman.id,
        )
        assert opening.status == "POSTED"
        assert opening.opening_type == "INITIAL"

        # Duplicate opening on same warehouse + FY + item must be rejected (409)
        with pytest.raises(Exception) as exc_dup:
            await open_svc.create_and_post(
                PaperOpeningStockCreate(
                    store_id=paper_wh.id,
                    financial_year_id=fy.id,
                    opening_date=fy.start_date,
                    lines=[PaperOpeningStockLineCreate(paper_item_id=sheet_item.id, unit_id=unit_ream.id, reams=1)],
                ),
                actor_id=cp_whman.id,
            )
        assert "409" in str(exc_dup.value) or "already exists" in str(exc_dup.value)

        # Issue 3 Reams 400 Sheets (= 1900 sheets) and 125.250 KG Reel
        ind_svc = PaperIndentIssueService(session)
        await ind_svc.create_manual_indent_and_issue(
            PaperManualIndentCreate(
                store_id=paper_wh.id,
                section_id=section.id,
                indent_date=date.today(),
                financial_year_id=fy.id,
                job_no=f"JOB-EXACT-{suffix}",
                lines=[
                    PaperIndentLineCreate(
                        paper_item_id=sheet_item.id,
                        unit_id=unit_ream.id,
                        requested_reams=3,
                        requested_sheets=400,
                        issued_reams=3,
                        issued_sheets=400,
                    ),
                    PaperIndentLineCreate(
                        paper_item_id=reel_item.id,
                        unit_id=unit_kg.id,
                        requested_quantity=Decimal("125.250"),
                        issued_quantity=Decimal("125.250"),
                        weight_kg=Decimal("125.250"),
                    ),
                ],
            ),
            actor_id=cp_whman.id,
        )

        # 10R 250S (5250) - 3R 400S (1900) = 3350 sheets = 6 Reams 350 Sheets
        stock_svc = PaperStockService(session)
        sh_bal, _ = await stock_svc.balance_for_item(paper_wh.id, fy.id, sheet_item.id)
        assert sh_bal == 3350
        assert from_total_sheets(sh_bal, 500) == (6, 350)

        rl_sh, rl_wt = await stock_svc.balance_for_item(paper_wh.id, fy.id, reel_item.id)
        assert rl_sh == 0
        assert rl_wt == Decimal("375.250")

        overview = await stock_svc.current_stock(paper_wh.id, fy.id)
        row_sh = next(r for r in overview if r["item"].id == sheet_item.id)
        assert row_sh["formatted_opening"] == "10 Reams 250 Sheets"
        assert row_sh["formatted_outward"] == "3 Reams 400 Sheets"
        assert row_sh["formatted_balance"] == "6 Reams 350 Sheets"


@pytest.mark.asyncio
async def test_section_user_online_paper_indent_and_warehouseman_issue():
    suffix = uuid.uuid4().hex[:6]
    async with AsyncSessionLocal() as session:
        fy = await session.scalar(select(FinancialYear).where(FinancialYear.is_current.is_(True)))
        cp_whman = await session.scalar(select(User).where(User.username == "dev_cp_whman"))
        foreman = await session.scalar(select(User).where(User.username == "dev_foreman1"))
        paper_wh = await session.scalar(select(Store).where(Store.code == "PRESS-PAPER-WH"))
        unit_ream = await session.scalar(select(Unit).where(Unit.code == "REAM"))
        sec_role = await session.scalar(
            select(Role).options(selectinload(Role.permissions)).where(Role.code == "SECTION_USER")
        )
        sec_perms = {p.code for p in sec_role.permissions}
        assert "PAPER_VIEW" in sec_perms and "PAPER_INDENT_CREATE" in sec_perms

        paper_item = PaperItem(
            code=f"PPR-ONL-{suffix}",
            name=f"Online Request Paper {suffix}",
            paper_type="Maplitho",
            form_type="SHEET",
            gsm=75,
            sheets_per_ream=500,
            unit_id=unit_ream.id,
            is_active=True,
        )
        session.add(paper_item)
        await session.flush()

        await PaperOpeningService(session).create_and_post(
            PaperOpeningStockCreate(
                store_id=paper_wh.id,
                financial_year_id=fy.id,
                opening_date=fy.start_date,
                lines=[PaperOpeningStockLineCreate(paper_item_id=paper_item.id, unit_id=unit_ream.id, reams=5, sheets=0)],
            ),
            actor_id=cp_whman.id,
        )
        foreman_token = create_access_token(foreman)
        wh_token = create_access_token(cp_whman)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Section user creates online paper request
        r_req_get = await client.get("/app/paper/online-indents/new", cookies={"csms_access_token": foreman_token})
        assert r_req_get.status_code == 200

        r_req_post = await client.post(
            "/app/paper/online-indents/new",
            cookies={"csms_access_token": foreman_token},
            data={
                "store_id": str(paper_wh.id),
                "indent_date": date.today().isoformat(),
                "financial_year_id": str(fy.id),
                "job_no": f"JOB-ONL-{suffix}",
                "remarks": "Need paper for offset press",
                "paper_item_id": [str(paper_item.id)],
                "requested_reams": ["2"],
                "requested_sheets": ["100"],
                "weight_kg": ["0"],
            },
            follow_redirects=False,
        )
        assert r_req_post.status_code == 303
        indent_url = r_req_post.headers["location"]
        assert "/app/paper/indents/" in indent_url

        # Warehouseman opens online request & fulfills 1 Ream 300 Sheets (= 800 sheets)
        r_wh_view = await client.get(indent_url, cookies={"csms_access_token": wh_token})
        assert r_wh_view.status_code == 200
        assert "Approve &amp; Issue Paper Stock" in r_wh_view.text

        indent_id = int(indent_url.split("?")[0].rstrip("/").split("/")[-1])
        async with AsyncSessionLocal() as s2:
            ind_obj = await PaperIndentIssueService(s2).get_indent(indent_id)
            assert ind_obj.request_source == "ONLINE"
            assert ind_obj.status == "SUBMITTED"
            line_id = ind_obj.lines[0].id

        r_issue = await client.post(
            f"/app/paper/indents/{indent_id}/issue",
            cookies={"csms_access_token": wh_token},
            data={
                "issue_date": date.today().isoformat(),
                "remarks": "Issued partial quantity",
                "indent_line_id": [str(line_id)],
                "issued_reams": ["1"],
                "issued_sheets": ["300"],
                "weight_kg": ["0"],
                "line_remarks": ["Partial batch"],
            },
            follow_redirects=False,
        )
        assert r_issue.status_code == 303

    async with AsyncSessionLocal() as s3:
        final_ind = await PaperIndentIssueService(s3).get_indent(indent_id)
        assert final_ind.status == "FINALIZED"
        assert final_ind.issue is not None
        sh_left, _ = await PaperStockService(s3).balance_for_item(paper_wh.id, fy.id, paper_item.id)
        # 5 Reams (2500) - 1 Ream 300 Sheets (800) = 1700 sheets = 3 Reams 200 Sheets
        assert sh_left == 1700
        assert from_total_sheets(sh_left, 500) == (3, 200)


@pytest.mark.asyncio
async def test_fy_close_carries_forward_both_general_store_and_paper_warehouse():
    suffix = uuid.uuid4().hex[:5]
    async with AsyncSessionLocal() as session:
        max_end = await session.scalar(select(FinancialYear.end_date).order_by(FinancialYear.end_date.desc()).limit(1))
        src_start = max_end + timedelta(days=1)
        src_end = src_start + timedelta(days=364)
        dst_start = src_end + timedelta(days=1)
        dst_end = dst_start + timedelta(days=364)

        src_fy = FinancialYear(
            year_name=f"FY-SRC-{suffix}",
            start_date=src_start,
            end_date=src_end,
            is_current=False,
            is_closed=False,
        )
        dst_fy = FinancialYear(
            year_name=f"FY-DST-{suffix}",
            start_date=dst_start,
            end_date=dst_end,
            is_current=False,
            is_closed=False,
        )
        session.add_all([src_fy, dst_fy])
        await session.flush()

        admin = await session.scalar(select(User).where(User.username == "dev_admin"))
        general_sk = await session.scalar(select(User).where(User.username == "dev_general_sk"))
        cp_whman = await session.scalar(select(User).where(User.username == "dev_cp_whman"))
        bp_whman = await session.scalar(select(User).where(User.username == "dev_bp_whman"))
        central_store = await session.scalar(select(Store).where(Store.code == "CENTRAL"))
        cp_wh = await session.scalar(select(Store).where(Store.code == "PRESS-PAPER-WH"))
        bp_wh = await session.scalar(select(Store).where(Store.code == "BP-PAPER-WH"))
        unit_ream = await session.scalar(select(Unit).where(Unit.code == "REAM"))
        unit_kg = await session.scalar(select(Unit).where(Unit.code == "KG")) or unit_ream
        cons_cat = await session.scalar(select(Category).where(Category.type == "CONSUMABLE").limit(1))

        # Unique consumable item + Sheet paper + Reel paper
        cons_item = Item(
            code=f"CONS-FY-{suffix}",
            name=f"FY Rollover Consumable {suffix}",
            category_id=cons_cat.id,
            unit_id=unit_ream.id,
            is_active=True,
        )
        sheet_item = PaperItem(
            code=f"PPR-FY-SH-{suffix}",
            name=f"FY Rollover Sheet {suffix}",
            paper_type="Maplitho",
            form_type="SHEET",
            gsm=70,
            sheets_per_ream=500,
            unit_id=unit_ream.id,
            is_active=True,
        )
        reel_item = PaperItem(
            code=f"PPR-FY-RL-{suffix}",
            name=f"FY Rollover Reel {suffix}",
            paper_type="Newsprint",
            form_type="REEL",
            gsm=45,
            sheets_per_ream=500,
            unit_id=unit_kg.id,
            is_active=True,
        )
        session.add_all([cons_item, sheet_item, reel_item])
        await session.flush()

        # Post opening stocks in src_fy across General Store AND both Press Paper Warehouses
        await StockService(session).create_and_post_opening(
            OpeningStockCreate(
                opening_date=src_start,
                financial_year_id=src_fy.id,
                store_id=central_store.id,
                lines=[
                    OpeningStockLineCreate(
                        item_id=cons_item.id,
                        quantity=Decimal("25.500"),
                        unit_id=unit_ream.id,
                    )
                ],
            ),
            actor_id=general_sk.id,
        )
        await PaperOpeningService(session).create_and_post(
            PaperOpeningStockCreate(
                store_id=cp_wh.id,
                financial_year_id=src_fy.id,
                opening_date=src_start,
                lines=[
                    PaperOpeningStockLineCreate(paper_item_id=sheet_item.id, unit_id=unit_ream.id, reams=4, sheets=120),
                    PaperOpeningStockLineCreate(paper_item_id=reel_item.id, unit_id=unit_kg.id, weight_kg=Decimal("88.500")),
                ],
            ),
            actor_id=cp_whman.id,
        )
        await PaperOpeningService(session).create_and_post(
            PaperOpeningStockCreate(
                store_id=bp_wh.id,
                financial_year_id=src_fy.id,
                opening_date=src_start,
                lines=[
                    PaperOpeningStockLineCreate(paper_item_id=sheet_item.id, unit_id=unit_ream.id, reams=2, sheets=50),
                ],
            ),
            actor_id=bp_whman.id,
        )

        # Close src_fy -> triggers automatic carry-forward into dst_fy!
        master = MasterAdminService(session)
        await master.update_financial_year(src_fy.id, {"is_closed": True}, actor_id=admin.id)
        await session.commit()

        # Verify General Store consumable carry-forward in dst_fy
        gen_dst_bal = await StockService(session).current_balance(central_store.id, dst_fy.id, cons_item.id)
        assert gen_dst_bal == Decimal("25.500")
        gen_op = await session.scalar(
            select(OpeningStock).where(
                OpeningStock.store_id == central_store.id,
                OpeningStock.financial_year_id == dst_fy.id,
                OpeningStock.opening_type == "CARRY_FORWARD",
            )
        )
        assert gen_op is not None and gen_op.source_financial_year_id == src_fy.id

        # Verify Paper Warehouse carry-forward in BOTH Central Press & Branch Press (treated equally!)
        cp_sh, cp_wt = await PaperStockService(session).balance_for_item(cp_wh.id, dst_fy.id, sheet_item.id)
        assert cp_sh == 4 * 500 + 120
        _, cp_reel_wt = await PaperStockService(session).balance_for_item(cp_wh.id, dst_fy.id, reel_item.id)
        assert cp_reel_wt == Decimal("88.500")

        bp_sh, _ = await PaperStockService(session).balance_for_item(bp_wh.id, dst_fy.id, sheet_item.id)
        assert bp_sh == 2 * 500 + 50

        # Idempotency check: re-running carry_forward returns zero new documents
        second = await FinancialYearRolloverService(session).carry_forward(src_fy.id, dst_fy.id, admin.id)
        assert second == {"general_items_carried": 0, "paper_items_carried": 0}


@pytest.mark.asyncio
async def test_paper_registers_and_general_register_separation():
    async with AsyncSessionLocal() as session:
        cp_whman = await session.scalar(select(User).where(User.username == "dev_cp_whman"))
        general_sk = await session.scalar(select(User).where(User.username == "dev_general_sk"))
        paper_wh = await session.scalar(select(Store).where(Store.code == "PRESS-PAPER-WH"))
        fy = await session.scalar(select(FinancialYear).where(FinancialYear.is_current.is_(True)))

        # General RegisterService strictly rejects PAPER_WAREHOUSE store_id
        gen_reg = RegisterService(session)
        with pytest.raises(Exception) as exc_gen:
            await gen_reg.transaction_register(general_sk.id, store_id=paper_wh.id, financial_year_id=fy.id)
        assert "403" in str(exc_gen.value) or "Paper Warehouse" in str(exc_gen.value)

        wh_token = create_access_token(cp_whman)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"csms_access_token": wh_token},
    ) as client:
        for kind in ("stock", "receipts", "issues", "transfers", "opening", "ledger"):
            r_html = await client.get(
                f"/app/paper/registers/{kind}?store_id={paper_wh.id}&financial_year_id={fy.id}"
            )
            assert r_html.status_code == 200, f"Paper register HTML failed for {kind}"

            r_pdf = await client.get(
                f"/app/paper/registers/{kind}.pdf?store_id={paper_wh.id}&financial_year_id={fy.id}"
            )
            assert r_pdf.status_code == 200, f"Paper register PDF failed for {kind}"
            assert r_pdf.headers.get("content-type", "").startswith("application/pdf")
            assert r_pdf.content.startswith(b"%PDF")
