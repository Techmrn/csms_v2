import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.financial_year import FinancialYear
from app.models.office import Office
from app.models.section import Section
from app.models.store import Store
from app.models.unit import Unit
from app.models.user import User, user_stores, user_roles
from app.models.role import Role
from app.paper_store.models.indent_issue import PaperIndent, PaperIssue
from app.paper_store.models.item import PaperItem
from app.paper_store.models.stock import PaperStockMovement
from app.paper_store.models.transfer import PaperTransfer
from app.paper_store.schemas.indent_issue import (
    PaperIndentLineCreate,
    PaperManualIndentCreate,
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
from app.paper_store.services.receipt import PaperReceiptService
from app.paper_store.services.stock import PaperStockService
from app.paper_store.services.transfer import PaperTransferService
from app.security.auth import create_access_token


@pytest.mark.asyncio
async def test_paper_section_issue_workflow():
    suffix = uuid.uuid4().hex[:6]
    async with AsyncSessionLocal() as session:
        fy = await session.scalar(select(FinancialYear).where(FinancialYear.is_current.is_(True)))
        press_office = await session.scalar(select(Office).where(Office.code == "PRESS"))
        paper_store = await session.scalar(select(Store).where(Store.code == "PRESS-PAPER-WH"))
        section = await session.scalar(select(Section).where(Section.office_id == press_office.id))
        unit_ream = await session.scalar(select(Unit).where(Unit.code == "REAM"))
        press_sk = await session.scalar(select(User).where(User.username == "dev_cp_whman"))

        # Create paper item
        paper_item = PaperItem(
            code=f"PPR-SEC-{suffix}",
            name=f"Maplitho for Section {suffix}",
            paper_type="Maplitho",
            form_type="SHEET",
            gsm=70,
            length_cm=Decimal("58.5"),
            width_cm=Decimal("91.0"),
            unit_id=unit_ream.id,
            weight_per_ream_kg=Decimal("18.632"),
            is_active=True,
        )
        session.add(paper_item)
        await session.flush()

        # Inward 100 reams first via Stationery Receipt
        receipt_svc = PaperReceiptService(session)
        receipt_payload = PaperReceiptCreate(
            store_id=paper_store.id,
            financial_year_id=fy.id,
            receipt_date=date.today(),
            source_depot="Govt Central Stationery Depot",
            challan_no=f"DC-SEC-{suffix}",
            challan_date=date.today(),
            lines=[
                PaperReceiptLineCreate(
                    paper_item_id=paper_item.id,
                    unit_id=unit_ream.id,
                    challan_quantity=Decimal("100"),
                    received_quantity=Decimal("100"),
                    accepted_quantity=Decimal("100"),
                    weight_kg=Decimal("1863.200"),
                )
            ],
        )
        await receipt_svc.create_and_post(receipt_payload, actor_id=press_sk.id)

        # Issue 30 reams to press section for Job #JOB-882
        indent_svc = PaperIndentIssueService(session)
        issue_payload = PaperManualIndentCreate(
            store_id=paper_store.id,
            section_id=section.id,
            indent_date=date.today(),
            financial_year_id=fy.id,
            job_no=f"JOB-882-{suffix}",
            remarks="Issue to machine section for school textbook printing",
            lines=[
                PaperIndentLineCreate(
                    paper_item_id=paper_item.id,
                    unit_id=unit_ream.id,
                    requested_quantity=Decimal("30"),
                    issued_quantity=Decimal("30"),
                    weight_kg=Decimal("558.960"),
                )
            ],
        )
        indent, issue = await indent_svc.create_manual_indent_and_issue(issue_payload, actor_id=press_sk.id)

        assert indent.id is not None
        assert indent.indent_no.startswith("PIN-")
        assert indent.status == "FINALIZED"
        assert issue.issue_no.startswith("PIS-")
        assert issue.status == "FINALIZED"

        # Check stock movement OUT
        movements = list(
            (
                await session.scalars(
                    select(PaperStockMovement).where(
                        PaperStockMovement.reference_type == "PAPER_ISSUE",
                        PaperStockMovement.reference_id == issue.id,
                    )
                )
            ).all()
        )
        assert len(movements) == 1
        assert movements[0].movement_type == "ISSUE_SECTION"
        assert movements[0].quantity_out == Decimal("30.000")
        assert movements[0].weight_kg_out == Decimal("558.960")

        # Balance check: 100 - 30 = 70 reams
        stock_svc = PaperStockService(session)
        bal_qty, bal_wt = await stock_svc.balance_for_item(paper_store.id, fy.id, paper_item.id)
        assert bal_qty == 70 * 500
        assert bal_wt == Decimal("1304.240")


@pytest.mark.asyncio
async def test_paper_section_insufficient_stock_rejection():
    suffix = uuid.uuid4().hex[:6]
    async with AsyncSessionLocal() as session:
        fy = await session.scalar(select(FinancialYear).where(FinancialYear.is_current.is_(True)))
        press_office = await session.scalar(select(Office).where(Office.code == "PRESS"))
        paper_store = await session.scalar(select(Store).where(Store.code == "PRESS-PAPER-WH"))
        section = await session.scalar(select(Section).where(Section.office_id == press_office.id))
        unit_ream = await session.scalar(select(Unit).where(Unit.code == "REAM"))
        press_sk = await session.scalar(select(User).where(User.username == "dev_cp_whman"))

        paper_item = PaperItem(
            code=f"PPR-OOS-{suffix}",
            name=f"Out of Stock Paper {suffix}",
            paper_type="Maplitho",
            form_type="SHEET",
            gsm=70,
            unit_id=unit_ream.id,
            is_active=True,
        )
        session.add(paper_item)
        await session.flush()

        indent_svc = PaperIndentIssueService(session)
        payload = PaperManualIndentCreate(
            store_id=paper_store.id,
            section_id=section.id,
            indent_date=date.today(),
            financial_year_id=fy.id,
            lines=[
                PaperIndentLineCreate(
                    paper_item_id=paper_item.id,
                    unit_id=unit_ream.id,
                    requested_quantity=Decimal("50"),
                    issued_quantity=Decimal("50"),
                )
            ],
        )
        with pytest.raises(Exception) as exc_info:
            await indent_svc.create_manual_indent_and_issue(payload, actor_id=press_sk.id)
        assert "Insufficient stock" in str(exc_info.value)


@pytest.mark.asyncio
async def test_inter_press_transfer_directorate_push_directive():
    """Validates that Directorate can initiate a Push Directive between Press A and Press B without owning stock."""
    suffix = uuid.uuid4().hex[:6]
    async with AsyncSessionLocal() as session:
        fy = await session.scalar(select(FinancialYear).where(FinancialYear.is_current.is_(True)))
        press1_store = await session.scalar(select(Store).where(Store.code == "PRESS-PAPER-WH"))
        press2_store = await session.scalar(select(Store).where(Store.code == "BP-PAPER-WH"))
        unit_ream = await session.scalar(select(Unit).where(Unit.code == "REAM"))
        director = await session.scalar(select(User).where(User.username == "dev_director"))
        press_sk = await session.scalar(select(User).where(User.username == "dev_cp_whman"))

        assert press1_store and press2_store and director and press_sk

        # Paper item
        paper_item = PaperItem(
            code=f"PPR-TRF-{suffix}",
            name=f"Inter-Press Paper {suffix}",
            paper_type="Maplitho",
            form_type="SHEET",
            gsm=80,
            unit_id=unit_ream.id,
            weight_per_ream_kg=Decimal("21.294"),
            is_active=True,
        )
        session.add(paper_item)
        await session.flush()

        # Inward 200 reams to Press 1
        rcpt_svc = PaperReceiptService(session)
        await rcpt_svc.create_and_post(
            PaperReceiptCreate(
                store_id=press1_store.id,
                financial_year_id=fy.id,
                receipt_date=date.today(),
                source_depot="Stationery Depot",
                challan_no=f"DC-TRF-{suffix}",
                lines=[
                    PaperReceiptLineCreate(
                        paper_item_id=paper_item.id,
                        unit_id=unit_ream.id,
                        challan_quantity=Decimal("200"),
                        received_quantity=Decimal("200"),
                        accepted_quantity=Decimal("200"),
                        weight_kg=Decimal("4258.800"),
                    )
                ],
            ),
            actor_id=press_sk.id,
        )

        # 1. Directorate initiates Push Directive: Command Press 1 to transfer 80 reams to Press 2
        trf_svc = PaperTransferService(session)
        transfer_payload = PaperTransferCreateRequest(
            source_store_id=press1_store.id,
            destination_store_id=press2_store.id,
            transfer_date=date.today(),
            financial_year_id=fy.id,
            transfer_mode="PUSH",
            remarks="Directorate directive: Urgent paper diversion for textbook printing",
            lines=[
                PaperTransferLineCreate(
                    paper_item_id=paper_item.id,
                    unit_id=unit_ream.id,
                    requested_quantity=Decimal("80"),
                )
            ],
        )
        transfer = await trf_svc.create(transfer_payload, actor_id=director.id)
        assert transfer.id is not None
        assert transfer.transfer_no.startswith("PTR-")
        assert transfer.transfer_mode == "PUSH"
        assert transfer.status == "DIRECTORATE_DIRECTIVE"

        # 2. Press 1 Warehouse Keeper dispatches the paper with Gate Pass
        dispatch_payload = PaperTransferDispatchRequest(
            vehicle_no="KL-01-AB-9999",
            driver_name="Ramesh",
            carrier_name="Kerala Govt Transport",
            gate_pass_no=f"GP-TRF-{suffix}",
            remarks="Dispatched in lorry covered by tarpaulin",
            lines=[
                PaperTransferDispatchLine(
                    line_id=transfer.lines[0].id,
                    dispatch_quantity=Decimal("80"),
                    weight_kg=Decimal("1703.520"),
                )
            ],
        )
        dispatched_transfer = await trf_svc.dispatch(transfer.id, dispatch_payload, actor_id=press_sk.id)
        assert dispatched_transfer.status == "DISPATCHED"
        assert dispatched_transfer.vehicle_no == "KL-01-AB-9999"

        # Press 1 balance should now be 200 - 80 = 120 reams
        stock_svc = PaperStockService(session)
        p1_qty, _ = await stock_svc.balance_for_item(press1_store.id, fy.id, paper_item.id)
        assert p1_qty == 120 * 500

        # Create storekeeper for Press 2
        role_sk = await session.scalar(select(Role).where(Role.code == "WAREHOUSEMAN"))
        press2_sk = User(
            code=f"SK-P2-{suffix}",
            username=f"dev_press2_sk_{suffix}",
            password_hash="test",
            full_name=f"Press 2 Storekeeper {suffix}",
            office_id=press2_store.office_id,
            is_active=True,
        )
        session.add(press2_sk)
        await session.flush()
        await session.execute(user_roles.insert().values(user_id=press2_sk.id, role_id=role_sk.id))
        await session.execute(user_stores.insert().values(user_id=press2_sk.id, store_id=press2_store.id, is_primary=True))
        await session.flush()

        # 3. Destination Press receives 80 reams in full
        receive_payload = PaperTransferReceiveRequest(
            remarks="Received all 80 reams in sound condition",
            lines=[
                PaperTransferReceiveLine(
                    line_id=transfer.lines[0].id,
                    received_quantity=Decimal("80"),
                    weight_kg=Decimal("1703.520"),
                )
            ],
        )
        received_transfer = await trf_svc.receive(transfer.id, receive_payload, actor_id=press2_sk.id)
        assert received_transfer.status == "RECEIVED"

        # Press 2 balance should now be 80 reams
        p2_qty, _ = await stock_svc.balance_for_item(press2_store.id, fy.id, paper_item.id)
        assert p2_qty == 80 * 500


@pytest.mark.asyncio
async def test_inter_press_transfer_discrepancy():
    """Validates that a shortage during receipt flags DISCREPANCY status."""
    suffix = uuid.uuid4().hex[:6]
    async with AsyncSessionLocal() as session:
        fy = await session.scalar(select(FinancialYear).where(FinancialYear.is_current.is_(True)))
        press1_store = await session.scalar(select(Store).where(Store.code == "PRESS-PAPER-WH"))
        press2_store = await session.scalar(select(Store).where(Store.code == "BP-PAPER-WH"))
        unit_ream = await session.scalar(select(Unit).where(Unit.code == "REAM"))
        director = await session.scalar(select(User).where(User.username == "dev_director"))
        press_sk = await session.scalar(select(User).where(User.username == "dev_cp_whman"))

        paper_item = PaperItem(
            code=f"PPR-DISC-{suffix}",
            name=f"Discrepancy Test Paper {suffix}",
            paper_type="Maplitho",
            form_type="SHEET",
            gsm=70,
            unit_id=unit_ream.id,
            is_active=True,
        )
        session.add(paper_item)
        await session.flush()

        # Inward 50 reams to Press 1
        rcpt_svc = PaperReceiptService(session)
        await rcpt_svc.create_and_post(
            PaperReceiptCreate(
                store_id=press1_store.id,
                financial_year_id=fy.id,
                receipt_date=date.today(),
                source_depot="Stationery Depot",
                lines=[
                    PaperReceiptLineCreate(
                        paper_item_id=paper_item.id,
                        unit_id=unit_ream.id,
                        challan_quantity=Decimal("50"),
                        received_quantity=Decimal("50"),
                        accepted_quantity=Decimal("50"),
                    )
                ],
            ),
            actor_id=press_sk.id,
        )

        trf_svc = PaperTransferService(session)
        transfer = await trf_svc.create(
            PaperTransferCreateRequest(
                source_store_id=press1_store.id,
                destination_store_id=press2_store.id,
                transfer_date=date.today(),
                transfer_mode="PUSH",
                lines=[
                    PaperTransferLineCreate(
                        paper_item_id=paper_item.id,
                        unit_id=unit_ream.id,
                        requested_quantity=Decimal("50"),
                    )
                ],
            ),
            actor_id=director.id,
        )

        # Dispatch 50 reams
        await trf_svc.dispatch(
            transfer.id,
            PaperTransferDispatchRequest(
                vehicle_no="KL-01-AB-1111",
                lines=[PaperTransferDispatchLine(line_id=transfer.lines[0].id, dispatch_quantity=Decimal("50"))],
            ),
            actor_id=press_sk.id,
        )

        # Create storekeeper for Press 2
        role_sk = await session.scalar(select(Role).where(Role.code == "WAREHOUSEMAN"))
        press2_sk = User(
            code=f"SK-P2-D-{suffix}",
            username=f"dev_press2_sk_d_{suffix}",
            password_hash="test",
            full_name=f"Press 2 Storekeeper {suffix}",
            office_id=press2_store.office_id,
            is_active=True,
        )
        session.add(press2_sk)
        await session.flush()
        await session.execute(user_roles.insert().values(user_id=press2_sk.id, role_id=role_sk.id))
        await session.execute(user_stores.insert().values(user_id=press2_sk.id, store_id=press2_store.id, is_primary=True))
        await session.flush()

        # Destination only receives 48 reams (2 reams lost/damaged in transit)
        received_transfer = await trf_svc.receive(
            transfer.id,
            PaperTransferReceiveRequest(
                remarks="2 reams water damaged during transit",
                lines=[PaperTransferReceiveLine(line_id=transfer.lines[0].id, received_quantity=Decimal("48"))],
            ),
            actor_id=press2_sk.id,
        )
        assert received_transfer.status == "DISCREPANCY"


@pytest.mark.asyncio
async def test_paper_web_ui_indents_and_transfers_flow():
    async with AsyncSessionLocal() as session:
        press_sk = await session.scalar(select(User).where(User.username == "dev_cp_whman"))
        director = await session.scalar(select(User).where(User.username == "dev_director"))
        press1_store = await session.scalar(select(Store).where(Store.code == "PRESS-PAPER-WH"))
        press2_store = await session.scalar(select(Store).where(Store.code == "BP-PAPER-WH"))
        section = await session.scalar(select(Section).where(Section.office_id == press1_store.office_id))
        paper_item = await session.scalar(select(PaperItem).limit(1))
        unit = await session.scalar(select(Unit).where(Unit.code == "REAM"))

        wh_token = create_access_token(press_sk)
        dir_token = create_access_token(director)

    # 1. Warehouseman issues paper to section via web form
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"csms_access_token": wh_token},
    ) as client:
        res_get_indent = await client.get("/app/paper/indents/new")
        assert res_get_indent.status_code == 200
        assert "Issue Paper to Press Section" in res_get_indent.text

        res_post_indent = await client.post(
            "/app/paper/indents/new",
            data={
                "store_id": str(press1_store.id),
                "section_id": str(section.id),
                "indent_date": date.today().isoformat(),
                "job_no": "JOB-WEB-TEST-001",
                "remarks": "Web test issue",
                "paper_item_id": [str(paper_item.id)],
                "unit_id": [str(unit.id)],
                "requested_quantity": ["5"],
                "issued_quantity": ["5"],
                "weight_kg": ["93.160"],
            },
            follow_redirects=False,
        )
        assert res_post_indent.status_code == 303
        redirect_url = res_post_indent.headers["location"]
        assert "/app/paper/indents/" in redirect_url

        res_indent_voucher = await client.get(redirect_url)
        assert res_indent_voucher.status_code == 200
        assert "Issue Voucher" in res_indent_voucher.text
        assert "JOB-WEB-TEST-001" in res_indent_voucher.text

    # 2. Directorate issues transfer directive via web form
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"csms_access_token": dir_token},
    ) as client:
        res_get_trf = await client.get("/app/paper/transfers/new")
        assert res_get_trf.status_code == 200
        assert "Directorate Transfer Directive" in res_get_trf.text

        res_post_trf = await client.post(
            "/app/paper/transfers/new",
            data={
                "source_store_id": str(press1_store.id),
                "destination_store_id": str(press2_store.id),
                "transfer_date": date.today().isoformat(),
                "transfer_mode": "PUSH",
                "remarks": "Directorate web directive",
                "paper_item_id": [str(paper_item.id)],
                "unit_id": [str(unit.id)],
                "requested_quantity": ["15"],
                "line_remarks": ["Urgent delivery"],
            },
            follow_redirects=False,
        )
        assert res_post_trf.status_code == 303
        trf_redirect_url = res_post_trf.headers["location"]
        assert "/app/paper/transfers/" in trf_redirect_url

        res_trf_detail = await client.get(trf_redirect_url)
        assert res_trf_detail.status_code == 200
        assert "Inter-Press Paper Transfer" in res_trf_detail.text
        assert "DIRECTORATE_DIRECTIVE" in res_trf_detail.text
