from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.financial_year import FinancialYear
from app.models.item import Item
from app.models.requisition import CentralStoreRequisition, CentralStoreRequisitionLine
from app.models.store import Store
from app.models.office import Office
from app.repositories.requisition import RequisitionRepository
from app.schemas.requisition import BranchApprovalRequest, CentralApprovalRequest, RequisitionCreate
from app.services.authorization import AuthorizationService


class RequisitionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = RequisitionRepository(session)
        self.auth = AuthorizationService(session)

    async def create(self, payload: RequisitionCreate, actor_id: int):
        await self.auth.require_permission(actor_id, "REQUISITION_CREATE")

        fy = await self.session.get(FinancialYear, payload.financial_year_id)
        office = await self.session.get(Office, payload.requesting_office_id)
        store = await self.session.get(Store, payload.requesting_store_id)
        if fy is None:
            raise HTTPException(404, "Financial year not found")
        if office is None:
            raise HTTPException(404, "Requesting office not found")
        if store is None:
            raise HTTPException(404, "Requesting store not found")
        if fy.is_closed:
            raise HTTPException(409, "Financial year is closed")
        if not (fy.start_date <= payload.requisition_date <= fy.end_date):
            raise HTTPException(422, "Requisition date is outside the financial year")
        if store.store_type != "BRANCH":
            raise HTTPException(422, "Only branch stores can request stock from Central Store")
        if store.office_id != office.id:
            raise HTTPException(422, "Requesting store does not belong to the selected office")
        if office.office_type != "BRANCH":
            raise HTTPException(422, "Central Store requisitions must originate from a branch office")

        await self.auth.require_store_assignment(actor_id, payload.requesting_store_id)

        seen: set[int] = set()
        lines = []
        for line in payload.lines:
            if line.item_id in seen:
                raise HTTPException(422, f"Duplicate item {line.item_id} in requisition")
            seen.add(line.item_id)
            item = await self.session.get(Item, line.item_id)
            if item is None or not item.is_active:
                raise HTTPException(404, f"Item {line.item_id} not found or inactive")
            category = await self.session.get(Category, item.category_id)
            if category is None:
                raise HTTPException(409, f"Item {line.item_id} has no valid category")
            if category.type != "CONSUMABLE":
                raise HTTPException(422, f"Central Store requisition supports consumables only: {item.code}")
            lines.append(CentralStoreRequisitionLine(
                item_id=item.id,
                requested_quantity=line.requested_quantity,
                approved_quantity=None,
                dispatched_quantity=Decimal("0"),
                received_quantity=Decimal("0"),
                remarks=line.remarks,
            ))

        requisition = CentralStoreRequisition(
            requisition_no=await self._next_number(),
            requisition_date=payload.requisition_date,
            financial_year_id=payload.financial_year_id,
            requesting_office_id=payload.requesting_office_id,
            requesting_store_id=payload.requesting_store_id,
            reference_no=payload.reference_no,
            status="SUBMITTED",
            remarks=payload.remarks,
            created_by=actor_id,
            lines=lines,
        )
        self.session.add(requisition)
        await self.session.commit()
        return await self.repository.get(requisition.id)

    async def approve_branch(self, requisition_id: int, payload: BranchApprovalRequest, actor_id: int, approve: bool = True):
        user = await self.auth.require_permission(actor_id, "REQUISITION_APPROVE_BRANCH")
        requisition = await self.repository.get(requisition_id, for_update=True)
        if requisition is None:
            raise HTTPException(404, "Requisition not found")
        if requisition.status != "SUBMITTED":
            raise HTTPException(409, f"Requisition is {requisition.status}; branch approval is not allowed")
        if user.office_id != requisition.requesting_office_id:
            raise HTTPException(403, "Branch Head can approve only their own office requisitions")
        if requisition.created_by == actor_id:
            raise HTTPException(409, "Creator cannot approve the same requisition")

        if approve:
            requisition.status = "BRANCH_APPROVED"
            requisition.branch_approved_by = actor_id
            requisition.branch_approved_at = datetime.now(timezone.utc)
        else:
            requisition.status = "REJECTED"
            requisition.remarks = payload.remarks or requisition.remarks
        if payload.remarks and approve:
            requisition.remarks = payload.remarks
        await self.session.commit()
        return await self.repository.get(requisition.id)

    async def approve_central(self, requisition_id: int, payload: CentralApprovalRequest, actor_id: int):
        user = await self.auth.require_permission(actor_id, "REQUISITION_APPROVE_CENTRAL")
        requisition = await self.repository.get(requisition_id, for_update=True)
        if requisition is None:
            raise HTTPException(404, "Requisition not found")
        if requisition.status != "BRANCH_APPROVED":
            raise HTTPException(409, f"Requisition is {requisition.status}; central approval is not allowed")
        if requisition.created_by == actor_id or requisition.branch_approved_by == actor_id:
            raise HTTPException(409, "Approver cannot approve a requisition they already created/approved")

        directorate = await self.session.scalar(select(Office).where(Office.office_type == "DIRECTORATE").order_by(Office.id))
        if directorate is not None and user.office_id != directorate.id:
            raise HTTPException(403, "Central approval is restricted to Directorate authority")

        supplied = {line.requisition_line_id: line.approved_quantity for line in payload.lines}
        expected = {line.id: line for line in requisition.lines}
        missing = sorted(set(expected) - set(supplied))
        unknown = sorted(set(supplied) - set(expected))
        if missing or unknown:
            raise HTTPException(422, f"Central approval lines must exactly match requisition lines; missing={missing}, unknown={unknown}")

        any_positive = False
        for line_id, approved_qty in supplied.items():
            line = expected[line_id]
            if approved_qty > line.requested_quantity:
                raise HTTPException(422, f"Approved quantity {approved_qty} exceeds requested quantity {line.requested_quantity} for line {line.id}")
            line.approved_quantity = approved_qty
            if approved_qty > 0:
                any_positive = True

        requisition.central_approved_by = actor_id
        requisition.central_approved_at = datetime.now(timezone.utc)
        requisition.status = "READY_FOR_TRANSFER" if any_positive else "CLOSED"
        if payload.remarks:
            requisition.remarks = payload.remarks
        if requisition.status == "CLOSED":
            requisition.closed_by = actor_id
            requisition.closed_at = datetime.now(timezone.utc)
        await self.session.commit()
        return await self.repository.get(requisition.id)

    async def reject_branch(self, requisition_id: int, payload: BranchApprovalRequest, actor_id: int):
        return await self.approve_branch(requisition_id, payload, actor_id, approve=False)

    async def list(self, requesting_store_id: int | None = None, status: str | None = None):
        return await self.repository.list(requesting_store_id, status)

    async def get(self, requisition_id: int):
        result = await self.repository.get(requisition_id)
        if result is None:
            raise HTTPException(404, "Requisition not found")
        return result

    async def _next_number(self) -> str:
        value = await self.session.scalar(text("SELECT nextval('requisition_no_seq')"))
        return f"CSR-{int(value):06d}"
