from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import SessionLocal, init_db
from app.core.metrics import API_REQUESTS_TOTAL
from app.services.data_seeder import ensure_seeded_data

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize database schema and ensure real-data baseline is loaded on startup."""
    init_db()
    db = SessionLocal()
    try:
        ensure_seeded_data(db)
    finally:
        db.close()
    yield


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def prometheus_request_middleware(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(settings.api_prefix):
            API_REQUESTS_TOTAL.labels(
                endpoint=request.url.path,
                method=request.method,
                status=str(response.status_code),
            ).inc()
        return response

    application.include_router(api_router, prefix=settings.api_prefix)
    application.mount("/metrics", make_asgi_app())

    if FRONTEND_DIR.exists():
        application.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @application.get("/", include_in_schema=False)
    def serve_dashboard():
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"message": settings.app_name, "docs": "/docs"}

    return application


app = create_app()
