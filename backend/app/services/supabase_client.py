"""Supabase client helpers for ClinicalPulse persistence."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from app.core.config import Settings, get_settings
from app.services.local_store import (
    local_get_consultation,
    local_insert_consultation,
    local_list_consultations,
    local_update_consultation,
)

logger = logging.getLogger(__name__)


def _is_network_or_connection_error(exc: Exception) -> bool:
    """Check if exception is caused by DNS resolution, network outage, or connection error."""
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "nodename nor servname",
            "not known",
            "nxdomain",
            "connecterror",
            "connection refused",
            "name resolution",
            "failed to establish a new connection",
            "network is unreachable",
            "getaddrinfo failed",
            "timeout",
        )
    )


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
    try:
        client = get_supabase_client()
        query = client.table("consultations").select("*")
        if status_filter:
            # Support comma-separated statuses for queue views
            statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
            if len(statuses) == 1:
                query = query.eq("status", statuses[0])
            elif statuses:
                query = query.in_("status", statuses)
        response = query.order("created_at", desc=True).limit(limit).execute()
        return list(getattr(response, "data", None) or [])
    except HTTPException as exc:
        if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            logger.warning("Supabase unconfigured. Falling back to local storage.")
            return local_list_consultations(status_filter=status_filter, limit=limit)
        raise
    except Exception as exc:  # noqa: BLE001
        if _is_network_or_connection_error(exc):
            logger.warning(
                "Supabase unreachable (%s). Falling back to local storage.",
                exc,
            )
            return local_list_consultations(status_filter=status_filter, limit=limit)
        _raise_supabase_error(exc, action="list consultations")
    return []


def get_consultation(consultation_id: str) -> Dict[str, Any]:
    """Fetch a consultation by id."""
    try:
        client = get_supabase_client()
        response = (
            client.table("consultations")
            .select("*")
            .eq("id", consultation_id)
            .limit(1)
            .execute()
        )
        data = getattr(response, "data", None) or []
        if data:
            return data[0]
    except HTTPException as exc:
        if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            local = local_get_consultation(consultation_id)
            if local:
                return local
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Consultation {consultation_id} not found",
            ) from exc
        raise
    except Exception as exc:  # noqa: BLE001
        if _is_network_or_connection_error(exc):
            local = local_get_consultation(consultation_id)
            if local:
                return local
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Consultation {consultation_id} not found in local store",
            ) from exc
        _raise_supabase_error(exc, action="get consultation")

    # If Supabase query returned no data, check local store as fallback
    local = local_get_consultation(consultation_id)
    if local:
        return local
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Consultation {consultation_id} not found",
    )


def update_consultation(consultation_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """Patch a consultation and return the updated row."""
    try:
        client = get_supabase_client()
        response = (
            client.table("consultations")
            .update(patch)
            .eq("id", consultation_id)
            .execute()
        )
        data = getattr(response, "data", None) or []
        if data:
            return data[0]
    except HTTPException as exc:
        if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            updated = local_update_consultation(consultation_id, patch)
            if updated:
                return updated
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Consultation {consultation_id} not found in local store",
            ) from exc
        raise
    except Exception as exc:  # noqa: BLE001
        if _is_network_or_connection_error(exc):
            logger.warning(
                "Supabase unreachable (%s). Updating in local storage.",
                exc,
            )
            updated = local_update_consultation(consultation_id, patch)
            if updated:
                return updated
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Consultation {consultation_id} not found in local store",
            ) from exc
        _raise_supabase_error(exc, action="update consultation")

    local_updated = local_update_consultation(consultation_id, patch)
    if local_updated:
        return local_updated
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Failed to update consultation record",
    )


def insert_consultation(row: Dict[str, Any]) -> Dict[str, Any]:
    """Insert a consultations row and return the created record."""
    try:
        client = get_supabase_client()
        response = client.table("consultations").insert(row).execute()
        data = getattr(response, "data", None) or []
        if data:
            return data[0]
    except HTTPException as exc:
        if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            logger.warning("Supabase unconfigured. Persisting consultation locally.")
            return local_insert_consultation(row)
        raise
    except Exception as exc:  # noqa: BLE001
        if _is_network_or_connection_error(exc):
            logger.warning(
                "Supabase unreachable (%s). Persisting consultation locally.",
                exc,
            )
            return local_insert_consultation(row)
        _raise_supabase_error(exc, action="insert consultation")

    # If Supabase gave empty response data, persist locally
    logger.warning("Supabase returned empty data on insert. Saving locally.")
    return local_insert_consultation(row)


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
