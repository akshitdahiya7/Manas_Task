"""FastAPI application entrypoint.

Every expected failure is mapped to a handler below, so clients always receive
the same JSON error envelope:

    {"error": {"code": "...", "message": "...", "details": [...]}}
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.errors import AppError
from app.routers import auth, logs, metrics, models, predict
from app.seed import run as run_seed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


def error_body(code: str, message: str, details: list | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or []}}


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        run_seed(db)
    finally:
        db.close()

    # Warm the active model so the first real request is not slowed by a
    # cold artifact load. A failure here must not stop the service starting -
    # /health stays up and the error surfaces as a 503 on first use.
    try:
        from app.predictor import ensure_loaded
        from app.services import get_active_model

        db = SessionLocal()
        try:
            ensure_loaded(get_active_model(db))
            logger.info("Warmed up the active model")
        finally:
            db.close()
    except Exception:
        logger.exception("Could not warm up the active model at startup")

    if settings.uses_placeholder_secret:
        logger.warning(
            "JWT_SECRET is still the built-in placeholder. Set a real value in .env "
            "before running this anywhere other than local development."
        )

    logger.info("Startup complete (environment=%s)", settings.environment)
    yield


app = FastAPI(
    title="MANAS Diabetes Inference Service",
    description=(
        "Production-style inference service for the BRFSS diabetes health "
        "indicators models, with model versioning, gated promotion and full "
        "inference logging."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# The frontend is served through nginx, which proxies /api to this service on
# the same origin, so CORS is not needed there. This stays open for local
# development, where Vite runs on a different port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError):
    """Our own exceptions carry their status code and machine-readable code."""
    if exc.status_code >= 500:
        logger.error("%s on %s: %s", exc.code, request.url.path, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, exc.details),
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    """Flatten pydantic errors into one entry per offending field."""
    details = [
        {
            "field": ".".join(str(part) for part in err["loc"][1:]) or "body",
            "message": err["msg"],
            "type": err["type"],
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=error_body("validation_error", "Request validation failed", details),
    )


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException):
    """Keep framework errors in the same envelope.

    Registered against Starlette's base class, not FastAPI's subclass, so that
    routing 404s and 405s are wrapped too - FastAPI raises those from Starlette
    directly and they would otherwise return a bare {"detail": ...}.
    """
    codes = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(codes.get(exc.status_code, "http_error"), str(exc.detail)),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    """Last line of defence.

    Anything we failed to anticipate is logged with its traceback and returned
    as a clean 500 - the client never sees a stack trace.
    """
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_body("internal_error", "An unexpected internal error occurred"),
    )


app.include_router(auth.router)
app.include_router(predict.router)
app.include_router(models.router)
app.include_router(logs.router)
app.include_router(metrics.router)


@app.get("/health", tags=["health"])
def health():
    """Liveness plus a database round-trip, for the container healthcheck."""
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        database_ok = True
    except Exception:
        logger.exception("Health check could not reach the database")
        database_ok = False

    return JSONResponse(
        status_code=200 if database_ok else 503,
        content={"status": "ok" if database_ok else "degraded", "database": database_ok},
    )
