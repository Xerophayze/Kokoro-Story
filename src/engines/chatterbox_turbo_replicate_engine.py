"""Chatterbox Turbo engine that streams through Replicate's hosted model."""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import requests
import soundfile as sf

from replicate import Client

from .base import EngineCapabilities, TtsEngineBase, VoiceAssignment
from ..audio_effects import AudioPostProcessor, VoiceFXSettings

logger = logging.getLogger(__name__)

CHATTERBOX_TURBO_REPLICATE_SAMPLE_RATE = 24000
DEFAULT_CHATTERBOX_TURBO_REPLICATE_MODEL = (
    "resemble-ai/chatterbox-turbo:95c87b883ff3e842a1643044dff67f9d204f70a80228f24ff64bffe4a4b917d4"
)
DEFAULT_CHATTERBOX_TURBO_REPLICATE_VOICE = "Andy"


class ChatterboxTurboReplicateEngine(TtsEngineBase):
    """Hosted Chatterbox Turbo inference on Replicate."""

    name = "chatterbox_turbo_replicate"
    capabilities = EngineCapabilities(
        supports_voice_cloning=True,
        supports_emotion_tags=True,
        supported_languages=["en"],
    )

    def __init__(
        self,
        api_token: str,
        *,
        model_version: str = DEFAULT_CHATTERBOX_TURBO_REPLICATE_MODEL,
        default_voice: str = DEFAULT_CHATTERBOX_TURBO_REPLICATE_VOICE,
        temperature: float = 0.8,
        top_p: float = 0.95,
        top_k: int = 1000,
        repetition_penalty: float = 1.2,
        seed: Optional[int] = None,
    ):
        if not api_token:
            raise ValueError("Replicate API token is required for Chatterbox Turbo (Replicate).")

        super().__init__(device="cpu")
        self.client = Client(api_token=api_token)
        self.model_ref = model_version or DEFAULT_CHATTERBOX_TURBO_REPLICATE_MODEL
        self.default_voice = default_voice or DEFAULT_CHATTERBOX_TURBO_REPLICATE_VOICE
        self.temperature = float(temperature)
        self.top_p = float(top_p)
        self.top_k = int(top_k)
        self.repetition_penalty = float(repetition_penalty)
        self.seed = seed
        self.prompt_upload_cache: Dict[str, str] = {}
        self.post_processor = AudioPostProcessor()

    # ------------------------------------------------------------------ #
    @property
    def sample_rate(self) -> int:
        return CHATTERBOX_TURBO_REPLICATE_SAMPLE_RATE

    # ------------------------------------------------------------------ #
    def generate_batch(
        self,
        segments: List[Dict],
        voice_config: Dict[str, Dict],
        output_dir: Path,
        speed: float = 1.0,
        sample_rate: Optional[int] = None,
        progress_cb=None,
    ) -> List[str]:
        if sample_rate and sample_rate != self.sample_rate:
            logger.warning(
                "Replicate Turbo outputs at %s Hz. Requested sample rate %s will be resampled later.",
                self.sample_rate,
                sample_rate,
            )

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_files: List[str] = []
        chunk_index = 0
        for seg_idx, segment in enumerate(segments):
            speaker = segment["speaker"]
            chunks = segment["chunks"]
            assignment = self._voice_assignment_for(voice_config, speaker)
            logger.info(
                "Chatterbox Turbo (Replicate) segment %s/%s speaker=%s voice=%s",
                seg_idx + 1,
                len(segments),
                speaker,
                assignment.voice or self.default_voice,
            )

            for chunk_text in chunks:
                output_path = output_dir / f"chunk_{chunk_index:04d}.wav"
                audio, sr = self._synthesize(chunk_text, assignment)
                sf.write(str(output_path), audio, sr)
                output_files.append(str(output_path))
                chunk_index += 1
                if callable(progress_cb):
                    progress_cb()

        return output_files

    # ------------------------------------------------------------------ #
    def cleanup(self) -> None:  # pragma: no cover - trivial
        """No persistent resources to release."""

    # ------------------------------------------------------------------ #
    def _voice_assignment_for(self, voice_config: Dict[str, Dict], speaker: str) -> VoiceAssignment:
        payload = voice_config.get(speaker) or voice_config.get("default") or {}
        return VoiceAssignment(
            voice=payload.get("voice"),
            lang_code=payload.get("lang_code"),
            audio_prompt_path=payload.get("audio_prompt_path"),
            fx_payload=payload.get("fx"),
            speed_override=payload.get("speed"),
            extra=payload.get("extra") or {},
        )

    # ------------------------------------------------------------------ #
    def _synthesize(self, text: str, assignment: VoiceAssignment) -> Tuple[np.ndarray, int]:
        reference_url = None
        if assignment.audio_prompt_path:
            reference_url = self._upload_reference_audio(assignment.audio_prompt_path)

        params = self._build_payload(text, assignment, reference_url)
        try:
            output_url = self.client.run(self.model_ref, input=params)
        except Exception as exc:  # pragma: no cover - API failure
            raise RuntimeError(f"Chatterbox Turbo (Replicate) request failed: {exc}") from exc

        audio_array = self._download_audio(output_url)
        fx_settings = VoiceFXSettings.from_payload(assignment.fx_payload)
        if fx_settings:
            audio_array = self.post_processor.apply(audio_array, self.sample_rate, fx_settings)
        return audio_array, self.sample_rate

    # ------------------------------------------------------------------ #
    def _build_payload(
        self,
        text: str,
        assignment: VoiceAssignment,
        reference_url: Optional[str],
    ) -> Dict:
        params = {
            "text": text,
            "temperature": self._resolve_numeric(assignment.extra, "temperature", self.temperature),
            "top_p": self._resolve_numeric(assignment.extra, "top_p", self.top_p),
            "top_k": int(self._resolve_numeric(assignment.extra, "top_k", self.top_k)),
            "repetition_penalty": self._resolve_numeric(
                assignment.extra, "repetition_penalty", self.repetition_penalty
            ),
        }
        if self.seed is not None:
            params["seed"] = int(self.seed)

        if reference_url:
            params["reference_audio"] = reference_url
        else:
            params["voice"] = assignment.voice or self.default_voice

        return params

    # ------------------------------------------------------------------ #
    def _resolve_numeric(self, extra: Dict, key: str, default_value: float) -> float:
        value = extra.get(key) if extra else None
        if value is None:
            return default_value
        try:
            return float(value)
        except (TypeError, ValueError):
            return default_value

    # ------------------------------------------------------------------ #
    def _upload_reference_audio(self, path_str: str) -> str:
        resolved = self._resolve_prompt_path(path_str)
        key = str(resolved.resolve())
        cached = self.prompt_upload_cache.get(key)
        if cached:
            return cached

        file_resource = self.client.files.create(str(resolved))
        url = (
            file_resource.urls.get("get")
            or file_resource.urls.get("download")
            or file_resource.urls.get("web")
        )
        if not url:
            raise RuntimeError("Replicate did not return a download URL for uploaded prompt.")
        self.prompt_upload_cache[key] = url
        return url

    # ------------------------------------------------------------------ #
    @staticmethod
    def _resolve_prompt_path(path_str: str) -> Path:
        candidate = Path(path_str)
        if candidate.is_file():
            return candidate
        alt = Path("data/voice_prompts") / path_str
        if alt.is_file():
            return alt
        raise FileNotFoundError(
            f"Reference audio not found: {path_str}. Place files in data/voice_prompts or provide an absolute path."
        )

    # ------------------------------------------------------------------ #
    def _download_audio(self, url: str) -> np.ndarray:
        if not url:
            raise RuntimeError("Replicate response did not include an audio URL.")
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        buffer = io.BytesIO(response.content)
        audio_array, sr = sf.read(buffer, dtype="float32")
        if sr != self.sample_rate:
            audio_array = self._resample_audio(audio_array, sr)
        if audio_array.ndim > 1:
            audio_array = np.mean(audio_array, axis=1)
        return audio_array.astype("float32")

    # ------------------------------------------------------------------ #
    def _resample_audio(self, audio: np.ndarray, original_sr: int) -> np.ndarray:
        if original_sr == self.sample_rate:
            return audio
        try:
            import librosa
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "librosa is required to resample Replicate audio output. Install via requirements."
            ) from exc
        return librosa.resample(audio, orig_sr=original_sr, target_sr=self.sample_rate)


__all__ = [
    "ChatterboxTurboReplicateEngine",
    "CHATTERBOX_TURBO_REPLICATE_SAMPLE_RATE",
    "DEFAULT_CHATTERBOX_TURBO_REPLICATE_MODEL",
    "DEFAULT_CHATTERBOX_TURBO_REPLICATE_VOICE",
]
