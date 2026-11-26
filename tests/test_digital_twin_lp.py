def test_monte_carlo_digital_twin(client):
    resp = client.post(
        "/api/v1/digital-twin/simulate",
        json={
            "sku": "SKU-WHOLE-MILK",
            "horizon_days": 14,
            "simulations": 100,
            "reorder_qty_kg": 40.0,
            "markdown_pct": 15.0,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["trajectory"]) == 14
    assert 0.0 <= body["stockout_probability_pct"] <= 100.0
    assert body["expected_total_waste_kg"] >= 0.0


def test_linear_programming_optimization(client):
    resp = client.post(
        "/api/v1/optimize/linear-programming",
        json={"max_budget_usd": 2500.0, "max_cold_storage_kg": 900.0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["solver_status"] == "Optimal"
    assert body["total_projected_profit_usd"] > 0
    assert body["budget_utilized_usd"] <= 2500.01
    assert len(body["allocations"]) >= 8


def test_rule_based_expiry_alerts(client):
    resp = client.get("/api/v1/alerts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_alerts"] >= 1
    assert body["total_potential_savings_usd"] > 0
