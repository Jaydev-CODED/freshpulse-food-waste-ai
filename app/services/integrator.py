import csv
import io
from datetime import date, timedelta

import httpx
import numpy as np
from sqlalchemy.orm import Session

from app.models.domain import ExternalIntegration, InventoryItem, SalesRecord
from app.schemas.api import (
    ConnectSiteRequest,
    ConnectSiteResponse,
    IntegrationSyncResult,
    WebhookInventoryItem,
)
from app.services.external_apis import fetch_live_weather


def _seed_sales_for_new_skus(db: Session, items: list[InventoryItem]) -> int:
    """Ensure every newly imported SKU has 60 days of baseline sales history for ML forecasting."""
    weather = fetch_live_weather()
    rng = np.random.default_rng(101)
    today = date.today()
    inserted = 0

    for item in items:
        has_sales = db.query(SalesRecord.id).filter(SalesRecord.sku == item.sku).first() is not None
        if has_sales:
            continue

        demand_anchor = max(8.0, item.current_stock_kg * 0.28)
        for days_ago in range(60, 0, -1):
            rec_date = today - timedelta(days=days_ago)
            weekend_boost = 1.2 if rec_date.weekday() >= 4 else 1.0
            noise = float(rng.normal(0.0, max(1.0, demand_anchor * 0.1)))
            units = max(2.0, round(demand_anchor * weekend_boost + noise, 2))
            waste = round(max(0.0, units * item.spoilage_rate_per_day * 0.3), 2)
            db.add(
                SalesRecord(
                    sku=item.sku,
                    sale_date=rec_date,
                    units_sold=units,
                    temperature_c=weather.temperature_c,
                    humidity_pct=weather.humidity_pct,
                    is_holiday=False,
                    promo_discount_pct=0.0,
                    waste_kg=waste,
                )
            )
            inserted += 1

    db.commit()
    return inserted


def upsert_custom_inventory(
    db: Session,
    items: list[WebhookInventoryItem],
    site_name: str,
) -> IntegrationSyncResult:
    """Upsert custom inventory items from a user's store, POS, or website."""
    existing = {row.sku: row for row in db.query(InventoryItem).all()}
    touched: list[InventoryItem] = []

    for entry in items:
        if entry.sku in existing:
            row = existing[entry.sku]
            row.name = entry.name
            row.category = entry.category
            row.current_stock_kg = entry.current_stock_kg
            row.unit_cost = entry.unit_cost
            row.selling_price = entry.selling_price
            row.shelf_life_days = entry.shelf_life_days
            row.days_remaining = entry.days_remaining
            row.supplier_name = entry.supplier_name
            row.supplier_lead_days = entry.supplier_lead_days
            row.spoilage_rate_per_day = entry.spoilage_rate_per_day
            touched.append(row)
        else:
            row = InventoryItem(
                sku=entry.sku,
                name=entry.name,
                category=entry.category,
                current_stock_kg=entry.current_stock_kg,
                unit_cost=entry.unit_cost,
                selling_price=entry.selling_price,
                shelf_life_days=entry.shelf_life_days,
                days_remaining=entry.days_remaining,
                supplier_name=entry.supplier_name,
                supplier_lead_days=entry.supplier_lead_days,
                spoilage_rate_per_day=entry.spoilage_rate_per_day,
                basket_frequency=180,
            )
            db.add(row)
            touched.append(row)

    db.commit()
    sales_seeded = _seed_sales_for_new_skus(db, touched)

    return IntegrationSyncResult(
        status="synced",
        site_name=site_name,
        items_upserted=len(touched),
        sales_rows_seeded=sales_seeded,
        message=f"Integrated {len(touched)} SKUs from {site_name} (INR ₹ pricing active).",
    )


def parse_and_import_csv(db: Session, csv_text: str, site_name: str) -> IntegrationSyncResult:
    """Parse user-uploaded CSV inventory into validated WebhookInventoryItem records."""
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    parsed: list[WebhookInventoryItem] = []

    for idx, row in enumerate(reader, start=1):
        norm = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items() if k}
        sku = norm.get("sku") or f"CUSTOM-SKU-{idx}"
        name = norm.get("name") or norm.get("product") or f"Custom Item {idx}"
        parsed.append(
            WebhookInventoryItem(
                sku=sku,
                name=name,
                category=norm.get("category") or "Custom Store",
                current_stock_kg=float(norm.get("current_stock_kg") or norm.get("stock") or 25.0),
                unit_cost=float(norm.get("unit_cost") or norm.get("cost_inr") or 50.0),
                selling_price=float(norm.get("selling_price") or norm.get("price_inr") or 80.0),
                shelf_life_days=int(float(norm.get("shelf_life_days") or 7)),
                days_remaining=int(float(norm.get("days_remaining") or 2)),
                supplier_name=norm.get("supplier_name") or f"{site_name} Vendor",
                supplier_lead_days=int(float(norm.get("supplier_lead_days") or 1)),
                spoilage_rate_per_day=float(norm.get("spoilage_rate_per_day") or 0.12),
            )
        )

    if not parsed:
        raise ValueError("CSV contains no valid inventory rows.")

    return upsert_custom_inventory(db, parsed, site_name)


def connect_external_site(
    db: Session,
    req: ConnectSiteRequest,
    base_url: str,
) -> ConnectSiteResponse:
    """Register an external website/platform and optionally pull its live feed."""
    items_synced = 0
    feed_url = req.data_feed_url.strip()

    if feed_url:
        try:
            resp = httpx.get(feed_url, timeout=6.0)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "json" in content_type or resp.text.lstrip().startswith(("[", "{")):
                raw_json = resp.json()
                raw_items = (
                    raw_json.get("items", raw_json) if isinstance(raw_json, dict) else raw_json
                )
                parsed = [WebhookInventoryItem(**entry) for entry in raw_items]
                res = upsert_custom_inventory(db, parsed, req.site_name)
                items_synced = res.items_upserted
            else:
                res = parse_and_import_csv(db, resp.text, req.site_name)
                items_synced = res.items_upserted
        except Exception:
            items_synced = 0

    integration = ExternalIntegration(
        site_name=req.site_name,
        site_url=req.site_url,
        platform_type=req.platform_type,
        data_feed_url=feed_url,
        currency=req.currency,
        items_synced=items_synced,
        status="connected",
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)

    clean_base = base_url.rstrip("/")
    script_tag = (
        f'<script src="{clean_base}/embed.js" '
        f'data-site="{req.site_name}" '
        f'data-currency="{req.currency}" '
        f'data-api="{clean_base}"></script>'
    )
    iframe_tag = (
        f'<iframe src="{clean_base}/shell?site={req.site_name}&embed=true" '
        f'style="width:100%;height:720px;border:0;border-radius:16px;" '
        f'title="FreshPulse AI Shell"></iframe>'
    )
    curl_cmd = (
        f'curl -X POST "{clean_base}/api/v1/integrate/webhook" '
        f'-H "Content-Type: application/json" '
        f'-d \'{{"site_name":"{req.site_name}","items":[{{"sku":"MY-MILK-01","name":"Store Fresh Milk","current_stock_kg":60,"unit_cost":52,"selling_price":66,"shelf_life_days":4,"days_remaining":1}}]}}\''
    )
    cli_cmd = (
        f'python -m app.shell_runner --site "{req.site_name}" '
        + (f'--feed-url "{feed_url}" ' if feed_url else "")
        + "--run-all"
    )

    return ConnectSiteResponse(
        integration_id=integration.id,
        site_name=integration.site_name,
        site_url=integration.site_url,
        platform_type=integration.platform_type,
        currency=integration.currency,
        items_synced=items_synced,
        script_embed_tag=script_tag,
        iframe_embed_tag=iframe_tag,
        webhook_curl_example=curl_cmd,
        shell_cli_command=cli_cmd,
    )
