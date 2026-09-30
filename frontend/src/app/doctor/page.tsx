"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Clock, Stethoscope, Users } from "lucide-react";
import AcousticCard from "@/components/doctor/AcousticCard";
import ConsultationSwitcher from "@/components/doctor/ConsultationSwitcher";
import DifferentialMatrix from "@/components/doctor/DifferentialMatrix";
import DoctorActionBox from "@/components/doctor/DoctorActionBox";
import SbarPanels from "@/components/doctor/SbarPanels";
import { DashboardSkeleton } from "@/components/doctor/Skeletons";
import VitalsOverviewCard from "@/components/doctor/VitalsOverviewCard";
import {
  formatQueueDuration,
  normalizeUrgency,
  urgencyBadgeClass,
} from "@/components/doctor/utils";
import { getConsultation, listConsultations } from "@/lib/api";
import type { Consultation } from "@/types/clinical";

const POLL_MS = 5000;

export default function DoctorCommandCenterPage() {
  const [queue, setQueue] = useState<Consultation[]>([]);
  const [queueLoading, setQueueLoading] = useState(true);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [active, setActive] = useState<Consultation | null>(null);
  const [chartLoading, setChartLoading] = useState(false);
  const [chartError, setChartError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const refreshQueue = useCallback(async () => {
    try {
      const items = await listConsultations("ready_for_doctor,analyzing");
      setQueue(items);
      setQueueError(null);
      setSelectedId((prev) => {
        if (prev && items.some((c) => c.id === prev)) return prev;
        return items[0]?.id ?? null;
      });
    } catch (err) {
      setQueueError(err instanceof Error ? err.message : "Queue unavailable");
    } finally {
      setQueueLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshQueue();
    const poll = setInterval(() => void refreshQueue(), POLL_MS);
    const clock = setInterval(() => setNow(Date.now()), 30000);
    return () => {
      clearInterval(poll);
      clearInterval(clock);
    };
  }, [refreshQueue]);

  useEffect(() => {
    if (!selectedId) {
      setActive(null);
      return;
    }
    let cancelled = false;
    setChartLoading(true);
    setChartError(null);
    (async () => {
      try {
        const row = await getConsultation(selectedId);
        if (!cancelled) setActive(row);
      } catch (err) {
        if (!cancelled) {
          setChartError(
            err instanceof Error ? err.message : "Failed to load chart",
          );
          setActive(null);
        }
      } finally {
        if (!cancelled) setChartLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const urgency = useMemo(
    () => normalizeUrgency(active?.sbar_report?.urgency_level),
    [active],
  );

  const onResolved = (updated: Consultation) => {
    setActive(updated);
    setQueue((prev) => prev.filter((c) => c.id !== updated.id));
    setSelectedId((prev) => {
      if (prev !== updated.id) return prev;
      const remaining = queue.filter((c) => c.id !== updated.id);
      return remaining[0]?.id ?? null;
    });
    void refreshQueue();
  };

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <div className="w-full shrink-0 lg:w-72 xl:w-80">
        <div className="sticky top-0 h-screen">
          <ConsultationSwitcher
            items={queue}
            selectedId={selectedId}
            loading={queueLoading}
            now={now}
            onSelect={setSelectedId}
            onRefresh={() => void refreshQueue()}
          />
        </div>
      </div>

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 bg-slate-950/80 px-5 py-4 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-emerald-500/30 bg-emerald-500/10 shadow-glow-sm">
              <Stethoscope className="h-5 w-5 text-emerald-300" />
            </div>
            <div>
              <p className="text-lg font-semibold text-slate-50">
                ClinicalPulse
              </p>
              <p className="text-xs text-slate-500">Doctor Command Center</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300">
              <Users className="h-3.5 w-3.5 text-emerald-400" />
              {queue.length} in queue
            </span>
            {active && (
              <>
                <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-700 px-3 py-1 font-mono text-xs text-slate-300">
                  <Clock className="h-3.5 w-3.5" />
                  Queue {formatQueueDuration(active.created_at, now)}
                </span>
                <span
                  className={`rounded-full border px-3 py-1 text-xs font-semibold tracking-wide ${urgencyBadgeClass(urgency)}`}
                >
                  {urgency}
                </span>
              </>
            )}
            <Link href="/" className="cp-btn-ghost !px-3 !py-1.5 text-xs">
              Patient portal
            </Link>
          </div>
        </header>

        {queueError && (
          <div className="mx-5 mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
            Queue sync issue: {queueError}. Ensure the API is running and
            Supabase env vars are set.
          </div>
        )}

        {!selectedId && !queueLoading && (
          <div className="flex flex-col items-center justify-center px-6 py-24 text-center">
            <p className="text-lg font-medium text-slate-200">
              No active consultations
            </p>
            <p className="mt-2 max-w-md text-sm text-slate-500">
              When a patient completes the triage wizard, their chart appears
              here automatically.
            </p>
          </div>
        )}

        {selectedId && chartLoading && <DashboardSkeleton />}

        {selectedId && chartError && !chartLoading && (
          <div className="m-6 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
            {chartError}
          </div>
        )}

        {active && !chartLoading && (
          <div className="animate-fadeUp space-y-6 p-5 sm:p-6">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-500">
                Active patient · {active.status.replaceAll("_", " ")}
              </p>
              <h1 className="mt-1 text-2xl font-semibold text-slate-50">
                {active.chief_complaint || "Untitled presentation"}
              </h1>
              <p className="mt-1 font-mono text-xs text-slate-600">
                {active.id}
              </p>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <VitalsOverviewCard consultation={active} />
              <AcousticCard consultation={active} />
            </div>

            <SbarPanels sbar={active.sbar_report} />

            <DifferentialMatrix items={active.differential_diagnosis} />

            <DoctorActionBox consultation={active} onResolved={onResolved} />
          </div>
        )}
      </div>
    </div>
  );
}
