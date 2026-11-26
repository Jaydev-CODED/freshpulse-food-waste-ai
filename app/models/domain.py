from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class InventoryItem(Base):
    """Perishable grocery SKU tracked for spoilage, forecasting, and optimization."""

    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    current_stock_kg: Mapped[float] = mapped_column(Float, nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False)
    selling_price: Mapped[float] = mapped_column(Float, nullable=False)
    shelf_life_days: Mapped[int] = mapped_column(Integer, nullable=False)
    days_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(128), nullable=False)
    supplier_lead_days: Mapped[int] = mapped_column(Integer, nullable=False)
    spoilage_rate_per_day: Mapped[float] = mapped_column(Float, nullable=False, default=0.05)
    basket_frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SalesRecord(Base):
    """Daily historical demand, weather context, and wastage telemetry per SKU."""

    __tablename__ = "sales_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sku: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    sale_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    units_sold: Mapped[float] = mapped_column(Float, nullable=False)
    temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    humidity_pct: Mapped[float] = mapped_column(Float, nullable=False)
    is_holiday: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    promo_discount_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    waste_kg: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class ModelRegistry(Base):
    """Tracks trained ML model versions, metrics, drift score, and champion/rollback status."""

    __tablename__ = "model_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    model_name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    mae: Mapped[float] = mapped_column(Float, nullable=False)
    rmse: Mapped[float] = mapped_column(Float, nullable=False)
    r2_score: Mapped[float] = mapped_column(Float, nullable=False)
    drift_psi: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_champion: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AlertLog(Base):
    """Persisted rule-based expiry and waste mitigation alerts."""

    __tablename__ = "alert_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sku: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(64), nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    expected_savings_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
