"""Conversational clinical intake via Groq (adaptive follow-up questions)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from groq import Groq

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "openai/gpt-oss-120b"


def _model() -> str:
    return get_settings().groq_model or _DEFAULT_MODEL

_SYSTEM_PROMPT = """You are ClinicalPulse Intake — a warm, precise virtual triage nurse.
Your job is to take a focused history before biometric vitals/cough capture.

Conversation rules:
- Ask ONE clear question at a time based on what the patient just said.
- Show clinical consciousness: follow up on red flags (chest pain, SOB, neuro deficits,
  severe bleeding, anaphylaxis, suicidal ideation), duration, severity, associated symptoms,
  relevant PMH/meds/allergies when useful.
- Do NOT dump a checklist. Adapt like a real clinician.
- Keep replies short (1–3 sentences). Empathetic, plain language. No diagnosis yet.
- After you have enough for a safe pre-clinical handoff (typically 4–8 patient turns,
  or sooner if the story is clear), set intake_complete=true and summarize.

Respond with STRICT JSON only:
{
  "reply": "Your next message to the patient",
  "intake_complete": false,
  "chief_complaint": "Short label for the main problem (update each turn)",
  "red_flags_noted": ["optional list"]
}

When intake_complete is true, reply should thank them and say they can continue to
the optical vitals check — do not ask another clinical question.
"""


class IntakeChatService:
    """Adaptive LLM intake interviewer."""

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

    def next_turn(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Given chat history, return the next assistant reply + completion flag.
        """
        cleaned = self._normalize_messages(messages)
        if not cleaned:
            return {
                "reply": "Hi — I'm your ClinicalPulse intake assistant. What's bothering you today?",
                "intake_complete": False,
                "chief_complaint": "",
                "red_flags_noted": [],
            }

        client = self._client()
        if not client:
            return self._heuristic_fallback(cleaned)

        try:
            completion = client.chat.completions.create(
                model=_model(),
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Continue this intake. Chat history (JSON):\n"
                            f"{json.dumps(cleaned, ensure_ascii=False)}\n"
                            "Return JSON only."
                        ),
                    },
                ],
                temperature=0.4,
                max_tokens=512,
                response_format={"type": "json_object"},
            )
            raw = completion.choices[0].message.content or "{}"
            parsed = self._parse_json(raw)
            return self._validate(parsed, cleaned)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Intake LLM failed: %s", exc)
            return self._heuristic_fallback(cleaned)

    @staticmethod
    def _normalize_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for m in messages:
            role = str(m.get("role") or "").strip().lower()
            content = str(m.get("content") or "").strip()
            if role not in {"user", "assistant", "system"} or not content:
                continue
            if role == "system":
                continue
            out.append({"role": role, "content": content[:2000]})
        return out[-24:]

    @staticmethod
    def _parse_json(raw: str) -> Dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return json.loads(text)

    def _validate(self, data: Dict[str, Any], history: List[Dict[str, str]]) -> Dict[str, Any]:
        reply = str(data.get("reply") or "").strip()
        if not reply:
            reply = "Could you tell me a bit more about that?"
        complete = bool(data.get("intake_complete"))
        chief = str(data.get("chief_complaint") or "").strip()
        if not chief:
            first_user = next((m["content"] for m in history if m["role"] == "user"), "")
            chief = first_user[:120]
        flags = data.get("red_flags_noted") or []
        if not isinstance(flags, list):
            flags = []
        return {
            "reply": reply,
            "intake_complete": complete,
            "chief_complaint": chief,
            "red_flags_noted": [str(x) for x in flags][:8],
            "model": _model(),
        }

    def _heuristic_fallback(self, history: List[Dict[str, str]]) -> Dict[str, Any]:
        """Offline / no-key adaptive-ish prompts (better than a fixed 3-list)."""
        user_turns = [m["content"] for m in history if m["role"] == "user"]
        n = len(user_turns)
        last = (user_turns[-1] if user_turns else "").lower()
        chief = user_turns[0][:120] if user_turns else ""

        if n == 0:
            return {
                "reply": "Hi — I'm your ClinicalPulse intake assistant. What's bothering you today?",
                "intake_complete": False,
                "chief_complaint": "",
                "red_flags_noted": [],
            }

        red_flags: List[str] = []
        for token, label in [
            ("chest pain", "chest pain"),
            ("shortness of breath", "dyspnea"),
            ("can't breathe", "dyspnea"),
            ("faint", "syncope"),
            ("stroke", "neuro"),
            ("suicid", "si"),
        ]:
            if token in last:
                red_flags.append(label)

        if red_flags and n < 5:
            return {
                "reply": (
                    "That sounds important. On a scale of 1–10, how severe is it right now, "
                    "and did it start suddenly or gradually?"
                ),
                "intake_complete": False,
                "chief_complaint": chief,
                "red_flags_noted": red_flags,
            }

        followups = [
            "How long have you had this, and is it getting better, worse, or staying the same?",
            "Any fever, chills, cough, nausea, or other symptoms along with this?",
            "Have you had this before, and are you on any medications or have allergies I should know?",
            "Anything that makes it better or worse (activity, position, food, rest)?",
        ]
        if n <= len(followups):
            return {
                "reply": followups[n - 1],
                "intake_complete": False,
                "chief_complaint": chief,
                "red_flags_noted": red_flags,
            }

        return {
            "reply": (
                "Thanks — I have enough for intake. Continue to the optical vitals check when you're ready."
            ),
            "intake_complete": True,
            "chief_complaint": chief,
            "red_flags_noted": red_flags,
        }
