from collections import Counter
from datetime import date, timedelta

import numpy as np
from sqlalchemy.orm import Session

from app.models.domain import InventoryItem, SalesRecord
from app.services.external_apis import (
    fetch_groceries_transactions,
    fetch_live_weather,
    fetch_upcoming_holidays,
)

# Perishable SKU catalog mapped directly to item labels in real groceries.csv
PERISHABLE_SKU_CATALOG = [
    {
        "sku": "SKU-WHOLE-MILK",
        "grocery_key": "whole milk",
        "name": "Fresh Whole Milk (1L)",
        "category": "Dairy & Chilled",
        "unit_cost": 1.15,
        "selling_price": 2.10,
        "shelf_life_days": 5,
        "days_remaining": 2,
        "current_stock_kg": 135.0,
        "supplier_name": "GreenValley Dairy Co-op",
        "supplier_lead_days": 1,
        "spoilage_rate_per_day": 0.14,
    },
    {
        "sku": "SKU-OTHER-VEG",
        "grocery_key": "other vegetables",
        "name": "Seasonal Leafy Greens Mix",
        "category": "Fresh Produce",
        "unit_cost": 1.40,
        "selling_price": 2.85,
        "shelf_life_days": 4,
        "days_remaining": 1,
        "current_stock_kg": 96.0,
        "supplier_name": "AgroFresh Harvest Farms",
        "supplier_lead_days": 2,
        "spoilage_rate_per_day": 0.18,
    },
    {
        "sku": "SKU-ROLLS-BUNS",
        "grocery_key": "rolls/buns",
        "name": "Artisan Wholegrain Rolls",
        "category": "Bakery",
        "unit_cost": 0.85,
        "selling_price": 1.95,
        "shelf_life_days": 3,
        "days_remaining": 1,
        "current_stock_kg": 88.0,
        "supplier_name": "Artisan Bakehouse Logistics",
        "supplier_lead_days": 1,
        "spoilage_rate_per_day": 0.22,
    },
    {
        "sku": "SKU-YOGURT",
        "grocery_key": "yogurt",
        "name": "Probiotic Greek Yogurt",
        "category": "Dairy & Chilled",
        "unit_cost": 1.50,
        "selling_price": 3.10,
        "shelf_life_days": 9,
        "days_remaining": 4,
        "current_stock_kg": 74.0,
        "supplier_name": "GreenValley Dairy Co-op",
        "supplier_lead_days": 1,
        "spoilage_rate_per_day": 0.08,
    },
    {
        "sku": "SKU-ROOT-VEG",
        "grocery_key": "root vegetables",
        "name": "Organic Root Vegetables",
        "category": "Fresh Produce",
        "unit_cost": 0.95,
        "selling_price": 2.05,
        "shelf_life_days": 12,
        "days_remaining": 6,
        "current_stock_kg": 68.0,
        "supplier_name": "AgroFresh Harvest Farms",
        "supplier_lead_days": 2,
        "spoilage_rate_per_day": 0.05,
    },
    {
        "sku": "SKU-TROP-FRUIT",
        "grocery_key": "tropical fruit",
        "name": "Ripened Tropical Mangoes & Papaya",
        "category": "Exotic Fruits",
        "unit_cost": 2.20,
        "selling_price": 4.40,
        "shelf_life_days": 5,
        "days_remaining": 2,
        "current_stock_kg": 62.0,
        "supplier_name": "TropiFruit Cold Imports",
        "supplier_lead_days": 3,
        "spoilage_rate_per_day": 0.16,
    },
    {
        "sku": "SKU-BERRIES",
        "grocery_key": "berries",
        "name": "Fresh Strawberries & Blueberries",
        "category": "Exotic Fruits",
        "unit_cost": 2.80,
        "selling_price": 5.50,
        "shelf_life_days": 3,
        "days_remaining": 1,
        "current_stock_kg": 42.0,
        "supplier_name": "TropiFruit Cold Imports",
        "supplier_lead_days": 3,
        "spoilage_rate_per_day": 0.25,
    },
    {
        "sku": "SKU-CURD",
        "grocery_key": "curd",
        "name": "Farm Fresh Cultured Curd",
        "category": "Dairy & Chilled",
        "unit_cost": 1.05,
        "selling_price": 2.15,
        "shelf_life_days": 6,
        "days_remaining": 3,
        "current_stock_kg": 54.0,
        "supplier_name": "GreenValley Dairy Co-op",
        "supplier_lead_days": 1,
        "spoilage_rate_per_day": 0.11,
    },
]


def _compute_grocery_frequencies(transactions: list[list[str]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for basket in transactions:
        counts.update(basket)
    return counts


def ensure_seeded_data(db: Session, force_sync: bool = False) -> dict:
    """Seed or refresh inventory and historical demand telemetry using real datasets & APIs."""
    transactions, source = fetch_groceries_transactions()
    item_counts = _compute_grocery_frequencies(transactions)
    weather = fetch_live_weather()
    holidays = fetch_upcoming_holidays()
    holiday_dates = {h.date for h in holidays}

    existing_items = {item.sku: item for item in db.query(InventoryItem).all()}
    total_baskets = max(len(transactions), 1)

    for entry in PERISHABLE_SKU_CATALOG:
        freq = item_counts.get(entry["grocery_key"], 250)
        if entry["sku"] in existing_items:
            item = existing_items[entry["sku"]]
            item.basket_frequency = freq
        else:
            item = InventoryItem(
                sku=entry["sku"],
                name=entry["name"],
                category=entry["category"],
                current_stock_kg=entry["current_stock_kg"],
                unit_cost=entry["unit_cost"],
                selling_price=entry["selling_price"],
                shelf_life_days=entry["shelf_life_days"],
                days_remaining=entry["days_remaining"],
                supplier_name=entry["supplier_name"],
                supplier_lead_days=entry["supplier_lead_days"],
                spoilage_rate_per_day=entry["spoilage_rate_per_day"],
                basket_frequency=freq,
            )
            db.add(item)

    db.commit()

    has_sales = db.query(SalesRecord.id).first() is not None
    if not has_sales or force_sync:
        if force_sync:
            db.query(SalesRecord).delete()
            db.commit()

        rng = np.random.default_rng(42)
        today = date.today()
        base_temp = weather.temperature_c
        base_hum = weather.humidity_pct

        records_to_insert: list[SalesRecord] = []
        for entry in PERISHABLE_SKU_CATALOG:
            freq = item_counts.get(entry["grocery_key"], 250)
            # Scale demand proportionally from real Kaggle groceries basket frequency
            demand_anchor = max(14.0, (freq / total_baskets) * 195.0)
            for days_ago in range(60, 0, -1):
                rec_date = today - timedelta(days=days_ago)
                dow = rec_date.weekday()
                weekend_boost = 1.22 if dow in (4, 5, 6) else 0.96
                is_hol = rec_date in holiday_dates or (days_ago % 19 == 0)
                holiday_boost = 1.28 if is_hol else 1.0
                temp = float(
                    np.clip(base_temp + rng.normal(0, 2.8) + 2.0 * np.sin(days_ago / 7.0), 14, 40)
                )
                hum = float(np.clip(base_hum + rng.normal(0, 6.0), 35, 95))
                promo = 15.0 if days_ago % 11 == 0 else 0.0
                promo_boost = 1.0 + (promo / 100.0) * 1.4
                weather_effect = 1.0 + (
                    0.012 * (temp - 24.0)
                    if "Fruit" in entry["category"] or "Dairy" in entry["category"]
                    else -0.004 * (temp - 25.0)
                )

                expected = (
                    demand_anchor * weekend_boost * holiday_boost * promo_boost * weather_effect
                )
                sold = float(max(4.0, round(expected + rng.normal(0, demand_anchor * 0.09), 2)))
                waste = float(
                    round(
                        max(0.4, sold * entry["spoilage_rate_per_day"] * rng.uniform(0.4, 1.15)), 2
                    )
                )

                records_to_insert.append(
                    SalesRecord(
                        sku=entry["sku"],
                        sale_date=rec_date,
                        units_sold=sold,
                        temperature_c=round(temp, 1),
                        humidity_pct=round(hum, 1),
                        is_holiday=is_hol,
                        promo_discount_pct=promo,
                        waste_kg=waste,
                    )
                )

        db.bulk_save_objects(records_to_insert)
        db.commit()

    return {
        "dataset_source": source,
        "transactions_ingested": len(transactions),
        "skus_tracked": len(PERISHABLE_SKU_CATALOG),
        "weather_source": weather.source,
    }
