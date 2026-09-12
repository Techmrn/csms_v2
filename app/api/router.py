from fastapi import APIRouter

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
from app.api.routes.stock_control import (
    verification_router as stock_verification_router,
    adjustment_router as stock_adjustment_router,
    unserviceable_router,
)

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(offices_router)
api_router.include_router(stores_router)
api_router.include_router(masters_router)
api_router.include_router(stock_router)
api_router.include_router(indents_router)
api_router.include_router(receipts_router)
api_router.include_router(returns_router)
api_router.include_router(requisitions_router)
api_router.include_router(transfers_router)
api_router.include_router(petty_purchases_router)
api_router.include_router(stock_verification_router)
api_router.include_router(stock_adjustment_router)
api_router.include_router(unserviceable_router)
