from datetime import date, datetime

from pydantic import BaseModel, Field


class WeatherContext(BaseModel):
    location: str
    temperature_c: float
    humidity_pct: float
    precipitation_mm: float
    condition: str
    source: str
    fetched_at: datetime


class HolidayContext(BaseModel):
    date: date
    name: str
    country_code: str
    is_upcoming_within_7d: bool


class SupplierFeedItem(BaseModel):
    supplier_name: str
    category: str
    lead_time_days: int
    reliability_score: float
    cold_chain_status: str


class InventorySummaryItem(BaseModel):
    sku: str
    name: str
    category: str
    current_stock_kg: float
    unit_cost: float
    selling_price: float
    shelf_life_days: int
    days_remaining: int
    supplier_name: str
    supplier_lead_days: int
    basket_frequency: int
    value_at_risk_usd: float


class DashboardSummaryResponse(BaseModel):
    kpis: dict
    weather: WeatherContext
    upcoming_holidays: list[HolidayContext]
    suppliers: list[SupplierFeedItem]
    inventory: list[InventorySummaryItem]
    data_source_info: dict


class ForecastPoint(BaseModel):
    date: date
    actual_demand: float | None = None
    xgboost_pred: float
    random_forest_pred: float


class ModelComparisonMetric(BaseModel):
    model_name: str
    mae: float
    rmse: float
    r2_score: float


class ForecastResponse(BaseModel):
    sku: str
    item_name: str
    horizon_days: int
    champion_model: str
    metrics: list[ModelComparisonMetric]
    feature_importances: dict[str, float]
    series: list[ForecastPoint]


class AprioriRuleItem(BaseModel):
    antecedents: list[str]
    consequents: list[str]
    support: float
    confidence: float
    lift: float
    bundle_suggestion: str


class AprioriResponse(BaseModel):
    transactions_analyzed: int
    dataset_source: str
    rules: list[AprioriRuleItem]


class DigitalTwinRequest(BaseModel):
    sku: str = "SKU-WHOLE-MILK"
    horizon_days: int = Field(default=14, ge=3, le=30)
    simulations: int = Field(default=500, ge=50, le=2000)
    reorder_qty_kg: float = Field(default=40.0, ge=0.0, le=500.0)
    markdown_pct: float = Field(default=0.0, ge=0.0, le=60.0)


class DigitalTwinDayStats(BaseModel):
    day: int
    p10_stock: float
    p50_stock: float
    p90_stock: float
    expected_spoilage_kg: float


class DigitalTwinResponse(BaseModel):
    sku: str
    item_name: str
    simulations: int
    horizon_days: int
    stockout_probability_pct: float
    spoilage_probability_pct: float
    expected_total_waste_kg: float
    expected_waste_cost_usd: float
    trajectory: list[DigitalTwinDayStats]


class OptimizationRequest(BaseModel):
    max_budget_usd: float = Field(default=2500.0, ge=100.0, le=50000.0)
    max_cold_storage_kg: float = Field(default=600.0, ge=50.0, le=5000.0)


class OptimizedSkuPlan(BaseModel):
    sku: str
    name: str
    current_stock_kg: float
    recommended_order_kg: float
    recommended_markdown_pct: float
    expected_sales_kg: float
    projected_waste_kg: float
    projected_profit_usd: float


class OptimizationResponse(BaseModel):
    solver_status: str
    total_projected_profit_usd: float
    total_projected_waste_kg: float
    baseline_waste_kg: float
    waste_reduction_pct: float
    budget_utilized_usd: float
    storage_utilized_kg: float
    allocations: list[OptimizedSkuPlan]


class RuleAlertItem(BaseModel):
    sku: str
    item_name: str
    severity: str
    rule_name: str
    days_remaining: int
    current_stock_kg: float
    recommendation: str
    expected_savings_usd: float


class AlertsResponse(BaseModel):
    total_alerts: int
    critical_count: int
    total_potential_savings_usd: float
    alerts: list[RuleAlertItem]


class MLOpsStatusResponse(BaseModel):
    champion_model: str
    champion_version: str
    champion_mae: float
    champion_rmse: float
    drift_psi: float
    drift_detected: bool
    drift_threshold: float
    auto_rollback_tolerance: float
    mlflow_tracking_uri: str
    history: list[dict]


class RetrainRequest(BaseModel):
    simulate_noisy_drift: bool = False


class RetrainResponse(BaseModel):
    action: str
    rolled_back: bool
    new_version: str
    new_mae: float
    baseline_mae: float
    drift_psi: float
    message: str
