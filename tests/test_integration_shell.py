def test_indian_data_and_inr_currency(client):
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["kpis"]["currency"] == "INR"
    assert data["kpis"]["currency_symbol"] == "₹"
    assert any(h["country_code"] == "IN" for h in data["upcoming_holidays"])
    assert any("Amul" in item["name"] or "Nashik" in item["name"] for item in data["inventory"])


def test_custom_csv_import_and_shell_embed(client):
    csv_payload = (
        "sku,name,category,current_stock_kg,unit_cost,selling_price,"
        "shelf_life_days,days_remaining,supplier_name\n"
        "KIRANA-TOMATO,Desi Fresh Tomatoes (kg),Fresh Produce,85,32,58,4,1,Nashik Mandi Hub\n"
    )
    import_resp = client.post(
        "/api/v1/integrate/upload-csv",
        json={"site_name": "My Indian Mart", "csv_text": csv_payload},
    )
    assert import_resp.status_code == 200
    assert import_resp.json()["items_upserted"] == 1
    assert import_resp.json()["sales_rows_seeded"] == 60

    connect_resp = client.post(
        "/api/v1/integrate/connect-site",
        json={
            "site_name": "My Indian Mart",
            "site_url": "https://myindianmart.in",
            "platform_type": "shopify",
            "currency": "INR",
        },
    )
    assert connect_resp.status_code == 200
    body = connect_resp.json()
    assert "/embed.js" in body["script_embed_tag"]
    assert "python -m app.shell_runner" in body["shell_cli_command"]

    embed_js = client.get("/embed.js")
    assert embed_js.status_code == 200
    assert "FreshPulseShell" in embed_js.text

    shell_page = client.get("/shell")
    assert shell_page.status_code == 200
