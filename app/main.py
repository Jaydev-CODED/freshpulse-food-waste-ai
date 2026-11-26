from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import SessionLocal, init_db
from app.core.metrics import API_REQUESTS_TOTAL
from app.services.data_seeder import ensure_seeded_data

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize database schema and ensure real-data baseline is loaded on startup."""
    init_db()
    db = SessionLocal()
    try:
        ensure_seeded_data(db)
    finally:
        db.close()
    yield


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def prometheus_request_middleware(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(settings.api_prefix):
            API_REQUESTS_TOTAL.labels(
                endpoint=request.url.path,
                method=request.method,
                status=str(response.status_code),
            ).inc()
        return response

    application.include_router(api_router, prefix=settings.api_prefix)
    application.mount("/metrics", make_asgi_app())

    if FRONTEND_DIR.exists():
        application.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @application.get("/", include_in_schema=False)
    def serve_dashboard():
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"message": settings.app_name, "docs": "/docs"}

    @application.get("/shell", include_in_schema=False)
    def serve_embed_shell():
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"message": settings.app_name, "mode": "shell"}

    @application.get("/embed.js", include_in_schema=False)
    def serve_embed_script(request: Request):
        base_url = str(request.base_url).rstrip("/")
        js = f"""(function() {{
  if (window.FreshPulseShell) return;
  const scriptEl = document.currentScript;
  const apiBase = (scriptEl && scriptEl.dataset.api) || "{base_url}";
  const siteName = (scriptEl && scriptEl.dataset.site) || window.location.hostname || "Partner Store";
  const currency = (scriptEl && scriptEl.dataset.currency) || "INR";

  const mountTarget = document.getElementById("freshpulse-shell");
  const iframeSrc = apiBase.replace(/\\/$/, "") + "/shell?embed=true&site=" + encodeURIComponent(siteName) + "&currency=" + encodeURIComponent(currency);

  if (mountTarget) {{
    const frame = document.createElement("iframe");
    frame.src = iframeSrc;
    frame.style.cssText = "width:100%;height:760px;border:0;border-radius:16px;background:#0b1120;";
    frame.title = "FreshPulse AI Shell";
    mountTarget.appendChild(frame);
  }} else {{
    const btn = document.createElement("button");
    btn.innerText = "FreshPulse AI Shell (₹)";
    btn.style.cssText = "position:fixed;bottom:20px;right:20px;z-index:99999;background:#059669;color:#fff;border:none;border-radius:9999px;padding:12px 18px;font-family:Inter,sans-serif;font-weight:600;font-size:13px;cursor:pointer;box-shadow:0 10px 25px rgba(0,0,0,0.45);";

    const drawer = document.createElement("div");
    drawer.style.cssText = "display:none;position:fixed;bottom:74px;right:20px;width:min(94vw,960px);height:min(82vh,720px);z-index:99999;border-radius:16px;overflow:hidden;border:1px solid #334155;box-shadow:0 24px 60px rgba(0,0,0,0.65);background:#0b1120;";

    const frame = document.createElement("iframe");
    frame.src = iframeSrc;
    frame.style.cssText = "width:100%;height:100%;border:0;";
    frame.title = "FreshPulse AI Shell";
    drawer.appendChild(frame);

    btn.addEventListener("click", function() {{
      drawer.style.display = drawer.style.display === "none" ? "block" : "none";
    }});

    document.body.appendChild(drawer);
    document.body.appendChild(btn);
  }}

  window.FreshPulseShell = {{
    apiBase: apiBase,
    siteName: siteName,
    pushInventory: async function(items) {{
      const res = await fetch(apiBase.replace(/\\/$/, "") + "/api/v1/integrate/webhook", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ site_name: siteName, items: items }})
      }});
      return res.json();
    }}
  }};
}})();
"""
        return Response(content=js, media_type="application/javascript")

    return application


app = create_app()
