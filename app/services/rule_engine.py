from sqlalchemy.orm import Session

from app.models.domain import AlertLog, InventoryItem, SalesRecord
from app.schemas.api import AlertsResponse, RuleAlertItem
from app.services.apriori_engine import mine_product_associations
from app.services.external_apis import fetch_live_weather


def evaluate_rule_engine(db: Session) -> AlertsResponse:
    """Evaluate deterministic business rules for expiry urgency, weather spoilage, and bundle promos."""
    items = db.query(InventoryItem).order_by(InventoryItem.days_remaining.asc()).all()
    weather = fetch_live_weather()

    # Build quick lookup from Apriori rules to enrich expiry markdowns with cross-sell bundles
    bundle_map: dict[str, str] = {}
    try:
        apriori_res = mine_product_associations(min_support=0.02, min_confidence=0.25, top_k=8)
        for rule in apriori_res.rules:
            for con in rule.consequents:
                if con not in bundle_map and rule.antecedents:
                    bundle_map[con] = rule.antecedents[0]
    except Exception:
        bundle_map = {}

    alerts: list[RuleAlertItem] = []

    for item in items:
        sales = db.query(SalesRecord.units_sold).filter(SalesRecord.sku == item.sku).all()
        avg_daily = sum(s[0] for s in sales) / max(len(sales), 1)
        days_of_supply = item.current_stock_kg / max(avg_daily, 1.0)

        # Rule 1: Critical Expiry Clearance
        if item.days_remaining <= 1 and item.current_stock_kg > avg_daily * 1.1:
            savings = round(item.current_stock_kg * 0.45 * item.unit_cost, 2)
            partner = bundle_map.get("whole milk", "whole milk")
            alerts.append(
                RuleAlertItem(
                    sku=item.sku,
                    item_name=item.name,
                    severity="CRITICAL",
                    rule_name="EXPIRY_FLASH_MARKDOWN",
                    days_remaining=item.days_remaining,
                    current_stock_kg=item.current_stock_kg,
                    recommendation=(
                        f"Apply 35% flash markdown immediately and bundle with '{partner}' "
                        f"({days_of_supply:.1f}d stock vs {item.days_remaining}d shelf life)."
                    ),
                    expected_savings_usd=savings,
                )
            )
        # Rule 2: Heat/Humidity Cold-Chain Risk
        elif item.days_remaining <= 2 and weather.temperature_c >= 26.0:
            savings = round(item.current_stock_kg * 0.25 * item.unit_cost, 2)
            alerts.append(
                RuleAlertItem(
                    sku=item.sku,
                    item_name=item.name,
                    severity="HIGH",
                    rule_name="WEATHER_SPOILAGE_GUARD",
                    days_remaining=item.days_remaining,
                    current_stock_kg=item.current_stock_kg,
                    recommendation=(
                        f"Ambient temp {weather.temperature_c}°C accelerates spoilage; "
                        "apply 20% promo & prioritize front-of-shelf FIFO rotation."
                    ),
                    expected_savings_usd=savings,
                )
            )
        # Rule 3: Low Stock vs Supplier Lead Time (Stockout Guard)
        elif days_of_supply < item.supplier_lead_days + 0.8:
            savings = round(avg_daily * (item.selling_price - item.unit_cost), 2)
            alerts.append(
                RuleAlertItem(
                    sku=item.sku,
                    item_name=item.name,
                    severity="MEDIUM",
                    rule_name="LEAD_TIME_REORDER_TRIGGER",
                    days_remaining=item.days_remaining,
                    current_stock_kg=item.current_stock_kg,
                    recommendation=(
                        f"Stock covers {days_of_supply:.1f}d (< {item.supplier_lead_days}d supplier lead). "
                        f"Trigger replenishment from {item.supplier_name}."
                    ),
                    expected_savings_usd=savings,
                )
            )

    # Persist latest alert snapshot cleanly
    db.query(AlertLog).delete()
    for alert in alerts:
        db.add(
            AlertLog(
                sku=alert.sku,
                severity=alert.severity,
                rule_name=alert.rule_name,
                recommendation=alert.recommendation,
                expected_savings_usd=alert.expected_savings_usd,
            )
        )
    db.commit()

    critical_count = sum(1 for a in alerts if a.severity == "CRITICAL")
    total_savings = round(sum(a.expected_savings_usd for a in alerts), 2)

    return AlertsResponse(
        total_alerts=len(alerts),
        critical_count=critical_count,
        total_potential_savings_usd=total_savings,
        alerts=alerts,
    )
