"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  HeartPulse,
  Loader2,
  Stethoscope,
} from "lucide-react";
import { getConsultation } from "@/lib/api";
import type { Consultation, PatientReport } from "@/types/clinical";

export default function HoldingRoomPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const [consultation, setConsultation] = useState<Consultation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await getConsultation(id);
        if (!cancelled) setConsultation(data);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not load consultation",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const report: PatientReport | undefined =
    consultation?.sbar_report?.patient_report;

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col px-4 py-12">
      <div className="mb-8 flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-emerald-500/30 bg-emerald-500/10 shadow-glow-sm">
          <Stethoscope className="h-5 w-5 text-emerald-300" />
        </div>
        <div>
          <p className="text-lg font-semibold text-slate-50">ClinicalPulse</p>
          <p className="text-xs text-slate-500">Consultation holding room</p>
        </div>
      </div>

      <div className="cp-panel animate-fadeUp p-6">
        {loading && (
          <div className="flex flex-col items-center py-10 text-slate-400">
            <Loader2 className="mb-3 h-8 w-8 animate-spin text-emerald-400" />
            Loading your report…
          </div>
        )}

        {error && (
          <div className="space-y-4">
            <p className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              Chart queued, but the server could not be reached: {error}
            </p>
            <p className="font-mono text-xs text-slate-500">ID: {id}</p>
          </div>
        )}

        {!loading && !error && consultation && (
          <div className="space-y-6">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="mt-0.5 h-6 w-6 shrink-0 text-emerald-400" />
              <div>
                <h1 className="text-xl font-semibold text-slate-100">
                  You&apos;re in the queue
                </h1>
                <p className="mt-1 text-sm text-slate-400">
                  {report?.headline ||
                    "Your pre-clinical workup is complete. A physician will review shortly."}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="cp-panel border-emerald-500/15 p-3">
                <p className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-slate-500">
                  <HeartPulse className="h-3 w-3" /> BPM
                </p>
                <p className="font-mono text-2xl text-emerald-300">
                  {consultation.heart_rate_bpm ?? "—"}
                </p>
              </div>
              <div className="cp-panel border-emerald-500/15 p-3">
                <p className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-slate-500">
                  <Clock className="h-3 w-3" /> Status
                </p>
                <p className="text-sm font-medium text-emerald-200">
                  {consultation.status?.replaceAll("_", " ") || "queued"}
                </p>
              </div>
            </div>

            {report?.what_we_measured && (
              <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
                <p className="text-xs uppercase tracking-wider text-slate-500">
                  What we measured
                </p>
                <p className="mt-1 text-sm leading-relaxed text-slate-200">
                  {report.what_we_measured}
                </p>
              </div>
            )}

            {report?.likely_conditions && report.likely_conditions.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Likely conditions (for discussion — not a diagnosis)
                </p>
                <ul className="space-y-2">
                  {report.likely_conditions.map((c, i) => (
                    <li
                      key={`${c.name}-${i}`}
                      className="rounded-xl border border-slate-800 bg-slate-950/60 p-4"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-slate-100">
                          {c.name}
                        </span>
                        <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-emerald-300">
                          {c.likelihood}
                        </span>
                      </div>
                      {c.plain_explanation && (
                        <p className="mt-2 text-sm leading-relaxed text-slate-400">
                          {c.plain_explanation}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {!report?.likely_conditions?.length &&
              consultation.differential_diagnosis &&
              consultation.differential_diagnosis.length > 0 && (
                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Possible conditions
                  </p>
                  <ul className="space-y-2">
                    {consultation.differential_diagnosis.slice(0, 3).map((d, i) => (
                      <li
                        key={`${d.condition}-${i}`}
                        className="rounded-xl border border-slate-800 bg-slate-950/60 p-4"
                      >
                        <div className="flex justify-between gap-2">
                          <span className="text-sm font-semibold text-slate-100">
                            {d.condition}
                          </span>
                          <span className="font-mono text-xs text-emerald-300">
                            {Math.round((d.probability ?? 0) * 100)}%
                          </span>
                        </div>
                        {d.reasoning && (
                          <p className="mt-2 text-sm text-slate-400">{d.reasoning}</p>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

            {report?.what_to_watch_for && report.what_to_watch_for.length > 0 && (
              <div className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-4">
                <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-amber-200/90">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  Seek emergency care if
                </p>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-100/80">
                  {report.what_to_watch_for.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </div>
            )}

            {report?.next_steps && (
              <p className="text-sm text-slate-300">{report.next_steps}</p>
            )}

            <p className="text-[11px] leading-relaxed text-slate-600">
              {report?.disclaimer ||
                "This is decision support, not a medical diagnosis. A licensed clinician must confirm."}
            </p>

            <p className="font-mono text-[11px] text-slate-600">
              Consultation · {consultation.id}
            </p>
          </div>
        )}
      </div>

      <Link href="/" className="cp-btn-ghost mt-6 self-center">
        Start another session
      </Link>
    </main>
  );
}
