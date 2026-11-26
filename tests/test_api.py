def test_health_endpoint(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"


def test_dashboard_summary_and_sync(client):
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["kpis"]["total_skus"] >= 8
    assert len(data["inventory"]) >= 8
    assert "temperature_c" in data["weather"]
    assert data["data_source_info"]["transactions_ingested"] > 0


def test_prometheus_metrics_exposed(client):
    client.get("/api/v1/health")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "freshpulse_api_requests_total" in resp.text
