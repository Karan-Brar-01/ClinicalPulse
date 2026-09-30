/**
 * Strict domain types for the Doctor Command Center.
 */

export type UrgencyLevel = "ROUTINE" | "URGENT" | "EMERGENCY";

export type ConsultationStatus =
  | "intake"
  | "analyzing"
  | "ready_for_doctor"
  | "completed";

export interface PatientReport {
  headline?: string;
  likely_conditions?: {
    name: string;
    likelihood: string;
    plain_explanation?: string;
  }[];
  what_we_measured?: string;
  what_to_watch_for?: string[];
  next_steps?: string;
  disclaimer?: string;
}

export interface SbarReport {
  situation?: string;
  background?: string;
  assessment?: string;
  recommendation?: string;
  urgency_level?: UrgencyLevel | string;
  model?: string;
  guardrails?: Record<string, unknown>;
  patient_report?: PatientReport;
  telemetry?: {
    heart_rate_bpm?: number | null;
    hrv_sdnn?: number | null;
    confidence?: number | null;
    pulse_wave?: number[];
    usable?: boolean;
  };
}

export interface DifferentialItem {
  condition: string;
  probability: number;
  icd10_code?: string;
  reasoning?: string;
}

export interface RespiratoryAnalysis {
  classification?: string;
  confidence?: number;
  spectrogram_url?: string;
  audio_url?: string;
  severity_score?: number;
  wheeze_detected?: boolean;
  crackle_detected?: boolean;
  features?: Record<string, unknown>;
  usable?: boolean;
}

export interface Consultation {
  id: string;
  patient_id?: string | null;
  status: ConsultationStatus | string;
  chief_complaint?: string | null;
  symptom_transcript?: { role?: string; content?: string }[] | unknown;
  heart_rate_bpm?: number | null;
  hrv_sdnn?: number | null;
  respiratory_analysis?: RespiratoryAnalysis | null;
  sbar_report?: SbarReport | null;
  differential_diagnosis?: DifferentialItem[] | null;
  doctor_notes?: string | null;
  prescription?: string | null;
  created_at: string;
}

export interface ResolveConsultationPayload {
  doctor_notes?: string;
  prescription?: string;
  approved?: boolean;
  status?: "completed" | "ready_for_doctor";
}
