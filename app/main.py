from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.debug_log import debug_log
from app.core.db import check_db_connection
from app.web.dashboard import router as dashboard_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.DATA_DIR.mkdir(exist_ok=True)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(dashboard_router)

# region agent log
class _DebugRequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        import time

        t0 = time.perf_counter()
        try:
            response = await call_next(request)
            status = getattr(response, "status_code", None)
            return response
        except Exception as e:
            debug_log(
                run_id="pre-fix",
                hypothesis_id="H2",
                location="app/main.py:_DebugRequestTimingMiddleware",
                message="request_exception",
                data={
                    "method": getattr(request, "method", None),
                    "path": getattr(getattr(request, "url", None), "path", None),
                    "exc_type": type(e).__name__,
                },
            )
            raise
        finally:
            try:
                debug_log(
                    run_id="pre-fix",
                    hypothesis_id="H2",
                    location="app/main.py:_DebugRequestTimingMiddleware",
                    message="request_timing",
                    data={
                        "method": getattr(request, "method", None),
                        "path": getattr(getattr(request, "url", None), "path", None),
                        "status": status if "status" in locals() else None,
                        "duration_ms": int((time.perf_counter() - t0) * 1000),
                    },
                )
            except Exception:
                pass


app.add_middleware(_DebugRequestTimingMiddleware)
# endregion


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV,
    }


@app.get("/health/db")
def health_db():
    return {
        "status": "ok" if check_db_connection() else "error",
        "database_url": settings.DATABASE_URL,
    }


@app.get("/health/collectors")
def health_collectors():
    return {
        "status": "ok",
        "timeout": settings.COLLECTOR_TIMEOUT,
        "concurrency": settings.COLLECTOR_CONCURRENCY,
    }


@app.get("/")
def root():
    return {
        "message": "Validator Dashboard API is running",
        "health": "/health",
        "health_db": "/health/db",
        "health_collectors": "/health/collectors",
        "dashboard": "/dashboard",
        "rewards": "/dashboard/rewards",
        "alerts": "/dashboard/alerts",
        "public_rpc": "/dashboard/public-rpc",
        "snapshots": "/dashboard/snapshots",
    }
