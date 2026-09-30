"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { DifferentialItem } from "@/types/clinical";

type Props = {
  items?: DifferentialItem[] | null;
};

export default function DifferentialMatrix({ items }: Props) {
  const [openId, setOpenId] = useState<number | null>(0);
  const ranked = [...(items ?? [])].sort(
    (a, b) => (b.probability ?? 0) - (a.probability ?? 0),
  );

  if (ranked.length === 0) {
    return (
      <section className="cp-panel p-5">
        <h3 className="text-sm font-semibold text-slate-100">
          Differential Diagnosis Matrix
        </h3>
        <p className="mt-3 text-sm text-slate-500">No differentials on file.</p>
      </section>
    );
  }

  return (
    <section className="cp-panel p-5">
      <h3 className="mb-4 text-sm font-semibold text-slate-100">
        Differential Diagnosis Matrix
      </h3>
      <ul className="space-y-3">
        {ranked.map((dx, idx) => {
          const pct = Math.round((dx.probability ?? 0) * 100);
          const open = openId === idx;
          return (
            <li
              key={`${dx.condition}-${idx}`}
              className="rounded-xl border border-slate-800 bg-slate-950/50"
            >
              <button
                type="button"
                className="flex w-full items-center gap-3 px-4 py-3 text-left"
                onClick={() => setOpenId(open ? null : idx)}
                aria-expanded={open}
              >
                <span className="font-mono text-xs text-slate-500">
                  #{idx + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-slate-100">
                      {dx.condition}
                    </span>
                    {dx.icd10_code && (
                      <span className="rounded border border-slate-700 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
                        {dx.icd10_code}
                      </span>
                    )}
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-emerald-600 to-emerald-300"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
                <span className="font-mono text-sm font-semibold text-emerald-300">
                  {pct}%
                </span>
                {open ? (
                  <ChevronDown className="h-4 w-4 text-slate-500" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-slate-500" />
                )}
              </button>
              {open && (
                <div className="border-t border-slate-800 px-4 py-3 text-sm leading-relaxed text-slate-300">
                  {dx.reasoning || "No clinical reasoning provided."}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
