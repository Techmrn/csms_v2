from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.security.auth import get_current_user
from app.models.user import User
from app.schemas.indent import IndentCreate, IndentResponse, IssueFinalizeRequest, IssueResponse
from app.services.indent import IndentService
from app.services.issue import IssueService

router = APIRouter(prefix="/indents", tags=["indents"])


@router.post("", response_model=IndentResponse, status_code=status.HTTP_201_CREATED)
async def create_indent(payload: IndentCreate, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return await IndentService(session).create(payload)


@router.get("", response_model=list[IndentResponse])
async def list_indents(
    store_id: int | None = None,
    status: str | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    return await IndentService(session).list(store_id, status)


@router.get("/{indent_id}", response_model=IndentResponse)
async def get_indent(indent_id: int, current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db_session)):
    return await IndentService(session).get(indent_id)


@router.post("/{indent_id}/finalize-issue", response_model=IssueResponse)
async def finalize_issue(
    indent_id: int,
    payload: IssueFinalizeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await IssueService(session).finalize_from_indent(indent_id, payload)
