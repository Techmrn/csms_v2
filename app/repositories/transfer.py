from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.transfer import StockTransfer, StockTransferLine, TransferDiscrepancy, TransferLineAsset


class TransferRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, transfer_id: int, for_update: bool = False):
        stmt = (
            select(StockTransfer)
            .options(
                selectinload(StockTransfer.lines).selectinload(StockTransferLine.item),
                selectinload(StockTransfer.lines).selectinload(StockTransferLine.unit),
                selectinload(StockTransfer.lines).selectinload(StockTransferLine.asset_links).selectinload(TransferLineAsset.asset),
            )
            .where(StockTransfer.id == transfer_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def list(self, store_id: int | None = None, status: str | None = None):
        stmt = select(StockTransfer).options(selectinload(StockTransfer.lines))
        if store_id is not None:
            stmt = stmt.where(
                (StockTransfer.source_store_id == store_id)
                | (StockTransfer.destination_store_id == store_id)
            )
        if status is not None:
            stmt = stmt.where(StockTransfer.status == status)
        stmt = stmt.order_by(StockTransfer.id.desc())
        return list((await self.session.scalars(stmt)).all())

    async def discrepancies(self, transfer_id: int):
        stmt = select(TransferDiscrepancy).where(TransferDiscrepancy.transfer_id == transfer_id)
        return list((await self.session.scalars(stmt)).all())
