from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

from app.api.router import api_router
from app.core.config import get_settings
from app.db.session import engine
from app.web.routes import router as web_router
from app.web.master_routes import router as master_router


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

from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)

from fastapi.responses import RedirectResponse, JSONResponse

app.include_router(api_router, prefix="/api")


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    from urllib.parse import quote
    message = "This entry already exists or conflicts with existing data. Please check the code/name and try again."
    if request.method in {"POST", "PUT", "PATCH"} and ("text/html" in request.headers.get("accept", "") or request.cookies.get("csms_access_token")):
        target = request.headers.get("referer") or request.url.path
        separator = "&" if "?" in target else "?"
        return RedirectResponse(url=f"{target}{separator}error={quote(message)}", status_code=303)
    return JSONResponse(status_code=409, content={"detail": message})


WEB_ROOT = Path(__file__).resolve().parent / "web"
STATIC_DIR = WEB_ROOT / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
import time


@app.middleware("http")
async def performance_and_cache_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    response.headers["X-Process-Time"] = f"{duration:.3f}s"
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    if not request.url.path.startswith("/api/health"):
        print(f"[{request.method}] {request.url.path} -> {response.status_code} ({duration:.3f}s)")
    return response


@app.middleware("http")
async def normalize_duplicate_app_prefix(request, call_next):
    # Defensive normalization for accidentally generated /app/app/...,
    # /app//app/..., or deeper repeated application prefixes.
    path = request.url.path

    if path.startswith("/app/"):
        remainder = path[5:]
        # Collapse repeated slash + app segments at the beginning:
        # /app/app/foo -> /app/foo
        # /app//app/foo -> /app/foo
        # /app/app/app/foo -> /app/foo
        while remainder.startswith("/"):
            remainder = remainder[1:]
        while remainder.startswith("app/"):
            remainder = remainder[4:]
            while remainder.startswith("/"):
                remainder = remainder[1:]

        normalized_path = "/app/" + remainder if remainder else "/app"
        if normalized_path != path:
            query = request.url.query
            target = normalized_path + (f"?{query}" if query else "")
            from starlette.responses import RedirectResponse
            return RedirectResponse(url=target, status_code=307)

    return await call_next(request)


app.include_router(web_router)
app.include_router(master_router)
