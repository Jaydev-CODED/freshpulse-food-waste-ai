from prometheus_client import Counter, Gauge, Histogram

API_REQUESTS_TOTAL = Counter(
    "freshpulse_api_requests_total",
    "Total API requests handled by FreshPulse AI",
    ["endpoint", "method", "status"],
)

MODEL_MAE_GAUGE = Gauge(
    "freshpulse_model_mae",
    "Current Mean Absolute Error by forecasting model",
    ["model_name"],
)

MODEL_RMSE_GAUGE = Gauge(
    "freshpulse_model_rmse",
    "Current Root Mean Squared Error by forecasting model",
    ["model_name"],
)

PREDICTED_WASTE_KG_GAUGE = Gauge(
    "freshpulse_predicted_waste_kg",
    "Total predicted perishable food waste across tracked SKUs in kg",
)

INVENTORY_VALUE_AT_RISK_GAUGE = Gauge(
    "freshpulse_inventory_value_at_risk_usd",
    "Estimated USD value of inventory at risk of expiry",
)

DATA_DRIFT_PSI_GAUGE = Gauge(
    "freshpulse_data_drift_psi",
    "Population Stability Index measuring input demand distribution drift",
)

SIMULATION_LATENCY_SECONDS = Histogram(
    "freshpulse_simulation_latency_seconds",
    "Latency of Monte Carlo Digital Twin and LP Optimization executions",
    ["engine"],
)
