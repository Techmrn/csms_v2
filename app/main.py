from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.db.session import engine
from app.web.routes import router as web_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api")

WEB_ROOT = Path(__file__).resolve().parent / "web"
STATIC_DIR = WEB_ROOT / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(web_router)
