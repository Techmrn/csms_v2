from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.user import User
from app.security.auth import get_current_user
from app.schemas.asset import AssetMovementResponse, AssetResponse
from app.services.asset import AssetService

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=list[AssetResponse])
async def list_assets(
    store_id: int | None = None,
    office_id: int | None = None,
    status: str | None = None,
    item_id: int | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await AssetService(session).list(
        actor_id=current_user.id,
        store_id=store_id,
        office_id=office_id,
        status=status,
        item_id=item_id
    )


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await AssetService(session).get(asset_id)


@router.get("/{asset_id}/movements", response_model=list[AssetMovementResponse])
async def asset_movements(
    asset_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await AssetService(session).movements(asset_id)
