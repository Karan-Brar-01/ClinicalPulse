"""REST routes for vitals, acoustic analysis, triage, and consultations."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status

from app.api.schemas import (
    IntakeChatRequest,
    ResolveConsultationRequest,
    RPPGJsonRequest,
    TriageCompleteRequest,
)
from app.services.acoustic_service import AcousticProcessor
from app.services.intake_service import IntakeChatService
from app.services.rppg_service import RPPGProcessor
from app.services.supabase_client import (
    get_consultation,
    insert_consultation,
    list_consultations,
    update_consultation,
)
from app.services.triage_service import ClinicalTriageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

_rppg = RPPGProcessor()
_acoustic = AcousticProcessor()
_triage = ClinicalTriageService()
_intake = IntakeChatService()


# ---------------------------------------------------------------------------
# Intake chat (LLM)
# ---------------------------------------------------------------------------


@router.post("/intake/chat")
async def intake_chat(body: IntakeChatRequest) -> Dict[str, Any]:
    """Adaptive LLM follow-up for the patient intake wizard."""
    return _intake.next_turn(body.messages)


# ---------------------------------------------------------------------------
# Vitals: rPPG
# ---------------------------------------------------------------------------


@router.post("/vitals/rppg")
async def process_rppg(request: Request) -> Dict[str, Any]:
    """
    Compute BPM / HRV from green-channel samples or an uploaded MP4/WebM video.

    Accepts either:
    - ``application/json`` with ``{ "green_series": [...], "fps": 30 }``
    - ``multipart/form-data`` with ``file`` (video) and optional ``fps``,
      or ``green_series`` as a JSON string form field.
    """
    content_type = (request.headers.get("content-type") or "").lower()

    # --- JSON body path ---
    if "application/json" in content_type:
        try:
            payload = RPPGJsonRequest.model_validate(await request.json())
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid rPPG JSON body: {exc}",
            ) from exc

        if payload.rgb_series:
            rgb_tuples = _coerce_rgb_series(payload.rgb_series)
            result = _rppg.process_rgb_samples(rgb_tuples, fps=payload.fps)
            return _format_rppg_response(result, source="rgb_series", fps=payload.fps)

        result = _rppg.process_raw_green_samples(
            payload.green_series or [], fps=payload.fps
        )
        return _format_rppg_response(result, source="green_series", fps=payload.fps)

    # --- Multipart form path ---
    if "multipart/form-data" in content_type:
        form = await request.form()
        fps_raw = form.get("fps", 30.0)
        try:
            fps = float(fps_raw) if fps_raw is not None else 30.0
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="fps must be a number",
            ) from exc

        green_raw = form.get("green_series")
        if green_raw is not None and not hasattr(green_raw, "read"):
            try:
                samples = json.loads(str(green_raw))
                if not isinstance(samples, list):
                    raise ValueError("green_series must be a JSON array of numbers")
                samples_f = [float(x) for x in samples]
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid green_series form field: {exc}",
                ) from exc
            result = _rppg.process_raw_green_samples(samples_f, fps=fps)
            return _format_rppg_response(result, source="green_series", fps=fps)

        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Provide multipart video file or green_series form field",
            )

        raw = await upload.read()  # type: ignore[union-attr]
        if not raw:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Uploaded video is empty",
            )

        filename = getattr(upload, "filename", None) or "clip.mp4"
        frames, detected_fps = _frames_from_video_bytes(raw, filename=filename)
        use_fps = detected_fps if detected_fps > 0 else fps
        result = _rppg.process_video_frames(frames, fps=use_fps)
        return _format_rppg_response(result, source="video", fps=use_fps)

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Content-Type must be application/json or multipart/form-data",
    )


def _format_rppg_response(
    result: Dict[str, Any],
    *,
    source: str,
    fps: Optional[float] = None,
) -> Dict[str, Any]:
    return {
        "heart_rate_bpm": result.get("heart_rate"),
        "hrv_sdnn": result.get("hrv_sdnn"),
        "confidence": result.get("confidence"),
        "pulse_wave": result.get("pulse_wave") or [],
        "usable": result.get("usable", False),
        "error": result.get("error"),
        "method": result.get("method"),
        "diagnostics": result.get("diagnostics"),
        "source": source,
        "fps": fps,
    }


def _coerce_rgb_series(raw: List[Any]) -> List[Tuple[float, float, float]]:
    out: List[Tuple[float, float, float]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append((float(item["r"]), float(item["g"]), float(item["b"])))
        elif hasattr(item, "r"):
            out.append((float(item.r), float(item.g), float(item.b)))
        elif isinstance(item, (list, tuple)) and len(item) >= 3:
            out.append((float(item[0]), float(item[1]), float(item[2])))
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="rgb_series items must be {r,g,b} or [r,g,b]",
            )
    return out


def _frames_from_video_bytes(
    data: bytes,
    *,
    filename: str,
    max_frames: int = 900,
) -> Tuple[List[np.ndarray], float]:
    """Decode video bytes via OpenCV; return frames and detected FPS."""
    suffix = Path(filename).suffix.lower() or ".mp4"
    if suffix not in {".mp4", ".webm", ".avi", ".mov", ".mkv"}:
        suffix = ".mp4"

    frames: List[np.ndarray] = []
    detected_fps = 30.0

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        cap = cv2.VideoCapture(tmp.name)
        if not cap.isOpened():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not open uploaded video (corrupt or unsupported codec)",
            )
        prop_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if prop_fps > 1.0:
            detected_fps = prop_fps
        try:
            while len(frames) < max_frames:
                ok, frame = cap.read()
                if not ok:
                    break
                frames.append(frame)
        finally:
            cap.release()

    if not frames:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No frames decoded from uploaded video",
        )
    return frames, detected_fps


# ---------------------------------------------------------------------------
# Vitals: acoustic
# ---------------------------------------------------------------------------


@router.post("/vitals/acoustic")
async def process_acoustic(
    file: UploadFile = File(...),
    sample_rate: int = Form(22050),
) -> Dict[str, Any]:
    """Analyze an uploaded cough / lung audio clip."""
    raw = await file.read()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded audio is empty",
        )
    if sample_rate <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="sample_rate must be positive",
        )

    result = _acoustic.analyze_cough_audio(raw, sample_rate=sample_rate)
    return {
        "cough_type": result.get("cough_type"),
        "severity_score": result.get("severity_score"),
        "wheeze_detected": result.get("wheeze_detected"),
        "crackle_detected": result.get("crackle_detected"),
        "acoustic_confidence": result.get("acoustic_confidence"),
        "spectrogram_url": result.get("spectrogram_url") or "",
        "usable": result.get("usable", False),
        "error": result.get("error"),
        "features": result.get("features"),
        "filename": file.filename,
    }


# ---------------------------------------------------------------------------
# Triage complete
# ---------------------------------------------------------------------------


@router.post("/triage/complete", status_code=status.HTTP_201_CREATED)
async def triage_complete(body: TriageCompleteRequest) -> Dict[str, Any]:
    """
    Generate SBAR + differential via Groq and persist a consultations row.
    """
    intake = {
        "chief_complaint": body.chief_complaint,
        "symptom_transcript": body.symptom_transcript,
        "age": body.age,
        "biological_sex": body.biological_sex,
        "notes": body.notes,
    }
    triage = _triage.generate_differential_and_sbar(
        intake_data=intake,
        vitals=body.vitals,
        acoustic=body.acoustic,
    )

    respiratory_analysis = {
        "classification": body.acoustic.get("cough_type"),
        "confidence": body.acoustic.get("acoustic_confidence"),
        "spectrogram_url": body.acoustic.get("spectrogram_url"),
        "audio_url": body.acoustic.get("audio_url"),
        "severity_score": body.acoustic.get("severity_score"),
        "wheeze_detected": body.acoustic.get("wheeze_detected"),
        "crackle_detected": body.acoustic.get("crackle_detected"),
        "features": body.acoustic.get("features"),
        "usable": body.acoustic.get("usable"),
    }

    hr = body.vitals.get("heart_rate_bpm", body.vitals.get("heart_rate"))
    hrv = body.vitals.get("hrv_sdnn")

    prescription_text = None
    rx_list = triage.get("suggested_prescriptions") or []
    if rx_list:
        prescription_text = "\n".join(str(x) for x in rx_list)

    row: Dict[str, Any] = {
        "patient_id": body.patient_id,
        "status": "ready_for_doctor",
        "chief_complaint": body.chief_complaint,
        "symptom_transcript": body.symptom_transcript,
        "heart_rate_bpm": hr,
        "hrv_sdnn": hrv,
        "respiratory_analysis": respiratory_analysis,
        "sbar_report": triage.get("sbar"),
        "differential_diagnosis": triage.get("differential_diagnosis"),
        "prescription": prescription_text,
    }

    # Attach urgency + telemetry in sbar_report without altering schema columns
    sbar = dict(triage.get("sbar") or {})
    sbar["urgency_level"] = triage.get("urgency_level")
    sbar["guardrails"] = triage.get("guardrails")
    sbar["model"] = triage.get("model")
    sbar["patient_report"] = triage.get("patient_report")
    sbar["telemetry"] = {
        "heart_rate_bpm": hr,
        "hrv_sdnn": hrv,
        "confidence": body.vitals.get("confidence"),
        "pulse_wave": body.vitals.get("pulse_wave") or [],
        "usable": body.vitals.get("usable"),
    }
    row["sbar_report"] = sbar

    created = insert_consultation(row)
    return {
        "consultation": created,
        "triage": triage,
    }


# ---------------------------------------------------------------------------
# Consultations
# ---------------------------------------------------------------------------


@router.get("/consultations")
async def fetch_consultations(
    status: Optional[str] = "ready_for_doctor,analyzing",
    limit: int = 50,
) -> Dict[str, Any]:
    """List queued / active consultations for the doctor sidebar."""
    items = list_consultations(status_filter=status, limit=min(limit, 100))
    return {"consultations": items, "count": len(items)}


@router.get("/consultations/{consultation_id}")
async def fetch_consultation(consultation_id: str) -> Dict[str, Any]:
    """Retrieve full consultation record for the doctor command center."""
    return get_consultation(consultation_id)


@router.post("/consultations/{consultation_id}/resolve")
async def resolve_consultation(
    consultation_id: str,
    body: ResolveConsultationRequest,
) -> Dict[str, Any]:
    """Doctor updates notes and approves or edits prescriptions."""
    patch: Dict[str, Any] = {}
    if body.doctor_notes is not None:
        patch["doctor_notes"] = body.doctor_notes
    if body.prescription is not None:
        patch["prescription"] = body.prescription

    if body.status is not None:
        patch["status"] = body.status
    elif body.approved:
        patch["status"] = "completed"
    else:
        patch["status"] = "ready_for_doctor"

    if not patch:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields to update",
        )

    return update_consultation(consultation_id, patch)
