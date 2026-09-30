"use client";

import { FormEvent, useEffect, useState } from "react";
import { CheckCircle2, Loader2, PenLine } from "lucide-react";
import type { Consultation } from "@/types/clinical";
import { resolveConsultation } from "@/lib/api";

type Props = {
  consultation: Consultation;
  onResolved: (updated: Consultation) => void;
};

export default function DoctorActionBox({ consultation, onResolved }: Props) {
  const [prescription, setPrescription] = useState(
    consultation.prescription ?? "",
  );
  const [notes, setNotes] = useState(consultation.doctor_notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(consultation.status === "completed");

  useEffect(() => {
    setPrescription(consultation.prescription ?? "");
    setNotes(consultation.doctor_notes ?? "");
    setDone(consultation.status === "completed");
    setError(null);
  }, [consultation]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const updated = await resolveConsultation(consultation.id, {
        prescription,
        doctor_notes: notes,
        approved: true,
        status: "completed",
      });
      setDone(true);
      onResolved(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dispatch failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="cp-panel border-emerald-500/20 p-5 shadow-glow-sm">
      <div className="mb-4 flex items-center gap-2">
        <PenLine className="h-4 w-4 text-emerald-400" />
        <h3 className="text-sm font-semibold text-slate-100">Doctor Action Box</h3>
      </div>

      <form onSubmit={(e) => void onSubmit(e)} className="space-y-4">
        <label className="block">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Prescription scratchpad
          </span>
          <textarea
            value={prescription}
            onChange={(e) => setPrescription(e.target.value)}
            rows={5}
            className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 font-mono text-sm text-slate-100 outline-none ring-emerald-500/30 focus:ring-2"
            placeholder="Medication — Dose — Frequency"
            disabled={done}
          />
        </label>

        <label className="block">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Clinical decision notes
          </span>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 outline-none ring-emerald-500/30 focus:ring-2"
            placeholder="Document clinical judgment, deviations from AI draft…"
            disabled={done}
          />
        </label>

        {error && (
          <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
            {error}
          </p>
        )}

        {done ? (
          <div className="inline-flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2.5 text-sm font-medium text-emerald-300">
            <CheckCircle2 className="h-4 w-4" />
            Signed &amp; dispatched
          </div>
        ) : (
          <button type="submit" className="cp-btn" disabled={saving}>
            {saving ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Dispatching…
              </>
            ) : (
              <>
                <CheckCircle2 className="h-4 w-4" />
                Sign &amp; Dispatch Prescription
              </>
            )}
          </button>
        )}
      </form>
    </section>
  );
}
