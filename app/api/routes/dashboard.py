from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.metrics import INVENTORY_VALUE_AT_RISK_GAUGE, PREDICTED_WASTE_KG_GAUGE
from app.models.domain import InventoryItem, SalesRecord
from app.schemas.api import DashboardSummaryResponse, InventorySummaryItem, OptimizationRequest
from app.services.data_seeder import ensure_seeded_data
from app.services.external_apis import (
    fetch_live_weather,
    fetch_upcoming_holidays,
    get_supplier_telemetry,
)
from app.services.optimizer import run_linear_programming_optimizer

router = APIRouter(tags=["Dashboard & Real-Time Ingestion"])


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(db: Session = Depends(get_db)) -> DashboardSummaryResponse:
    """Return real-time KPIs, external weather/holiday feeds, suppliers, and perishable inventory."""
    ingest_info = ensure_seeded_data(db, force_sync=False)
    weather = fetch_live_weather()
    holidays = fetch_upcoming_holidays()
    suppliers = get_supplier_telemetry()

    items = db.query(InventoryItem).order_by(InventoryItem.days_remaining.asc()).all()
    total_stock_kg = sum(i.current_stock_kg for i in items)
    value_at_risk = sum(i.current_stock_kg * i.unit_cost for i in items if i.days_remaining <= 2)
    critical_skus = sum(1 for i in items if i.days_remaining <= 1)

    opt_snapshot = run_linear_programming_optimizer(db, OptimizationRequest())
    total_sales_rows = db.query(SalesRecord).count()

    INVENTORY_VALUE_AT_RISK_GAUGE.set(round(value_at_risk, 2))
    PREDICTED_WASTE_KG_GAUGE.set(opt_snapshot.total_projected_waste_kg)

    inventory_out = [
        InventorySummaryItem(
            sku=i.sku,
            name=i.name,
            category=i.category,
            current_stock_kg=i.current_stock_kg,
            unit_cost=i.unit_cost,
            selling_price=i.selling_price,
            shelf_life_days=i.shelf_life_days,
            days_remaining=i.days_remaining,
            supplier_name=i.supplier_name,
            supplier_lead_days=i.supplier_lead_days,
            basket_frequency=i.basket_frequency,
            value_at_risk_usd=round(i.current_stock_kg * i.unit_cost, 2)
            if i.days_remaining <= 2
            else 0.0,
        )
        for i in items
    ]

    return DashboardSummaryResponse(
        kpis={
            "total_skus": len(items),
            "total_stock_kg": round(total_stock_kg, 2),
            "inventory_value_at_risk_usd": round(value_at_risk, 2),
            "critical_expiry_skus": critical_skus,
            "projected_waste_kg": opt_snapshot.total_projected_waste_kg,
            "waste_reduction_pct": opt_snapshot.waste_reduction_pct,
            "projected_7d_profit_usd": opt_snapshot.total_projected_profit_usd,
            "sales_records_count": total_sales_rows,
            "currency": "INR",
            "currency_symbol": "₹",
        },
        weather=weather,
        upcoming_holidays=holidays,
        suppliers=suppliers,
        inventory=inventory_out,
        data_source_info=ingest_info,
    )


@router.post("/data/sync")
def sync_realtime_data(db: Session = Depends(get_db)) -> dict:
    """Force re-ingestion of Kaggle/UCI groceries feed, live weather, and holiday signals."""
    info = ensure_seeded_data(db, force_sync=True)
    return {"status": "synced", **info}
