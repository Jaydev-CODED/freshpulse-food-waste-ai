from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict:
    """Verify API and database connectivity."""
    settings = get_settings()
    db.execute(text("SELECT 1"))
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "database": "postgresql" if "postgresql" in settings.database_url else "sqlite",
    }
