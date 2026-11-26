def test_mlops_status_and_auto_rollback(client):
    status_resp = client.get("/api/v1/mlops/status")
    assert status_resp.status_code == 200
    baseline_version = status_resp.json()["champion_version"]

    # Clean retrain should validate and promote or retain valid champion
    clean_resp = client.post("/api/v1/mlops/retrain", json={"simulate_noisy_drift": False})
    assert clean_resp.status_code == 200

    # Noisy drift retrain should fail validation gate and trigger auto-rollback
    drift_resp = client.post("/api/v1/mlops/retrain", json={"simulate_noisy_drift": True})
    assert drift_resp.status_code == 200
    drift_body = drift_resp.json()
    assert drift_body["rolled_back"] is True
    assert drift_body["action"] == "rolled_back"

    post_status = client.get("/api/v1/mlops/status").json()
    assert post_status["champion_version"] != drift_body["new_version"]
    assert len(post_status["history"]) >= 2
    assert baseline_version is not None
