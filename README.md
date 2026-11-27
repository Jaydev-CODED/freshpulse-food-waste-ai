# FreshPulse AI 🌿
## AI-Powered Food Inventory Loss & Wastage Optimization Platform

> **A demonstrable, full-stack AI system** that ingests real grocery transaction data from Kaggle/UCI, trains self-improving ML models, simulates future inventory with a Monte Carlo Digital Twin, and optimizes perishable profit with Linear Programming — all visualized on a live dashboard.

[![CI/CD](https://github.com/Jaydev-CODED/freshpulse-food-waste-ai/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/Jaydev-CODED/freshpulse-food-waste-ai/actions)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.165-green)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 🚀 What This Does

| Capability | Technology | Live Data Source |
|---|---|---|
| **Demand Forecasting** | XGBoost + Random Forest | Kaggle/UCI Grocery Baskets |
| **Market Basket Bundles** | Apriori (mlxtend) | 9,835 real transactions |
| **Digital Twin Simulation** | Monte Carlo (500 paths) | Historical demand + Open-Meteo weather |
| **Profit Optimization** | Linear Programming (PuLP CBC) | Live inventory + supplier telemetry |
| **Expiry Alerts** | Rule-Based Engine | Shelf-life + weather + lead-time rules |
| **Self-Learning AI** | MLflow + PSI drift + Auto-Rollback | Automated nightly retraining |
| **Real-Time Weather** | Open-Meteo API | Live Mumbai (or any lat/lon) |
| **Festival Signals** | Nager.Date API | Upcoming public holidays |

---

## 📁 Branch Structure

| Branch | Purpose |
|---|---|
| `main` | Production-ready, tagged releases |
| `develop` | Integration branch for all features |
| `feature/backend-api` | FastAPI + DB models + services |
| `feature/ml-algorithms` | XGBoost, RF, Apriori, Digital Twin, LP |
| `feature/frontend-dashboard` | Tailwind + Chart.js live dashboard |
| `feature/ci-cd` | GitHub Actions, Docker, SonarCloud |
| `mlops` | Nightly model retraining triggers |

---

## 🏃 Quick Start (Local)

```bash
# 1. Clone the repository
git clone https://github.com/Jaydev-CODED/freshpulse-food-waste-ai.git
cd freshpulse-food-waste-ai

# 2. Create virtual environment & install dependencies
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt

# 3. Copy env config
cp .env.example .env

# 4. Launch the server (auto-seeds real data on startup)
uvicorn app.main:app --reload --port 8000
```

Then open **http://localhost:8000** for the live dashboard.
API docs at **http://localhost:8000/docs** | Prometheus metrics at **http://localhost:8000/metrics**

---

## 🐳 Docker Compose (Full Stack)

```bash
# Starts: FastAPI + PostgreSQL + Prometheus + Grafana
docker compose up --build

# Access:
#   Dashboard  → http://localhost:8000
#   Grafana    → http://localhost:3000  (admin/admin)
#   Prometheus → http://localhost:9090
```

---

## 🧪 Running Tests

```bash
pytest -v                        # All tests
pytest --cov=app --cov-report=term-missing   # With coverage
```

**Test coverage areas:**
- API health & dashboard endpoints
- XGBoost vs Random Forest forecasting accuracy
- Apriori basket rule mining (real transactions)
- Monte Carlo Digital Twin simulation
- PuLP Linear Programming optimization
- MLOps Auto-Rollback gate (clean + noisy drift)

---

## 🔄 CI/CD Pipeline

```
Push to GitHub
    │
    ├── 1. Ruff Lint + Format Check
    ├── 2. Pytest + Coverage Report → Codecov
    ├── 3. SonarCloud Code Quality Gate
    ├── 4. Docker Build + Push → ghcr.io
    ├── 5. Deploy to Staging (main only)
    └── 6. Nightly MLOps Retrain (cron 2am UTC)
```

---

## 📊 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/health` | Service health + DB connectivity |
| GET | `/api/v1/dashboard/summary` | Real-time KPIs, weather, holidays, inventory |
| POST | `/api/v1/data/sync` | Force Kaggle/weather re-ingestion |
| GET | `/api/v1/forecast` | XGBoost vs RF demand forecast |
| GET | `/api/v1/apriori` | Market basket association rules |
| POST | `/api/v1/digital-twin/simulate` | Monte Carlo inventory simulation |
| POST | `/api/v1/optimize/linear-programming` | LP profit + waste optimizer |
| GET | `/api/v1/alerts` | Rule-based expiry & reorder alerts |
| GET | `/api/v1/mlops/status` | Champion model, PSI drift status |
| POST | `/api/v1/mlops/retrain` | Trigger retrain + auto-rollback |

---

## 🛠️ Tech Stack

**Backend:** FastAPI · SQLAlchemy · SQLite (dev) / PostgreSQL (prod)  
**ML:** XGBoost · scikit-learn · mlxtend (Apriori) · SciPy · NumPy · PuLP  
**External APIs:** Open-Meteo (weather) · Nager.Date (holidays) · Kaggle/UCI (groceries)  
**MLOps:** PSI + KS drift detection · Auto-Rollback · Model Registry (DB-backed)  
**Monitoring:** Prometheus · Grafana  
**CI/CD:** GitHub Actions · Docker · GHCR · SonarCloud · Codecov  
**Frontend:** Tailwind CSS · Chart.js

---

## 📄 License

MIT © 2026 Jaydev-CODED
