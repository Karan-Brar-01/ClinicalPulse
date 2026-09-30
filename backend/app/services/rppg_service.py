"""Optical rPPG vitals extraction using POS / CHROM + Welch PSD fusion."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import signal

logger = logging.getLogger(__name__)

# Physiological band: 45–180 BPM (tighten for resting adult accuracy)
_BAND_LOW_HZ = 0.75
_BAND_HIGH_HZ = 3.0
_BUTTER_ORDER = 3
_MIN_SAMPLES = 90  # ~3 s at 30 FPS absolute floor
_ROI_FRAC = 0.4


def _empty_result(reason: str) -> Dict[str, Any]:
    return {
        "heart_rate": 0.0,
        "hrv_sdnn": 0.0,
        "confidence": 0.0,
        "pulse_wave": [],
        "error": reason,
        "usable": False,
        "method": None,
    }


class RPPGProcessor:
    """
    Remote PPG processor.

    Preferred path: RGB time series → POS (Plane-Orthogonal-to-Skin) BVP,
    Welch PSD peak with parabolic interpolation, fused with time-domain RR BPM.
    Fallback: single green channel with detrend + same spectral pipeline.
    """

    def process_video_frames(
        self,
        frames: List[np.ndarray],
        fps: float = 30.0,
    ) -> Dict[str, Any]:
        if not frames:
            return _empty_result("no_frames: empty frame list")
        if fps <= 0:
            return _empty_result("invalid_fps: fps must be positive")

        rgb: List[Tuple[float, float, float]] = []
        for i, frame in enumerate(frames):
            try:
                sample = self._mean_rgb_roi(frame)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping corrupt frame %s: %s", i, exc)
                continue
            if sample is not None:
                rgb.append(sample)

        if len(rgb) < _MIN_SAMPLES:
            return _empty_result(
                f"insufficient_frames: got {len(rgb)}, need >= {_MIN_SAMPLES}"
            )
        return self.process_rgb_samples(rgb, fps=fps)

    def process_raw_green_samples(
        self,
        samples: List[float],
        fps: float = 30.0,
    ) -> Dict[str, Any]:
        """Legacy green-only path (still improved with Welch + fusion)."""
        if fps <= 0:
            return _empty_result("invalid_fps: fps must be positive")
        if not samples or len(samples) < _MIN_SAMPLES:
            n = 0 if not samples else len(samples)
            return _empty_result(
                f"insufficient_samples: got {n}, need >= {_MIN_SAMPLES}"
            )
        g = np.asarray(samples, dtype=np.float64)
        # Synthetic RGB with G dominant (finger-on-lens often floods red too)
        rgb = [(float(x), float(x), float(x) * 0.85) for x in g.tolist()]
        # Prefer pure green pipeline when R≈G≈B synthetic
        return self._analyze_bvp(g, fps=fps, method_hint="green_welch")

    def process_rgb_samples(
        self,
        samples: Sequence[Tuple[float, float, float]],
        fps: float = 30.0,
    ) -> Dict[str, Any]:
        if fps <= 0:
            return _empty_result("invalid_fps: fps must be positive")
        if len(samples) < _MIN_SAMPLES:
            return _empty_result(
                f"insufficient_samples: got {len(samples)}, need >= {_MIN_SAMPLES}"
            )

        arr = np.asarray(samples, dtype=np.float64)
        if arr.ndim != 2 or arr.shape[1] != 3:
            return _empty_result("bad_rgb_shape: expected Nx3 RGB means")
        if not np.isfinite(arr).all():
            arr = arr[np.isfinite(arr).all(axis=1)]
            if arr.shape[0] < _MIN_SAMPLES:
                return _empty_result("corrupt_signal: non-finite samples dominate")

        # Try POS then CHROM; keep higher-confidence result
        candidates: List[Dict[str, Any]] = []
        for name, builder in (
            ("pos", self._pos_bvp),
            ("chrom", self._chrom_bvp),
            ("green", lambda a: a[:, 1]),
        ):
            try:
                bvp = builder(arr)
                result = self._analyze_bvp(bvp, fps=fps, method_hint=name)
                if result.get("usable") or result.get("confidence", 0) > 0:
                    candidates.append(result)
            except Exception as exc:  # noqa: BLE001
                logger.warning("rPPG method %s failed: %s", name, exc)

        if not candidates:
            return _empty_result("all_methods_failed: poor signal quality")

        candidates.sort(key=lambda r: float(r.get("confidence") or 0), reverse=True)
        best = candidates[0]
        # Soft consensus: if top-2 BPM within 6, average
        if len(candidates) >= 2:
            a = float(candidates[0].get("heart_rate") or 0)
            b = float(candidates[1].get("heart_rate") or 0)
            if a > 0 and b > 0 and abs(a - b) <= 6.0:
                best = dict(best)
                best["heart_rate"] = round((a + b) / 2.0, 1)
                best["confidence"] = round(
                    min(1.0, float(best.get("confidence") or 0) + 0.05),
                    3,
                )
                best["method"] = f"{candidates[0].get('method')}+{candidates[1].get('method')}"
        return best

    # ------------------------------------------------------------------
    # BVP extractors
    # ------------------------------------------------------------------

    @staticmethod
    def _pos_bvp(rgb: np.ndarray) -> np.ndarray:
        """Wang et al. POS: Plane-Orthogonal-to-Skin."""
        means = np.mean(rgb, axis=0)
        means = np.where(means < 1e-6, 1e-6, means)
        cn = rgb / means
        xs = cn[:, 0] - cn[:, 1]
        ys = cn[:, 0] + cn[:, 1] - 2.0 * cn[:, 2]
        s_x = float(np.std(xs)) + 1e-12
        s_y = float(np.std(ys)) + 1e-12
        alpha = s_x / s_y
        return xs - alpha * ys

    @staticmethod
    def _chrom_bvp(rgb: np.ndarray) -> np.ndarray:
        """De Haan & Jeanne CHROM."""
        means = np.mean(rgb, axis=0)
        means = np.where(means < 1e-6, 1e-6, means)
        cn = rgb / means
        xs = 3.0 * cn[:, 0] - 2.0 * cn[:, 1]
        ys = 1.5 * cn[:, 0] + cn[:, 1] - 1.5 * cn[:, 2]
        s_x = float(np.std(xs)) + 1e-12
        s_y = float(np.std(ys)) + 1e-12
        alpha = s_x / s_y
        return xs - alpha * ys

    def _analyze_bvp(
        self,
        bvp: np.ndarray,
        *,
        fps: float,
        method_hint: str,
    ) -> Dict[str, Any]:
        x = np.asarray(bvp, dtype=np.float64).ravel()
        if x.size < _MIN_SAMPLES:
            return _empty_result("bvp_too_short")

        std = float(np.std(x))
        if std < 1e-9:
            return _empty_result("flat_signal: near-zero variance")

        x = signal.detrend(x, type="linear")
        x = (x - float(np.mean(x))) / (float(np.std(x)) + 1e-12)

        try:
            filtered = self._bandpass(x, fps)
        except ValueError as exc:
            return _empty_result(f"filter_error: {exc}")

        bpm_spec, peak_power, snr, freqs, psd = self._welch_bpm(filtered, fps)
        bpm_td, hrv_sdnn, peak_count = self._time_domain_bpm(filtered, fps)

        bpm, method = self._fuse_bpm(bpm_spec, bpm_td, snr, method_hint)
        if bpm <= 0:
            return _empty_result("no_reliable_peak")

        confidence = self._estimate_confidence(
            snr=snr,
            peak_power=peak_power,
            peak_count=peak_count,
            n_samples=filtered.size,
            fps=fps,
            bpm_spec=bpm_spec,
            bpm_td=bpm_td,
        )

        return {
            "heart_rate": round(float(bpm), 1),
            "hrv_sdnn": round(float(hrv_sdnn), 2),
            "confidence": round(float(confidence), 3),
            "pulse_wave": filtered[:300].tolist(),
            "usable": confidence >= 0.35 and 45.0 <= bpm <= 180.0,
            "method": method,
            "diagnostics": {
                "bpm_spectral": round(float(bpm_spec), 2) if bpm_spec else None,
                "bpm_time_domain": round(float(bpm_td), 2) if bpm_td else None,
                "snr": round(float(snr), 3),
            },
        }

    @staticmethod
    def _fuse_bpm(
        bpm_spec: float,
        bpm_td: float,
        snr: float,
        method_hint: str,
    ) -> Tuple[float, str]:
        if bpm_spec <= 0 and bpm_td <= 0:
            return 0.0, method_hint
        if bpm_spec <= 0:
            return bpm_td, f"{method_hint}_td"
        if bpm_td <= 0:
            return bpm_spec, f"{method_hint}_welch"
        if abs(bpm_spec - bpm_td) <= 8.0:
            # Agreement → average (weighted by SNR)
            w = float(np.clip(snr, 0.2, 0.8))
            return w * bpm_spec + (1.0 - w) * bpm_td, f"{method_hint}_fused"
        # Prefer spectral when SNR is decent; else time-domain
        if snr >= 0.35:
            return bpm_spec, f"{method_hint}_welch"
        return bpm_td, f"{method_hint}_td"

    def _welch_bpm(
        self, filtered: np.ndarray, fps: float
    ) -> Tuple[float, float, float, np.ndarray, np.ndarray]:
        nperseg = min(filtered.size, max(64, int(fps * 8)))
        freqs, psd = signal.welch(
            filtered,
            fs=fps,
            nperseg=nperseg,
            noverlap=nperseg // 2,
            window="hann",
            detrend="constant",
            scaling="density",
        )
        band = (freqs >= _BAND_LOW_HZ) & (freqs <= _BAND_HIGH_HZ)
        if not np.any(band):
            return 0.0, 0.0, 0.0, freqs, psd

        band_f = freqs[band]
        band_p = psd[band]
        idx = int(np.argmax(band_p))
        # Parabolic interpolation around peak for sub-bin frequency
        f_max = self._parabolic_peak(band_f, band_p, idx)
        bpm = f_max * 60.0

        peak_power = float(band_p[idx])
        # SNR: peak vs median in-band (exclude ±0.1 Hz around peak)
        mask_noise = np.abs(band_f - f_max) > 0.1
        noise = float(np.median(band_p[mask_noise])) if np.any(mask_noise) else float(np.median(band_p))
        snr = peak_power / (noise + 1e-12)
        snr_norm = float(np.clip(np.log1p(snr) / 4.0, 0.0, 1.0))
        return bpm, peak_power, snr_norm, freqs, psd

    @staticmethod
    def _parabolic_peak(freqs: np.ndarray, power: np.ndarray, idx: int) -> float:
        if idx <= 0 or idx >= power.size - 1:
            return float(freqs[idx])
        y0, y1, y2 = float(power[idx - 1]), float(power[idx]), float(power[idx + 1])
        denom = y0 - 2.0 * y1 + y2
        if abs(denom) < 1e-18:
            return float(freqs[idx])
        delta = 0.5 * (y0 - y2) / denom
        delta = float(np.clip(delta, -0.5, 0.5))
        # Assume uniform spacing
        df = float(freqs[idx] - freqs[idx - 1])
        return float(freqs[idx]) + delta * df

    def _time_domain_bpm(
        self, filtered: np.ndarray, fps: float
    ) -> Tuple[float, float, int]:
        if filtered.size < 3:
            return 0.0, 0.0, 0

        min_distance = max(1, int(fps * 0.33))  # max ~180 BPM
        prominence = max(0.08, float(np.std(filtered)) * 0.35)
        peaks, _ = signal.find_peaks(
            filtered,
            distance=min_distance,
            prominence=prominence,
        )
        if peaks.size < 3:
            return 0.0, 0.0, int(peaks.size)

        rr_sec = np.diff(peaks.astype(np.float64)) / fps
        rr_ms = rr_sec * 1000.0
        rr_ms = rr_ms[(rr_ms >= 333.0) & (rr_ms <= 1333.0)]  # 45–180 BPM
        if rr_ms.size < 2:
            return 0.0, 0.0, int(peaks.size)

        # Use median RR (robust to outliers) for BPM
        bpm = 60000.0 / float(np.median(rr_ms))
        sdnn = float(np.std(rr_ms, ddof=1))
        return bpm, sdnn, int(peaks.size)

    @staticmethod
    def _mean_rgb_roi(frame: np.ndarray) -> Optional[Tuple[float, float, float]]:
        if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
            return None
        if frame.ndim == 2:
            v = float(np.mean(frame.astype(np.float64)))
            return (v, v, v)
        if frame.ndim != 3 or frame.shape[2] < 3:
            raise ValueError(f"unsupported frame shape {frame.shape}")

        # OpenCV BGR → treat as B,G,R; canvas RGB → R,G,B.
        # Heuristic: if channel0 mean >> channel2, likely BGR (OpenCV).
        img = frame.astype(np.float64)
        c0, c1, c2 = img[:, :, 0], img[:, :, 1], img[:, :, 2]
        h, w = c0.shape
        side = max(1, int(min(h, w) * _ROI_FRAC))
        y0 = max(0, (h - side) // 2)
        x0 = max(0, (w - side) // 2)
        r0 = c0[y0 : y0 + side, x0 : x0 + side]
        r1 = c1[y0 : y0 + side, x0 : x0 + side]
        r2 = c2[y0 : y0 + side, x0 : x0 + side]
        m0, m1, m2 = float(np.mean(r0)), float(np.mean(r1)), float(np.mean(r2))
        # OpenCV VideoCapture is BGR
        return (m2, m1, m0)  # R, G, B

    @staticmethod
    def _bandpass(x: np.ndarray, fps: float) -> np.ndarray:
        nyquist = fps / 2.0
        low = _BAND_LOW_HZ / nyquist
        high = min(_BAND_HIGH_HZ / nyquist, 0.99)
        if low <= 0 or high >= 1.0 or low >= high:
            raise ValueError(f"invalid critical frequencies for fps={fps}")
        b, a = signal.butter(_BUTTER_ORDER, [low, high], btype="band")
        padlen = 3 * max(len(a), len(b))
        if x.size <= padlen:
            raise ValueError(f"signal too short for filtfilt (n={x.size})")
        return signal.filtfilt(b, a, x)

    @staticmethod
    def _estimate_confidence(
        *,
        snr: float,
        peak_power: float,
        peak_count: int,
        n_samples: int,
        fps: float,
        bpm_spec: float,
        bpm_td: float,
    ) -> float:
        duration_sec = n_samples / fps
        duration_score = float(np.clip(duration_sec / 20.0, 0.0, 1.0))
        agree = 0.0
        if bpm_spec > 0 and bpm_td > 0:
            agree = float(np.clip(1.0 - abs(bpm_spec - bpm_td) / 20.0, 0.0, 1.0))
        peak_score = float(np.clip(peak_count / max(1.0, duration_sec * 1.2), 0.0, 1.0))
        conf = (
            0.4 * float(np.clip(snr, 0.0, 1.0))
            + 0.25 * agree
            + 0.2 * duration_score
            + 0.15 * peak_score
        )
        return float(np.clip(conf, 0.0, 1.0))
