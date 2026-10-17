"""ClinicalPulse FastAPI entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.core.config import get_settings
from app.routers import health

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Pre-clinical triage and biometric telemetry API",
)

allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]
if settings.cors_origins:
    for origin in settings.cors_origins.split(","):
        cleaned = origin.strip()
        if cleaned and cleaned not in allowed_origins:
            allowed_origins.append(cleaned)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(api_router)


@app.get("/")
def root() -> dict[str, str]:
    """Root metadata for quick smoke checks."""
    return {"service": "ClinicalPulse", "docs": "/docs"}
