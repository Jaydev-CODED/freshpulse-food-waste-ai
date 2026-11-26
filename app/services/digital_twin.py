import time

import numpy as np
from sqlalchemy.orm import Session

from app.core.metrics import SIMULATION_LATENCY_SECONDS
from app.models.domain import InventoryItem, SalesRecord
from app.schemas.api import DigitalTwinDayStats, DigitalTwinRequest, DigitalTwinResponse


def run_monte_carlo_digital_twin(db: Session, req: DigitalTwinRequest) -> DigitalTwinResponse:
    """Simulate stochastic future inventory paths (Digital Twin) to quantify stockout and spoilage risk."""
    started = time.perf_counter()
    item = db.query(InventoryItem).filter(InventoryItem.sku == req.sku).first()
    if not item:
        item = db.query(InventoryItem).first()
    if not item:
        raise ValueError("No inventory item found for simulation.")

    sales = db.query(SalesRecord.units_sold).filter(SalesRecord.sku == item.sku).all()
    demand_vals = np.array([row[0] for row in sales], dtype=float)
    mean_demand = float(np.mean(demand_vals)) if len(demand_vals) else 15.0
    std_demand = float(max(2.0, np.std(demand_vals))) if len(demand_vals) else 3.5

    # Markdown discount boosts daily demand elasticity
    markdown_boost = 1.0 + (req.markdown_pct / 100.0) * 1.5
    adj_mean = mean_demand * markdown_boost

    rng = np.random.default_rng(123)
    stock_paths = np.zeros((req.simulations, req.horizon_days), dtype=float)
    spoilage_paths = np.zeros((req.simulations, req.horizon_days), dtype=float)
    stockout_events = np.zeros(req.simulations, dtype=bool)

    for sim_idx in range(req.simulations):
        stock = float(item.current_stock_kg)
        remaining_life = int(item.days_remaining)
        for day_idx in range(req.horizon_days):
            # Replenishment arrives after supplier lead time on day == supplier_lead_days
            if day_idx == item.supplier_lead_days and req.reorder_qty_kg > 0:
                stock += req.reorder_qty_kg
                remaining_life = max(remaining_life, item.shelf_life_days)

            daily_demand = max(0.0, rng.normal(adj_mean, std_demand))
            sold = min(stock, daily_demand)
            if daily_demand > stock:
                stockout_events[sim_idx] = True

            stock -= sold

            # Perishable spoilage: accelerated loss when batch reaches expiry day
            if remaining_life <= 0 and stock > 0:
                spoiled = stock * 0.85
                remaining_life = item.shelf_life_days
            else:
                spoiled = stock * (item.spoilage_rate_per_day * 0.5)
            stock = max(0.0, stock - spoiled)
            remaining_life -= 1

            stock_paths[sim_idx, day_idx] = stock
            spoilage_paths[sim_idx, day_idx] = spoiled

    trajectory: list[DigitalTwinDayStats] = []
    for day_idx in range(req.horizon_days):
        day_stocks = stock_paths[:, day_idx]
        trajectory.append(
            DigitalTwinDayStats(
                day=day_idx + 1,
                p10_stock=round(float(np.percentile(day_stocks, 10)), 2),
                p50_stock=round(float(np.percentile(day_stocks, 50)), 2),
                p90_stock=round(float(np.percentile(day_stocks, 90)), 2),
                expected_spoilage_kg=round(float(np.mean(spoilage_paths[:, day_idx])), 2),
            )
        )

    total_waste_per_sim = np.sum(spoilage_paths, axis=1)
    expected_waste_kg = float(np.mean(total_waste_per_sim))
    spoilage_prob = float(np.mean(total_waste_per_sim > 5.0) * 100.0)
    stockout_prob = float(np.mean(stockout_events) * 100.0)

    SIMULATION_LATENCY_SECONDS.labels(engine="monte_carlo").observe(time.perf_counter() - started)

    return DigitalTwinResponse(
        sku=item.sku,
        item_name=item.name,
        simulations=req.simulations,
        horizon_days=req.horizon_days,
        stockout_probability_pct=round(stockout_prob, 2),
        spoilage_probability_pct=round(spoilage_prob, 2),
        expected_total_waste_kg=round(expected_waste_kg, 2),
        expected_waste_cost_usd=round(expected_waste_kg * item.unit_cost, 2),
        trajectory=trajectory,
    )
