"""Pydantic request/response models for ClinicalPulse API."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


class RgbSample(BaseModel):
    r: float
    g: float
    b: float


class RPPGJsonRequest(BaseModel):
    """JSON body for green-channel and/or RGB rPPG time series."""

    green_series: Optional[List[float]] = None
    rgb_series: Optional[List[Union[RgbSample, List[float]]]] = None
    fps: float = Field(default=30.0, gt=0)
    consultation_id: Optional[str] = None

    @model_validator(mode="after")
    def require_series(self) -> "RPPGJsonRequest":
        if not self.green_series and not self.rgb_series:
            raise ValueError("Provide green_series and/or rgb_series")
        return self


class IntakeChatRequest(BaseModel):
    messages: List[Dict[str, str]] = Field(default_factory=list)


class TriageCompleteRequest(BaseModel):
    """Full session payload for SBAR + differential synthesis."""

    chief_complaint: Optional[str] = None
    symptom_transcript: List[Any] = Field(default_factory=list)
    age: Optional[int] = None
    biological_sex: Optional[str] = None
    patient_id: Optional[str] = None
    vitals: Dict[str, Any] = Field(default_factory=dict)
    acoustic: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None


class ResolveConsultationRequest(BaseModel):
    """Doctor sign-off: notes + prescription approval."""

    doctor_notes: Optional[str] = None
    prescription: Optional[str] = None
    approved: bool = True
    status: Optional[Literal["completed", "ready_for_doctor"]] = None
