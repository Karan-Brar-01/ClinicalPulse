"""Supabase client helpers for ClinicalPulse persistence."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def get_supabase_client(settings: Optional[Settings] = None) -> Any:
    """
    Return a Supabase client or raise 503 if credentials are missing.

    Uses the service/anon key from SUPABASE_KEY.
    """
    cfg = settings or get_settings()
    if not cfg.supabase_url or not cfg.supabase_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase is not configured (SUPABASE_URL / SUPABASE_KEY)",
        )
    try:
        from supabase import create_client
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="supabase package is not installed",
        ) from exc

    return create_client(cfg.supabase_url, cfg.supabase_key)


def list_consultations(
    status_filter: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """List consultations, optionally filtered by status (newest first)."""
    client = get_supabase_client()
    query = client.table("consultations").select("*")
    if status_filter:
        # Support comma-separated statuses for queue views
        statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
        if len(statuses) == 1:
            query = query.eq("status", statuses[0])
        elif statuses:
            query = query.in_("status", statuses)
    try:
        response = query.order("created_at", desc=True).limit(limit).execute()
    except Exception as exc:  # noqa: BLE001
        _raise_supabase_error(exc, action="list consultations")
    return list(getattr(response, "data", None) or [])


def get_consultation(consultation_id: str) -> Dict[str, Any]:
    """Fetch a consultation by id."""
    client = get_supabase_client()
    try:
        response = (
            client.table("consultations")
            .select("*")
            .eq("id", consultation_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        _raise_supabase_error(exc, action="get consultation")
    data = getattr(response, "data", None) or []
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consultation {consultation_id} not found",
        )
    return data[0]


def update_consultation(consultation_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """Patch a consultation and return the updated row."""
    client = get_supabase_client()
    try:
        response = (
            client.table("consultations")
            .update(patch)
            .eq("id", consultation_id)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        _raise_supabase_error(exc, action="update consultation")
    data = getattr(response, "data", None) or []
    if not data:
        # Distinguish missing vs empty update
        get_consultation(consultation_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to update consultation record",
        )
    return data[0]


def insert_consultation(row: Dict[str, Any]) -> Dict[str, Any]:
    """Insert a consultations row and return the created record."""
    client = get_supabase_client()
    try:
        response = client.table("consultations").insert(row).execute()
    except Exception as exc:  # noqa: BLE001
        _raise_supabase_error(exc, action="insert consultation")
    data = getattr(response, "data", None) or []
    if not data:
        logger.error("Supabase insert returned no data: %s", response)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create consultation record",
        )
    return data[0]


def _raise_supabase_error(exc: Exception, *, action: str) -> None:
    """Map PostgREST errors into actionable HTTP responses."""
    message = str(exc)
    logger.exception("Supabase %s failed: %s", action, message)
    if "Could not find the table" in message or "PGRST205" in message:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Supabase connected, but tables are missing. "
                "Open the Supabase SQL Editor and run supabase_schema.sql, then retry."
            ),
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Supabase {action} failed: {message}",
    ) from exc
