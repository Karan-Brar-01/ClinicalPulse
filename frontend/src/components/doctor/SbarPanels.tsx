"use client";

import type { SbarReport } from "@/types/clinical";

type Props = {
  sbar?: SbarReport | null;
};

const PANELS: { key: keyof SbarReport; label: string; accent: string }[] = [
  { key: "situation", label: "Situation", accent: "border-l-emerald-400" },
  { key: "background", label: "Background", accent: "border-l-sky-400" },
  { key: "assessment", label: "Assessment", accent: "border-l-amber-400" },
  { key: "recommendation", label: "Recommendation", accent: "border-l-violet-400" },
];

export default function SbarPanels({ sbar }: Props) {
  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold tracking-wide text-slate-100">
        SBAR Clinical Synthesis
      </h3>
      <div className="grid gap-3 md:grid-cols-2">
        {PANELS.map(({ key, label, accent }) => {
          const text =
            typeof sbar?.[key] === "string" ? (sbar[key] as string) : "—";
          return (
            <article
              key={key}
              className={`rounded-2xl border border-slate-800 border-l-4 bg-slate-950/70 p-4 ${accent}`}
            >
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                {label}
              </p>
              <p className="mt-2 text-sm leading-relaxed text-slate-100">{text}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}
