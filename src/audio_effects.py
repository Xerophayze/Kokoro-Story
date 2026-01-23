"""
Lightweight post-processing utilities for TTS-Story audio output.
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
    speed: float = 1.0  # 0.5 to 2.0 (1.0 = normal)
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
        speed = float(payload.get("speed", 1.0) or 1.0)
        tone = (payload.get("tone") or "neutral").strip().lower()
        if tone not in {"neutral", "warm", "bright"}:
            tone = "neutral"

        pitch = max(-12.0, min(pitch, 12.0))
        speed = max(0.5, min(speed, 2.0))

        if abs(pitch) < 1e-3 and abs(speed - 1.0) < 1e-3 and tone == "neutral":
            return None

        return cls(pitch_semitones=pitch, speed=speed, tone=tone)


logger = logging.getLogger(__name__)


class AudioPostProcessor:
    """Applies pitch, speed, and tonal shaping to generated audio arrays."""

    def apply(self, audio: np.ndarray, sample_rate: int, fx: Optional[VoiceFXSettings], blend_override: Optional[float] = None) -> np.ndarray:
        """
        Apply audio effects to the input audio.
        
        Args:
            audio: Input audio array
            sample_rate: Sample rate of the audio
            fx: Voice FX settings to apply
            blend_override: If provided, overrides the computed blend mix. Set to 0.0 to disable blending.
        """
        if audio is None or fx is None:
            return audio

        # Handle stereo audio - convert to mono for processing
        is_stereo = audio.ndim == 2 and audio.shape[1] == 2
        if is_stereo:
            # Average the channels to mono
            audio = np.mean(audio, axis=1)

        base_audio = audio.astype(np.float32, copy=False)
        processed = base_audio.copy()

        # Apply speed change first (time stretch without pitch change)
        if math.isfinite(fx.speed) and abs(fx.speed - 1.0) > 1e-3:
            processed = self._apply_speed(processed, sample_rate, fx.speed)

        if math.isfinite(fx.pitch_semitones) and abs(fx.pitch_semitones) > 1e-3:
            processed = self._apply_pitch(processed, sample_rate, fx.pitch_semitones)

        if fx.tone and fx.tone != "neutral":
            processed = self._apply_tone(processed, sample_rate, fx.tone)

        # Use blend_override if provided, otherwise compute blend mix
        if blend_override is not None:
            blend_mix = blend_override
        else:
            blend_mix = self._compute_blend_mix(fx)
        
        if blend_mix > 0.0:
            processed = self._blend_with_original(base_audio, processed, mix=blend_mix)

        return np.clip(processed, -1.0, 1.0)

    @staticmethod
    def _compute_blend_mix(fx: VoiceFXSettings) -> float:
        if fx is None:
            return 0.0
        severity = min(abs(fx.pitch_semitones) / 3.0, 1.0)
        if abs(fx.speed - 1.0) > 0.1:
            severity = min(1.0, severity + 0.1)
        if fx.tone != "neutral":
            severity = min(1.0, severity + 0.15)
        return max(0.0, 0.2 * (1.0 - severity))

    @staticmethod
    def _apply_speed(audio: np.ndarray, sample_rate: int, speed: float) -> np.ndarray:
        """
        Apply speed/tempo change without affecting pitch.
        speed > 1.0 = faster (shorter duration)
        speed < 1.0 = slower (longer duration)
        """
        AudioPostProcessor._require_librosa("speed")
        if pyrb is not None:
            try:
                # Use high-quality settings for Rubber Band
                return pyrb.time_stretch(audio, sample_rate, speed).astype(np.float32)
            except Exception as exc:  # pragma: no cover - graceful degradation
                logger.warning("Rubber Band time_stretch failed (%s); falling back to librosa", exc)

        # Use larger hop_length and n_fft for better quality (reduces metallic artifacts)
        # Default librosa uses n_fft=2048, hop_length=512 which can sound robotic
        n_fft = 4096
        hop_length = 1024
        
        # Compute STFT with better parameters
        stft = librosa.stft(audio, n_fft=n_fft, hop_length=hop_length)
        
        # Apply phase vocoder time stretch
        stft_stretched = librosa.phase_vocoder(stft, rate=speed, hop_length=hop_length)
        
        # Reconstruct audio
        stretched = librosa.istft(stft_stretched, hop_length=hop_length)
        
        return stretched.astype(np.float32, copy=False)

    @staticmethod
    def _apply_pitch(audio: np.ndarray, sample_rate: int, semitones: float) -> np.ndarray:
        AudioPostProcessor._require_librosa("pitch")
        if pyrb is not None:
            try:
                return pyrb.pitch_shift(audio, sample_rate, semitones).astype(np.float32)
            except Exception as exc:  # pragma: no cover - graceful degradation
                logger.warning("Rubber Band pitch_shift failed (%s); falling back to librosa", exc)

        # Use librosa's built-in pitch_shift with better parameters
        # n_fft=4096 provides smoother frequency resolution
        # Using larger values reduces metallic/robotic artifacts
        n_fft = 4096
        hop_length = 1024
        
        # Try high-quality resampling, fall back to kaiser_best if soxr not available
        try:
            shifted = librosa.effects.pitch_shift(
                audio,
                sr=sample_rate,
                n_steps=semitones,
                n_fft=n_fft,
                hop_length=hop_length,
                res_type='soxr_hq'
            )
        except Exception:
            shifted = librosa.effects.pitch_shift(
                audio,
                sr=sample_rate,
                n_steps=semitones,
                n_fft=n_fft,
                hop_length=hop_length,
                res_type='kaiser_best'
            )
        
        return shifted.astype(np.float32, copy=False)

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
