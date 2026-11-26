from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    app_name: str = "FreshPulse AI - Food Inventory Loss & Wastage Optimizer"
    app_version: str = "1.0.0"
    api_prefix: str = "/api/v1"

    database_url: str = "sqlite:///./freshpulse.db"

    weather_latitude: float = 19.0760
    weather_longitude: float = 72.8777
    weather_location_name: str = "Mumbai APMC & Retail Hub"
    holiday_country_code: str = "IN"
    currency_code: str = "INR"
    currency_symbol: str = "₹"
    kaggle_groceries_feed_url: str = "https://raw.githubusercontent.com/stedy/Machine-Learning-with-R-datasets/master/groceries.csv"

    mlflow_tracking_uri: str = "./mlruns"
    auto_rollback_mae_tolerance: float = 1.05
    drift_psi_threshold: float = 0.20

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
