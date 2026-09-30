"use client";

import type { Consultation } from "@/types/clinical";
import {
  formatQueueDuration,
  normalizeUrgency,
  urgencyBadgeClass,
} from "@/components/doctor/utils";
import { SidebarSkeleton } from "@/components/doctor/Skeletons";

type Props = {
  items: Consultation[];
  selectedId: string | null;
  loading: boolean;
  now: number;
  onSelect: (id: string) => void;
  onRefresh: () => void;
};

export default function ConsultationSwitcher({
  items,
  selectedId,
  loading,
  now,
  onSelect,
  onRefresh,
}: Props) {
  return (
    <aside className="flex h-full w-full flex-col border-r border-slate-800 bg-slate-950/60">
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">
            Live queue
          </p>
          <p className="text-sm font-semibold text-slate-100">
            {items.length} active
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="rounded-lg border border-slate-700 px-2.5 py-1 text-[11px] text-slate-300 hover:border-emerald-500/40 hover:text-emerald-300"
        >
          Refresh
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading && items.length === 0 ? (
          <SidebarSkeleton />
        ) : items.length === 0 ? (
          <p className="p-4 text-sm text-slate-500">
            No patients waiting. Queue updates every few seconds.
          </p>
        ) : (
          <ul className="space-y-2 p-3">
            {items.map((c) => {
              const urgency = normalizeUrgency(c.sbar_report?.urgency_level);
              const active = c.id === selectedId;
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(c.id)}
                    className={`w-full rounded-xl border px-3 py-3 text-left transition ${
                      active
                        ? "border-emerald-500/40 bg-emerald-500/10 shadow-glow-sm"
                        : "border-slate-800 bg-slate-900/40 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold tracking-wide ${urgencyBadgeClass(urgency)}`}
                      >
                        {urgency}
                      </span>
                      <span className="font-mono text-[10px] text-slate-500">
                        {formatQueueDuration(c.created_at, now)}
                      </span>
                    </div>
                    <p className="mt-2 line-clamp-2 text-sm font-medium text-slate-100">
                      {c.chief_complaint || "Untitled complaint"}
                    </p>
                    <p className="mt-1 font-mono text-[10px] text-slate-600">
                      {c.id.slice(0, 8)}…
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}
