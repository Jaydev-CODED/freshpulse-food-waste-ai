import numpy as np
from scipy.stats import ks_2samp
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sqlalchemy.orm import Session
from xgboost import XGBRegressor

from app.core.config import get_settings
from app.core.metrics import DATA_DRIFT_PSI_GAUGE, MODEL_MAE_GAUGE, MODEL_RMSE_GAUGE
from app.models.domain import ModelRegistry, SalesRecord
from app.schemas.api import MLOpsStatusResponse, RetrainResponse
from app.services.forecasting import FEATURE_COLUMNS, _prepare_features


def compute_psi(baseline: np.ndarray, current: np.ndarray, bins: int = 8) -> float:
    """Compute Population Stability Index (PSI) between baseline and recent demand distributions."""
    if len(baseline) < 5 or len(current) < 5:
        return 0.0
    quantiles = np.linspace(0, 100, bins + 1)
    edges = np.unique(np.percentile(baseline, quantiles))
    if len(edges) < 3:
        return 0.0
    base_counts, _ = np.histogram(baseline, bins=edges)
    curr_counts, _ = np.histogram(current, bins=edges)

    base_pct = np.clip(base_counts / max(len(baseline), 1), 1e-4, 1.0)
    curr_pct = np.clip(curr_counts / max(len(current), 1), 1e-4, 1.0)
    psi = float(np.sum((curr_pct - base_pct) * np.log(curr_pct / base_pct)))
    return round(max(0.0, psi), 4)


def ensure_initial_model_registered(db: Session) -> ModelRegistry:
    """Ensure a baseline champion XGBoost model exists in ModelRegistry."""
    champion = (
        db.query(ModelRegistry)
        .filter(ModelRegistry.is_champion.is_(True))
        .order_by(ModelRegistry.id.desc())
        .first()
    )
    if champion:
        return champion

    records = (
        db.query(SalesRecord)
        .filter(SalesRecord.sku == "SKU-WHOLE-MILK")
        .order_by(SalesRecord.sale_date.asc())
        .all()
    )
    df = _prepare_features(records)
    split = max(10, int(len(df) * 0.8))

    model = XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.08, random_state=42)
    model.fit(df.iloc[:split][FEATURE_COLUMNS], df.iloc[:split]["units_sold"])
    preds = model.predict(df.iloc[split:][FEATURE_COLUMNS])
    actual = df.iloc[split:]["units_sold"]

    mae = round(float(mean_absolute_error(actual, preds)), 3)
    rmse = round(float(root_mean_squared_error(actual, preds)), 3)
    r2 = round(float(r2_score(actual, preds)), 3)
    psi = compute_psi(df.iloc[:split]["units_sold"].to_numpy(), df.iloc[split:]["units_sold"].to_numpy())

    entry = ModelRegistry(
        model_name="XGBoost-DemandForecaster",
        version="v1.0.0",
        mae=mae,
        rmse=rmse,
        r2_score=r2,
        drift_psi=psi,
        is_champion=True,
        status="champion",
        notes="Initial champion trained on real Kaggle grocery-anchored demand telemetry",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    MODEL_MAE_GAUGE.labels(model_name="XGBoost").set(mae)
    MODEL_RMSE_GAUGE.labels(model_name="XGBoost").set(rmse)
    DATA_DRIFT_PSI_GAUGE.set(psi)
    return entry


def get_mlops_status(db: Session) -> MLOpsStatusResponse:
    """Return current champion model metadata, drift metrics, and version history."""
    settings = get_settings()
    champion = ensure_initial_model_registered(db)
    rows = db.query(ModelRegistry).order_by(ModelRegistry.id.desc()).limit(10).all()

    history = [
        {
            "version": r.version,
            "model_name": r.model_name,
            "mae": r.mae,
            "rmse": r.rmse,
            "r2_score": r.r2_score,
            "drift_psi": r.drift_psi,
            "is_champion": r.is_champion,
            "status": r.status,
            "notes": r.notes,
            "trained_at": r.trained_at.isoformat(),
        }
        for r in rows
    ]
    DATA_DRIFT_PSI_GAUGE.set(champion.drift_psi)

    return MLOpsStatusResponse(
        champion_model=champion.model_name,
        champion_version=champion.version,
        champion_mae=champion.mae,
        champion_rmse=champion.rmse,
        drift_psi=champion.drift_psi,
        drift_detected=champion.drift_psi >= settings.drift_psi_threshold,
        drift_threshold=settings.drift_psi_threshold,
        auto_rollback_tolerance=settings.auto_rollback_mae_tolerance,
        mlflow_tracking_uri=settings.mlflow_tracking_uri,
        history=history,
    )


def retrain_with_auto_rollback(
    db: Session,
    simulate_noisy_drift: bool = False,
) -> RetrainResponse:
    """Retrain XGBoost candidate, evaluate Evidently-style PSI/KS drift, and auto-rollback on degradation."""
    settings = get_settings()
    champion = ensure_initial_model_registered(db)

    records = (
        db.query(SalesRecord)
        .filter(SalesRecord.sku == "SKU-WHOLE-MILK")
        .order_by(SalesRecord.sale_date.asc())
        .all()
    )
    df = _prepare_features(records)
    split = max(10, int(len(df) * 0.8))

    train_df = df.iloc[:split].copy()
    test_df = df.iloc[split:].copy()

    if simulate_noisy_drift:
        # Inject severe label/sensor corruption to demonstrate the safety auto-rollback gate
        rng = np.random.default_rng(99)
        train_df["units_sold"] = train_df["units_sold"] + rng.normal(0, 14.0, size=len(train_df))
        test_df_shifted = test_df["units_sold"].to_numpy() * 1.45
    else:
        test_df_shifted = test_df["units_sold"].to_numpy()

    psi = compute_psi(df.iloc[:split]["units_sold"].to_numpy(), test_df_shifted)
    _, ks_p_value = ks_2samp(df.iloc[:split]["units_sold"].to_numpy(), test_df_shifted)
    DATA_DRIFT_PSI_GAUGE.set(psi)

    candidate = XGBRegressor(
        n_estimators=150,
        max_depth=5 if not simulate_noisy_drift else 2,
        learning_rate=0.06,
        subsample=0.92,
        random_state=7,
    )
    candidate.fit(train_df[FEATURE_COLUMNS], train_df["units_sold"])
    preds = candidate.predict(test_df[FEATURE_COLUMNS])

    new_mae = round(float(mean_absolute_error(test_df["units_sold"], preds)), 3)
    new_rmse = round(float(root_mean_squared_error(test_df["units_sold"], preds)), 3)
    new_r2 = round(float(r2_score(test_df["units_sold"], preds)), 3)

    total_versions = db.query(ModelRegistry).count()
    next_version = f"v1.{total_versions}.0"
    allowed_max_mae = champion.mae * settings.auto_rollback_mae_tolerance

    if new_mae > allowed_max_mae:
        # Validation failed -> Auto-rollback! Keep previous champion active.
        rolled_entry = ModelRegistry(
            model_name="XGBoost-DemandForecaster",
            version=next_version,
            mae=new_mae,
            rmse=new_rmse,
            r2_score=new_r2,
            drift_psi=psi,
            is_champion=False,
            status="rolled_back",
            notes=(
                f"Auto-rollback triggered: MAE {new_mae} > threshold {allowed_max_mae:.3f} "
                f"(KS p={ks_p_value:.3f})"
            ),
        )
        db.add(rolled_entry)
        db.commit()
        return RetrainResponse(
            action="rolled_back",
            rolled_back=True,
            new_version=next_version,
            new_mae=new_mae,
            baseline_mae=champion.mae,
            drift_psi=psi,
            message=(
                f"Validation failed (MAE {new_mae} > {allowed_max_mae:.3f}). "
                f"Auto-rollback preserved champion {champion.version}."
            ),
        )

    # Promote candidate to champion
    db.query(ModelRegistry).filter(ModelRegistry.is_champion.is_(True)).update({"is_champion": False})
    promoted_entry = ModelRegistry(
        model_name="XGBoost-DemandForecaster",
        version=next_version,
        mae=new_mae,
        rmse=new_rmse,
        r2_score=new_r2,
        drift_psi=psi,
        is_champion=True,
        status="promoted",
        notes=f"Promoted via automated validation gate (KS p={ks_p_value:.3f}, PSI={psi})",
    )
    db.add(promoted_entry)
    db.commit()

    MODEL_MAE_GAUGE.labels(model_name="XGBoost").set(new_mae)
    MODEL_RMSE_GAUGE.labels(model_name="XGBoost").set(new_rmse)

    return RetrainResponse(
        action="promoted",
        rolled_back=False,
        new_version=next_version,
        new_mae=new_mae,
        baseline_mae=champion.mae,
        drift_psi=psi,
        message=f"Candidate {next_version} validated (MAE {new_mae}) and promoted to champion.",
    )
