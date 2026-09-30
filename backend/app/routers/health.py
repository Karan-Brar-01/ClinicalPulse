"""Health and readiness probes."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Liveness probe for local and container orchestration."""
    return {"status": "ok", "service": "clinicalpulse"}
