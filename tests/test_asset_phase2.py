"""Asset Phase 2 regression tests against the CURRENT CSMS V2 API.

These tests are intentionally data-isolated by using unique item/serial values;
they do not truncate the developer database.
"""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.asset import Asset, AssetMovement
from app.models.category import Category
from app.models.financial_year import FinancialYear
from app.models.item import Item
from app.models.store import Store
from app.models.unit import Unit


async def _setup_assets(count: int = 8):
    async with AsyncSessionLocal() as session:
        category = await session.scalar(select(Category).where(Category.type == "ASSET"))
        unit = await session.scalar(select(Unit).where(Unit.code == "NOS"))
        fy = await session.scalar(select(FinancialYear).where(FinancialYear.is_current.is_(True)))
        central = await session.scalar(select(Store).where(Store.store_type == "CENTRAL").order_by(Store.id))
        press = await session.scalar(select(Store).where(Store.code == "PRESS-STORE"))
        assert category and unit and fy and central and press

        suffix = uuid.uuid4().hex[:10]
        item = Item(code=f"PH2-{suffix}", name=f"Phase2 Asset {suffix}", category_id=category.id, unit_id=unit.id)
        session.add(item)
        await session.flush()
        assets=[]
        for i in range(count):
            asset=Asset(
                asset_no=f"AST-PH2-{suffix}-{i}",
                item_id=item.id,
                serial_no=f"SN-PH2-{suffix}-{i}",
                current_store_id=central.id,
                status="IN_STOCK",
                acquisition_financial_year_id=fy.id,
                created_by=3,
            )
            session.add(asset)
            assets.append(asset)
        await session.flush()
        for asset in assets:
            session.add(AssetMovement(
                asset_id=asset.id,
                movement_type="RECEIPT",
                to_store_id=central.id,
                reference_type="TEST_SETUP",
                reference_id=asset.id,
                reference_document=f"TEST-{suffix}",
                movement_date=fy.start_date,
                created_by=3,
            ))
        await session.commit()
        return {
            "suffix": suffix, "fy": fy, "central": central, "press": press,
            "item_id": item.id, "asset_ids": [a.id for a in assets],
            "central_office_id": central.office_id, "press_office_id": press.office_id,
        }


@pytest.mark.asyncio
async def test_asset_phase2_issue_duplicate_and_return(client, dev_tokens):
    data = await _setup_assets(5)
    headers = {"Authorization": f"Bearer {dev_tokens['dev_general_sk']}"}

    indent = await client.post(
        "/api/indents",
        json={
            "indent_date": str(data["fy"].start_date),
            "financial_year_id": data["fy"].id,
            "store_id": data["central"].id,
            "office_id": data["central_office_id"],
            "request_source": "PHYSICAL",
            "lines": [{"item_id": data["item_id"], "requested_quantity": 2}],
        }, headers=headers,
    )
    assert indent.status_code == 201, indent.text
    line_id = indent.json()["lines"][0]["id"]
    indent_id = indent.json()["id"]

    issue = await client.post(
        f"/api/indents/{indent_id}/finalize-issue",
        json={"issue_date": str(data["fy"].start_date), "lines":[{
            "indent_line_id": line_id, "issued_quantity": 2,
            "asset_ids": data["asset_ids"][:2]
        }]}, headers=headers,
    )
    assert issue.status_code == 200, issue.text
    issue_json = issue.json()
    assert float(issue_json["lines"][0]["quantity"]) == 2
    issue_id = issue_json["id"]

    # Cannot reuse an already-assigned asset.
    indent2 = await client.post(
        "/api/indents",
        json={
            "indent_date": str(data["fy"].start_date), "financial_year_id": data["fy"].id,
            "store_id": data["central"].id, "office_id": data["central_office_id"],
            "request_source":"PHYSICAL", "lines":[{"item_id":data["item_id"],"requested_quantity":1}],
        }, headers=headers,
    )
    assert indent2.status_code == 201, indent2.text
    il2=indent2.json()["lines"][0]["id"]
    reused = await client.post(
        f"/api/indents/{indent2.json()['id']}/finalize-issue",
        json={"issue_date":str(data["fy"].start_date),"lines":[{"indent_line_id":il2,"issued_quantity":1,"asset_ids":[data["asset_ids"][0]]}]},
        headers=headers,
    )
    assert reused.status_code in (409, 422), reused.text

    # Return exact issued assets to original issuing store.
    ret = await client.post(
        "/api/returns",
        json={
            "return_date": str(data["fy"].start_date),
            "financial_year_id": data["fy"].id,
            "store_id": data["central"].id,
            "original_issue_id": issue_id,
            "returning_office_id": data["central_office_id"],
            "reason": "Asset return test",
            "lines": [{"original_issue_line_id": issue_json["lines"][0]["id"], "quantity": 1, "asset_ids":[data["asset_ids"][0]]}],
        }, headers=headers,
    )
    assert ret.status_code == 201, ret.text
    verify_headers = {"Authorization": f"Bearer {dev_tokens['dev_assistant_sk']}"}
    assert (await client.post(f"/api/returns/{ret.json()['id']}/verify", headers=verify_headers)).status_code == 200
    posted = await client.post(f"/api/returns/{ret.json()['id']}/post", headers=headers)
    assert posted.status_code == 200, posted.text

    async with AsyncSessionLocal() as session:
        asset = await session.get(Asset, data["asset_ids"][0])
        assert asset.status == "IN_STOCK"
        assert asset.current_store_id == data["central"].id


@pytest.mark.asyncio
async def test_asset_duplicate_ids_rejected_current_api(client, dev_tokens):
    data = await _setup_assets(2)
    headers = {"Authorization": f"Bearer {dev_tokens['dev_general_sk']}"}
    indent = await client.post("/api/indents", json={
        "indent_date":str(data["fy"].start_date),"financial_year_id":data["fy"].id,
        "store_id":data["central"].id,"office_id":data["central_office_id"],"request_source":"PHYSICAL",
        "lines":[{"item_id":data["item_id"],"requested_quantity":2}],
    }, headers=headers)
    assert indent.status_code == 201, indent.text
    line_id=indent.json()["lines"][0]["id"]
    bad=await client.post(f"/api/indents/{indent.json()['id']}/finalize-issue", json={
        "issue_date":str(data["fy"].start_date),
        "lines":[{"indent_line_id":line_id,"issued_quantity":2,"asset_ids":[data["asset_ids"][0],data["asset_ids"][0]]}],
    }, headers=headers)
    assert bad.status_code == 422, bad.text


@pytest.mark.asyncio
async def test_asset_transfer_to_press_store_and_receive(client, dev_tokens):
    data=await _setup_assets(1)
    press_sk={"Authorization":f"Bearer {dev_tokens['dev_press_sk']}"}
    press_head={"Authorization":f"Bearer {dev_tokens['dev_press_head']}"}
    deputy={"Authorization":f"Bearer {dev_tokens['dev_deputy']}"}
    central_sk={"Authorization":f"Bearer {dev_tokens['dev_general_sk']}"}

    req=await client.post("/api/requisitions",json={
        "requisition_date":str(data["fy"].start_date),"financial_year_id":data["fy"].id,
        "requesting_office_id":data["press_office_id"],"requesting_store_id":data["press"].id,
        "lines":[{"item_id":data["item_id"],"requested_quantity":1}],
    },headers=press_sk)
    assert req.status_code==201,req.text
    rid=req.json()["id"]; rline=req.json()["lines"][0]["id"]
    assert (await client.post(f"/api/requisitions/{rid}/approve-branch",json={},headers=press_head)).status_code==200
    ca=await client.post(f"/api/requisitions/{rid}/approve-central",json={"lines":[{"requisition_line_id":rline,"approved_quantity":1}],"remarks":"test"},headers=deputy)
    assert ca.status_code==200,ca.text

    disp=await client.post(f"/api/transfers/requisitions/{rid}/dispatch",json={
        "transfer_date":str(data["fy"].start_date),"lines":[{"requisition_line_id":rline,"dispatch_quantity":1,"asset_ids":[data["asset_ids"][0]]}],
    },headers=central_sk)
    assert disp.status_code==200,disp.text
    tid=disp.json()["id"]; tline=disp.json()["lines"][0]["id"]
    rec=await client.post(f"/api/transfers/{tid}/receive",json={"receive_date":str(data["fy"].start_date),"lines":[{"transfer_line_id":tline,"received_quantity":1}]},headers=press_sk)
    assert rec.status_code==200,rec.text

    async with AsyncSessionLocal() as session:
        asset=await session.get(Asset,data["asset_ids"][0])
        assert asset.current_store_id==data["press"].id
        assert asset.status=="IN_STOCK"


@pytest.mark.asyncio
async def test_asset_repair_restores_location(client, dev_tokens):
    data=await _setup_assets(1)
    headers={"Authorization":f"Bearer {dev_tokens['dev_general_sk']}"}
    r=await client.post(f"/api/assets/{data['asset_ids'][0]}/repair",json={"reason":"Test repair"},headers=headers)
    assert r.status_code==200,r.text
    assert r.json()["status"]=="UNDER_REPAIR"
    r2=await client.post(f"/api/assets/{data['asset_ids'][0]}/repair-return",json={"resolution":"Repaired"},headers=headers)
    assert r2.status_code==200,r2.text
    assert r2.json()["status"]=="IN_STOCK"
    assert r2.json()["current_store_id"]==data["central"].id


@pytest.mark.asyncio
async def test_asset_unserviceable_dispose_and_lost(client, dev_tokens):
    data=await _setup_assets(2)
    controller={"Authorization":f"Bearer {dev_tokens['dev_deputy']}"}
    for aid in data["asset_ids"]:
        assert (await client.get(f"/api/assets/{aid}",headers=controller)).status_code==200
    u=await client.post(f"/api/assets/{data['asset_ids'][0]}/unserviceable",json={"reason":"Beyond repair"},headers=controller)
    assert u.status_code==200,u.text
    d=await client.post(f"/api/assets/{data['asset_ids'][0]}/dispose",json={"reason":"Disposed"},headers=controller)
    assert d.status_code==200,d.text
    assert d.json()["status"]=="DISPOSED"
    l=await client.post(f"/api/assets/{data['asset_ids'][1]}/lost",json={"reason":"Lost test"},headers=controller)
    assert l.status_code==200,l.text
    assert l.json()["status"]=="LOST"


@pytest.mark.asyncio
async def test_asset_resource_scope_and_history(client, dev_tokens):
    data=await _setup_assets(1)
    press_headers={"Authorization":f"Bearer {dev_tokens['dev_press_sk']}"}
    r=await client.get(f"/api/assets/{data['asset_ids'][0]}",headers=press_headers)
    assert r.status_code==403,r.text
    r=await client.get(f"/api/assets/{data['asset_ids'][0]}/movements",headers=press_headers)
    assert r.status_code==403,r.text
    r=await client.get("/api/assets",params={"store_id":data["central"].id},headers=press_headers)
    assert r.status_code==403,r.text
