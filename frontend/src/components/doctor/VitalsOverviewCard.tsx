"use client";

import { useMemo } from "react";
import { Activity, HeartPulse } from "lucide-react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  YAxis,
} from "recharts";
import type { Consultation } from "@/types/clinical";
import { hrBand, synthesizePulseWave } from "@/components/doctor/utils";

type Props = {
  consultation: Consultation;
};

export default function VitalsOverviewCard({ consultation }: Props) {
  const bpm = consultation.heart_rate_bpm ?? consultation.sbar_report?.telemetry?.heart_rate_bpm;
  const hrv = consultation.hrv_sdnn ?? consultation.sbar_report?.telemetry?.hrv_sdnn;
  const band = hrBand(bpm != null ? Number(bpm) : null);

  const wave = useMemo(() => {
    const raw =
      consultation.sbar_report?.telemetry?.pulse_wave?.filter(
        (v) => typeof v === "number" && Number.isFinite(v),
      ) ?? [];
    const series =
      raw.length >= 10
        ? raw.slice(0, 300)
        : synthesizePulseWave(Number(bpm) || 72);
    return series.map((v, i) => ({ t: i, v }));
  }, [consultation, bpm]);

  const bandLabel =
    band === "normal"
      ? "Normal"
      : band === "high"
        ? "Tachycardia"
        : band === "low"
          ? "Bradycardia"
          : "Unknown";

  const bandClass =
    band === "normal"
      ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
      : band === "unknown"
        ? "border-slate-600 bg-slate-800 text-slate-400"
        : "border-amber-500/40 bg-amber-500/10 text-amber-200";

  return (
    <div className="cp-panel flex h-full flex-col p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <HeartPulse className="h-4 w-4 text-emerald-400" />
          <h3 className="text-sm font-semibold text-slate-100">Vitals Overview</h3>
        </div>
        <span className={`rounded-full border px-2.5 py-0.5 text-[10px] font-semibold ${bandClass}`}>
          {bandLabel}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
          <p className="text-[10px] uppercase tracking-wider text-slate-500">Heart Rate</p>
          <p className="mt-1 font-mono text-3xl font-bold text-emerald-300">
            {bpm != null ? Number(bpm) : "—"}
            <span className="ml-1 text-xs font-medium text-slate-500">BPM</span>
          </p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
          <p className="text-[10px] uppercase tracking-wider text-slate-500">HRV · SDNN</p>
          <p className="mt-1 font-mono text-3xl font-bold text-emerald-300">
            {hrv != null ? Number(hrv) : "—"}
            <span className="ml-1 text-xs font-medium text-slate-500">ms</span>
          </p>
        </div>
      </div>

      <div className="mt-4 flex-1">
        <div className="mb-2 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-500">
          <Activity className="h-3 w-3" />
          Raw PPG pulse wave
        </div>
        <div className="h-28 w-full rounded-xl border border-slate-800 bg-slate-950/50 p-2">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={wave}>
              <YAxis hide domain={["auto", "auto"]} />
              <Line
                type="monotone"
                dataKey="v"
                stroke="#34d399"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
