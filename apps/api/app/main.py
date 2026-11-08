import json
import logging
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import access, auth, catalog, documents, notifications, operation_keys
from app.body_limit import BodyLimit
from app.config import settings
from app.db import SessionLocal
from app.dms import router as dms_router
from app.workflows import router as workflows_router

app = FastAPI(
    title="NEXORA",
    version="0.1.0",
    docs_url="/api/docs" if settings().app_env == "development" else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings().app_env == "development" else None,
)
app.add_middleware(BodyLimit)
logger = logging.getLogger("nexora.requests")
logging.basicConfig(level=logging.INFO)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    start = time.monotonic()
    response = None
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin != settings().web_origin:
            response = JSONResponse(
                {"error": "origin_forbidden", "request_id": request.state.request_id}, 403
            )
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > settings().max_upload_bytes + 1024 * 1024):
            response = JSONResponse({"error": "file_too_large", "request_id": request.state.request_id}, 413)
    try:
        if response is None:
            response = await call_next(request)
    except Exception as exc:
        # Log exception class, not messages which can contain SQL parameters/secrets.
        logger.error(json.dumps({"request_id": request.state.request_id, "exception": type(exc).__name__}))
        response = JSONResponse({"error": "server_error", "request_id": request.state.request_id}, 500)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        json.dumps(
            {
                "request_id": request.state.request_id,
                "method": request.method,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - start) * 1000),
            }
        )
    )
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse({"error": exc.detail, "request_id": request.state.request_id}, exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse({"error": "validation_error", "request_id": request.state.request_id}, 422)


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/ready")
def ready() -> dict:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, "database_unavailable") from None
    return {"status": "ready"}


for router in (auth.router, documents.router, catalog.router, access.router, operation_keys.router,
               notifications.router):
    app.include_router(router, prefix="/api/v1")


app.include_router(dms_router, prefix="/api/v1")

app.include_router(workflows_router, prefix="/api/v1")


@app.get("/api/v1/capabilities")
def capabilities(user: auth.Actor):
    return {
        "malware_scanning": settings().malware_scanner,
        "development": settings().app_env == "development",
    }
