from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.api import (
    AlertsResponse,
    DigitalTwinRequest,
    DigitalTwinResponse,
    OptimizationRequest,
    OptimizationResponse,
)
from app.services.data_seeder import ensure_seeded_data
from app.services.digital_twin import run_monte_carlo_digital_twin
from app.services.optimizer import run_linear_programming_optimizer
from app.services.rule_engine import evaluate_rule_engine

router = APIRouter(tags=["Digital Twin, LP Optimization & Rules"])


@router.post("/digital-twin/simulate", response_model=DigitalTwinResponse)
def simulate_digital_twin(
    req: DigitalTwinRequest,
    db: Session = Depends(get_db),
) -> DigitalTwinResponse:
    """Run Monte Carlo Digital Twin stochastic inventory simulation."""
    ensure_seeded_data(db)
    return run_monte_carlo_digital_twin(db, req)


@router.post("/optimize/linear-programming", response_model=OptimizationResponse)
def optimize_inventory(
    req: OptimizationRequest,
    db: Session = Depends(get_db),
) -> OptimizationResponse:
    """Run Linear Programming optimization for profit maximization and waste minimization."""
    ensure_seeded_data(db)
    return run_linear_programming_optimizer(db, req)


@router.get("/alerts", response_model=AlertsResponse)
def get_rule_alerts(db: Session = Depends(get_db)) -> AlertsResponse:
    """Evaluate Rule-Based Engine for expiry markdowns, cold-chain risks, and reorders."""
    ensure_seeded_data(db)
    return evaluate_rule_engine(db)
