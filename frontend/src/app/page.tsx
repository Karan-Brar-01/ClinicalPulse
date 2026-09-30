"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Bot,
  HeartPulse,
  Loader2,
  Mic,
  Send,
  Sparkles,
  Stethoscope,
} from "lucide-react";
import AudioAuscultation from "@/components/AudioAuscultation";
import VitalsScanner from "@/components/VitalsScanner";
import {
  postIntakeChat,
  postTriageComplete,
  type AcousticResult,
  type RppgResult,
} from "@/lib/api";

type Step = 1 | 2 | 3 | 4;
type ChatMessage = { role: "assistant" | "user"; content: string };

const STEP_META: { id: Step; label: string }[] = [
  { id: 1, label: "Talk" },
  { id: 2, label: "Pulse" },
  { id: 3, label: "Cough" },
  { id: 4, label: "Report" },
];

export default function PatientWizardPage() {
  const router = useRouter();
  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const [step, setStep] = useState<Step>(1);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "Hi — I'm your ClinicalPulse intake nurse. What's bothering you today?",
    },
  ]);
  const [draft, setDraft] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [intakeComplete, setIntakeComplete] = useState(false);
  const [chiefFromLlm, setChiefFromLlm] = useState("");
  const [vitals, setVitals] = useState<RppgResult | null>(null);
  const [acoustic, setAcoustic] = useState<AcousticResult | null>(null);
  const [synthError, setSynthError] = useState<string | null>(null);
  const [synthStatus, setSynthStatus] = useState("Building your clinical brief…");

  const chiefComplaint = useMemo(() => {
    if (chiefFromLlm) return chiefFromLlm.slice(0, 240);
    const firstUser = messages.find((m) => m.role === "user");
    return firstUser?.content?.slice(0, 240) || "General symptom check";
  }, [messages, chiefFromLlm]);

  const intakeReady =
    intakeComplete || messages.filter((m) => m.role === "user").length >= 1;

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatBusy]);

  const sendChat = async (e?: FormEvent) => {
    e?.preventDefault();
    const text = draft.trim();
    if (!text || chatBusy) return;

    setChatError(null);
    const nextMessages: ChatMessage[] = [
      ...messages,
      { role: "user", content: text },
    ];
    setMessages(nextMessages);
    setDraft("");
    setChatBusy(true);

    try {
      const res = await postIntakeChat(nextMessages);
      setMessages((prev) => [...prev, { role: "assistant", content: res.reply }]);
      if (res.chief_complaint) setChiefFromLlm(res.chief_complaint);
      if (res.intake_complete) setIntakeComplete(true);
      requestAnimationFrame(() => inputRef.current?.focus());
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Intake assistant unavailable";
      setChatError(msg);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "I couldn't reach the clinical AI just now. Check that the API is running, then try again — or continue to vitals.",
        },
      ]);
    } finally {
      setChatBusy(false);
    }
  };

  const runTriage = async () => {
    setStep(4);
    setSynthError(null);
    setSynthStatus("Building your clinical brief…");
    const statuses = [
      "Reading your intake…",
      "Merging pulse and cough signals…",
      "Writing your plain-language report…",
    ];
    let i = 0;
    const tick = setInterval(() => {
      i = (i + 1) % statuses.length;
      setSynthStatus(statuses[i]);
    }, 1400);

    try {
      const res = await postTriageComplete({
        chief_complaint: chiefComplaint,
        symptom_transcript: messages,
        vitals: {
          heart_rate_bpm: vitals?.heart_rate_bpm,
          hrv_sdnn: vitals?.hrv_sdnn,
          confidence: vitals?.confidence,
          usable: vitals?.usable,
          pulse_wave: vitals?.pulse_wave,
        },
        acoustic: {
          cough_type: acoustic?.cough_type,
          severity_score: acoustic?.severity_score,
          wheeze_detected: acoustic?.wheeze_detected,
          crackle_detected: acoustic?.crackle_detected,
          acoustic_confidence: acoustic?.acoustic_confidence,
          spectrogram_url: acoustic?.spectrogram_url,
          usable: acoustic?.usable,
        },
      });
      clearInterval(tick);
      const id = res.consultation?.id;
      if (!id) throw new Error("No consultation id returned");
      router.push(`/holding/${id}`);
    } catch (err) {
      clearInterval(tick);
      setSynthError(err instanceof Error ? err.message : "Triage failed");
      setSynthStatus("Something went wrong");
    }
  };

  return (
    <main className="cp-shell flex flex-col">
      <header className="mb-6 flex items-end justify-between gap-4">
        <div>
          <p className="font-display text-3xl tracking-tight text-mist-100 sm:text-4xl">
            Clinical<span className="text-sea-400">Pulse</span>
          </p>
          <p className="mt-1 max-w-md text-sm text-mist-500">
            Tell us what hurts. We measure what we can. A clinician finishes the rest.
          </p>
        </div>
        <a
          href="/doctor"
          className="hidden rounded-full border border-white/10 px-3 py-1.5 text-xs text-mist-300 transition hover:border-sea-400/40 hover:text-sea-300 sm:inline-flex"
        >
          Clinician view
        </a>
      </header>

      {/* Progress */}
      <div className="mb-6">
        <div className="mb-2 flex justify-between text-[11px] uppercase tracking-[0.16em] text-mist-500">
          {STEP_META.map((s) => (
            <span
              key={s.id}
              className={step >= s.id ? "text-sea-300" : undefined}
            >
              {s.label}
            </span>
          ))}
        </div>
        <div className="h-1 overflow-hidden rounded-full bg-white/10">
          <div
            className="h-full rounded-full bg-sea-400 transition-all duration-500"
            style={{ width: `${(step / 4) * 100}%` }}
          />
        </div>
      </div>

      <section className="cp-panel flex min-h-[70vh] flex-1 flex-col overflow-hidden">
        {step === 1 && (
          <div className="animate-fadeUp flex h-full min-h-[70vh] flex-col">
            <div className="border-b border-white/10 px-5 py-4 sm:px-6">
              <div className="flex items-center gap-2">
                <Stethoscope className="h-4 w-4 text-sea-400" />
                <h2 className="text-sm font-semibold text-mist-100">
                  Intake conversation
                </h2>
              </div>
              <p className="mt-1 text-xs text-mist-500">
                Adaptive questions — not a fixed script.
              </p>
            </div>

            <div className="cp-scroll flex-1 space-y-4 overflow-y-auto px-5 py-5 sm:px-6">
              {messages.map((m, idx) => (
                <div
                  key={`${m.role}-${idx}`}
                  className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[88%] rounded-3xl px-4 py-3 text-[15px] leading-relaxed ${
                      m.role === "user"
                        ? "rounded-br-md bg-sea-400 text-ink-950"
                        : "rounded-bl-md border border-white/10 bg-ink-950/50 text-mist-100"
                    }`}
                  >
                    {m.role === "assistant" && (
                      <span className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-sea-300/80">
                        <Bot className="h-3 w-3" /> Nurse
                      </span>
                    )}
                    {m.content}
                  </div>
                </div>
              ))}
              {chatBusy && (
                <div className="flex items-center gap-2 text-sm text-mist-500">
                  <Loader2 className="h-4 w-4 animate-spin text-sea-400" />
                  Listening…
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            <div className="border-t border-white/10 bg-ink-950/40 px-4 py-4 sm:px-6">
              {chatError && (
                <p className="mb-3 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                  Send failed: {chatError}
                </p>
              )}
              <form
                className="flex gap-2"
                onSubmit={(e) => {
                  void sendChat(e);
                }}
              >
                <input
                  ref={inputRef}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="Type how you feel…"
                  disabled={chatBusy}
                  className="cp-input"
                  autoComplete="off"
                />
                <button
                  type="submit"
                  className="cp-btn shrink-0 !px-4"
                  disabled={chatBusy || !draft.trim()}
                  aria-label="Send message"
                >
                  {chatBusy ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                </button>
              </form>

              <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs text-mist-500">
                  {intakeComplete
                    ? "Intake looks complete — continue when ready."
                    : "Answer a couple of follow-ups, then continue."}
                </p>
                <button
                  type="button"
                  className="cp-btn"
                  disabled={!intakeReady || chatBusy}
                  onClick={() => setStep(2)}
                >
                  Continue <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="animate-fadeUp space-y-4 p-5 sm:p-6">
            <div className="flex items-center gap-2 text-sea-300">
              <HeartPulse className="h-4 w-4" />
              <h2 className="text-sm font-semibold">Optical pulse check</h2>
            </div>
            <VitalsScanner onComplete={(r) => setVitals(r)} />
            <div className="flex justify-between pt-2">
              <button type="button" className="cp-btn-ghost" onClick={() => setStep(1)}>
                Back
              </button>
              <button
                type="button"
                className="cp-btn"
                disabled={!vitals}
                onClick={() => setStep(3)}
              >
                Continue <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="animate-fadeUp space-y-4 p-5 sm:p-6">
            <div className="flex items-center gap-2 text-sea-300">
              <Mic className="h-4 w-4" />
              <h2 className="text-sm font-semibold">Cough capture</h2>
            </div>
            <AudioAuscultation onComplete={(r) => setAcoustic(r)} />
            <div className="flex justify-between pt-2">
              <button type="button" className="cp-btn-ghost" onClick={() => setStep(2)}>
                Back
              </button>
              <button
                type="button"
                className="cp-btn"
                disabled={!acoustic}
                onClick={() => void runTriage()}
              >
                Finish &amp; view report <Sparkles className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}

        {step === 4 && (
          <div className="animate-fadeUp flex flex-1 flex-col items-center justify-center px-6 py-16 text-center">
            <div className="relative mb-6">
              <div className="h-16 w-16 animate-spinSlow rounded-full border border-sea-400/20 border-t-sea-400" />
              <Sparkles className="absolute inset-0 m-auto h-6 w-6 text-sea-300" />
            </div>
            <h2 className="font-display text-2xl text-mist-100">{synthStatus}</h2>
            <p className="mt-2 max-w-sm text-sm text-mist-500">
              Preparing a clinician brief and a plain-language summary for you.
            </p>
            {synthError && (
              <div className="mt-6 space-y-3">
                <p className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                  {synthError}
                </p>
                <button type="button" className="cp-btn" onClick={() => void runTriage()}>
                  Retry
                </button>
              </div>
            )}
          </div>
        )}
      </section>

      <p className="mt-6 text-center text-[11px] text-mist-500">
        Not a diagnosis. A licensed clinician reviews every chart.
      </p>
    </main>
  );
}
