from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.api import (
    AprioriResponse,
    ForecastResponse,
    MLOpsStatusResponse,
    RetrainRequest,
    RetrainResponse,
)
from app.services.apriori_engine import mine_product_associations
from app.services.data_seeder import ensure_seeded_data
from app.services.forecasting import run_demand_forecast
from app.services.mlops import get_mlops_status, retrain_with_auto_rollback

router = APIRouter(tags=["ML Forecasting, Apriori & MLOps"])


@router.get("/forecast", response_model=ForecastResponse)
def get_forecast(
    sku: str = Query(default="SKU-WHOLE-MILK"),
    horizon_days: int = Query(default=7, ge=3, le=14),
    db: Session = Depends(get_db),
) -> ForecastResponse:
    """Run XGBoost vs Random Forest demand forecast and return MAE/RMSE comparison."""
    ensure_seeded_data(db)
    return run_demand_forecast(db, sku=sku, horizon_days=horizon_days)


@router.get("/apriori", response_model=AprioriResponse)
def get_apriori_rules(
    min_support: float = Query(default=0.015, ge=0.005, le=0.2),
    min_confidence: float = Query(default=0.25, ge=0.1, le=0.9),
    top_k: int = Query(default=10, ge=1, le=25),
) -> AprioriResponse:
    """Mine real supermarket basket association rules using Apriori."""
    return mine_product_associations(
        min_support=min_support,
        min_confidence=min_confidence,
        top_k=top_k,
    )


@router.get("/mlops/status", response_model=MLOpsStatusResponse)
def mlops_status(db: Session = Depends(get_db)) -> MLOpsStatusResponse:
    """Return champion model version, PSI drift status, and validation history."""
    ensure_seeded_data(db)
    return get_mlops_status(db)


@router.post("/mlops/retrain", response_model=RetrainResponse)
def mlops_retrain(req: RetrainRequest, db: Session = Depends(get_db)) -> RetrainResponse:
    """Trigger XGBoost retraining with drift evaluation and automatic rollback safety gate."""
    ensure_seeded_data(db)
    return retrain_with_auto_rollback(db, simulate_noisy_drift=req.simulate_noisy_drift)
