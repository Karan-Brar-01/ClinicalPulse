/**
 * Backend API helpers. Proxies through Next rewrite or absolute URL.
 */

import type {
  Consultation,
  ResolveConsultationPayload,
} from "@/types/clinical";

export type RppgResult = {
  heart_rate_bpm: number;
  hrv_sdnn: number;
  confidence?: number;
  pulse_wave?: number[];
  usable?: boolean;
  error?: string;
  source?: string;
  method?: string;
  diagnostics?: Record<string, unknown>;
};

export type AcousticResult = {
  cough_type: string;
  severity_score: number;
  wheeze_detected: boolean;
  crackle_detected: boolean;
  acoustic_confidence?: number;
  spectrogram_url?: string;
  audio_url?: string;
  usable?: boolean;
  error?: string;
};

export type TriageCompleteResponse = {
  consultation: Consultation;
  triage: Record<string, unknown>;
};

export type IntakeChatResponse = {
  reply: string;
  intake_complete: boolean;
  chief_complaint: string;
  red_flags_noted?: string[];
};

export type RgbSample = { r: number; g: number; b: number };

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "/backend-api";

export function apiUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  // Avoid double /api when base already ends with path prefix
  return `${API_BASE}${p}`;
}

async function readError(res: Response): Promise<string> {
  const detail = await res.text();
  return detail || `Request failed (${res.status})`;
}

export async function postIntakeChat(
  messages: { role: string; content: string }[],
): Promise<IntakeChatResponse> {
  const res = await fetch(apiUrl("/api/intake/chat"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function postRppg(
  greenSeries: number[],
  fps = 30,
  rgbSeries?: RgbSample[],
): Promise<RppgResult> {
  const body: Record<string, unknown> = { fps };
  if (rgbSeries && rgbSeries.length > 0) {
    body.rgb_series = rgbSeries;
  } else {
    body.green_series = greenSeries;
  }
  const res = await fetch(apiUrl("/api/vitals/rppg"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function postAcoustic(
  blob: Blob,
  sampleRate = 22050,
): Promise<AcousticResult> {
  const form = new FormData();
  const ext = blob.type.includes("wav") ? "wav" : "webm";
  form.append("file", blob, `cough.${ext}`);
  form.append("sample_rate", String(sampleRate));

  const res = await fetch(apiUrl("/api/vitals/acoustic"), {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function postTriageComplete(payload: {
  chief_complaint: string;
  symptom_transcript: { role: string; content: string }[];
  vitals: Record<string, unknown>;
  acoustic: Record<string, unknown>;
}): Promise<TriageCompleteResponse> {
  const res = await fetch(apiUrl("/api/triage/complete"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function listConsultations(
  status = "ready_for_doctor,analyzing",
): Promise<Consultation[]> {
  const res = await fetch(
    apiUrl(`/api/consultations?status=${encodeURIComponent(status)}&limit=50`),
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error(await readError(res));
  const data = (await res.json()) as { consultations: Consultation[] };
  return data.consultations ?? [];
}

export async function getConsultation(id: string): Promise<Consultation> {
  const res = await fetch(apiUrl(`/api/consultations/${id}`), {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

export async function resolveConsultation(
  id: string,
  payload: ResolveConsultationPayload,
): Promise<Consultation> {
  const res = await fetch(apiUrl(`/api/consultations/${id}/resolve`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}
