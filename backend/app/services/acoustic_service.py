"""Acoustic cough / lung auscultation analysis via classical DSP features."""

from __future__ import annotations

import base64
import io
import logging
import uuid
from typing import Any

import librosa
import librosa.display
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
from scipy import signal as sp_signal

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_MIN_DURATION_SEC = 0.5
_SILENCE_RMS_DB = -50.0
_SILENCE_RATIO_MAX = 0.85
_SPECTROGRAM_BUCKET = "spectrograms"


def _empty_result(reason: str) -> dict[str, Any]:
    """Descriptive fallback for silent or corrupted audio."""
    return {
        "cough_type": "Normal",
        "severity_score": 0.0,
        "wheeze_detected": False,
        "crackle_detected": False,
        "acoustic_confidence": 0.0,
        "spectrogram_url": "",
        "error": reason,
        "usable": False,
    }


class AcousticProcessor:
    """Cough acoustic classifier and Mel-spectrogram renderer."""

    def analyze_cough_audio(
        self,
        audio_bytes: bytes,
        sample_rate: int = 22050,
    ) -> dict[str, Any]:
        """
        Analyze a cough recording and return classification + spectrogram URL.

        Spectrogram is uploaded to Supabase Storage when credentials are set;
        otherwise a data-URI PNG is returned for local prototyping.
        """
        if not audio_bytes:
            return _empty_result("empty_audio: zero-length buffer")

        if sample_rate <= 0:
            return _empty_result("invalid_sample_rate: must be positive")

        try:
            y, sr = self._load_audio(audio_bytes, sample_rate)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Audio decode failed")
            return _empty_result(f"corrupt_audio: {exc}")

        if y.size == 0:
            return _empty_result("empty_audio: decoded signal has no samples")

        duration = float(y.size) / float(sr)
        if duration < _MIN_DURATION_SEC:
            return _empty_result(
                f"too_short: duration={duration:.2f}s, need >= {_MIN_DURATION_SEC}s"
            )

        rms = float(np.sqrt(np.mean(y**2)) + 1e-12)
        rms_db = 20.0 * np.log10(rms)
        silence_ratio = self._silence_ratio(y)
        if rms_db < _SILENCE_RMS_DB or silence_ratio > _SILENCE_RATIO_MAX:
            return _empty_result(
                f"silent_audio: rms_db={rms_db:.1f}, silence_ratio={silence_ratio:.2f}"
            )

        # Core spectral features
        stft = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
        zcr = librosa.feature.zero_crossing_rate(y)
        flatness = librosa.feature.spectral_flatness(y=y)
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85)

        centroid_hz = float(np.mean(spectral_centroid))
        flatness_mean = float(np.mean(flatness))
        rolloff_hz = float(np.mean(rolloff))
        zcr_mean = float(np.mean(zcr))
        mfcc_mean = mfcc.mean(axis=1)

        wheeze_detected, wheeze_conf = self._detect_wheeze(stft, sr)
        crackle_detected, crackle_conf = self._detect_crackle(y, sr)

        cough_type, severity, class_conf = self._classify_cough(
            centroid_hz=centroid_hz,
            flatness=flatness_mean,
            rolloff_hz=rolloff_hz,
            zcr=zcr_mean,
            mfcc_mean=mfcc_mean,
            wheeze=wheeze_detected,
            crackle=crackle_detected,
        )

        try:
            spectrogram_url = self._render_and_store_mel(y, sr)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Spectrogram render/upload failed: %s", exc)
            spectrogram_url = ""

        acoustic_confidence = float(
            np.clip(
                0.5 * class_conf
                + 0.2 * (1.0 - silence_ratio)
                + 0.15 * max(wheeze_conf, crackle_conf)
                + 0.15 * float(np.clip((rms_db + 60.0) / 40.0, 0.0, 1.0)),
                0.0,
                1.0,
            )
        )

        return {
            "cough_type": cough_type,
            "severity_score": round(float(severity), 1),
            "wheeze_detected": bool(wheeze_detected),
            "crackle_detected": bool(crackle_detected),
            "acoustic_confidence": round(acoustic_confidence, 3),
            "spectrogram_url": spectrogram_url,
            "usable": acoustic_confidence >= 0.25 and bool(spectrogram_url),
            "features": {
                "mfcc_mean": mfcc_mean.astype(float).tolist(),
                "spectral_centroid_hz": round(centroid_hz, 2),
                "spectral_flatness": round(flatness_mean, 4),
                "spectral_rolloff_hz": round(rolloff_hz, 2),
                "zero_crossing_rate": round(zcr_mean, 4),
                "rms_db": round(rms_db, 2),
                "duration_sec": round(duration, 2),
            },
        }

    @staticmethod
    def _load_audio(audio_bytes: bytes, target_sr: int) -> tuple[np.ndarray, int]:
        """Decode audio bytes with librosa (supports wav and common codecs)."""
        buffer = io.BytesIO(audio_bytes)
        y, sr = librosa.load(buffer, sr=target_sr, mono=True)
        y = np.asarray(y, dtype=np.float32)
        if not np.isfinite(y).all():
            y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
        return y, int(sr)

    @staticmethod
    def _silence_ratio(y: np.ndarray, frame_length: int = 2048) -> float:
        """Fraction of frames below a relative energy threshold."""
        if y.size < frame_length:
            return 1.0 if float(np.sqrt(np.mean(y**2))) < 1e-4 else 0.0
        # Frame without centering to avoid edge artifacts on short coughs
        rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=512)[0]
        if rms.size == 0:
            return 1.0
        thresh = max(float(np.max(rms)) * 0.05, 1e-5)
        return float(np.mean(rms < thresh))

    @staticmethod
    def _detect_wheeze(stft_mag: np.ndarray, sr: int) -> tuple[bool, float]:
        """
        Wheeze biomarker: persistent harmonic energy above 400 Hz.

        Looks for frequency bins >400 Hz that remain strong across many frames.
        """
        if stft_mag.size == 0:
            return False, 0.0

        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
        high_mask = freqs > 400.0
        if not np.any(high_mask):
            return False, 0.0

        high_band = stft_mag[high_mask, :]
        # Per-frame peak in high band vs median
        frame_peaks = np.max(high_band, axis=0)
        frame_med = np.median(stft_mag, axis=0) + 1e-12
        prominence = frame_peaks / frame_med
        sustained = float(np.mean(prominence > 4.0))
        # Continuity: autocorrelation-ish persistence of high energy
        detected = sustained > 0.25
        confidence = float(np.clip(sustained, 0.0, 1.0))
        return detected, confidence

    @staticmethod
    def _detect_crackle(y: np.ndarray, sr: int) -> tuple[bool, float]:
        """
        Crackle biomarker: explosive transients shorter than ~20 ms.

        Uses envelope peak width on a high-passed signal.
        """
        if y.size < 16:
            return False, 0.0

        # Emphasize transient energy
        nyq = sr / 2.0
        cutoff = min(1000.0 / nyq, 0.99)
        b, a = sp_signal.butter(2, cutoff, btype="high")
        try:
            hp = sp_signal.filtfilt(b, a, y)
        except ValueError:
            hp = y

        envelope = np.abs(sp_signal.hilbert(hp))
        # Smooth lightly
        win = max(1, int(sr * 0.002))
        kernel = np.ones(win) / win
        env_s = np.convolve(envelope, kernel, mode="same")

        thresh = float(np.mean(env_s) + 3.0 * np.std(env_s))
        min_distance = max(1, int(sr * 0.02))  # 20 ms separation
        peaks, _props = sp_signal.find_peaks(
            env_s,
            height=thresh,
            distance=min_distance,
            prominence=float(np.std(env_s)),
        )
        if peaks.size == 0:
            return False, 0.0

        # Estimate width at half-prominence; crackles are <20 ms
        widths = sp_signal.peak_widths(env_s, peaks, rel_height=0.5)[0]
        width_sec = widths / float(sr)
        short = width_sec < 0.020
        short_count = int(np.sum(short))
        detected = short_count >= 2
        confidence = float(np.clip(short_count / 5.0, 0.0, 1.0))
        return detected, confidence

    @staticmethod
    def _classify_cough(
        *,
        centroid_hz: float,
        flatness: float,
        rolloff_hz: float,
        zcr: float,
        mfcc_mean: np.ndarray,
        wheeze: bool,
        crackle: bool,
    ) -> tuple[str, float, float]:
        """
        Rule-based cough typing.

        - Dry / Irritative: high flatness, high-frequency energy
        - Productive / Wet: low-frequency dampening, bubbling / crackle energy
        - Normal: otherwise low-severity profile
        """
        dry_score = 0.0
        wet_score = 0.0

        if flatness > 0.15:
            dry_score += 0.35
        if centroid_hz > 1600.0:
            dry_score += 0.25
        if rolloff_hz > 3500.0:
            dry_score += 0.2
        if zcr > 0.12:
            dry_score += 0.15
        if wheeze:
            dry_score += 0.15

        # Low-frequency / dampened → wet
        if centroid_hz < 1200.0:
            wet_score += 0.3
        if rolloff_hz < 2500.0:
            wet_score += 0.2
        if flatness < 0.08:
            wet_score += 0.2
        if crackle:
            wet_score += 0.35
        # MFCC[1] often tracks spectral balance
        if mfcc_mean.size > 1 and float(mfcc_mean[1]) < 0:
            wet_score += 0.1

        dry_score = float(np.clip(dry_score, 0.0, 1.0))
        wet_score = float(np.clip(wet_score, 0.0, 1.0))

        if dry_score < 0.35 and wet_score < 0.35:
            return "Normal", round(max(dry_score, wet_score) * 40.0, 1), 0.55

        if wet_score >= dry_score:
            severity = 40.0 + wet_score * 60.0
            return "Productive / Wet", round(severity, 1), wet_score

        severity = 35.0 + dry_score * 55.0
        if wheeze:
            severity = min(100.0, severity + 10.0)
        return "Dry / Irritative", round(severity, 1), dry_score

    def _render_and_store_mel(self, y: np.ndarray, sr: int) -> str:
        """Render Mel-spectrogram PNG and upload or return a data URI."""
        png_bytes = self._mel_png_bytes(y, sr)
        settings = get_settings()

        if settings.supabase_url and settings.supabase_key:
            url = self._upload_supabase(png_bytes, settings.supabase_url, settings.supabase_key)
            if url:
                return url

        b64 = base64.b64encode(png_bytes).decode("ascii")
        return f"data:image/png;base64,{b64}"

    @staticmethod
    def _mel_png_bytes(y: np.ndarray, sr: int) -> bytes:
        """Render a Mel-spectrogram figure to PNG bytes."""
        mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128, fmax=8000)
        mel_db = librosa.power_to_db(mel, ref=np.max)

        fig, ax = plt.subplots(figsize=(6, 3), dpi=100)
        img = librosa.display.specshow(
            mel_db,
            x_axis="time",
            y_axis="mel",
            sr=sr,
            fmax=8000,
            ax=ax,
            cmap="magma",
        )
        fig.colorbar(img, ax=ax, format="%+2.0f dB")
        ax.set_title("Cough Mel-Spectrogram")
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    @staticmethod
    def _upload_supabase(png_bytes: bytes, url: str, key: str) -> str:
        """Upload PNG to Supabase Storage; return public URL or empty string."""
        try:
            from supabase import create_client

            client = create_client(url, key)
            object_path = f"cough/{uuid.uuid4().hex}.png"
            client.storage.from_(_SPECTROGRAM_BUCKET).upload(
                path=object_path,
                file=png_bytes,
                file_options={"content-type": "image/png", "upsert": "true"},
            )
            public = client.storage.from_(_SPECTROGRAM_BUCKET).get_public_url(object_path)
            return str(public)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Supabase spectrogram upload failed: %s", exc)
            return ""
