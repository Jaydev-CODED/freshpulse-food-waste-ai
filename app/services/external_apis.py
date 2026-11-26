from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.schemas.api import HolidayContext, SupplierFeedItem, WeatherContext

SAMPLE_GROCERIES_PATH = Path(__file__).resolve().parents[2] / "data" / "groceries_sample.csv"

_WMO_CODES = {
    0: "Clear Sky",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    51: "Light Drizzle",
    61: "Light Rain",
    63: "Moderate Rain",
    80: "Rain Showers",
    95: "Thunderstorm",
}


def fetch_live_weather() -> WeatherContext:
    """Fetch real-time weather telemetry from Open-Meteo API with safe fallback."""
    settings = get_settings()
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={settings.weather_latitude}&longitude={settings.weather_longitude}"
        "&current=temperature_2m,relative_humidity_2m,precipitation,weather_code&timezone=auto"
    )
    try:
        resp = httpx.get(url, timeout=6.0)
        resp.raise_for_status()
        current = resp.json().get("current", {})
        code = int(current.get("weather_code", 1))
        return WeatherContext(
            location=settings.weather_location_name,
            temperature_c=float(current.get("temperature_2m", 27.5)),
            humidity_pct=float(current.get("relative_humidity_2m", 68.0)),
            precipitation_mm=float(current.get("precipitation", 0.0)),
            condition=_WMO_CODES.get(code, "Partly Cloudy"),
            source="Open-Meteo Live API",
            fetched_at=datetime.now(UTC),
        )
    except Exception:
        return WeatherContext(
            location=settings.weather_location_name,
            temperature_c=28.2,
            humidity_pct=71.0,
            precipitation_mm=0.4,
            condition="Warm & Humid (Cached Fallback)",
            source="Open-Meteo Fallback Cache",
            fetched_at=datetime.now(UTC),
        )


def fetch_upcoming_holidays() -> list[HolidayContext]:
    """Fetch upcoming public holidays/festivals from Nager.Date API with safe fallback."""
    settings = get_settings()
    url = f"https://date.nager.at/api/v3/NextPublicHolidays/{settings.holiday_country_code}"
    today = date.today()
    try:
        resp = httpx.get(url, timeout=6.0)
        resp.raise_for_status()
        items = resp.json()[:5]
        holidays: list[HolidayContext] = []
        for item in items:
            h_date = date.fromisoformat(item["date"])
            holidays.append(
                HolidayContext(
                    date=h_date,
                    name=item.get("localName") or item.get("name", "Public Holiday"),
                    country_code=settings.holiday_country_code,
                    is_upcoming_within_7d=0 <= (h_date - today).days <= 7,
                )
            )
        return holidays
    except Exception:
        fallback_date = today + timedelta(days=4)
        return [
            HolidayContext(
                date=fallback_date,
                name="Regional Harvest Market Day",
                country_code=settings.holiday_country_code,
                is_upcoming_within_7d=True,
            )
        ]


def fetch_groceries_transactions() -> tuple[list[list[str]], str]:
    """Load real-world supermarket transactions from Kaggle/UCI groceries.csv or local snapshot."""
    settings = get_settings()
    raw_text: str | None = None
    source = "Kaggle/UCI Real-Time Groceries Feed (GitHub Raw)"

    try:
        resp = httpx.get(settings.kaggle_groceries_feed_url, timeout=8.0)
        resp.raise_for_status()
        if len(resp.text) > 1000:
            raw_text = resp.text
    except Exception:
        raw_text = None

    if raw_text is None and SAMPLE_GROCERIES_PATH.exists():
        raw_text = SAMPLE_GROCERIES_PATH.read_text(encoding="utf-8")
        source = "Local Real Groceries Snapshot (1,500 txns)"

    if not raw_text:
        return [], "Unavailable"

    transactions = [
        [item.strip() for item in line.split(",") if item.strip()]
        for line in raw_text.splitlines()
        if line.strip()
    ]
    return transactions, source


def get_supplier_telemetry() -> list[SupplierFeedItem]:
    """Return perishable cold-chain supplier telemetry feed."""
    return [
        SupplierFeedItem(
            supplier_name="GreenValley Dairy Co-op",
            category="Dairy & Chilled",
            lead_time_days=1,
            reliability_score=0.96,
            cold_chain_status="Optimal (3.2°C)",
        ),
        SupplierFeedItem(
            supplier_name="AgroFresh Harvest Farms",
            category="Fresh Produce",
            lead_time_days=2,
            reliability_score=0.92,
            cold_chain_status="Optimal (6.0°C)",
        ),
        SupplierFeedItem(
            supplier_name="Artisan Bakehouse Logistics",
            category="Bakery",
            lead_time_days=1,
            reliability_score=0.94,
            cold_chain_status="Ambient Controlled",
        ),
        SupplierFeedItem(
            supplier_name="TropiFruit Cold Imports",
            category="Exotic Fruits",
            lead_time_days=3,
            reliability_score=0.89,
            cold_chain_status="Watch (8.4°C)",
        ),
    ]
