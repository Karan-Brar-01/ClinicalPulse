"""Local SQLite fallback storage for ClinicalPulse consultations."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "consultations.db"


def _init_db() -> None:
    """Ensure the local database directory and table exist."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS consultations (
                id TEXT PRIMARY KEY,
                patient_id TEXT,
                status TEXT NOT NULL DEFAULT 'ready_for_doctor',
                chief_complaint TEXT,
                symptom_transcript TEXT,
                heart_rate_bpm REAL,
                hrv_sdnn REAL,
                respiratory_analysis TEXT,
                sbar_report TEXT,
                differential_diagnosis TEXT,
                doctor_notes TEXT,
                prescription TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_consultations_status_created
            ON consultations (status, created_at DESC)
            """
        )


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert an sqlite3 Row to a clean dictionary matching Supabase shape."""
    d = dict(row)
    for json_col in (
        "symptom_transcript",
        "respiratory_analysis",
        "sbar_report",
        "differential_diagnosis",
    ):
        raw_val = d.get(json_col)
        if isinstance(raw_val, str) and raw_val.strip():
            try:
                d[json_col] = json.loads(raw_val)
            except Exception:
                pass
        elif raw_val is None:
            if json_col in ("symptom_transcript", "differential_diagnosis"):
                d[json_col] = []
            else:
                d[json_col] = {}
    return d


def local_insert_consultation(row: Dict[str, Any]) -> Dict[str, Any]:
    """Insert a consultation into local SQLite store."""
    _init_db()
    cid = str(row.get("id") or uuid.uuid4())
    created_at = str(row.get("created_at") or datetime.now(timezone.utc).isoformat())

    status = str(row.get("status") or "ready_for_doctor")
    patient_id = str(row.get("patient_id")) if row.get("patient_id") else None
    chief_complaint = row.get("chief_complaint")
    symptom_transcript = json.dumps(row.get("symptom_transcript") or [])
    heart_rate_bpm = row.get("heart_rate_bpm")
    hrv_sdnn = row.get("hrv_sdnn")
    respiratory_analysis = json.dumps(row.get("respiratory_analysis") or {})
    sbar_report = json.dumps(row.get("sbar_report") or {})
    differential_diagnosis = json.dumps(row.get("differential_diagnosis") or [])
    doctor_notes = row.get("doctor_notes")
    prescription = row.get("prescription")

    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT OR REPLACE INTO consultations (
                id, patient_id, status, chief_complaint, symptom_transcript,
                heart_rate_bpm, hrv_sdnn, respiratory_analysis, sbar_report,
                differential_diagnosis, doctor_notes, prescription, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cid,
                patient_id,
                status,
                chief_complaint,
                symptom_transcript,
                heart_rate_bpm,
                hrv_sdnn,
                respiratory_analysis,
                sbar_report,
                differential_diagnosis,
                doctor_notes,
                prescription,
                created_at,
            ),
        )
        cur = conn.execute("SELECT * FROM consultations WHERE id = ?", (cid,))
        inserted = cur.fetchone()
        return _row_to_dict(inserted)


def local_list_consultations(
    status_filter: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """List consultations from local SQLite store."""
    _init_db()
    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM consultations"
        params: List[Any] = []
        if status_filter:
            statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
            if statuses:
                placeholders = ",".join("?" for _ in statuses)
                query += f" WHERE status IN ({placeholders})"
                params.extend(statuses)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cur = conn.execute(query, params)
        return [_row_to_dict(r) for r in cur.fetchall()]


def local_get_consultation(consultation_id: str) -> Optional[Dict[str, Any]]:
    """Get a single consultation by ID from local SQLite store."""
    _init_db()
    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM consultations WHERE id = ?", (consultation_id,))
        row = cur.fetchone()
        return _row_to_dict(row) if row else None


def local_update_consultation(
    consultation_id: str,
    patch: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Patch a consultation in local SQLite store."""
    _init_db()
    allowed_cols = {
        "status",
        "chief_complaint",
        "symptom_transcript",
        "heart_rate_bpm",
        "hrv_sdnn",
        "respiratory_analysis",
        "sbar_report",
        "differential_diagnosis",
        "doctor_notes",
        "prescription",
    }
    set_clauses: List[str] = []
    params: List[Any] = []
    for k, v in patch.items():
        if k not in allowed_cols:
            continue
        if k in (
            "symptom_transcript",
            "respiratory_analysis",
            "sbar_report",
            "differential_diagnosis",
        ) and isinstance(v, (dict, list)):
            v = json.dumps(v)
        set_clauses.append(f"{k} = ?")
        params.append(v)

    if not set_clauses:
        return local_get_consultation(consultation_id)

    params.append(consultation_id)
    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            f"UPDATE consultations SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )
        cur = conn.execute("SELECT * FROM consultations WHERE id = ?", (consultation_id,))
        row = cur.fetchone()
        return _row_to_dict(row) if row else None
