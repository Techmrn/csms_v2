import asyncio
from decimal import Decimal
from datetime import date
from sqlalchemy import select
from fastapi import HTTPException
from app.db.session import AsyncSessionLocal
from app.services.issue import IssueService
from app.schemas.indent import IssueFinalizeRequest, IssueFinalizeLine
from app.models import Indent, IndentLine, Item, Asset, Store, FinancialYear, Office

async def run_test():
    async with AsyncSessionLocal() as session:
        # Setup: Find a store and FY
        fy = await session.scalar(select(FinancialYear).limit(1))
        store = await session.scalar(select(Store).limit(1))
        office = await session.scalar(select(Office).limit(1))
        item = await session.scalar(select(Item).where(Item.code == "TEST-ASS-1").limit(1))
        
        # Create an asset in stock
        asset = Asset(
            asset_no="TEST-ASSET-DUP-1",
            item_id=item.id,
            status="IN_STOCK",
            current_store_id=store.id,
            acquisition_financial_year_id=fy.id,
        )
        asset2 = Asset(
            asset_no="TEST-ASSET-DUP-2",
            item_id=item.id,
            status="IN_STOCK",
            current_store_id=store.id,
            acquisition_financial_year_id=fy.id,
        )
        session.add(asset)
        session.add(asset2)
        await session.flush()
        
        # Create an indent
        indent = Indent(
            indent_no="IND-DUP-TEST-2",
            indent_date=date.today(),
            financial_year_id=fy.id,
            store_id=store.id,
            office_id=office.id,
            status="RECORDED"
        )
        session.add(indent)
        await session.flush()
        
        # Create indent line
        line1 = IndentLine(
            indent_id=indent.id,
            item_id=item.id,
            requested_quantity=Decimal("2")
        )
        line2 = IndentLine(
            indent_id=indent.id,
            item_id=item.id,
            requested_quantity=Decimal("1")
        )
        session.add(line1)
        session.add(line2)
        await session.flush()
        await session.commit()
        
        print("Testing duplicate asset IDs within one line...")
        service = IssueService(session)
        payload = IssueFinalizeRequest(
            issue_date=date.today(),
            lines=[
                IssueFinalizeLine(
                    indent_line_id=line1.id,
                    issued_quantity=Decimal("2"),
                    asset_ids=[asset.id, asset.id]
                )
            ]
        )
        try:
            await service.finalize_from_indent(indent.id, payload, actor_id=1)
            print("FAIL: Duplicate asset IDs within one line were allowed!")
        except HTTPException as e:
            if e.status_code == 422:
                print("PASS: Duplicate asset IDs within one line rejected with 422")
            else:
                print(f"FAIL: Wrong exception status: {e.status_code}")
                
        print("Testing same asset ID across two lines...")
        payload = IssueFinalizeRequest(
            issue_date=date.today(),
            lines=[
                IssueFinalizeLine(
                    indent_line_id=line1.id,
                    issued_quantity=Decimal("1"),
                    asset_ids=[asset.id]
                ),
                IssueFinalizeLine(
                    indent_line_id=line2.id,
                    issued_quantity=Decimal("1"),
                    asset_ids=[asset.id]
                )
            ]
        )
        try:
            await service.finalize_from_indent(indent.id, payload, actor_id=1)
            print("FAIL: Same asset ID across two lines was allowed!")
        except HTTPException as e:
            if e.status_code == 422:
                print("PASS: Same asset ID across two lines rejected with 422")
            else:
                print(f"FAIL: Wrong exception status: {e.status_code}")
                
        # Clean up
        await session.rollback()

if __name__ == "__main__":
    asyncio.run(run_test())
