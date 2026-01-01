"""
Lightweight post-processing utilities for Kokoro-Story audio output.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
import logging
from typing import Dict, Optional

import numpy as np

try:
    import librosa
    from librosa import util as librosa_util
except ImportError:  # pragma: no cover - optional dependency
    librosa = None
    librosa_util = None

try:  # Optional dependency that librosa uses for resampling-heavy effects
    import resampy  # noqa: F401
except ImportError:  # pragma: no cover
    resampy = None

try:  # Optional, higher-quality transformations
    import pyrubberband as pyrb  # noqa: F401
except ImportError:  # pragma: no cover
    pyrb = None

@dataclass
class VoiceFXSettings:
    """Container for user-defined post-processing controls."""

    pitch_semitones: float = 0.0
    tempo: float = 1.0
    tone: str = "neutral"  # neutral | warm | bright

    @classmethod
    def from_payload(cls, payload: Optional[Dict]) -> Optional["VoiceFXSettings"]:
        """
        Build a VoiceFXSettings instance from a JSON payload.
        Returns None when effects are effectively disabled.
        """
        if not payload or payload.get("enabled") is False:
            return None

        pitch = float(payload.get("pitch", 0.0) or 0.0)
        tempo = float(payload.get("tempo", 1.0) or 1.0)
        tone = (payload.get("tone") or "neutral").strip().lower()
        if tone not in {"neutral", "warm", "bright"}:
            tone = "neutral"

        tempo = max(0.75, min(tempo, 1.35))
        pitch = max(-6.0, min(pitch, 6.0))

        if abs(pitch) < 1e-3 and abs(tempo - 1.0) < 1e-3 and tone == "neutral":
            return None

        return cls(pitch_semitones=pitch, tempo=tempo, tone=tone)


logger = logging.getLogger(__name__)


class AudioPostProcessor:
    """Applies pitch, tempo, and tonal shaping to generated audio arrays."""

    def apply(self, audio: np.ndarray, sample_rate: int, fx: Optional[VoiceFXSettings]) -> np.ndarray:
        if audio is None or fx is None:
            return audio

        base_audio = audio.astype(np.float32, copy=False)
        processed = base_audio.copy()

        if math.isfinite(fx.pitch_semitones) and abs(fx.pitch_semitones) > 1e-3:
            processed = self._apply_pitch(processed, sample_rate, fx.pitch_semitones)

        if math.isfinite(fx.tempo) and abs(fx.tempo - 1.0) > 1e-3:
            processed = self._apply_tempo(processed, sample_rate, fx.tempo)

        if fx.tone and fx.tone != "neutral":
            processed = self._apply_tone(processed, sample_rate, fx.tone)

        blend_mix = self._compute_blend_mix(fx)
        if blend_mix > 0.0:
            processed = self._blend_with_original(base_audio, processed, mix=blend_mix)

        return np.clip(processed, -1.0, 1.0)

    @staticmethod
    def _compute_blend_mix(fx: VoiceFXSettings) -> float:
        if fx is None:
            return 0.0
        if abs(fx.tempo - 1.0) > 0.01:
            return 0.0
        severity_pitch = min(abs(fx.pitch_semitones) / 3.0, 1.0)
        severity_tempo = min(abs(fx.tempo - 1.0) / 0.15, 1.0)
        severity = max(severity_pitch, severity_tempo)
        if fx.tone != "neutral":
            severity = min(1.0, severity + 0.15)
        return max(0.0, 0.2 * (1.0 - severity))

    @staticmethod
    def _apply_pitch(audio: np.ndarray, sample_rate: int, semitones: float) -> np.ndarray:
        AudioPostProcessor._require_librosa("pitch")
        if pyrb is not None:
            try:
                return pyrb.pitch_shift(audio, sample_rate, semitones).astype(np.float32)
            except Exception as exc:  # pragma: no cover - graceful degradation
                logger.warning("Rubber Band pitch_shift failed (%s); falling back to librosa", exc)

        factor = 2.0 ** (semitones / 12.0)
        target_sr = int(sample_rate * factor)
        resampled = librosa.resample(
            audio,
            orig_sr=sample_rate,
            target_sr=max(1000, target_sr),
            res_type="kaiser_best",
        )
        stretched = librosa.effects.time_stretch(resampled, rate=factor)
        if librosa_util is not None:
            stretched = librosa_util.fix_length(stretched, size=audio.shape[0])
        else:
            stretched = np.interp(
                np.linspace(0, 1, num=audio.shape[0], endpoint=False),
                np.linspace(0, 1, num=len(stretched), endpoint=False),
                stretched,
            )
        return stretched.astype(np.float32, copy=False)

    @staticmethod
    def _apply_tempo(audio: np.ndarray, sample_rate: int, rate: float) -> np.ndarray:
        rate = max(0.5, min(rate, 1.5))
        AudioPostProcessor._require_librosa("tempo")
        if pyrb is not None:
            try:
                return pyrb.time_stretch(audio, sample_rate, rate).astype(np.float32)
            except Exception as exc:  # pragma: no cover - graceful degradation
                logger.warning("Rubber Band time_stretch failed (%s); falling back to librosa", exc)
        return librosa.effects.time_stretch(audio, rate=rate)

    @staticmethod
    def _apply_tone(audio: np.ndarray, sample_rate: int, profile: str) -> np.ndarray:
        spectrum = np.fft.rfft(audio)
        if spectrum.size == 0:
            return audio

        freqs = np.fft.rfftfreq(audio.shape[0], d=1.0 / sample_rate)
        last_freq = freqs[-1] or 1.0
        norm = freqs / last_freq

        strength = 0.18
        if profile == "warm":
            gain = 1.0 - strength * norm
        else:  # bright
            gain = 1.0 + strength * norm

        gain = np.clip(gain, 0.2, 1.8)
        spectrum *= gain
        shaped = np.fft.irfft(spectrum, n=audio.shape[0])
        return shaped.astype(np.float32)

    @staticmethod
    def _require_librosa(feature: str):
        if librosa is None:
            raise ImportError(
                "librosa is required for audio post-processing "
                f"({feature}). Run `pip install -r requirements.txt` "
                "to install the dependency."
            )

    @staticmethod
    def _blend_with_original(original: np.ndarray, processed: np.ndarray, mix: float = 0.15) -> np.ndarray:
        if processed is None or original is None or mix <= 0.0:
            return processed
        if processed.shape[0] != original.shape[0]:
            if librosa_util is not None:
                original = librosa_util.fix_length(original, size=processed.shape[0])
            else:
                original = np.interp(
                    np.linspace(0, 1, num=processed.shape[0], endpoint=False),
                    np.linspace(0, 1, num=original.shape[0], endpoint=False),
                    original
                ).astype(np.float32)
        mix = max(0.0, min(mix, 0.4))
        return (1.0 - mix) * processed + mix * original
