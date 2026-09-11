from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.api.routes.indents import router as indents_router
from app.api.routes.masters import router as masters_router
from app.api.routes.offices import router as offices_router
from app.api.routes.stock import router as stock_router
from app.api.routes.stores import router as stores_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(offices_router)
api_router.include_router(stores_router)
api_router.include_router(masters_router)
api_router.include_router(stock_router)
api_router.include_router(indents_router)
