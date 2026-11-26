def test_xgboost_vs_random_forest_forecast(client):
    resp = client.get("/api/v1/forecast?sku=SKU-WHOLE-MILK&horizon_days=7")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sku"] == "SKU-WHOLE-MILK"
    assert len(body["metrics"]) == 2
    model_names = {m["model_name"] for m in body["metrics"]}
    assert model_names == {"XGBoost", "RandomForest"}
    assert any(p["actual_demand"] is None for p in body["series"])


def test_apriori_market_basket_rules(client):
    resp = client.get("/api/v1/apriori?top_k=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["transactions_analyzed"] > 0
    assert len(body["rules"]) > 0
    assert body["rules"][0]["lift"] >= 1.0
