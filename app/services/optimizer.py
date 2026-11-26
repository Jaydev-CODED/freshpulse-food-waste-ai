import time

import numpy as np
import pulp
from sqlalchemy.orm import Session

from app.core.metrics import (
    INVENTORY_VALUE_AT_RISK_GAUGE,
    PREDICTED_WASTE_KG_GAUGE,
    SIMULATION_LATENCY_SECONDS,
)
from app.models.domain import InventoryItem, SalesRecord
from app.schemas.api import OptimizationRequest, OptimizationResponse, OptimizedSkuPlan


def run_linear_programming_optimizer(
    db: Session,
    req: OptimizationRequest,
) -> OptimizationResponse:
    """Solve a Linear Program maximizing net perishable profit while minimizing spoilage waste."""
    started = time.perf_counter()
    items = db.query(InventoryItem).order_by(InventoryItem.sku.asc()).all()
    if not items:
        raise ValueError("No inventory items available for optimization.")

    # Estimate 7-day demand horizon per SKU from historical records
    demand_7d: dict[str, float] = {}
    for item in items:
        sales = db.query(SalesRecord.units_sold).filter(SalesRecord.sku == item.sku).all()
        avg_daily = float(np.mean([s[0] for s in sales])) if sales else 15.0
        demand_7d[item.sku] = round(avg_daily * 7.0, 2)

    prob = pulp.LpProblem("FreshPulse_Profit_Waste_Optimization", pulp.LpMaximize)

    order_vars = {
        item.sku: pulp.LpVariable(f"order_{item.sku}", lowBound=0, upBound=250) for item in items
    }
    markdown_vars = {
        item.sku: pulp.LpVariable(f"markdown_{item.sku}", lowBound=0, upBound=40) for item in items
    }
    sell_vars = {item.sku: pulp.LpVariable(f"sell_{item.sku}", lowBound=0) for item in items}
    waste_vars = {item.sku: pulp.LpVariable(f"waste_{item.sku}", lowBound=0) for item in items}

    # Objective: Maximize Gross Revenue - Order Cost - Waste Penalty (with markdown clearance incentive)
    objective_terms = []
    for item in items:
        margin_revenue = item.selling_price * sell_vars[item.sku]
        # Discount cost approximation linearized at average clearance volume
        discount_cost = 0.008 * item.selling_price * item.current_stock_kg * markdown_vars[item.sku]
        procurement_cost = item.unit_cost * order_vars[item.sku]
        waste_penalty = (item.unit_cost * 1.65) * waste_vars[item.sku]
        objective_terms.append(margin_revenue - discount_cost - procurement_cost - waste_penalty)

    prob += pulp.lpSum(objective_terms)

    # Global constraints: procurement budget and cold-storage capacity
    prob += (
        pulp.lpSum(item.unit_cost * order_vars[item.sku] for item in items) <= req.max_budget_usd
    )
    prob += (
        pulp.lpSum(item.current_stock_kg + order_vars[item.sku] for item in items)
        <= req.max_cold_storage_kg
    )

    for item in items:
        d7 = demand_7d[item.sku]
        # Markdown increases effective sellable demand by up to 0.8% per 1% discount
        effective_demand_cap = d7 + (0.008 * d7) * markdown_vars[item.sku]
        available_stock = item.current_stock_kg + order_vars[item.sku]

        # Sales cannot exceed available stock or price-elastic demand
        prob += sell_vars[item.sku] <= available_stock
        prob += sell_vars[item.sku] <= effective_demand_cap

        # Remaining unsold stock scaled by expiry urgency becomes waste
        expiry_risk = 0.65 if item.days_remaining <= 2 else 0.25
        prob += waste_vars[item.sku] >= expiry_risk * (available_stock - sell_vars[item.sku])

        # Do not reorder if item is already within 1 day of expiry and overstocked
        if item.days_remaining <= 1 and item.current_stock_kg > d7 * 0.5:
            prob += order_vars[item.sku] == 0

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    status_str = pulp.LpStatus.get(prob.status, "Unknown")

    allocations: list[OptimizedSkuPlan] = []
    total_profit = 0.0
    total_waste = 0.0
    baseline_waste = 0.0
    budget_used = 0.0
    storage_used = 0.0
    value_at_risk = 0.0

    for item in items:
        order_q = round(float(pulp.value(order_vars[item.sku]) or 0.0), 2)
        md_pct = round(float(pulp.value(markdown_vars[item.sku]) or 0.0), 1)
        sold_q = round(float(pulp.value(sell_vars[item.sku]) or 0.0), 2)
        waste_q = round(float(pulp.value(waste_vars[item.sku]) or 0.0), 2)

        effective_price = item.selling_price * (1.0 - md_pct / 100.0)
        sku_profit = round(
            (effective_price * sold_q) - (item.unit_cost * (order_q + waste_q)),
            2,
        )

        # Baseline waste without optimization (naive reorder + no markdown)
        d7 = demand_7d[item.sku]
        naive_unsold = max(
            0.0, item.current_stock_kg + max(0.0, d7 - item.current_stock_kg * 0.5) - d7
        )
        expiry_risk = 0.65 if item.days_remaining <= 2 else 0.25
        baseline_waste += round(
            naive_unsold * expiry_risk + item.current_stock_kg * item.spoilage_rate_per_day, 2
        )

        total_profit += sku_profit
        total_waste += waste_q
        budget_used += order_q * item.unit_cost
        storage_used += item.current_stock_kg + order_q
        if item.days_remaining <= 2:
            value_at_risk += item.current_stock_kg * item.unit_cost

        allocations.append(
            OptimizedSkuPlan(
                sku=item.sku,
                name=item.name,
                current_stock_kg=item.current_stock_kg,
                recommended_order_kg=order_q,
                recommended_markdown_pct=md_pct,
                expected_sales_kg=sold_q,
                projected_waste_kg=waste_q,
                projected_profit_usd=sku_profit,
            )
        )

    baseline_waste = max(baseline_waste, total_waste + 1.0)
    reduction_pct = round(((baseline_waste - total_waste) / baseline_waste) * 100.0, 2)

    PREDICTED_WASTE_KG_GAUGE.set(round(total_waste, 2))
    INVENTORY_VALUE_AT_RISK_GAUGE.set(round(value_at_risk, 2))
    SIMULATION_LATENCY_SECONDS.labels(engine="linear_programming").observe(
        time.perf_counter() - started
    )

    return OptimizationResponse(
        solver_status=status_str,
        total_projected_profit_usd=round(total_profit, 2),
        total_projected_waste_kg=round(total_waste, 2),
        baseline_waste_kg=round(baseline_waste, 2),
        waste_reduction_pct=max(0.0, reduction_pct),
        budget_utilized_usd=round(budget_used, 2),
        storage_utilized_kg=round(storage_used, 2),
        allocations=allocations,
    )
