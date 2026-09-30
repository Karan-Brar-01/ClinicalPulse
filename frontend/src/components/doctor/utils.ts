import type { UrgencyLevel } from "@/types/clinical";

export function formatQueueDuration(createdAt: string, now = Date.now()): string {
  const start = new Date(createdAt).getTime();
  if (Number.isNaN(start)) return "—";
  const mins = Math.max(0, Math.floor((now - start) / 60000));
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h}h ${m}m`;
}

export function normalizeUrgency(raw?: string | null): UrgencyLevel {
  const u = (raw || "ROUTINE").toUpperCase();
  if (u === "EMERGENCY" || u === "URGENT" || u === "ROUTINE") return u;
  return "URGENT";
}

export function urgencyBadgeClass(level: UrgencyLevel): string {
  switch (level) {
    case "EMERGENCY":
      return "border-rose-500/50 bg-rose-500/15 text-rose-300 shadow-[0_0_16px_rgba(244,63,94,0.25)]";
    case "URGENT":
      return "border-amber-500/50 bg-amber-500/15 text-amber-200 shadow-[0_0_16px_rgba(245,158,11,0.25)]";
    default:
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-300 shadow-glow-sm";
  }
}

/** Adult resting HR heuristics for badge only — not diagnostic. */
export function hrBand(bpm: number | null | undefined): "low" | "normal" | "high" | "unknown" {
  if (bpm == null || Number.isNaN(Number(bpm))) return "unknown";
  const v = Number(bpm);
  if (v < 50) return "low";
  if (v > 100) return "high";
  return "normal";
}

export function synthesizePulseWave(bpm: number, points = 90): number[] {
  const freq = Math.max(0.5, bpm / 60);
  return Array.from({ length: points }, (_, i) => {
    const t = i / 30;
    return Math.sin(2 * Math.PI * freq * t) * 0.8 + Math.sin(4 * Math.PI * freq * t) * 0.15;
  });
}
