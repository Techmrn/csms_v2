import asyncio
from decimal import Decimal
from datetime import date
from sqlalchemy import select
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
            asset_no="TEST-ASSET-DUP",
            item_id=item.id,
            status="IN_STOCK",
            current_store_id=store.id,
            acquisition_financial_year_id=fy.id,
        )
        session.add(asset)
        await session.flush()
        
        # Create an indent
        indent = Indent(
            indent_no="IND-DUP-TEST",
            indent_date=date.today(),
            financial_year_id=fy.id,
            store_id=store.id,
            office_id=office.id,
            status="RECORDED"
        )
        session.add(indent)
        await session.flush()
        
        # Create indent line
        line = IndentLine(
            indent_id=indent.id,
            item_id=item.id,
            requested_quantity=Decimal("2")
        )
        session.add(line)
        await session.flush()
        await session.commit()
        
        # Now try to finalize issue with duplicate asset ID
        print(f"Testing duplicate issue for asset_id: {asset.id}")
        service = IssueService(session)
        payload = IssueFinalizeRequest(
            issue_date=date.today(),
            lines=[
                IssueFinalizeLine(
                    indent_line_id=line.id,
                    issued_quantity=Decimal("2"),
                    asset_ids=[asset.id, asset.id]
                )
            ]
        )
        try:
            await service.finalize_from_indent(indent.id, payload, actor_id=1)
            print("FAIL: Duplicate asset IDs were allowed!")
        except Exception as e:
            print(f"EXCEPTION: {type(e)} - {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_test())
