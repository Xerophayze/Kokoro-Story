"""Kokoro-based TTS engine implementation."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

import numpy as np
import soundfile as sf
import torch

from .base import EngineCapabilities, TtsEngineBase
from ..audio_effects import AudioPostProcessor, VoiceFXSettings
from ..custom_voice_store import CUSTOM_CODE_PREFIX, get_custom_voice_by_code

DEFAULT_SAMPLE_RATE = 24000

try:
    from kokoro import KPipeline  # type: ignore
    KOKORO_AVAILABLE = True
except ImportError:  # pragma: no cover - handled upstream
    KOKORO_AVAILABLE = False
    logging.warning("Kokoro not installed. Local TTS will not be available.")


class KokoroEngine(TtsEngineBase):
    """Local GPU TTS via Kokoro pipelines."""

    name = "kokoro"
    capabilities = EngineCapabilities(
        supports_voice_cloning=True,
        supported_languages=None,  # Determined by kokoro pipelines dynamically
    )

    def __init__(self, device: str = "auto"):
        if not KOKORO_AVAILABLE:
            raise ImportError("Kokoro is not installed. Run: pip install kokoro>=0.9.4")

        super().__init__(device=device)

        if self.device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.pipelines: Dict[str, KPipeline] = {}
        self.custom_voice_cache: Dict[str, torch.FloatTensor] = {}
        self.post_processor = AudioPostProcessor()
        logging.info("Initializing Kokoro engine on %s", self.device)

    # ------------------------------------------------------------------
    @property
    def sample_rate(self) -> int:
        return DEFAULT_SAMPLE_RATE

    # ------------------------------------------------------------------
    def generate_audio(
        self,
        text: str,
        voice: str,
        lang_code: str = "a",
        speed: float = 1.0,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        output_path: Optional[Union[str, Path]] = None,
        fx_settings: Optional[VoiceFXSettings] = None,
        max_samples: Optional[int] = None,
    ) -> np.ndarray:
        """
        Public wrapper for generating a single clip.
        """
        resolved_path = Path(output_path) if output_path else None
        return self._generate_audio(
            text=text,
            voice=voice,
            lang_code=lang_code,
            speed=speed,
            sample_rate=sample_rate,
            output_path=resolved_path,
            fx_settings=fx_settings,
            max_samples=max_samples,
        )

    # ------------------------------------------------------------------
    def generate_batch(
        self,
        segments: List[Dict],
        voice_config: Dict[str, Dict],
        output_dir: Union[str, Path],
        speed: float = 1.0,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        progress_cb=None,
        chunk_cb=None,
    ) -> List[str]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_files: List[str] = []
        chunk_index = 0

        for seg_idx, segment in enumerate(segments):
            speaker = segment["speaker"]
            chunks = segment["chunks"]

            voice_info = voice_config.get(speaker) or voice_config.get(
                "default",
                {"voice": "af_heart", "lang_code": "a"},
            )
            voice = voice_info.get("voice", "af_heart")
            lang_code = voice_info.get("lang_code", "a")
            fx_settings = VoiceFXSettings.from_payload(voice_info.get("fx"))

            logging.info(
                "Processing segment %s/%s speaker %s", seg_idx + 1, len(segments), speaker
            )

            for chunk_idx, chunk_text in enumerate(chunks):
                output_path = output_dir / f"chunk_{chunk_index:04d}.wav"

                self._generate_audio(
                    text=chunk_text,
                    voice=voice,
                    lang_code=lang_code,
                    speed=speed,
                    sample_rate=sample_rate,
                    output_path=output_path,
                    fx_settings=fx_settings,
                )

                output_files.append(str(output_path))
                chunk_index += 1
                if callable(progress_cb):
                    progress_cb()
                if callable(chunk_cb):
                    chunk_meta = {
                        "speaker": speaker,
                        "text": chunk_text,
                        "segment_index": seg_idx,
                        "chunk_index": chunk_idx,
                    }
                    chunk_cb(chunk_index - 1, chunk_meta, str(output_path))

        return output_files

    # ------------------------------------------------------------------
    def cleanup(self) -> None:
        self.pipelines.clear()
        self.custom_voice_cache.clear()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # ------------------------------------------------------------------
    def _generate_audio(
        self,
        text: str,
        voice: str,
        lang_code: str = "a",
        speed: float = 1.0,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        output_path: Optional[Path] = None,
        fx_settings: Optional[VoiceFXSettings] = None,
        max_samples: Optional[int] = None,
    ) -> np.ndarray:
        pipeline = self._get_pipeline(lang_code)
        voice_input = self._resolve_voice_input(pipeline, voice, lang_code)

        generator = pipeline(text, voice=voice_input, speed=speed, split_pattern=r"\n+")

        audio_chunks: List[np.ndarray] = []
        total_samples = 0
        for _, _, audio in generator:
            audio_chunks.append(audio)
            total_samples += len(audio)
            if max_samples and total_samples >= max_samples:
                break

        if not audio_chunks:
            logging.warning("No audio generated for text chunk")
            return np.array([])

        full_audio = np.concatenate(audio_chunks)
        if max_samples and full_audio.shape[0] > max_samples:
            full_audio = full_audio[:max_samples]

        if fx_settings:
            full_audio = self.post_processor.apply(full_audio, sample_rate, fx_settings)

        if output_path:
            sf.write(str(output_path), full_audio, sample_rate)

        return full_audio

    # ------------------------------------------------------------------
    def _get_pipeline(self, lang_code: str) -> KPipeline:
        if lang_code not in self.pipelines:
            logging.info("Creating Kokoro pipeline for %s", lang_code)
            self.pipelines[lang_code] = KPipeline(lang_code=lang_code)
        return self.pipelines[lang_code]

    # ------------------------------------------------------------------
    def _resolve_voice_input(
        self, pipeline: KPipeline, voice: str, lang_code: str
    ) -> Union[str, torch.FloatTensor]:
        if not voice or not voice.startswith(CUSTOM_CODE_PREFIX):
            return voice

        cache_key = f"{lang_code}:{voice}"
        if cache_key in self.custom_voice_cache:
            return self.custom_voice_cache[cache_key]

        definition = get_custom_voice_by_code(voice)
        if not definition:
            raise ValueError(f"Custom voice '{voice}' does not exist.")

        components = definition.get("components") or []
        if not components:
            raise ValueError(f"Custom voice '{voice}' has no components.")

        blended_pack = self._blend_custom_voice(pipeline, components)
        self.custom_voice_cache[cache_key] = blended_pack
        return blended_pack

    # ------------------------------------------------------------------
    def _blend_custom_voice(self, pipeline: KPipeline, components: List) -> torch.FloatTensor:
        packs: List[torch.FloatTensor] = []
        weights: List[float] = []

        for component in components:
            comp_voice: Optional[str] = None
            weight_value: float = 1.0

            if isinstance(component, str):
                comp_voice = component.strip()
            elif isinstance(component, dict):
                comp_voice = (component.get("voice") or component.get("name") or "").strip()
                weight_value = float(
                    component.get("weight")
                    or component.get("ratio")
                    or component.get("mix")
                    or 1.0
                )
            else:
                continue

            if not comp_voice:
                continue

            pack = pipeline.load_voice(comp_voice)
            packs.append(pack)
            weights.append(max(weight_value, 0.0))

        if not packs:
            raise ValueError("No valid component voices could be loaded for blending.")

        stacked = torch.stack(packs)
        weight_tensor = torch.tensor(weights, dtype=stacked.dtype, device=stacked.device)
        total = float(weight_tensor.sum().item())
        if total <= 0:
            weight_tensor = torch.ones_like(weight_tensor)
            total = float(weight_tensor.sum().item())
        weight_tensor = weight_tensor / total

        while len(weight_tensor.shape) < len(stacked.shape):
            weight_tensor = weight_tensor.unsqueeze(-1)

        return torch.sum(stacked * weight_tensor, dim=0)

    # ------------------------------------------------------------------
    def clear_custom_voice_cache(self, voice_code: Optional[str] = None) -> int:
        if not self.custom_voice_cache:
            return 0

        if not voice_code:
            removed = len(self.custom_voice_cache)
            self.custom_voice_cache.clear()
            return removed

        suffix = f":{voice_code}"
        original = len(self.custom_voice_cache)
        self.custom_voice_cache = {
            key: value for key, value in self.custom_voice_cache.items() if not key.endswith(suffix)
        }
        return original - len(self.custom_voice_cache)

    # ------------------------------------------------------------------
    def get_device_info(self) -> Dict:
        info = {
            "device": self.device,
            "cuda_available": torch.cuda.is_available(),
        }
        if torch.cuda.is_available():
            info["cuda_device_name"] = torch.cuda.get_device_name(0)
            info["cuda_memory_allocated"] = torch.cuda.memory_allocated(0)
            info["cuda_memory_reserved"] = torch.cuda.memory_reserved(0)
        return info
