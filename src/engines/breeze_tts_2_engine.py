"""Breeze TTS 2 adapter for voice design, cloning, and directed delivery."""
from __future__ import annotations

import gc
import hashlib
import importlib.util
import json
import logging
import os
import re
import sys
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import soundfile as sf

from .base import EngineCapabilities, TtsEngineBase, VoiceAssignment
from ..audio_effects import AudioPostProcessor, VoiceFXSettings, convert_mp3_to_wav_if_needed


logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = ROOT / "engines" / "breeze_tts_2"
RUNTIME_ROOT = ENGINE_ROOT / "runtime"
LICENSE_MARKER = ENGINE_ROOT / ".license_accepted"
VOICE_PROMPT_DIR = ROOT / "data" / "voice_prompts"
TRANSCRIPTS_FILE = VOICE_PROMPT_DIR / "transcripts.json"

if RUNTIME_ROOT.is_dir() and str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

try:
    import torch
    from transformers import AutoTokenizer
    from huggingface_hub import snapshot_download
    from qwen_tts import Qwen3TTSTokenizer
    from breeze_infer import templates as breeze_templates
    from breeze_infer.runtime import set_all_seeds, update_generation_config_for_breeze
    from models.breeze import BreezeForConditionalGeneration
    from models.fast_streaming import FastBreezeStreamingRuntime, FastStreamingConfig
    from models.warmup_profile import load_warmup_profile
    BREEZE_TTS_2_AVAILABLE = True
    BREEZE_TTS_2_IMPORT_ERROR = ""
except (ImportError, OSError) as exc:  # pragma: no cover - optional isolated dependency
    torch = None  # type: ignore[assignment]
    AutoTokenizer = Qwen3TTSTokenizer = None  # type: ignore[assignment]
    snapshot_download = None  # type: ignore[assignment]
    breeze_templates = None  # type: ignore[assignment]
    set_all_seeds = update_generation_config_for_breeze = None  # type: ignore[assignment]
    BreezeForConditionalGeneration = None  # type: ignore[assignment]
    FastBreezeStreamingRuntime = FastStreamingConfig = None  # type: ignore[assignment]
    load_warmup_profile = None  # type: ignore[assignment]
    BREEZE_TTS_2_AVAILABLE = False
    BREEZE_TTS_2_IMPORT_ERROR = str(exc)


class BreezeTTS2Engine(TtsEngineBase):
    """Official Breeze TTS 2 eager runtime hosted in an isolated process."""

    name = "breeze_tts_2"
    capabilities = EngineCapabilities(
        supports_voice_cloning=True,
        supports_emotion_tags=True,
        supported_languages=["en", "zh"],
    )

    def __init__(
        self,
        *,
        device: str = "auto",
        runtime: str = "pytorch",
        model_id: str = "BreezeBlue/Breeze-TTS-2",
        seed: int = 42,
        clone_cfg_scale: float = 1.0,
        design_cfg_scale: float = 4.0,
        direction_cfg_scale: float = 4.0,
        max_new_tokens: int = 1500,
        max_seq_len: int = 2048,
        fast_mode: bool = False,
        default_prompt: Optional[str] = None,
        default_prompt_text: Optional[str] = None,
        default_instruction: str = "Speak clearly and naturally.",
    ) -> None:
        if not LICENSE_MARKER.is_file():
            raise PermissionError(
                "Breeze TTS 2 requires acceptance of the BreezeBlue Research and "
                "Non-Commercial License in Settings."
            )
        if runtime not in {"pytorch", "q8"}:
            raise ValueError("Unknown Breeze runtime; select PyTorch or Q8 in Settings.")
        self.runtime_kind = runtime
        if runtime == "pytorch" and not BREEZE_TTS_2_AVAILABLE:
            raise ImportError(
                "Breeze TTS 2 is not installed. Install it from Settings → Engine Settings. "
                + BREEZE_TTS_2_IMPORT_ERROR
            )
        if runtime == "pytorch" and not torch.cuda.is_available():
            raise RuntimeError("The official Breeze TTS 2 runtime requires an NVIDIA CUDA GPU.")

        requested_device = str(device or "auto").strip().lower()
        self.device = "cuda:0" if requested_device == "auto" else requested_device
        if runtime == "pytorch" and not self.device.startswith("cuda"):
            raise RuntimeError("Breeze TTS 2 currently supports CUDA devices only.")
        self.dtype = "bfloat16"
        self.model_id = str(model_id or "BreezeBlue/Breeze-TTS-2").strip()
        self.seed = int(seed)
        self.clone_cfg_scale = self._positive_float(clone_cfg_scale, 1.0)
        self.design_cfg_scale = self._positive_float(design_cfg_scale, 4.0)
        self.direction_cfg_scale = self._positive_float(direction_cfg_scale, 4.0)
        self.max_new_tokens = max(64, min(int(max_new_tokens), 3000))
        self.max_seq_len = max(512, min(int(max_seq_len), 4096))
        self.fast_mode = bool(fast_mode)
        self.default_prompt = str(default_prompt or "").strip() or None
        self.default_prompt_text = str(default_prompt_text or "").strip() or None
        self.default_instruction = self._clean_instruction(default_instruction) or "Speak clearly and naturally."
        self.post_processor = AudioPostProcessor()
        self._transcripts = self._load_transcripts()
        self._reference_codes_cache: Dict[str, object] = {}

        if runtime == "q8":
            from .breeze_q8 import Q8Runtime
            self.runtime = Q8Runtime(cpu=requested_device == "cpu")
            self.dtype = "Q8_0 (mixed precision)"
            self.device = getattr(self.runtime, "backend", "vulkan")
            self._sample_rate = self.runtime.sample_rate
            return

        model_path = self._ensure_model(self.model_id)
        started = time.perf_counter()
        logger.info(
            "Loading Breeze TTS 2 model=%s device=%s mode=%s",
            self.model_id, self.device, "fast" if self.fast_mode else "eager",
        )
        self.tokenizer, self.model, self.audio_tokenizer = self._load_runtime(model_path)
        update_generation_config_for_breeze(self.model)
        config = FastStreamingConfig(
            max_new_tokens=self.max_new_tokens,
            max_seq_len=self.max_seq_len,
            # Backbone-only CUDA graphs do not require torch.compile or the
            # high-VRAM full warmup profile. Capture lazily on first synthesis.
            fast_all=True if self.fast_mode else None,
            fast_backbone_decode=True,
            repetition_penalty=1.1,
        )
        self.runtime = FastBreezeStreamingRuntime(
            self.model,
            self.audio_tokenizer,
            config,
            tokenizer=self.tokenizer,
        )
        if self.fast_mode:
            profile = load_warmup_profile(RUNTIME_ROOT / "configs" / "fast.json")
            profile = replace(profile, codec_chunk_frames=self.runtime.codec_chunk_frames)
            manifest = self.runtime.warmup_from_profile(profile)
            logger.info("Breeze fast runtime warmup completed: %s", manifest)
        self._sample_rate = int(self.runtime.sample_rate)
        logger.info("Breeze backbone decode CUDA graphs enabled; full fast mode=%s", self.fast_mode)
        self._install_reference_cache()
        logger.info(
            "Breeze TTS 2 ready sample_rate=%d load_seconds=%.2f",
            self.sample_rate, time.perf_counter() - started,
        )

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def generate_audio(
        self,
        text: str,
        audio_prompt_path: Optional[str] = None,
        prompt_text: Optional[str] = None,
        instruction: Optional[str] = None,
        delivery_instruction: Optional[str] = None,
        voice_design_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        fx_settings=None,
        **_kwargs,
    ) -> np.ndarray:
        assignment = VoiceAssignment(
            audio_prompt_path=audio_prompt_path,
            fx_payload=fx_settings,
            extra={
                "prompt_text": prompt_text or "",
                "instruction": instruction or "",
                "delivery_instruction": delivery_instruction or "",
                "voice_design_prompt": voice_design_prompt or "",
            },
        )
        return self._synthesize(self._validate_text(text), assignment, self.seed if seed is None else seed)

    def generate_batch(
        self,
        segments: List[Dict],
        voice_config: Dict[str, Dict],
        output_dir: Path,
        speed: float = 1.0,
        sample_rate: Optional[int] = None,
        progress_cb=None,
        chunk_cb=None,
        parallel_workers: int = 1,
        group_by_speaker: bool = False,
    ) -> List[str]:
        del speed, sample_rate, parallel_workers
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        # Reference encodings are cached per speaker, so chronological segment
        # order can be retained even when the global group-by-speaker option is on.
        del group_by_speaker
        ordered_segments = list(segments)

        total = sum(len(segment.get("chunks") or []) for segment in ordered_segments)
        files: List[Optional[str]] = [None] * total
        order = 0
        for segment_index, segment in enumerate(ordered_segments):
            speaker = segment.get("speaker") or "default"
            assignment = self._voice_assignment_for(voice_config, speaker)
            emotion = self._clean_instruction(
                segment.get("delivery_instruction") or segment.get("emotion") or ""
            )
            if emotion:
                assignment.extra = {**(assignment.extra or {}), "delivery_instruction": emotion}
            speaker_seed = self._speaker_seed(speaker)
            for local_index, chunk_text in enumerate(segment.get("chunks") or []):
                output_path = output_dir / f"chunk_{order:06d}.wav"
                audio = self._synthesize(self._validate_text(chunk_text), assignment, speaker_seed)
                sf.write(str(output_path), audio, self.sample_rate)
                files[order] = str(output_path)
                metadata = {
                    "speaker": speaker,
                    "text": chunk_text,
                    "emotion": emotion or None,
                    "delivery_instruction": emotion or None,
                    "segment_index": segment_index,
                    "chunk_index": local_index,
                    "order_index": order,
                }
                if callable(progress_cb):
                    progress_cb()
                if callable(chunk_cb):
                    chunk_cb(local_index, metadata, str(output_path))
                order += 1
        return [path for path in files if path]

    def _synthesize(self, text: str, assignment: VoiceAssignment, seed: int) -> np.ndarray:
        started = time.perf_counter()
        extra = assignment.extra or {}
        prompt = assignment.audio_prompt_path or self.default_prompt
        transcript = str(extra.get("prompt_text") or self.default_prompt_text or "").strip()
        direction = self._clean_instruction(
            extra.get("delivery_instruction") or extra.get("instruction") or ""
        )
        design = self._clean_instruction(extra.get("voice_design_prompt") or "")
        instruction = direction or design or self.default_instruction
        temporary_conversion = None
        temporary_prompt = None
        fx = VoiceFXSettings.from_payload(assignment.fx_payload)
        output_fx = fx
        try:
            if prompt:
                prompt = self._resolve_prompt(prompt)
                if not transcript:
                    transcript = self._transcript_for(Path(prompt))
                if not transcript:
                    raise ValueError(
                        f"Breeze TTS 2 requires an exact transcript for reference voice "
                        f"'{Path(prompt).name}'. Add or generate it in Available Voices first."
                    )
                prompt, temporary_conversion = convert_mp3_to_wav_if_needed(prompt)
                if fx:
                    temporary_prompt = self.post_processor.prepare_prompt_audio(prompt, fx)
                    if temporary_prompt:
                        prompt = str(temporary_prompt)
                        output_fx = (
                            VoiceFXSettings(pitch_semitones=0.0, speed=1.0, tone=fx.tone)
                            if fx.tone != "neutral" else None
                        )

            request_id = f"tts-story-{uuid.uuid4().hex}"
            request = {
                "id": request_id,
                "text": text,
                "instruction": instruction,
                "speaker": "S0",
            }
            template_name = "tts_instruction"
            cfg_scale = self.design_cfg_scale
            mode = "design"
            if prompt:
                request["ref_audio_path"] = str(prompt)
                request["ref_text"] = transcript
                template_name = "ref_edit_tata"
                cfg_scale = self.direction_cfg_scale if direction else self.clone_cfg_scale
                mode = "direction" if direction else "clone"

            if self.runtime_kind == "q8":
                audio = self.runtime.generate(
                    text, instruction, prompt, transcript, cfg_scale, int(seed), self.max_new_tokens,
                )
                processed = self.post_processor.apply_post_pipeline(audio, self.sample_rate, output_fx)
                logger.info(
                    "Breeze Q8 mode=%s chars=%d audio_seconds=%.2f elapsed_seconds=%.2f",
                    mode, len(text), len(processed) / self.sample_rate, time.perf_counter() - started,
                )
                return np.asarray(processed, dtype=np.float32)

            set_all_seeds(int(seed))
            inputs = breeze_templates.prepare_inputs(
                self.tokenizer,
                self.audio_tokenizer,
                self.model,
                [request],
                breeze_templates.get_template(template_name),
                guidance_scale=cfg_scale,
                guidance_scale_ref=None,
                guidance_scale_ins=None,
            )
            chunks = [
                np.asarray(chunk.audio, dtype=np.float32).reshape(-1)
                for chunk in self.runtime.iter_audio_chunks(inputs, request_id=request_id)
                if np.asarray(chunk.audio).size
            ]
            if not chunks:
                raise RuntimeError("Breeze TTS 2 returned no audio.")
            audio = np.concatenate(chunks)
            processed = self.post_processor.apply_post_pipeline(audio, self.sample_rate, output_fx)
            logger.info(
                "Breeze synthesis mode=%s chars=%d instruction_chars=%d audio_seconds=%.2f "
                "elapsed_seconds=%.2f rtf=%.3f",
                mode, len(text), len(instruction), len(processed) / float(self.sample_rate),
                time.perf_counter() - started,
                (time.perf_counter() - started) / max(len(processed) / float(self.sample_rate), 0.001),
            )
            return np.asarray(processed, dtype=np.float32)
        finally:
            if temporary_prompt:
                Path(temporary_prompt).unlink(missing_ok=True)
            if temporary_conversion:
                Path(temporary_conversion).unlink(missing_ok=True)

    def _install_reference_cache(self) -> None:
        original = breeze_templates._encode_prompt_audio

        def cached(audio_tokenizer, audio_path: str):
            path = Path(audio_path)
            stat = path.stat()
            key = hashlib.sha256(
                f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
            ).hexdigest()
            if key not in self._reference_codes_cache:
                self._reference_codes_cache[key] = original(audio_tokenizer, audio_path)
                logger.info(
                    "Breeze reference encoded and cached file=%s cache_entries=%d",
                    path.name, len(self._reference_codes_cache),
                )
            else:
                logger.info("Breeze reference cache hit file=%s", path.name)
            return self._reference_codes_cache[key]

        breeze_templates._encode_prompt_audio = cached

    def _ensure_model(self, model_id: str) -> Path:
        models_root = Path(
            str(Path.cwd() / "engines" / "breeze_tts_2" / "models")
        )
        configured_root = Path(str(os.environ.get("TTS_STORY_ENGINE_MODEL_ROOT") or models_root))
        target = configured_root / "Breeze-TTS-2"
        if not (target / "config.json").is_file():
            target.mkdir(parents=True, exist_ok=True)
            logger.info("Downloading Breeze TTS 2 model=%s to %s", model_id, target)
            snapshot_download(repo_id=model_id, local_dir=str(target))
        return target

    def _load_runtime(self, model_path: Path):
        """Load Breeze without requiring the checkpoint's optional FlashAttention default."""
        text_encoder_attention = (
            "flash_attention_2" if importlib.util.find_spec("flash_attn") is not None else "eager"
        )
        model_config = BreezeForConditionalGeneration.config_class.from_pretrained(model_path)
        text_encoder_config = getattr(model_config, "text_encoder_config", None)
        if text_encoder_config is not None:
            text_encoder_config.preferred_attn_implementation = text_encoder_attention
            text_encoder_config._attn_implementation = text_encoder_attention
        logger.info(
            "Breeze attention backends: main=eager text_encoder=%s flash_attn_installed=%s",
            text_encoder_attention,
            text_encoder_attention == "flash_attention_2",
        )
        tokenizer = AutoTokenizer.from_pretrained(model_path)
        model = BreezeForConditionalGeneration.from_pretrained(
            model_path,
            config=model_config,
            dtype=torch.bfloat16,
            attn_implementation="eager",
        )
        model.to(self.device).eval()
        bundled_audio_tokenizer = model_path / "audio_tokenizer"
        if not bundled_audio_tokenizer.is_dir():
            raise FileNotFoundError(
                f"Bundled audio tokenizer not found at {bundled_audio_tokenizer}. "
                "Repair the Breeze TTS 2 installation."
            )
        audio_tokenizer = Qwen3TTSTokenizer.from_pretrained(
            str(bundled_audio_tokenizer), device_map=self.device
        )
        return tokenizer, model, audio_tokenizer

    @staticmethod
    def _positive_float(value, fallback: float) -> float:
        try:
            result = float(value)
            return result if result > 0 else fallback
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _clean_instruction(value) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def _validate_text(text: str) -> str:
        value = re.sub(r"\s+", " ", str(text or "")).strip()
        if not value:
            raise ValueError("Breeze TTS 2 cannot synthesize empty text.")
        return value

    def _speaker_seed(self, speaker: str) -> int:
        digest = hashlib.sha256(str(speaker).encode("utf-8")).digest()
        return (self.seed + int.from_bytes(digest[:4], "big")) % 2147483647

    @staticmethod
    def _voice_assignment_for(config: Dict[str, Dict], speaker: str) -> VoiceAssignment:
        payload = config.get(speaker) or config.get("default") or {}
        return VoiceAssignment(
            voice=payload.get("voice"),
            lang_code=payload.get("lang_code"),
            audio_prompt_path=payload.get("audio_prompt_path"),
            fx_payload=payload.get("fx"),
            speed_override=payload.get("speed"),
            extra=payload.get("extra") or {},
        )

    @staticmethod
    def _resolve_prompt(value: str) -> str:
        path = Path(value)
        if not path.is_file():
            path = VOICE_PROMPT_DIR / Path(value).name
        if not path.is_file():
            raise FileNotFoundError(f"Breeze reference voice not found: {value}")
        return str(path)

    def _transcript_for(self, path: Path) -> str:
        try:
            stat = path.stat()
            library_key = hashlib.md5(
                f"{path.name}:{stat.st_size}:{stat.st_mtime}".encode()
            ).hexdigest()[:16]
        except OSError:
            library_key = ""
        names = [library_key, path.name, path.stem, str(path.resolve())]
        for name in names:
            value = self._transcripts.get(name)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                transcript = str(value.get("transcript") or value.get("text") or "").strip()
                if transcript:
                    return transcript
        return ""

    @staticmethod
    def _load_transcripts() -> Dict:
        try:
            with TRANSCRIPTS_FILE.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                return {}
            transcripts = payload.get("transcripts")
            return transcripts if isinstance(transcripts, dict) else payload
        except (OSError, ValueError):
            return {}

    def cleanup(self) -> None:
        if getattr(self, "runtime_kind", "pytorch") == "q8" and hasattr(self, "runtime"):
            self.runtime.close()
        self._reference_codes_cache.clear()
        for name in ("runtime", "audio_tokenizer", "model", "tokenizer"):
            if hasattr(self, name):
                delattr(self, name)
        gc.collect()
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()
