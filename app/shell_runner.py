"""Standalone FreshPulse AI Shell Runner.

Allows any retail website, ERP, or server cron job to run FreshPulse AI as a shell
against its own CSV/JSON inventory feed and output INR optimization + expiry alerts.
"""

import argparse
import json
from pathlib import Path

import httpx

from app.core.database import SessionLocal, init_db
from app.schemas.api import OptimizationRequest, WebhookInventoryItem
from app.services.data_seeder import ensure_seeded_data
from app.services.integrator import parse_and_import_csv, upsert_custom_inventory
from app.services.optimizer import run_linear_programming_optimizer
from app.services.rule_engine import evaluate_expiry_rules


def main() -> None:
    parser = argparse.ArgumentParser(description="FreshPulse AI Shell Runner (INR)")
    parser.add_argument("--site", default="External Platform", help="Store or website name")
    parser.add_argument("--csv-file", default="", help="Path to local inventory CSV file")
    parser.add_argument("--feed-url", default="", help="Remote JSON/CSV inventory feed URL")
    parser.add_argument("--budget-inr", type=float, default=150000.0, help="Max LP budget in INR")
    parser.add_argument("--storage-kg", type=float, default=800.0, help="Max cold storage in kg")
    parser.add_argument("--run-all", action="store_true", help="Run LP optimization and alerts")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        ensure_seeded_data(db)

        if args.csv_file:
            csv_text = Path(args.csv_file).read_text(encoding="utf-8")
            sync_res = parse_and_import_csv(db, csv_text, args.site)
            print(f"[SYNC] {sync_res.message}")

        if args.feed_url:
            resp = httpx.get(args.feed_url, timeout=8.0)
            resp.raise_for_status()
            if resp.text.lstrip().startswith(("[", "{")):
                raw = resp.json()
                raw_items = raw.get("items", raw) if isinstance(raw, dict) else raw
                parsed = [WebhookInventoryItem(**entry) for entry in raw_items]
                sync_res = upsert_custom_inventory(db, parsed, args.site)
            else:
                sync_res = parse_and_import_csv(db, resp.text, args.site)
            print(f"[SYNC] {sync_res.message}")

        lp_res = run_linear_programming_optimizer(
            db,
            OptimizationRequest(
                max_budget_usd=args.budget_inr,
                max_cold_storage_kg=args.storage_kg,
            ),
        )
        alerts_res = evaluate_expiry_rules(db)

        summary = {
            "site": args.site,
            "currency": "INR",
            "lp_status": lp_res.solver_status,
            "projected_7d_profit_inr": lp_res.total_projected_profit_usd,
            "projected_waste_kg": lp_res.total_projected_waste_kg,
            "waste_reduction_pct": lp_res.waste_reduction_pct,
            "critical_alerts": alerts_res.critical_count,
            "potential_savings_inr": alerts_res.total_potential_savings_usd,
            "top_recommendations": [
                {
                    "sku": a.sku,
                    "severity": a.severity,
                    "action": a.recommendation,
                    "savings_inr": a.expected_savings_usd,
                }
                for a in alerts_res.alerts[:5]
            ],
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    finally:
        db.close()


if __name__ == "__main__":
    main()
