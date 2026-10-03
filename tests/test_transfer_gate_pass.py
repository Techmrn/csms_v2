import os
import pytest
from decimal import Decimal
from datetime import date
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.transfer import (
    TransferDispatchRequest,
    TransferDispatchLine,
    TransferGatePassUpdateRequest,
    TransferResponse,
)
from app.services.pdf_reports import make_transfer_gate_pass_pdf


def test_transfer_schemas_support_optional_vehicle_and_receiver():
    # Test dispatch request with optional fields provided
    req = TransferDispatchRequest(
        transfer_date=date(2026, 10, 3),
        lines=[TransferDispatchLine(requisition_line_id=1, dispatch_quantity=Decimal("10"))],
        vehicle_no="KL-01-AB-1234",
        received_by_name="Ramesh (Driver)",
    )
    assert req.vehicle_no == "KL-01-AB-1234"
    assert req.received_by_name == "Ramesh (Driver)"

    # Test dispatch request without vehicle_no or received_by_name (non-mandatory)
    req_empty = TransferDispatchRequest(
        transfer_date=date(2026, 10, 3),
        lines=[TransferDispatchLine(requisition_line_id=1, dispatch_quantity=Decimal("10"))],
    )
    assert req_empty.vehicle_no is None
    assert req_empty.received_by_name is None

    # Test gate pass update schema
    update_req = TransferGatePassUpdateRequest(
        vehicle_no="KL-07-CD-5678",
        received_by_name="Suresh Kumar",
    )
    assert update_req.vehicle_no == "KL-07-CD-5678"
    assert update_req.received_by_name == "Suresh Kumar"

    # Test transfer response schema
    resp = TransferResponse(
        id=1,
        transfer_no="TRF-000001",
        transfer_date=date(2026, 10, 3),
        financial_year_id=1,
        source_store_id=1,
        destination_store_id=2,
        requisition_id=10,
        status="DISPATCHED",
        vehicle_no="KL-01-AB-1234",
        received_by_name="Ramesh",
        dispatched_at=None,
        received_at=None,
        closed_at=None,
        lines=[],
    )
    assert resp.vehicle_no == "KL-01-AB-1234"
    assert resp.received_by_name == "Ramesh"


def test_make_transfer_gate_pass_pdf_generation():
    info = {
        "transfer_no": "TRF-000042",
        "transfer_date": "2026-10-03",
        "requisition_no": "REQ-2026-0099",
        "requisition_date": "2026-10-02",
        "source_store": "Central Store (Directorate)",
        "destination_store": "Central Press Store",
        "destination_office": "Central Press, Thiruvananthapuram",
        "vehicle_no": "KL-01-CZ-9999",
        "received_by_name": "K. Murugan (Driver)",
        "fy_name": "2026-2027",
        "dispatched_by_name": "General Storekeeper",
    }
    items = [
        {
            "item_code": "P-A4-75",
            "item_name": "Printing Paper A4 75 GSM",
            "unit_code": "REAM",
            "quantity": "50.000",
            "remarks": "Packed in 10 cartons",
            "asset_numbers": "",
        },
        {
            "item_code": "TONER-HP-85A",
            "item_name": "HP LaserJet 85A Toner Cartridge",
            "unit_code": "NOS",
            "quantity": "5.000",
            "remarks": "Original seal intact",
            "asset_numbers": "",
        },
    ]

    pdf_buffer = make_transfer_gate_pass_pdf(info, items)
    pdf_bytes = pdf_buffer.getvalue()

    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF")


def test_gate_pass_web_routes_registered():
    def get_routes(routes, prefix=""):
        result = set()
        for route in routes:
            if hasattr(route, "path") and hasattr(route, "endpoint"):
                result.add(prefix + route.path)
            if hasattr(route, "routes"):
                p = getattr(route, "path", "") or ""
                result.update(get_routes(route.routes, prefix + p))
            elif hasattr(route, "original_router") and hasattr(route.original_router, "routes"):
                p = getattr(route, "path", "") or getattr(getattr(route, "include_context", None), "prefix", "") or ""
                result.update(get_routes(route.original_router.routes, prefix + p))
        return result

    routes = get_routes(app.routes)
    assert "/app/transfers/{transfer_id}/gate-pass" in routes
    assert "/app/transfers/{transfer_id}/gate-pass.pdf" in routes
    assert "/app/requisitions/{requisition_id}/gate-pass" in routes


def test_stock_transfer_line_model_attributes():
    from app.models.transfer import StockTransfer, StockTransferLine
    assert hasattr(StockTransferLine, "unit")
    assert hasattr(StockTransferLine, "item")
    assert hasattr(StockTransferLine, "transfer")
    assert hasattr(StockTransferLine, "requested_quantity")
    assert hasattr(StockTransferLine, "approved_quantity")
    assert hasattr(StockTransferLine, "received_quantity")
    assert hasattr(StockTransfer, "vehicle_no")
    assert hasattr(StockTransfer, "received_by_name")
    assert hasattr(StockTransfer, "transfer_mode")
    assert hasattr(StockTransfer, "branch_approved_by")
    assert hasattr(StockTransfer, "directorate_approved_by")
    assert hasattr(StockTransfer, "supply_authorized_by")
    assert hasattr(StockTransfer, "rejected_by")
    assert hasattr(StockTransfer, "rejection_reason")


def test_all_transfer_workflow_web_routes_registered():
    def get_routes(routes, prefix=""):
        result = set()
        for route in routes:
            if hasattr(route, "path") and hasattr(route, "endpoint"):
                result.add(prefix + route.path)
            if hasattr(route, "routes"):
                p = getattr(route, "path", "") or ""
                result.update(get_routes(route.routes, prefix + p))
            elif hasattr(route, "original_router") and hasattr(route.original_router, "routes"):
                p = getattr(route, "path", "") or getattr(getattr(route, "include_context", None), "prefix", "") or ""
                result.update(get_routes(route.original_router.routes, prefix + p))
        return result

    routes = get_routes(app.routes)
    assert "/app/transfers" in routes
    assert "/app/transfers/new" in routes
    assert "/app/transfers/{transfer_id}" in routes
    assert "/app/transfers/{transfer_id}/approve-branch" in routes
    assert "/app/transfers/{transfer_id}/approve-directorate" in routes
    assert "/app/transfers/{transfer_id}/authorize-supply" in routes
    assert "/app/transfers/{transfer_id}/reject" in routes
    assert "/app/transfers/{transfer_id}/dispatch" in routes
    assert "/app/transfers/{transfer_id}/receive" in routes
    assert "/app/transfers/{transfer_id}/gate-pass" in routes
    assert "/app/transfers/{transfer_id}/gate-pass.pdf" in routes


def test_transfer_create_schemas_push_and_pull():
    from app.schemas.transfer import TransferCreateRequest, TransferCreateLine
    pull_req = TransferCreateRequest(
        source_store_id=1,
        destination_store_id=2,
        transfer_mode="PULL",
        lines=[TransferCreateLine(item_id=10, unit_id=1, requested_quantity=Decimal("25"))],
        remarks="Urgent replenishment request",
    )
    assert pull_req.transfer_mode == "PULL"
    assert pull_req.lines[0].requested_quantity == Decimal("25")

    push_req = TransferCreateRequest(
        source_store_id=1,
        destination_store_id=3,
        transfer_mode="PUSH",
        lines=[TransferCreateLine(item_id=10, unit_id=1, requested_quantity=Decimal("100"))],
        remarks="Directorate redistribution directive",
    )
    assert push_req.transfer_mode == "PUSH"
    assert push_req.destination_store_id == 3


@pytest.mark.asyncio
async def test_directorate_push_and_pull_transfer_services():
    import uuid
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.models.category import Category
    from app.models.unit import Unit
    from app.models.item import Item
    from app.models.store import Store
    from app.models.financial_year import FinancialYear
    from app.models.stock import StockAccount, StockMovement
    from app.models.user import User
    from app.services.transfer import TransferService
    from app.services.stock import StockService
    from app.schemas.transfer import (
        TransferCreateRequest,
        TransferCreateLine,
        TransferApproveBranchRequest,
        TransferApproveDirectorateRequest,
        TransferDispatchRequest,
        TransferDispatchLine,
        TransferReceiveRequest,
        TransferReceiveLine,
    )

    suffix = uuid.uuid4().hex[:6]
    async with AsyncSessionLocal() as session:
        cat = await session.scalar(select(Category).where(Category.type == "CONSUMABLE"))
        unit = await session.scalar(select(Unit).where(Unit.code == "NOS"))
        fy = await session.scalar(select(FinancialYear).where(FinancialYear.is_current.is_(True)))
        central_store = await session.scalar(select(Store).where(Store.store_type == "CENTRAL"))
        press_store = await session.scalar(select(Store).where(Store.code == "PRESS-STORE"))

        deputy = await session.scalar(select(User).where(User.username == "dev_deputy"))
        general_sk = await session.scalar(select(User).where(User.username == "dev_general_sk"))
        press_sk = await session.scalar(select(User).where(User.username == "dev_press_sk"))
        press_head = await session.scalar(select(User).where(User.username == "dev_press_head"))

        assert cat and unit and fy and central_store and press_store
        assert deputy and general_sk and press_sk and press_head

        # Create a test consumable item
        item = Item(
            code=f"TRF-{suffix}",
            name=f"Transfer Item {suffix}",
            category_id=cat.id,
            unit_id=unit.id,
            is_active=True,
        )
        session.add(item)
        await session.flush()

        # Seed 100 units in Central Store
        session.add(StockAccount(store_id=central_store.id, financial_year_id=fy.id, item_id=item.id))
        session.add(
            StockMovement(
                movement_type="OPENING",
                movement_date=fy.start_date,
                financial_year_id=fy.id,
                store_id=central_store.id,
                item_id=item.id,
                quantity_in=Decimal("100.000"),
                quantity_out=Decimal("0"),
                reference_type="OPENING_STOCK",
                reference_id=item.id,
                created_by=general_sk.id,
            )
        )
        await session.commit()

        # -------------------------------------------------------------------------
        # Scenario 1: Directorate initiates a PUSH transfer (Central Store -> Press Store)
        # -------------------------------------------------------------------------
        svc = TransferService(session)
        push_create = TransferCreateRequest(
            source_store_id=central_store.id,
            destination_store_id=press_store.id,
            transfer_mode="PUSH",
            transfer_date=date.today(),
            remarks="Directorate urgent push quota",
            lines=[
                TransferCreateLine(
                    item_id=item.id,
                    unit_id=unit.id,
                    requested_quantity=Decimal("40.000"),
                    remarks="Push line",
                )
            ],
        )
        push_transfer = await svc.create(push_create, actor_id=deputy.id)
        # Because Directorate initiated and Central Store is source, it is immediately ready for dispatch!
        assert push_transfer.status == "READY_FOR_DISPATCH"
        assert push_transfer.transfer_mode == "PUSH"
        assert push_transfer.lines[0].approved_quantity == Decimal("40.000")

        # Central Storekeeper dispatches with optional vehicle_no and received_by_name
        dispatch_req = TransferDispatchRequest(
            transfer_date=date.today(),
            vehicle_no="KL-01-DIR-0001",
            received_by_name="M. Driver",
            remarks="Dispatched in secured van",
            lines=[
                TransferDispatchLine(
                    transfer_line_id=push_transfer.lines[0].id,
                    dispatch_quantity=Decimal("40.000"),
                )
            ],
        )
        push_transfer = await svc.dispatch_transfer(push_transfer.id, dispatch_req, actor_id=general_sk.id)
        assert push_transfer.status == "DISPATCHED"
        assert push_transfer.vehicle_no == "KL-01-DIR-0001"
        assert push_transfer.received_by_name == "M. Driver"

        # Verify stock deducted at Central Store
        bal_central = await StockService(session).current_balance(central_store.id, fy.id, item.id)
        assert bal_central == Decimal("60.000")

        # Press Storekeeper receives into Press Store
        receive_req = TransferReceiveRequest(
            receive_date=date.today(),
            remarks="Received in good condition",
            lines=[
                TransferReceiveLine(
                    transfer_line_id=push_transfer.lines[0].id,
                    received_quantity=Decimal("40.000"),
                )
            ],
        )
        push_transfer = await svc.receive(push_transfer.id, receive_req, actor_id=press_sk.id)
        assert push_transfer.status in ("RECEIVED", "CLOSED")

        # Verify stock credited at Press Store
        bal_press = await StockService(session).current_balance(press_store.id, fy.id, item.id)
        assert bal_press == Decimal("40.000")

        # -------------------------------------------------------------------------
        # Scenario 2: Press Storekeeper raises a PULL transfer (Central Store -> Press Store)
        # -------------------------------------------------------------------------
        pull_create = TransferCreateRequest(
            source_store_id=central_store.id,
            destination_store_id=press_store.id,
            transfer_mode="PULL",
            transfer_date=date.today(),
            remarks="Press store pull request",
            lines=[
                TransferCreateLine(
                    item_id=item.id,
                    unit_id=unit.id,
                    requested_quantity=Decimal("20.000"),
                )
            ],
        )
        pull_transfer = await svc.create(pull_create, actor_id=press_sk.id)
        assert pull_transfer.status == "SUBMITTED"

        # Press Branch Head reviews and approves
        pull_transfer = await svc.approve_branch(
            pull_transfer.id,
            TransferApproveBranchRequest(remarks="Approved by Press Head"),
            actor_id=press_head.id,
        )
        assert pull_transfer.status == "BRANCH_APPROVED"

        # Directorate approves -> becomes READY_FOR_DISPATCH (Central Store is source)
        pull_transfer = await svc.approve_directorate(
            pull_transfer.id,
            TransferApproveDirectorateRequest(remarks="Directorate approval granted"),
            actor_id=deputy.id,
        )
        assert pull_transfer.status == "READY_FOR_DISPATCH"


