from fastapi import APIRouter, Depends
from app.api.routes.auth import router as auth_router
from app.security.auth import get_current_user

from app.api.routes.health import router as health_router
from app.api.routes.indents import router as indents_router
from app.api.routes.receipts import router as receipts_router
from app.api.routes.returns import router as returns_router
from app.api.routes.masters import router as masters_router
from app.api.routes.offices import router as offices_router
from app.api.routes.stock import router as stock_router
from app.api.routes.stores import router as stores_router
from app.api.routes.requisitions import router as requisitions_router
from app.api.routes.transfers import router as transfers_router
from app.api.routes.petty_purchases import router as petty_purchases_router
from app.api.routes.assets import router as assets_router
from app.api.routes.stock_control import (
    verification_router as stock_verification_router,
    adjustment_router as stock_adjustment_router,
    unserviceable_router,
)

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(health_router)

protected_router = APIRouter(dependencies=[Depends(get_current_user)])
protected_router.include_router(offices_router)
protected_router.include_router(stores_router)
protected_router.include_router(masters_router)
protected_router.include_router(stock_router)
protected_router.include_router(indents_router)
protected_router.include_router(receipts_router)
protected_router.include_router(returns_router)
protected_router.include_router(requisitions_router)
protected_router.include_router(transfers_router)
protected_router.include_router(petty_purchases_router)
protected_router.include_router(stock_verification_router)
protected_router.include_router(stock_adjustment_router)
protected_router.include_router(unserviceable_router)
protected_router.include_router(assets_router)

api_router.include_router(protected_router)
