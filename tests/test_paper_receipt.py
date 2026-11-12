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
from app.models.store import Store
from app.models.unit import Unit
from app.models.user import User
from app.paper_store.models.item import PaperItem
from app.paper_store.models.receipt import PaperReceipt
from app.paper_store.models.stock import PaperStockMovement
from app.paper_store.schemas.receipt import PaperReceiptCreate, PaperReceiptLineCreate
from app.paper_store.services.receipt import PaperReceiptService
from app.paper_store.services.stock import PaperStockService
from app.security.auth import create_access_token
from app.services.authorization import AuthorizationService


@pytest.mark.asyncio
async def test_paper_receipt_service_creates_and_posts_stock():
    suffix = uuid.uuid4().hex[:6]
    async with AsyncSessionLocal() as session:
        fy = await session.scalar(select(FinancialYear).where(FinancialYear.is_current.is_(True)))
        paper_store = await session.scalar(select(Store).where(Store.code == "PRESS-PAPER-WH"))
        unit_ream = await session.scalar(select(Unit).where(Unit.code == "REAM"))
        whman = await session.scalar(select(User).where(User.username == "dev_cp_whman"))

        assert fy and paper_store and unit_ream and whman

        # Create paper item
        paper_item = PaperItem(
            code=f"PPR-{suffix}",
            name=f"Test White Maplitho 70 GSM {suffix}",
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

        svc = PaperReceiptService(session)
        payload = PaperReceiptCreate(
            store_id=paper_store.id,
            financial_year_id=fy.id,
            receipt_date=date.today(),
            source_depot="Govt Central Stationery Depot, Thiruvananthapuram",
            allotment_no=f"SD/ALLOT/{suffix}",
            allotment_date=date.today(),
            challan_no=f"DC-{suffix}",
            challan_date=date.today(),
            vehicle_no="KL-01-CB-4890",
            carrier_name="State Transport Agency",
            lorry_receipt_no=f"LR-{suffix}",
            remarks="Full consignment unloaded in good condition",
            lines=[
                PaperReceiptLineCreate(
                    paper_item_id=paper_item.id,
                    unit_id=unit_ream.id,
                    challan_quantity=Decimal("500.000"),
                    received_quantity=Decimal("500.000"),
                    accepted_quantity=Decimal("495.000"),
                    damaged_quantity=Decimal("5.000"),
                    weight_kg=Decimal("9222.840"),
                    remarks="5 reams wrapper damaged",
                )
            ],
        )

        receipt = await svc.create_and_post(payload, actor_id=whman.id)

        assert receipt.id is not None
        assert receipt.status == "POSTED"
        assert receipt.receipt_no.startswith("PWR-")
        assert len(receipt.lines) == 1
        assert receipt.lines[0].accepted_quantity == Decimal("495.000")
        assert receipt.lines[0].damaged_quantity == Decimal("5.000")

        # Verify stock movement ledger
        movements = list(
            (
                await session.scalars(
                    select(PaperStockMovement).where(
                        PaperStockMovement.reference_type == "PAPER_RECEIPT",
                        PaperStockMovement.reference_id == receipt.id,
                    )
                )
            ).all()
        )
        assert len(movements) == 1
        assert movements[0].movement_type == "RECEIPT_STATIONERY"
        assert movements[0].quantity_in == Decimal("495.000")
        assert movements[0].quantity_out == Decimal("0.000")
        assert movements[0].weight_kg_in == Decimal("9222.840")

        # Verify balance
        stock_svc = PaperStockService(session)
        qty_bal, wt_bal = await stock_svc.balance_for_item(paper_store.id, fy.id, paper_item.id)
        assert qty_bal == 495 * 500
        assert wt_bal == Decimal("9222.840")


@pytest.mark.asyncio
async def test_paper_receipt_validations():
    async with AsyncSessionLocal() as session:
        fy = await session.scalar(select(FinancialYear).where(FinancialYear.is_current.is_(True)))
        general_store = await session.scalar(select(Store).where(Store.code == "CENTRAL"))
        paper_store = await session.scalar(select(Store).where(Store.code == "PRESS-PAPER-WH"))
        unit_ream = await session.scalar(select(Unit).where(Unit.code == "REAM"))
        whman = await session.scalar(select(User).where(User.username == "dev_cp_whman"))
        paper_item = await session.scalar(select(PaperItem).limit(1))

        svc = PaperReceiptService(session)

        # 1. Rejects if store is not PAPER_WAREHOUSE
        invalid_store_payload = PaperReceiptCreate(
            store_id=general_store.id,
            financial_year_id=fy.id,
            receipt_date=date.today(),
            source_depot="Stationery Depot",
            lines=[
                PaperReceiptLineCreate(
                    paper_item_id=paper_item.id,
                    unit_id=unit_ream.id,
                    challan_quantity=Decimal("100"),
                    received_quantity=Decimal("100"),
                    accepted_quantity=Decimal("100"),
                )
            ],
        )
        with pytest.raises(Exception) as exc_info:
            await svc.create_and_post(invalid_store_payload, actor_id=whman.id)
        assert "PAPER_WAREHOUSE" in str(exc_info.value)

        # 2. Rejects if accepted + damaged > received
        excess_qty_payload = PaperReceiptCreate(
            store_id=paper_store.id,
            financial_year_id=fy.id,
            receipt_date=date.today(),
            source_depot="Stationery Depot",
            lines=[
                PaperReceiptLineCreate(
                    paper_item_id=paper_item.id,
                    unit_id=unit_ream.id,
                    challan_quantity=Decimal("100"),
                    received_quantity=Decimal("100"),
                    accepted_quantity=Decimal("95"),
                    damaged_quantity=Decimal("10"),  # 95 + 10 = 105 > 100
                )
            ],
        )
        with pytest.raises(Exception) as exc_info:
            await svc.create_and_post(excess_qty_payload, actor_id=whman.id)
        assert "exceeds" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_office_head_controls_paper_warehouse():
    """Validates that the Branch Head of the Press Office controls the Paper Warehouse as well."""
    async with AsyncSessionLocal() as session:
        press_head = await session.scalar(select(User).where(User.username == "dev_press_head"))
        paper_store = await session.scalar(select(Store).where(Store.code == "PRESS-PAPER-WH"))
        auth = AuthorizationService(session)

        # 1. Branch head can control the paper store
        controller = await auth.require_store_controller(press_head.id, paper_store.id)
        assert controller.id == press_head.id

        # 2. Branch head has paper store visible
        visible_stores = await auth.get_visible_stores(press_head.id)
        assert paper_store.id in visible_stores


@pytest.mark.asyncio
async def test_paper_web_ui_flow():
    async with AsyncSessionLocal() as session:
        whman = await session.scalar(select(User).where(User.username == "dev_cp_whman"))
        paper_store = await session.scalar(select(Store).where(Store.code == "PRESS-PAPER-WH"))
        paper_item = await session.scalar(select(PaperItem).limit(1))
        unit = await session.scalar(select(Unit).where(Unit.code == "REAM"))
        token = create_access_token(whman)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"csms_access_token": token},
    ) as client:
        # 1. GET /app/paper/receipts/new
        res_get = await client.get("/app/paper/receipts/new")
        assert res_get.status_code == 200
        assert "Receive Paper from Stationery Dept" in res_get.text
        assert "Stationery Department" in res_get.text

        # 2. POST /app/paper/receipts/new
        suffix = uuid.uuid4().hex[:6]
        post_data = {
            "store_id": str(paper_store.id),
            "receipt_date": date.today().isoformat(),
            "source_depot": "Govt Central Stationery Depot",
            "allotment_no": f"SD-{suffix}",
            "challan_no": f"DC-{suffix}",
            "challan_date": date.today().isoformat(),
            "vehicle_no": "KL-07-AA-1234",
            "paper_item_id": [str(paper_item.id)],
            "unit_id": [str(unit.id)],
            "challan_quantity": ["100"],
            "received_quantity": ["100"],
            "accepted_quantity": ["98"],
            "damaged_quantity": ["2"],
            "weight_kg": ["1825.936"],
            "reel_count": [""],
            "reel_numbers": [""],
            "line_remarks": ["Normal transit"],
            "remarks": "Received by lorry",
        }
        res_post = await client.post("/app/paper/receipts/new", data=post_data, follow_redirects=False)
        assert res_post.status_code == 303
        redirect_url = res_post.headers["location"]
        assert "/app/paper/receipts/" in redirect_url

        # 3. Follow redirect to voucher
        res_detail = await client.get(redirect_url)
        assert res_detail.status_code == 200
        assert "Paper Receipt Voucher" in res_detail.text
        assert "Warehouseman" in res_detail.text
        assert f"DC-{suffix}" in res_detail.text

        # 4. GET /app/paper/stock
        res_stock = await client.get("/app/paper/stock")
        assert res_stock.status_code == 200
        assert "Paper Warehouse Stock" in res_stock.text
        assert paper_item.name in res_stock.text

