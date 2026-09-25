import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.category import Category
from app.models.financial_year import FinancialYear
from app.models.indent import Indent, IndentLine
from app.models.item import Item
from app.models.office import Office
from app.models.section import Section
from app.models.stock import StockAccount, StockMovement
from app.models.store import Store
from app.models.unit import Unit
from app.models.user import User
from app.security.auth import create_access_token


@pytest.mark.asyncio
async def test_online_indent_approval_workflow_with_quantity_modification(client):
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        cat = await session.scalar(select(Category).where(Category.type == "CONSUMABLE"))
        unit = await session.scalar(select(Unit).where(Unit.code == "NOS"))
        fy = await session.scalar(select(FinancialYear).where(FinancialYear.is_current.is_(True)))
        press_office = await session.scalar(select(Office).where(Office.code == "PRESS"))
        press_section = await session.scalar(select(Section).where(Section.office_id == press_office.id))
        press_store = await session.scalar(select(Store).where(Store.code == "PRESS-STORE"))
        
        foreman = await session.scalar(select(User).where(User.username == "dev_foreman1"))
        press_head = await session.scalar(select(User).where(User.username == "dev_press_head"))
        press_sk = await session.scalar(select(User).where(User.username == "dev_press_sk"))
        general_sk = await session.scalar(select(User).where(User.username == "dev_general_sk"))

        assert cat and unit and fy and press_office and press_section and press_store
        assert foreman and press_head and press_sk and general_sk

        # Create a test item with stock in press_store
        item = Item(code=f"ITM-{suffix}", name=f"Test Consumable {suffix}", category_id=cat.id, unit_id=unit.id, is_active=True)
        session.add(item)
        await session.flush()

        # Seed initial stock of 20
        stock_acc = StockAccount(
            store_id=press_store.id,
            financial_year_id=fy.id,
            item_id=item.id,
        )
        session.add(stock_acc)
        movement = StockMovement(
            movement_type="OPENING",
            movement_date=fy.start_date,
            financial_year_id=fy.id,
            store_id=press_store.id,
            item_id=item.id,
            quantity_in=Decimal("20.000"),
            quantity_out=Decimal("0"),
            reference_type="OPENING_STOCK",
            reference_id=item.id,
            created_by=press_sk.id,
        )
        session.add(movement)
        await session.commit()

        foreman_token = create_access_token(foreman)
        press_head_token = create_access_token(press_head)
        press_sk_token = create_access_token(press_sk)
        general_sk_token = create_access_token(general_sk)

        item_id = item.id
        store_id = press_store.id
        office_id = press_office.id
        section_id = press_section.id
        fy_id = fy.id

    foreman_headers = {"Authorization": f"Bearer {foreman_token}"}
    head_headers = {"Authorization": f"Bearer {press_head_token}"}
    sk_headers = {"Authorization": f"Bearer {press_sk_token}"}
    gen_sk_headers = {"Authorization": f"Bearer {general_sk_token}"}

    # 1. Section User creates an online indent for 10 units
    create_resp = await client.post(
        "/api/indents",
        headers=foreman_headers,
        json={
            "indent_date": str(date.today()),
            "financial_year_id": fy_id,
            "store_id": store_id,
            "office_id": office_id,
            "section_id": section_id,
            "request_source": "ONLINE",
            "remarks": "Urgent requirement for production",
            "lines": [
                {"item_id": item_id, "requested_quantity": 10.0, "remarks": "High quality paper"}
            ],
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    indent_data = create_resp.json()
    indent_id = indent_data["id"]
    line_id = indent_data["lines"][0]["id"]
    assert indent_data["status"] == "RECORDED"
    assert Decimal(str(indent_data["lines"][0]["requested_quantity"])) == Decimal("10.000")
    assert indent_data["lines"][0]["approved_quantity"] is None

    # 2. Indent creator cannot approve their own indent
    self_approve_resp = await client.post(f"/api/indents/{indent_id}/approve", headers=foreman_headers, json={})
    assert self_approve_resp.status_code == 403

    # 3. Storekeeper (not store controller) cannot approve indent
    sk_approve_resp = await client.post(f"/api/indents/{indent_id}/approve", headers=sk_headers, json={})
    assert sk_approve_resp.status_code == 403

    # 4. Approver views indent via API
    get_resp = await client.get(f"/api/indents/{indent_id}", headers=head_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["indent_no"] == indent_data["indent_no"]

    # 5. Approver tries to approve quantity > requested (15 > 10) -> Should fail 422
    over_resp = await client.post(
        f"/api/indents/{indent_id}/approve",
        headers=head_headers,
        json={
            "lines": [{"indent_line_id": line_id, "approved_quantity": 15.0}],
            "remarks": "Over approval",
        },
    )
    assert over_resp.status_code == 422

    # 6. Approver tries to approve negative quantity -> Should fail 422
    neg_resp = await client.post(
        f"/api/indents/{indent_id}/approve",
        headers=head_headers,
        json={
            "lines": [{"indent_line_id": line_id, "approved_quantity": -2.0}],
        },
    )
    assert neg_resp.status_code == 422

    # 7. Approver modifies numbers: reduces approved quantity from 10 to 4
    approve_resp = await client.post(
        f"/api/indents/{indent_id}/approve",
        headers=head_headers,
        json={
            "lines": [{"indent_line_id": line_id, "approved_quantity": 4.0}],
            "remarks": "Approved 4 units due to quota limit",
        },
    )
    assert approve_resp.status_code == 200, approve_resp.text
    approved_indent = approve_resp.json()
    assert approved_indent["status"] == "PROCESSING"
    assert Decimal(str(approved_indent["lines"][0]["requested_quantity"])) == Decimal("10.000")
    assert Decimal(str(approved_indent["lines"][0]["approved_quantity"])) == Decimal("4.000")

    # 8. Storekeeper attempts to issue more than approved quantity (5 > 4) -> 422
    over_issue_resp = await client.post(
        f"/api/indents/{indent_id}/finalize-issue",
        headers=sk_headers,
        json={
            "issue_date": str(date.today()),
            "lines": [
                {"indent_line_id": line_id, "issued_quantity": 5.0}
            ],
        },
    )
    assert over_issue_resp.status_code == 422
    assert "exceeds approved quantity" in over_issue_resp.json()["detail"]

    # 9. Storekeeper issues 4 units (up to approved quantity) -> Success
    issue_resp = await client.post(
        f"/api/indents/{indent_id}/finalize-issue",
        headers=sk_headers,
        json={
            "issue_date": str(date.today()),
            "lines": [
                {"indent_line_id": line_id, "issued_quantity": 4.0}
            ],
        },
    )
    assert issue_resp.status_code == 200, issue_resp.text

    # Verify stock balance decremented: 20 - 4 = 16
    async with AsyncSessionLocal() as session:
        from app.services.stock import StockService
        bal = await StockService(session).current_balance(store_id, fy_id, item_id)
        assert bal == Decimal("16.000")

        # Verify indent record
        ind = await session.scalar(select(Indent).where(Indent.id == indent_id))
        assert ind.status == "FINALIZED"
        assert ind.lines[0].requested_quantity == Decimal("10.000")
        assert ind.lines[0].approved_quantity == Decimal("4.000")
        assert ind.lines[0].issued_quantity == Decimal("4.000")


@pytest.mark.asyncio
async def test_online_indent_web_approval_flow(client):
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        cat = await session.scalar(select(Category).where(Category.type == "CONSUMABLE"))
        unit = await session.scalar(select(Unit).where(Unit.code == "NOS"))
        fy = await session.scalar(select(FinancialYear).where(FinancialYear.is_current.is_(True)))
        press_office = await session.scalar(select(Office).where(Office.code == "PRESS"))
        press_section = await session.scalar(select(Section).where(Section.office_id == press_office.id))
        press_store = await session.scalar(select(Store).where(Store.code == "PRESS-STORE"))
        foreman = await session.scalar(select(User).where(User.username == "dev_foreman1"))
        press_head = await session.scalar(select(User).where(User.username == "dev_press_head"))
        press_sk = await session.scalar(select(User).where(User.username == "dev_press_sk"))

        item = Item(code=f"WEB-{suffix}", name=f"Web Item {suffix}", category_id=cat.id, unit_id=unit.id, is_active=True)
        session.add(item)
        await session.commit()

        foreman_token = create_access_token(foreman)
        press_head_token = create_access_token(press_head)
        press_sk_token = create_access_token(press_sk)
        item_id = item.id
        store_id = press_store.id
        office_id = press_office.id
        section_id = press_section.id
        fy_id = fy.id

    # Create online indent
    create_resp = await client.post(
        "/api/indents",
        headers={"Authorization": f"Bearer {foreman_token}"},
        json={
            "indent_date": str(date.today()),
            "financial_year_id": fy_id,
            "store_id": store_id,
            "office_id": office_id,
            "section_id": section_id,
            "request_source": "ONLINE",
            "lines": [
                {"item_id": item_id, "requested_quantity": 8.0}
            ],
        },
    )
    assert create_resp.status_code == 201
    indent_id = create_resp.json()["id"]
    line_id = create_resp.json()["lines"][0]["id"]

    # Approver views detail page via web cookie/token - approver SHOULD see balance
    web_cookies = {"csms_access_token": press_head_token}
    detail_page_resp = await client.get(f"/app/indents/{indent_id}", cookies=web_cookies)
    assert detail_page_resp.status_code == 200
    html = detail_page_resp.text
    assert "Review &amp; Approve Online Indent" in html or "Review & Approve Online Indent" in html
    assert "Approved Quantity (Modify if needed)" in html
    assert f'value="8.000"' in html or f'value="8"' in html
    assert "Current Available" in html

    # Section user / initiator views online indent creation page - Available column MUST NOT be present
    foreman_cookies = {"csms_access_token": foreman_token}
    new_indent_page_resp = await client.get("/app/online-indents/new", cookies=foreman_cookies)
    assert new_indent_page_resp.status_code == 200
    new_html = new_indent_page_resp.text
    assert "<th>Available</th>" not in new_html
    assert "data-available" not in new_html
    assert "available-value" not in new_html

    # Section user / initiator views indent detail page - Current Available MUST be hidden
    initiator_detail_resp = await client.get(f"/app/indents/{indent_id}", cookies=foreman_cookies)
    assert initiator_detail_resp.status_code == 200
    initiator_html = initiator_detail_resp.text
    assert "Current Available" not in initiator_html
    assert "Review &amp; Approve Online Indent" not in initiator_html

    # Indent list page shows "Review &amp; Approve" button for approver
    list_resp = await client.get("/app/online-indents", cookies=web_cookies)
    assert list_resp.status_code == 200
    assert "Review &amp; Approve" in list_resp.text

    # Approver submits web form modifying number to 3.5
    approve_form_resp = await client.post(
        f"/app/indents/{indent_id}/approve",
        cookies=web_cookies,
        data={
            "indent_line_id": str(line_id),
            "approved_quantity": "3.5",
            "approval_remarks": "Modified via web review",
        },
        follow_redirects=False,
    )
    assert approve_form_resp.status_code == 303
    assert f"/app/indents/{indent_id}" in approve_form_resp.headers["location"]

    # Verify updated approved quantity
    async with AsyncSessionLocal() as session:
        ind = await session.scalar(select(Indent).where(Indent.id == indent_id))
        assert ind.status == "PROCESSING"
        assert ind.lines[0].requested_quantity == Decimal("8.000")
        assert ind.lines[0].approved_quantity == Decimal("3.500")

    # Storekeeper / Issuer views detail page - issuer SHOULD see Current Available and Process/Issue
    sk_cookies = {"csms_access_token": press_sk_token}
    issuer_detail_resp = await client.get(f"/app/indents/{indent_id}", cookies=sk_cookies)
    assert issuer_detail_resp.status_code == 200
    assert "Current Available" in issuer_detail_resp.text
    assert "Process / Issue Stock" in issuer_detail_resp.text
