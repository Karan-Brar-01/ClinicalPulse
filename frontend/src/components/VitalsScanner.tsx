"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, Heart, Loader2, RefreshCw, ShieldCheck } from "lucide-react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  YAxis,
} from "recharts";
import { postRppg, type RgbSample, type RppgResult } from "@/lib/api";

const SCAN_SECONDS = 25;
const SAMPLE_FPS = 30;
const ROI = 64;

type Phase = "idle" | "scanning" | "uploading" | "done" | "error";

type Props = {
  onComplete: (result: RppgResult, greenSeries: number[]) => void;
};

export default function VitalsScanner({ onComplete }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const samplesRef = useRef<number[]>([]);
  const rgbRef = useRef<RgbSample[]>([]);
  const rafRef = useRef<number | null>(null);
  const lastSampleRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [phase, setPhase] = useState<Phase>("idle");
  const [secondsLeft, setSecondsLeft] = useState(SCAN_SECONDS);
  const [wave, setWave] = useState<{ t: number; v: number }[]>([]);
  const [result, setResult] = useState<RppgResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const stopStream = useCallback(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => () => stopStream(), [stopStream]);

  const sampleLoop = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) {
      rafRef.current = requestAnimationFrame(sampleLoop);
      return;
    }

    const now = performance.now();
    const interval = 1000 / SAMPLE_FPS;
    if (now - lastSampleRef.current >= interval) {
      lastSampleRef.current = now;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (ctx) {
        const vw = video.videoWidth;
        const vh = video.videoHeight;
        const sx = Math.max(0, Math.floor(vw / 2 - ROI / 2));
        const sy = Math.max(0, Math.floor(vh / 2 - ROI / 2));
        canvas.width = ROI;
        canvas.height = ROI;
        ctx.drawImage(video, sx, sy, ROI, ROI, 0, 0, ROI, ROI);
        const { data } = ctx.getImageData(0, 0, ROI, ROI);
        let rSum = 0;
        let gSum = 0;
        let bSum = 0;
        const pixels = ROI * ROI;
        for (let i = 0; i < data.length; i += 4) {
          rSum += data[i];
          gSum += data[i + 1];
          bSum += data[i + 2];
        }
        const r = rSum / pixels;
        const g = gSum / pixels;
        const b = bSum / pixels;
        samplesRef.current.push(g);
        rgbRef.current.push({ r, g, b });
        const recent = samplesRef.current.slice(-120);
        const mean = recent.reduce((a, v) => a + v, 0) / recent.length;
        setWave(
          recent.map((v, i) => ({
            t: i,
            v: Number((v - mean).toFixed(3)),
          })),
        );
      }
    }
    rafRef.current = requestAnimationFrame(sampleLoop);
  }, []);

  const finishScan = useCallback(async () => {
    stopStream();
    setPhase("uploading");
    const series = [...samplesRef.current];
    const rgb = [...rgbRef.current];
    try {
      const data = await postRppg(series, SAMPLE_FPS, rgb);
      setResult(data);
      setPhase("done");
      onComplete(data, series);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Vitals analysis failed";
      setError(msg);
      setPhase("error");
    }
  }, [onComplete, stopStream]);

  const startScan = async () => {
    setError(null);
    setResult(null);
    samplesRef.current = [];
    rgbRef.current = [];
    setWave([]);
    setSecondsLeft(SCAN_SECONDS);
    setPhase("scanning");

    try {
      const constraints: MediaStreamConstraints = {
        audio: false,
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
          frameRate: { ideal: SAMPLE_FPS },
          // @ts-expect-error torch is non-standard but supported on many mobiles
          advanced: [{ torch: true }],
        },
      };
      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia(constraints);
      } catch {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: {
            facingMode: { ideal: "user" },
            width: { ideal: 1280 },
            height: { ideal: 720 },
            frameRate: { ideal: SAMPLE_FPS },
          },
        });
      }

      // Try enabling torch after track starts
      const track = stream.getVideoTracks()[0];
      try {
        await track.applyConstraints({
          // @ts-expect-error advanced torch
          advanced: [{ torch: true }],
        });
      } catch {
        /* torch unsupported */
      }

      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      lastSampleRef.current = 0;
      rafRef.current = requestAnimationFrame(sampleLoop);

      timerRef.current = setInterval(() => {
        setSecondsLeft((s) => {
          if (s <= 1) {
            if (timerRef.current) clearInterval(timerRef.current);
            void finishScan();
            return 0;
          }
          return s - 1;
        });
      }, 1000);
    } catch (err) {
      const msg =
        err instanceof Error
          ? err.message
          : "Camera permission denied or unavailable";
      setError(msg);
      setPhase("error");
      stopStream();
    }
  };

  const progress = ((SCAN_SECONDS - secondsLeft) / SCAN_SECONDS) * 100;

  return (
    <div className="animate-fadeUp space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="cp-badge mb-2">
            <Activity className="h-3.5 w-3.5" />
            POS / CHROM rPPG · 30 FPS
          </p>
          <h2 className="text-xl font-semibold text-slate-100">
            Optical Vitals Check
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Cover the rear camera with your fingertip (flashlight on if
            available). Stay still for {SCAN_SECONDS}s — longer capture improves
            BPM accuracy.
          </p>
        </div>
        {phase === "scanning" && (
          <div className="flex flex-col items-center">
            <svg
              viewBox="0 0 24 24"
              className="h-10 w-10 animate-heartbeat text-emerald-400 drop-shadow-[0_0_12px_rgba(52,211,153,0.7)]"
              fill="currentColor"
            >
              <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
            </svg>
            <span className="mt-1 font-mono text-2xl font-bold text-emerald-300">
              {secondsLeft}s
            </span>
          </div>
        )}
      </div>

      <div className="relative overflow-hidden rounded-2xl border border-slate-800 bg-slate-950">
        <video
          ref={videoRef}
          playsInline
          muted
          className="aspect-[4/3] w-full object-cover opacity-90"
        />
        <canvas ref={canvasRef} className="hidden" aria-hidden />

        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div
            className={`relative flex h-40 w-40 items-center justify-center rounded-full border-2 ${
              phase === "scanning"
                ? "animate-pulseGlow border-emerald-400/80 shadow-glow"
                : "border-slate-500/60"
            }`}
          >
            <div className="h-28 w-28 rounded-full border border-dashed border-emerald-400/40" />
            <span className="absolute bottom-3 text-[10px] font-medium uppercase tracking-[0.2em] text-emerald-200/80">
              Finger ROI
            </span>
          </div>
        </div>

        {phase === "scanning" && (
          <div className="absolute bottom-0 left-0 right-0 h-1 bg-slate-800">
            <div
              className="h-full bg-emerald-400 transition-all duration-1000 ease-linear"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}
      </div>

      <div className="cp-panel p-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
            Live pulse proxy (G channel)
          </span>
          <span className="font-mono text-xs text-emerald-400/80">
            n={rgbRef.current.length || wave.length}
          </span>
        </div>
        <div className="h-24 w-full">
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

      {phase === "done" && result && (
        <div className="grid grid-cols-2 gap-3 animate-fadeUp">
          <div className="cp-panel border-emerald-500/20 p-4 shadow-glow-sm">
            <p className="text-xs uppercase tracking-wider text-slate-500">
              Heart Rate
            </p>
            <p className="mt-1 font-mono text-3xl font-bold text-emerald-300">
              {result.heart_rate_bpm}
              <span className="ml-1 text-sm font-medium text-slate-400">BPM</span>
            </p>
          </div>
          <div className="cp-panel border-emerald-500/20 p-4 shadow-glow-sm">
            <p className="text-xs uppercase tracking-wider text-slate-500">
              HRV · SDNN
            </p>
            <p className="mt-1 font-mono text-3xl font-bold text-emerald-300">
              {result.hrv_sdnn}
              <span className="ml-1 text-sm font-medium text-slate-400">ms</span>
            </p>
          </div>
          <div className="col-span-2 flex flex-wrap gap-2">
            <span className="cp-badge">
              <ShieldCheck className="h-3.5 w-3.5" />
              Confidence {Math.round((result.confidence ?? 0) * 100)}%
            </span>
            {result.method && (
              <span className="cp-badge">Method {result.method}</span>
            )}
            {result.usable === false && (
              <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-xs text-amber-300">
                Low signal quality — retake recommended
              </span>
            )}
          </div>
        </div>
      )}

      {error && (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
          {error}
        </p>
      )}

      <div className="flex gap-3">
        {phase === "idle" || phase === "error" || phase === "done" ? (
          <button type="button" className="cp-btn" onClick={() => void startScan()}>
            {phase === "done" ? (
              <>
                <RefreshCw className="h-4 w-4" /> Retake Scan
              </>
            ) : (
              <>
                <Heart className="h-4 w-4" /> Start {SCAN_SECONDS}s Scan
              </>
            )}
          </button>
        ) : null}
        {phase === "uploading" && (
          <div className="cp-btn pointer-events-none opacity-80">
            <Loader2 className="h-4 w-4 animate-spin" />
            Computing BPM / HRV…
          </div>
        )}
        {phase === "scanning" && (
          <button type="button" className="cp-btn-ghost" onClick={stopStream}>
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}
