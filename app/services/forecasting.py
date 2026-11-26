from datetime import date, timedelta

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sqlalchemy.orm import Session
from xgboost import XGBRegressor

from app.core.metrics import MODEL_MAE_GAUGE, MODEL_RMSE_GAUGE
from app.models.domain import InventoryItem, SalesRecord
from app.schemas.api import ForecastPoint, ForecastResponse, ModelComparisonMetric
from app.services.external_apis import fetch_live_weather, fetch_upcoming_holidays

FEATURE_COLUMNS = [
    "day_of_week",
    "is_weekend",
    "temperature_c",
    "humidity_pct",
    "is_holiday",
    "promo_discount_pct",
    "lag_1_demand",
    "rolling_7d_demand",
]


def _prepare_features(records: list[SalesRecord]) -> pd.DataFrame:
    df = pd.DataFrame(
        [
            {
                "sale_date": r.sale_date,
                "units_sold": r.units_sold,
                "temperature_c": r.temperature_c,
                "humidity_pct": r.humidity_pct,
                "is_holiday": int(r.is_holiday),
                "promo_discount_pct": r.promo_discount_pct,
            }
            for r in records
        ]
    ).sort_values("sale_date")

    df["day_of_week"] = pd.to_datetime(df["sale_date"]).dt.day_of_week
    df["is_weekend"] = (df["day_of_week"] >= 4).astype(int)
    df["lag_1_demand"] = df["units_sold"].shift(1).bfill()
    df["rolling_7d_demand"] = (
        df["units_sold"].rolling(window=7, min_periods=1).mean().shift(1).bfill()
    )
    return df


def run_demand_forecast(
    db: Session,
    sku: str = "SKU-WHOLE-MILK",
    horizon_days: int = 7,
) -> ForecastResponse:
    """Train and compare XGBoost vs Random Forest demand forecasters for a perishable SKU."""
    item = db.query(InventoryItem).filter(InventoryItem.sku == sku).first()
    if not item:
        item = db.query(InventoryItem).first()
    if not item:
        raise ValueError("No inventory items available for forecasting.")

    records = (
        db.query(SalesRecord)
        .filter(SalesRecord.sku == item.sku)
        .order_by(SalesRecord.sale_date.asc())
        .all()
    )
    if len(records) < 14:
        raise ValueError(f"Insufficient historical records for {item.sku}.")

    df = _prepare_features(records)
    split_idx = max(10, int(len(df) * 0.8))

    X_train = df.iloc[:split_idx][FEATURE_COLUMNS]
    y_train = df.iloc[:split_idx]["units_sold"]
    X_test = df.iloc[split_idx:][FEATURE_COLUMNS]
    y_test = df.iloc[split_idx:]["units_sold"]

    xgb_model = XGBRegressor(
        n_estimators=120,
        max_depth=4,
        learning_rate=0.08,
        subsample=0.9,
        random_state=42,
    )
    rf_model = RandomForestRegressor(n_estimators=120, max_depth=6, random_state=42)

    xgb_model.fit(X_train, y_train)
    rf_model.fit(X_train, y_train)

    xgb_test_pred = xgb_model.predict(X_test)
    rf_test_pred = rf_model.predict(X_test)

    xgb_mae = float(round(mean_absolute_error(y_test, xgb_test_pred), 3))
    xgb_rmse = float(round(root_mean_squared_error(y_test, xgb_test_pred), 3))
    xgb_r2 = float(round(r2_score(y_test, xgb_test_pred), 3))

    rf_mae = float(round(mean_absolute_error(y_test, rf_test_pred), 3))
    rf_rmse = float(round(root_mean_squared_error(y_test, rf_test_pred), 3))
    rf_r2 = float(round(r2_score(y_test, rf_test_pred), 3))

    MODEL_MAE_GAUGE.labels(model_name="XGBoost").set(xgb_mae)
    MODEL_RMSE_GAUGE.labels(model_name="XGBoost").set(xgb_rmse)
    MODEL_MAE_GAUGE.labels(model_name="RandomForest").set(rf_mae)
    MODEL_RMSE_GAUGE.labels(model_name="RandomForest").set(rf_rmse)

    champion = "XGBoost" if xgb_mae <= rf_mae else "RandomForest"

    # Build backtest + future forecast series enriched with real weather & holiday context
    series: list[ForecastPoint] = []
    tail_df = df.iloc[split_idx:]
    for idx, (_, row) in enumerate(tail_df.iterrows()):
        series.append(
            ForecastPoint(
                date=row["sale_date"],
                actual_demand=round(float(row["units_sold"]), 2),
                xgboost_pred=round(float(xgb_test_pred[idx]), 2),
                random_forest_pred=round(float(rf_test_pred[idx]), 2),
            )
        )

    weather = fetch_live_weather()
    holiday_dates = {h.date for h in fetch_upcoming_holidays()}
    last_date: date = df["sale_date"].iloc[-1]
    last_demand = float(df["units_sold"].iloc[-1])
    recent_window = list(df["units_sold"].iloc[-7:].astype(float))

    for step in range(1, horizon_days + 1):
        fut_date = last_date + timedelta(days=step)
        dow = fut_date.weekday()
        feat_row = pd.DataFrame(
            [
                {
                    "day_of_week": dow,
                    "is_weekend": int(dow >= 4),
                    "temperature_c": weather.temperature_c,
                    "humidity_pct": weather.humidity_pct,
                    "is_holiday": int(fut_date in holiday_dates),
                    "promo_discount_pct": 10.0 if item.days_remaining <= 2 else 0.0,
                    "lag_1_demand": last_demand,
                    "rolling_7d_demand": float(np.mean(recent_window[-7:])),
                }
            ]
        )
        xgb_fut = float(max(1.0, xgb_model.predict(feat_row)[0]))
        rf_fut = float(max(1.0, rf_model.predict(feat_row)[0]))
        series.append(
            ForecastPoint(
                date=fut_date,
                actual_demand=None,
                xgboost_pred=round(xgb_fut, 2),
                random_forest_pred=round(rf_fut, 2),
            )
        )
        last_demand = xgb_fut
        recent_window.append(xgb_fut)

    importances = {
        col: round(float(val), 4)
        for col, val in zip(FEATURE_COLUMNS, xgb_model.feature_importances_, strict=True)
    }

    return ForecastResponse(
        sku=item.sku,
        item_name=item.name,
        horizon_days=horizon_days,
        champion_model=champion,
        metrics=[
            ModelComparisonMetric(
                model_name="XGBoost", mae=xgb_mae, rmse=xgb_rmse, r2_score=xgb_r2
            ),
            ModelComparisonMetric(
                model_name="RandomForest", mae=rf_mae, rmse=rf_rmse, r2_score=rf_r2
            ),
        ],
        feature_importances=importances,
        series=series,
    )
