"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Loader2,
  Mic,
  MicOff,
  RefreshCw,
  ShieldAlert,
  Waves,
  Wind,
} from "lucide-react";
import { postAcoustic, type AcousticResult } from "@/lib/api";

const RECORD_SECONDS = 6;
const BAR_COUNT = 24;

type Phase =
  | "idle"
  | "need_permission"
  | "recording"
  | "uploading"
  | "done"
  | "error";

type Props = {
  onComplete: (result: AcousticResult) => void;
};

function pickMimeType(): string {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg",
  ];
  for (const t of candidates) {
    if (
      typeof MediaRecorder !== "undefined" &&
      MediaRecorder.isTypeSupported(t)
    ) {
      return t;
    }
  }
  return "";
}

function micErrorMessage(err: unknown): string {
  const name =
    err && typeof err === "object" && "name" in err
      ? String((err as { name?: string }).name)
      : "";
  const message = err instanceof Error ? err.message : String(err);

  if (
    name === "NotAllowedError" ||
    name === "PermissionDeniedError" ||
    /permission|denied|not allowed/i.test(message)
  ) {
    return (
      "Microphone access is blocked for this site. Click the lock / tune icon in your " +
      "browser address bar → Site settings → Microphone → Allow, then reload and try again. " +
      "On macOS, also check System Settings → Privacy & Security → Microphone for your browser."
    );
  }
  if (name === "NotFoundError") {
    return "No microphone was found. Plug in a mic or check that one is enabled.";
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return "Microphone is busy (another app may be using it). Close Zoom/Meet and retry.";
  }
  if (name === "SecurityError" || !window.isSecureContext) {
    return "Browsers only allow the mic on HTTPS or http://localhost. Open the app via localhost, not a raw LAN IP.";
  }
  return message || "Could not access the microphone.";
}

async function requestMicStream(): Promise<MediaStream> {
  if (typeof window === "undefined") {
    throw new Error("Window unavailable");
  }
  if (!window.isSecureContext) {
    const err = new Error("Insecure context");
    (err as Error & { name: string }).name = "SecurityError";
    throw err;
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error(
      "This browser does not support microphone capture (getUserMedia missing).",
    );
  }

  // 1) Simplest constraints — most reliable for showing the permission prompt
  try {
    return await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
  } catch (first) {
    // 2) Retry with looser / alternate constraints
    try {
      return await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: true,
        },
        video: false,
      });
    } catch {
      throw first;
    }
  }
}

export default function AudioAuscultation({ onComplete }: Props) {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const rafRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [phase, setPhase] = useState<Phase>("idle");
  const [secondsLeft, setSecondsLeft] = useState(RECORD_SECONDS);
  const [levels, setLevels] = useState<number[]>(() =>
    Array(BAR_COUNT).fill(0.15),
  );
  const [result, setResult] = useState<AcousticResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [permState, setPermState] = useState<PermissionState | "unknown">(
    "unknown",
  );

  const stopVisual = useCallback(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const cleanup = useCallback(() => {
    stopVisual();
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    try {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
      }
    } catch {
      /* already stopped */
    }
    mediaRecorderRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    void audioCtxRef.current?.close().catch(() => undefined);
    audioCtxRef.current = null;
    analyserRef.current = null;
  }, [stopVisual]);

  useEffect(() => () => cleanup(), [cleanup]);

  // Reflect current mic permission (Chrome/Edge). Safari may not support this.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await navigator.permissions?.query({
          name: "microphone" as PermissionName,
        });
        if (!status || cancelled) return;
        setPermState(status.state);
        status.onchange = () => setPermState(status.state);
        if (status.state === "denied") {
          setPhase("need_permission");
          setError(micErrorMessage({ name: "NotAllowedError", message: "denied" }));
        }
      } catch {
        setPermState("unknown");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const tickLevels = useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser) return;
    const data = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(data);
    const next: number[] = [];
    const step = Math.floor(data.length / BAR_COUNT) || 1;
    for (let i = 0; i < BAR_COUNT; i++) {
      const slice = data.slice(i * step, (i + 1) * step);
      const avg =
        slice.reduce((a, b) => a + b, 0) / Math.max(slice.length, 1) / 255;
      next.push(Math.max(0.08, Math.min(1, avg * 1.4)));
    }
    setLevels(next);
    rafRef.current = requestAnimationFrame(tickLevels);
  }, []);

  const uploadBlob = async (blob: Blob) => {
    setPhase("uploading");
    try {
      const data = await postAcoustic(blob);
      setResult(data);
      setPhase("done");
      onComplete(data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Acoustic upload failed";
      setError(msg);
      setPhase("error");
    }
  };

  /** Step A: ask for mic only (shows browser prompt from this click). */
  const enableMicrophone = async () => {
    setError(null);
    try {
      const stream = await requestMicStream();
      // Immediately stop — we only wanted the permission grant + prompt
      stream.getTracks().forEach((t) => t.stop());
      setPermState("granted");
      setPhase("idle");
      setError(null);
    } catch (err) {
      setPermState("denied");
      setError(micErrorMessage(err));
      setPhase("need_permission");
    }
  };

  /** Step B: record 6s after permission is available. */
  const startRecording = async () => {
    setError(null);
    setResult(null);
    setSecondsLeft(RECORD_SECONDS);
    chunksRef.current = [];

    try {
      const stream = await requestMicStream();
      setPermState("granted");
      setPhase("recording");
      streamRef.current = stream;

      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext })
          .webkitAudioContext;
      const ctx = new AudioCtx();
      // Safari often starts suspended until resume() after a gesture
      if (ctx.state === "suspended") {
        await ctx.resume();
      }
      audioCtxRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;
      rafRef.current = requestAnimationFrame(tickLevels);

      if (typeof MediaRecorder === "undefined") {
        throw new Error("MediaRecorder is not supported in this browser.");
      }

      const mime = pickMimeType();
      const recorder = mime
        ? new MediaRecorder(stream, { mimeType: mime })
        : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        const type = recorder.mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type });
        stream.getTracks().forEach((t) => t.stop());
        stopVisual();
        void uploadBlob(blob);
      };
      recorder.onerror = () => {
        setError("Recording failed mid-capture. Please try again.");
        setPhase("error");
        cleanup();
      };

      recorder.start(250);

      timerRef.current = setInterval(() => {
        setSecondsLeft((s) => {
          if (s <= 1) {
            if (timerRef.current) clearInterval(timerRef.current);
            if (recorder.state === "recording") recorder.stop();
            return 0;
          }
          return s - 1;
        });
      }, 1000);
    } catch (err) {
      setError(micErrorMessage(err));
      setPhase(
        (err as { name?: string })?.name === "NotAllowedError" ||
          (err as { name?: string })?.name === "PermissionDeniedError"
          ? "need_permission"
          : "error",
      );
      cleanup();
    }
  };

  const congestionLabel = result
    ? result.cough_type === "Productive / Wet"
      ? "Airway Congestion"
      : result.cough_type === "Dry / Irritative"
        ? "Irritative Airway Pattern"
        : "Airway Profile"
    : "";

  return (
    <div className="animate-fadeUp space-y-5">
      <div>
        <p className="cp-badge mb-2">
          <Waves className="h-3.5 w-3.5" />
          Acoustic Auscultation · 6s
        </p>
        <h2 className="text-xl font-semibold text-mist-100">
          Acoustic Stethoscope Exam
        </h2>
        <p className="mt-2 rounded-2xl border border-sea-400/20 bg-sea-500/10 px-4 py-3 text-sm text-mist-100">
          Hold phone <strong>6 inches from mouth</strong>. Cough forcefully{" "}
          <strong>3 times</strong> during the recording window.
        </p>
      </div>

      {(phase === "need_permission" || permState === "denied") && (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-500/10 p-4 text-sm text-amber-100">
          <p className="flex items-center gap-2 font-semibold">
            <ShieldAlert className="h-4 w-4" />
            Microphone permission needed
          </p>
          <p className="mt-2 text-amber-100/80">
            Your browser blocked the mic without showing a prompt (often because
            it was denied earlier). Allow the mic for this site, then tap
            Enable microphone.
          </p>
          <button
            type="button"
            className="cp-btn mt-3"
            onClick={() => void enableMicrophone()}
          >
            <Mic className="h-4 w-4" /> Enable microphone
          </button>
        </div>
      )}

      <div className="cp-panel flex h-36 items-end justify-center gap-1.5 px-4 py-6">
        {levels.map((lvl, i) => (
          <div
            key={i}
            className="w-2 origin-bottom rounded-full bg-gradient-to-t from-sea-600 to-sea-300 transition-[height] duration-75"
            style={{
              height: `${Math.round(lvl * 100)}%`,
              opacity: phase === "recording" ? 0.9 : 0.35,
            }}
          />
        ))}
      </div>

      {phase === "recording" && (
        <div className="flex items-center justify-center gap-3">
          <span className="relative flex h-3 w-3">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-400 opacity-75" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-rose-500" />
          </span>
          <span className="font-mono text-2xl font-bold text-mist-100">
            {secondsLeft}s
          </span>
          <span className="text-sm text-mist-500">recording</span>
        </div>
      )}

      {phase === "done" && result && (
        <div className="space-y-3 animate-fadeUp">
          <div className="cp-panel border-sea-400/25 p-5">
            <p className="text-xs uppercase tracking-wider text-mist-500">
              Findings
            </p>
            <p className="mt-2 text-lg font-semibold text-sea-300">
              {congestionLabel}:{" "}
              <span className="font-mono">
                {Math.round(result.severity_score)}%
              </span>{" "}
              <span className="text-mist-300">({result.cough_type})</span>
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <span className="cp-badge">
                <Wind className="h-3.5 w-3.5" />
                Wheeze {result.wheeze_detected ? "detected" : "not detected"}
              </span>
              <span className="cp-badge">
                Crackle {result.crackle_detected ? "detected" : "not detected"}
              </span>
              <span className="cp-badge">
                Conf {Math.round((result.acoustic_confidence ?? 0) * 100)}%
              </span>
            </div>
          </div>
          {result.spectrogram_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={result.spectrogram_url}
              alt="Cough Mel-spectrogram"
              className="w-full rounded-xl border border-white/10"
            />
          ) : null}
        </div>
      )}

      {error && phase !== "need_permission" && (
        <p className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
          <MicOff className="mr-1 inline h-4 w-4" />
          {error}
        </p>
      )}
      {error && phase === "need_permission" && (
        <p className="text-xs text-mist-500">{error}</p>
      )}

      <div className="flex flex-wrap gap-3">
        {(phase === "idle" || phase === "error" || phase === "done") && (
          <>
            {permState !== "granted" && (
              <button
                type="button"
                className="cp-btn-ghost"
                onClick={() => void enableMicrophone()}
              >
                <Mic className="h-4 w-4" /> Enable microphone
              </button>
            )}
            <button
              type="button"
              className="cp-btn"
              onClick={() => void startRecording()}
            >
              {phase === "done" ? (
                <>
                  <RefreshCw className="h-4 w-4" /> Record Again
                </>
              ) : (
                <>
                  <Mic className="h-4 w-4" /> Start 6s Capture
                </>
              )}
            </button>
          </>
        )}
        {phase === "need_permission" && (
          <button
            type="button"
            className="cp-btn"
            onClick={() => void enableMicrophone()}
          >
            <Mic className="h-4 w-4" /> Try Enable microphone again
          </button>
        )}
        {phase === "uploading" && (
          <div className="cp-btn pointer-events-none opacity-80">
            <Loader2 className="h-4 w-4 animate-spin" />
            Analyzing acoustics…
          </div>
        )}
      </div>
    </div>
  );
}
