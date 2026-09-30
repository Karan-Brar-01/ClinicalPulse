"use client";

import { Mic, Volume2, Wind } from "lucide-react";
import type { Consultation } from "@/types/clinical";

type Props = {
  consultation: Consultation;
};

export default function AcousticCard({ consultation }: Props) {
  const resp = consultation.respiratory_analysis;
  const classification = resp?.classification || "—";
  const severity = resp?.severity_score;
  const spectrogram = resp?.spectrogram_url;
  const audioUrl = resp?.audio_url;

  return (
    <div className="cp-panel flex h-full flex-col p-5">
      <div className="mb-4 flex items-center gap-2">
        <Mic className="h-4 w-4 text-emerald-400" />
        <h3 className="text-sm font-semibold text-slate-100">
          Acoustic Auscultation
        </h3>
      </div>

      <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3">
        <p className="text-[10px] uppercase tracking-wider text-slate-500">
          Cough classification
        </p>
        <p className="mt-1 text-base font-semibold text-emerald-200">
          {classification}
          {severity != null && (
            <span className="ml-2 font-mono text-sm text-emerald-400">
              {Math.round(Number(severity))}% severity
            </span>
          )}
        </p>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <span
          className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${
            resp?.wheeze_detected
              ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
              : "border-slate-700 bg-slate-900 text-slate-400"
          }`}
        >
          <Wind className="mr-1 inline h-3 w-3" />
          Wheeze {resp?.wheeze_detected ? "YES" : "NO"}
        </span>
        <span
          className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${
            resp?.crackle_detected
              ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
              : "border-slate-700 bg-slate-900 text-slate-400"
          }`}
        >
          Crackle {resp?.crackle_detected ? "YES" : "NO"}
        </span>
      </div>

      <div className="mt-4">
        <p className="mb-2 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-500">
          <Volume2 className="h-3 w-3" />
          Audio sample
        </p>
        {audioUrl ? (
          <audio controls src={audioUrl} className="w-full" />
        ) : (
          <p className="rounded-lg border border-dashed border-slate-700 px-3 py-2 text-xs text-slate-500">
            No stored audio URL for this session (spectrogram retained).
          </p>
        )}
      </div>

      <div className="mt-4 flex-1">
        <p className="mb-2 text-[10px] uppercase tracking-wider text-slate-500">
          Mel-spectrogram
        </p>
        {spectrogram ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={spectrogram}
            alt="Cough Mel-spectrogram"
            className="max-h-40 w-full rounded-xl border border-slate-800 object-contain bg-slate-950"
          />
        ) : (
          <div className="flex h-28 items-center justify-center rounded-xl border border-dashed border-slate-700 text-xs text-slate-500">
            Spectrogram unavailable
          </div>
        )}
      </div>
    </div>
  );
}
