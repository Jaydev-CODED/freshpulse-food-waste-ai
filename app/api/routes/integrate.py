from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.domain import ExternalIntegration, InventoryItem
from app.schemas.api import (
    ConnectSiteRequest,
    ConnectSiteResponse,
    CsvImportRequest,
    IntegrationSyncResult,
    WebhookInventoryPayload,
)
from app.services.integrator import (
    connect_external_site,
    parse_and_import_csv,
    upsert_custom_inventory,
)

router = APIRouter(prefix="/integrate", tags=["Platform & Site Shell Integration"])


@router.post("/upload-csv", response_model=IntegrationSyncResult)
def import_custom_csv(
    req: CsvImportRequest,
    db: Session = Depends(get_db),
) -> IntegrationSyncResult:
    """Import custom store/POS inventory via CSV text and auto-seed ML history."""
    try:
        return parse_and_import_csv(db, req.csv_text, req.site_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/webhook", response_model=IntegrationSyncResult)
def ingest_webhook_inventory(
    payload: WebhookInventoryPayload,
    db: Session = Depends(get_db),
) -> IntegrationSyncResult:
    """Ingest live JSON inventory pushes from Shopify, WooCommerce, POS, or custom sites."""
    return upsert_custom_inventory(db, payload.items, payload.site_name)


@router.post("/connect-site", response_model=ConnectSiteResponse)
def register_external_site(
    req: ConnectSiteRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ConnectSiteResponse:
    """Connect an external site/feed and generate 1-line embed shell & CLI commands."""
    base_url = str(request.base_url).rstrip("/")
    return connect_external_site(db, req, base_url)


@router.get("/status")
def list_integrations(db: Session = Depends(get_db)) -> dict:
    """Return connected sites/platforms and current active SKU count."""
    sites = db.query(ExternalIntegration).order_by(ExternalIntegration.id.desc()).all()
    total_skus = db.query(InventoryItem).count()
    return {
        "total_skus": total_skus,
        "currency": "INR",
        "connected_sites": [
            {
                "id": s.id,
                "site_name": s.site_name,
                "site_url": s.site_url,
                "platform_type": s.platform_type,
                "currency": s.currency,
                "items_synced": s.items_synced,
                "status": s.status,
            }
            for s in sites
        ],
    }
