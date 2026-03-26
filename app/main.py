from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
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
