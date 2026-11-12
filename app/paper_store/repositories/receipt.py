from datetime import date
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.financial_year import FinancialYear
from app.models.store import Store
from app.paper_store.models.item import PaperItem
from app.paper_store.models.receipt import PaperReceipt, PaperReceiptLine


class PaperReceiptRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, receipt_id: int) -> PaperReceipt | None:
        stmt = (
            select(PaperReceipt)
            .options(
                selectinload(PaperReceipt.lines).selectinload(PaperReceiptLine.paper_item).selectinload(PaperItem.unit),
                selectinload(PaperReceipt.lines).selectinload(PaperReceiptLine.unit),
                selectinload(PaperReceipt.store).selectinload(Store.office),
                selectinload(PaperReceipt.financial_year),
            )
            .where(PaperReceipt.id == receipt_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list(
        self,
        store_id: int | None = None,
        financial_year_id: int | None = None,
        limit: int = 100,
    ) -> list[PaperReceipt]:
        stmt = (
            select(PaperReceipt)
            .options(
                selectinload(PaperReceipt.lines).selectinload(PaperReceiptLine.paper_item).selectinload(PaperItem.unit),
                selectinload(PaperReceipt.lines).selectinload(PaperReceiptLine.unit),
                selectinload(PaperReceipt.store).selectinload(Store.office),
                selectinload(PaperReceipt.financial_year),
            )
            .order_by(PaperReceipt.receipt_date.desc(), PaperReceipt.id.desc())
            .limit(limit)
        )
        if store_id is not None:
            stmt = stmt.where(PaperReceipt.store_id == store_id)
        if financial_year_id is not None:
            stmt = stmt.where(PaperReceipt.financial_year_id == financial_year_id)
        return list((await self.session.scalars(stmt)).all())

    async def next_receipt_number(self, financial_year: FinancialYear) -> str:
        prefix = f"PWR-{financial_year.year_name}-"
        last_num = await self.session.scalar(
            select(func.max(PaperReceipt.receipt_no)).where(
                PaperReceipt.financial_year_id == financial_year.id,
                PaperReceipt.receipt_no.like(f"{prefix}%"),
            )
        )
        if not last_num:
            return f"{prefix}0001"
        try:
            seq = int(last_num.replace(prefix, "")) + 1
        except ValueError:
            seq = 1
        return f"{prefix}{seq:04d}"
