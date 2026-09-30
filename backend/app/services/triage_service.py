"""Clinical LLM triage: SBAR brief + differential diagnosis via Groq."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from groq import Groq

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "openai/gpt-oss-120b"
_VALID_URGENCY = frozenset({"ROUTINE", "URGENT", "EMERGENCY"})


def _model() -> str:
    return get_settings().groq_model or _DEFAULT_MODEL

_SYSTEM_PROMPT = """You are a Senior Board-Certified Emergency Triage Physician.
You perform pre-clinical triage decision support for a telemedicine platform.

Analyze the patient chief complaint, conversational transcript, and objective
telemetry (heart rate BPM, HRV SDNN, acoustic cough profile). Reconcile
subjective symptoms with measured vitals and acoustics. Do NOT invent vitals
or acoustic findings that are not provided. If telemetry is missing or marked
unusable, state that limitation in assessment.

Respond with STRICT JSON only (no markdown fences) matching this schema:
{
  "sbar": {
    "situation": "Concise 1-sentence headline",
    "background": "Relevant medical history and symptom timeline",
    "assessment": "Clinical synthesis reconciling physical symptoms with vitals/acoustic data",
    "recommendation": "Suggested immediate diagnostic/pharmacological actions for the reviewing physician"
  },
  "differential_diagnosis": [
    {
      "condition": "Condition Name",
      "probability": 0.85,
      "icd10_code": "J20.9",
      "reasoning": "Why this aligns with cough acoustics and tachycardia"
    }
  ],
  "urgency_level": "ROUTINE" | "URGENT" | "EMERGENCY",
  "suggested_prescriptions": ["Medication Name - Dosage - Frequency"],
  "patient_report": {
    "headline": "Short plain-language summary for the patient",
    "likely_conditions": [
      {
        "name": "Condition in plain words",
        "likelihood": "possible",
        "plain_explanation": "Why this might fit, without alarming jargon"
      }
    ],
    "what_we_measured": "Your heart rate was … cough pattern suggested …",
    "what_to_watch_for": ["Seek emergency care if …"],
    "next_steps": "A clinician will review your chart shortly.",
    "disclaimer": "This is decision support, not a medical diagnosis."
  }
}

Rules:
- Provide 2–5 differential entries; probabilities should be between 0 and 1 and ideally sum near 1.0.
- Use plausible ICD-10 codes.
- suggested_prescriptions are DRAFTS for physician review only — never imply automatic dispensing.
- urgency_level must be exactly one of: ROUTINE, URGENT, EMERGENCY.
- ALSO include patient_report for the waiting patient (plain language, no drug orders):
  {
    "headline": "Short plain-language summary",
    "likely_conditions": [{"name": "...", "likelihood": "possible|likely|less likely", "plain_explanation": "..."}],
    "what_we_measured": "1–2 sentences on vitals/cough findings in plain English",
    "what_to_watch_for": ["red-flag symptoms that mean seek ER now"],
    "next_steps": "What happens while waiting for the doctor",
    "disclaimer": "This is not a diagnosis..."
  }
"""


class ClinicalTriageService:
    """Groq-backed SBAR and differential diagnosis generator."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key_override = api_key

    def _client(self) -> Optional[Groq]:
        key = (
            self._api_key_override
            if self._api_key_override is not None
            else get_settings().groq_api_key
        )
        if not key:
            return None
        return Groq(api_key=key)

    def generate_differential_and_sbar(
        self,
        intake_data: dict[str, Any],
        vitals: dict[str, Any],
        acoustic: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Call llama-3.3-70b-versatile and return validated triage JSON.

        On model/API failure returns a safe deterministic fallback with
        urgency URGENT so a physician still reviews the chart.
        """
        user_payload = self._build_user_payload(intake_data, vitals, acoustic)

        client = self._client()
        if not client:
            logger.error("GROQ_API_KEY missing — returning fallback triage")
            return self._fallback(
                intake_data,
                vitals,
                acoustic,
                reason="groq_api_key_missing",
            )

        try:
            completion = client.chat.completions.create(
                model=_model(),
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Analyze this pre-clinical session and return JSON only:\n"
                            f"{json.dumps(user_payload, default=str)}"
                        ),
                    },
                ],
                temperature=0.2,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            raw = completion.choices[0].message.content or ""
            parsed = self._parse_json(raw)
            return self._validate(parsed)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Groq triage generation failed: %s", exc)
            return self._fallback(
                intake_data,
                vitals,
                acoustic,
                reason=f"groq_error: {exc}",
            )

    @staticmethod
    def _build_user_payload(
        intake_data: dict[str, Any],
        vitals: dict[str, Any],
        acoustic: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "intake": {
                "chief_complaint": intake_data.get("chief_complaint"),
                "age": intake_data.get("age"),
                "biological_sex": intake_data.get("biological_sex"),
                "transcript": intake_data.get("symptom_transcript")
                or intake_data.get("transcript")
                or [],
                "notes": intake_data.get("notes"),
            },
            "vitals": {
                "heart_rate_bpm": vitals.get("heart_rate")
                or vitals.get("heart_rate_bpm"),
                "hrv_sdnn": vitals.get("hrv_sdnn"),
                "confidence": vitals.get("confidence"),
                "usable": vitals.get("usable"),
                "error": vitals.get("error"),
            },
            "acoustic": {
                "cough_type": acoustic.get("cough_type"),
                "severity_score": acoustic.get("severity_score"),
                "wheeze_detected": acoustic.get("wheeze_detected"),
                "crackle_detected": acoustic.get("crackle_detected"),
                "acoustic_confidence": acoustic.get("acoustic_confidence"),
                "usable": acoustic.get("usable"),
                "error": acoustic.get("error"),
            },
            "disclaimer": (
                "Decision support only. Physician must confirm before any treatment."
            ),
        }

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return json.loads(text)

    def _validate(self, data: dict[str, Any]) -> dict[str, Any]:
        sbar_in = data.get("sbar") if isinstance(data.get("sbar"), dict) else {}
        sbar = {
            "situation": str(sbar_in.get("situation") or "").strip() or "Triage pending review",
            "background": str(sbar_in.get("background") or "").strip() or "Insufficient background",
            "assessment": str(sbar_in.get("assessment") or "").strip() or "Assessment incomplete",
            "recommendation": str(sbar_in.get("recommendation") or "").strip()
            or "Physician review required",
        }

        differentials: list[dict[str, Any]] = []
        raw_dx = data.get("differential_diagnosis") or []
        if isinstance(raw_dx, list):
            for item in raw_dx:
                if not isinstance(item, dict):
                    continue
                try:
                    prob = float(item.get("probability", 0))
                except (TypeError, ValueError):
                    prob = 0.0
                differentials.append(
                    {
                        "condition": str(item.get("condition") or "Unspecified").strip(),
                        "probability": max(0.0, min(1.0, prob)),
                        "icd10_code": str(item.get("icd10_code") or "").strip(),
                        "reasoning": str(item.get("reasoning") or "").strip(),
                    }
                )

        if not differentials:
            differentials = [
                {
                    "condition": "Undifferentiated presentation",
                    "probability": 1.0,
                    "icd10_code": "R69",
                    "reasoning": "Model returned no differentials; default placeholder.",
                }
            ]

        # Soft-normalize probabilities if wildly off
        total = sum(d["probability"] for d in differentials) or 1.0
        if abs(total - 1.0) > 0.15:
            for d in differentials:
                d["probability"] = round(d["probability"] / total, 3)

        urgency = str(data.get("urgency_level") or "URGENT").upper().strip()
        if urgency not in _VALID_URGENCY:
            urgency = "URGENT"

        rx_raw = data.get("suggested_prescriptions") or []
        prescriptions: list[str] = []
        if isinstance(rx_raw, list):
            prescriptions = [str(x).strip() for x in rx_raw if str(x).strip()]

        patient_report = self._validate_patient_report(
            data.get("patient_report"),
            differentials=differentials,
            vitals_hint=None,
        )

        return {
            "sbar": sbar,
            "differential_diagnosis": differentials,
            "urgency_level": urgency,
            "suggested_prescriptions": prescriptions,
            "patient_report": patient_report,
            "model": _model(),
            "guardrails": {
                "schema_validated": True,
                "disclaimer": (
                    "Decision support only. Physician must confirm before treatment."
                ),
            },
        }

    def _validate_patient_report(
        self,
        raw: Any,
        *,
        differentials: list[dict[str, Any]],
        vitals_hint: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        pr = raw if isinstance(raw, dict) else {}
        likely: list[dict[str, str]] = []
        raw_likely = pr.get("likely_conditions") or []
        if isinstance(raw_likely, list):
            for item in raw_likely[:5]:
                if not isinstance(item, dict):
                    continue
                likely.append(
                    {
                        "name": str(item.get("name") or "").strip() or "Unspecified",
                        "likelihood": str(item.get("likelihood") or "possible").strip(),
                        "plain_explanation": str(
                            item.get("plain_explanation") or ""
                        ).strip(),
                    }
                )
        if not likely:
            for d in differentials[:3]:
                likely.append(
                    {
                        "name": d["condition"],
                        "likelihood": (
                            "likely"
                            if d["probability"] >= 0.45
                            else "possible"
                            if d["probability"] >= 0.2
                            else "less likely"
                        ),
                        "plain_explanation": d.get("reasoning") or "",
                    }
                )

        watch = pr.get("what_to_watch_for") or []
        if not isinstance(watch, list):
            watch = []
        watch_s = [str(x).strip() for x in watch if str(x).strip()][:6]
        if not watch_s:
            watch_s = [
                "Worsening shortness of breath",
                "Chest pain or pressure",
                "Confusion, fainting, or severe weakness",
            ]

        return {
            "headline": str(pr.get("headline") or "").strip()
            or "Your pre-visit check is complete and a clinician will review it soon.",
            "likely_conditions": likely,
            "what_we_measured": str(pr.get("what_we_measured") or "").strip()
            or "We captured your symptoms, heart-rate estimate, and cough acoustics for your clinician.",
            "what_to_watch_for": watch_s,
            "next_steps": str(pr.get("next_steps") or "").strip()
            or "Please stay available — a physician will review your chart and may follow up.",
            "disclaimer": str(pr.get("disclaimer") or "").strip()
            or (
                "This is not a diagnosis or prescription. Only a licensed clinician can confirm "
                "your condition and treatment."
            ),
        }

    def _fallback(
        self,
        intake_data: dict[str, Any],
        vitals: dict[str, Any],
        acoustic: dict[str, Any],
        *,
        reason: str,
    ) -> dict[str, Any]:
        complaint = intake_data.get("chief_complaint") or "unspecified complaint"
        hr = vitals.get("heart_rate") or vitals.get("heart_rate_bpm") or "n/a"
        cough = acoustic.get("cough_type") or "n/a"
        return {
            "sbar": {
                "situation": f"Automated triage unavailable — patient reports {complaint}",
                "background": "LLM triage engine failed or is not configured.",
                "assessment": (
                    f"Telemetry on chart: HR={hr} BPM, cough profile={cough}. "
                    f"Engine reason: {reason}"
                ),
                "recommendation": (
                    "Physician must complete manual triage. Do not rely on draft Rx."
                ),
            },
            "differential_diagnosis": [
                {
                    "condition": "Undifferentiated presentation — manual review required",
                    "probability": 1.0,
                    "icd10_code": "R69",
                    "reasoning": "Fallback path; no model-generated differential.",
                }
            ],
            "urgency_level": "URGENT",
            "suggested_prescriptions": [],
            "patient_report": {
                "headline": f"You're in the queue for: {complaint}",
                "likely_conditions": [
                    {
                        "name": "Needs clinician review",
                        "likelihood": "possible",
                        "plain_explanation": (
                            "Automated summary was unavailable; your measurements are still on file."
                        ),
                    }
                ],
                "what_we_measured": f"Heart rate reading: {hr}. Cough profile: {cough}.",
                "what_to_watch_for": [
                    "Severe breathing difficulty",
                    "Chest pain",
                    "Fainting or confusion",
                ],
                "next_steps": "A clinician will review your chart shortly.",
                "disclaimer": (
                    "This is not a diagnosis. A licensed clinician must confirm next steps."
                ),
            },
            "model": _model(),
            "guardrails": {
                "schema_validated": False,
                "fallback": True,
                "reason": reason,
                "disclaimer": (
                    "Decision support only. Physician must confirm before treatment."
                ),
            },
        }
