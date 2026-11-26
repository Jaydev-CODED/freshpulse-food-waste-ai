from fastapi import APIRouter

from app.api.routes import dashboard, health, ml, optimization

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(dashboard.router)
api_router.include_router(ml.router)
api_router.include_router(optimization.router)
