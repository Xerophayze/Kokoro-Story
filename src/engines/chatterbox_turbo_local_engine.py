"""Local Chatterbox Turbo engine powered by chatterbox-tts weights."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import soundfile as sf
import torch

from .base import EngineCapabilities, TtsEngineBase, VoiceAssignment
from ..audio_effects import AudioPostProcessor, VoiceFXSettings

logger = logging.getLogger(__name__)

CHATTERBOX_TURBO_SAMPLE_RATE = 24000

try:
    from chatterbox.tts_turbo import ChatterboxTurboTTS  # type: ignore

    CHATTERBOX_TURBO_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    CHATTERBOX_TURBO_AVAILABLE = False
    ChatterboxTurboTTS = None  # type: ignore[assignment]


class ChatterboxTurboLocalEngine(TtsEngineBase):
    """Offline-capable Chatterbox Turbo engine."""

    name = "chatterbox_turbo_local"
    capabilities = EngineCapabilities(
        supports_voice_cloning=True,
        supports_emotion_tags=True,
        supported_languages=["en"],
    )

    def __init__(
        self,
        *,
        device: str = "auto",
        default_prompt: Optional[str] = None,
        temperature: float = 0.8,
        top_p: float = 0.95,
        top_k: int = 1000,
        repetition_penalty: float = 1.2,
        cfg_weight: float = 0.0,
        exaggeration: float = 0.0,
        norm_loudness: bool = True,
        prompt_norm_loudness: bool = True,
    ):
        if not CHATTERBOX_TURBO_AVAILABLE:
            raise ImportError(
                "chatterbox-tts is not installed. Run setup.bat to install the Chatterbox Turbo runtime."
            )

        resolved_device = self._resolve_device(device)
        logger.info("Loading Chatterbox Turbo on device=%s", resolved_device)
        self._patch_s3tokenizer_prepare_audio()  # Must patch BEFORE model loads
        self._patch_prepare_conditionals()  # Patch to ensure float32 audio throughout
        self.model: ChatterboxTurboTTS = ChatterboxTurboTTS.from_pretrained(
            device=resolved_device
        )
        self._coerce_tokenizer_buffers()

        self.device = resolved_device
        self.default_prompt = self._normalize_prompt_path(default_prompt)
        self.temperature = float(temperature)
        self.top_p = float(top_p)
        self.top_k = int(top_k)
        self.repetition_penalty = float(repetition_penalty)
        self.cfg_weight = float(cfg_weight)
        self.exaggeration = float(exaggeration)
        self.norm_loudness = bool(norm_loudness)
        self.prompt_norm_loudness = bool(prompt_norm_loudness)
        self.prompt_cache: Dict[str, Path] = {}
        self.post_processor = AudioPostProcessor()

    def _patch_s3tokenizer_prepare_audio(self) -> None:
        """Patch S3Tokenizer._prepare_audio to ensure float32 tensors.

        librosa.resample() can return float64 numpy arrays. When these are
        converted to torch tensors via torch.from_numpy(), they become float64
        tensors. The s3tokenizer encoder then fails because mask_to_bias()
        asserts dtype must be float32/bfloat16/float16.

        This patch ensures all audio arrays are converted to float32 before
        becoming tensors, fixing the dtype mismatch at its source.
        """
        try:
            from chatterbox.models.s3tokenizer.s3tokenizer import S3Tokenizer
        except Exception:  # pragma: no cover - optional dependency internals
            return

        original = getattr(S3Tokenizer, "_prepare_audio", None)
        if not callable(original):
            return

        if getattr(original, "__kokoro_story_patched__", False):
            return

        import numpy as np

        def _prepare_audio_patched(self, wavs):  # type: ignore[no-untyped-def]
            """Prepare audio with forced float32 conversion."""
            processed_wavs = []
            for wav in wavs:
                if isinstance(wav, np.ndarray):
                    # Force float32 to avoid dtype issues downstream
                    wav = torch.from_numpy(wav.astype(np.float32))
                elif torch.is_tensor(wav):
                    if wav.dtype != torch.float32:
                        wav = wav.float()
                if wav.dim() == 1:
                    wav = wav.unsqueeze(0)
                processed_wavs.append(wav)
            return processed_wavs

        setattr(_prepare_audio_patched, "__kokoro_story_patched__", True)
        S3Tokenizer._prepare_audio = _prepare_audio_patched  # type: ignore[assignment]

    def _patch_prepare_conditionals(self) -> None:
        """Patch ChatterboxTurboTTS.prepare_conditionals to ensure float32 audio.

        librosa.resample() returns float64 numpy arrays. The resampled audio
        is used in two places:
        1. S3Tokenizer.forward() - handled by _patch_s3tokenizer_prepare_audio
        2. VoiceEncoder.embeds_from_wavs() - fails because LSTM expects float32

        This patch converts the resampled audio to float32 immediately after
        resampling, fixing dtype issues in both code paths.
        """
        try:
            from chatterbox.tts_turbo import ChatterboxTurboTTS
        except Exception:  # pragma: no cover - optional dependency internals
            return

        original = getattr(ChatterboxTurboTTS, "prepare_conditionals", None)
        if not callable(original):
            return

        if getattr(original, "__kokoro_story_patched__", False):
            return

        import librosa
        from chatterbox.tts_turbo import S3GEN_SR, S3_SR

        def prepare_conditionals_patched(self, wav_fpath, exaggeration=0.5, norm_loudness=True):
            """Patched prepare_conditionals with float32 audio conversion."""
            # Load and norm reference wav
            s3gen_ref_wav, _sr = librosa.load(wav_fpath, sr=S3GEN_SR)

            assert len(s3gen_ref_wav) / _sr > 5.0, "Audio prompt must be longer than 5 seconds!"

            if norm_loudness:
                s3gen_ref_wav = self.norm_loudness(s3gen_ref_wav, _sr)

            # Resample and FORCE float32 - this is the critical fix
            ref_16k_wav = librosa.resample(s3gen_ref_wav, orig_sr=S3GEN_SR, target_sr=S3_SR)
            ref_16k_wav = ref_16k_wav.astype(np.float32)  # Force float32
            s3gen_ref_wav = s3gen_ref_wav.astype(np.float32)  # Also ensure this is float32

            s3gen_ref_wav = s3gen_ref_wav[:self.DEC_COND_LEN]
            s3gen_ref_dict = self.s3gen.embed_ref(s3gen_ref_wav, S3GEN_SR, device=self.device)

            # Speech cond prompt tokens
            if plen := self.t3.hp.speech_cond_prompt_len:
                s3_tokzr = self.s3gen.tokenizer
                t3_cond_prompt_tokens, _ = s3_tokzr.forward([ref_16k_wav[:self.ENC_COND_LEN]], max_len=plen)
                t3_cond_prompt_tokens = torch.atleast_2d(t3_cond_prompt_tokens).to(self.device)

            # Voice-encoder speaker embedding
            ve_embed = torch.from_numpy(self.ve.embeds_from_wavs([ref_16k_wav], sample_rate=S3_SR))
            ve_embed = ve_embed.mean(axis=0, keepdim=True).to(self.device)

            # Import these inside the function to avoid circular imports
            from chatterbox.tts_turbo import T3Cond, Conditionals

            t3_cond = T3Cond(
                speaker_emb=ve_embed,
                cond_prompt_speech_tokens=t3_cond_prompt_tokens,
                emotion_adv=exaggeration * torch.ones(1, 1, 1),
            ).to(device=self.device)
            self.conds = Conditionals(t3_cond, s3gen_ref_dict)

        setattr(prepare_conditionals_patched, "__kokoro_story_patched__", True)
        ChatterboxTurboTTS.prepare_conditionals = prepare_conditionals_patched  # type: ignore[assignment]

    # ------------------------------------------------------------------ #
    @property
    def sample_rate(self) -> int:
        return CHATTERBOX_TURBO_SAMPLE_RATE

    # ------------------------------------------------------------------ #
    def generate_batch(
        self,
        segments: List[Dict],
        voice_config: Dict[str, Dict],
        output_dir: Path,
        speed: float = 1.0,
        sample_rate: Optional[int] = None,
        progress_cb=None,
        chunk_cb=None,
    ) -> List[str]:
        if sample_rate and sample_rate != self.sample_rate:
            logger.warning(
                "Chatterbox Turbo outputs at %s Hz. Requested sample rate %s will be resampled during merge.",
                self.sample_rate,
                sample_rate,
            )
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        files: List[str] = []
        chunk_index = 0
        for seg_idx, segment in enumerate(segments):
            speaker = segment["speaker"]
            chunks = segment["chunks"]
            assignment = self._voice_assignment_for(voice_config, speaker)
            logger.info(
                "Chatterbox Turbo segment %s/%s speaker=%s voice=%s",
                seg_idx + 1,
                len(segments),
                speaker,
                assignment.voice,
            )

            for chunk_idx, chunk_text in enumerate(chunks):
                output_path = output_dir / f"chunk_{chunk_index:04d}.wav"
                audio, sr = self._synthesize(chunk_text, assignment, speed)
                sf.write(str(output_path), audio, sr)
                files.append(str(output_path))
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
                    chunk_cb(chunk_idx, chunk_meta, str(output_path))

        return files

    # ------------------------------------------------------------------ #
    def cleanup(self) -> None:  # pragma: no cover - device cleanup
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

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
    def _synthesize(
        self,
        text: str,
        assignment: VoiceAssignment,
        speed: float,
        sample_rate: Optional[int] = None,
    ) -> Tuple[np.ndarray, int]:
        # Some upstream libraries recreate tokenizer buffers with double precision;
        # ensure we keep things in float32 before each conditioning step.
        self._ensure_tokenizer_buffers()
        prompt_path = assignment.audio_prompt_path or self.default_prompt
        reference_seconds = None
        if prompt_path:
            try:
                resolved_prompt = self._resolve_prompt_path(prompt_path)
            except FileNotFoundError:
                if assignment.audio_prompt_path:
                    raise
                logger.warning(
                    f"Default prompt '{prompt_path}' not found, proceeding without reference voice. "
                    "Add a voice in Settings or the Chatterbox Voices section."
                )
                prompt_path = None
        if prompt_path:
            reference_seconds = None
            try:
                import soundfile as _sf
                info = _sf.info(resolved_prompt)
                reference_seconds = info.frames / float(info.samplerate or 16000)
            except Exception:  # pragma: no cover - best effort warning
                reference_seconds = None
            if reference_seconds is not None and reference_seconds < 5.0:
                raise ValueError(
                    f"Reference prompt '{prompt_path}' is only {reference_seconds:.2f}s. "
                    "Chatterbox Turbo requires clips at least 5 seconds long."
                )
            self.model.prepare_conditionals(
                str(resolved_prompt),
                exaggeration=self._resolve_numeric(
                    assignment.extra, "exaggeration", self.exaggeration
                ),
                norm_loudness=self.prompt_norm_loudness,
            )
        elif self.model.conds is None:
            raise ValueError(
                "Chatterbox Turbo requires a reference audio prompt of at least 5 seconds. "
                "Specify an audio_prompt_path per speaker or set chatterbox_local_default_prompt."
            )

        params = self._resolve_generation_params(assignment.extra or {})
        wav = self.model.generate(
            text=text,
            temperature=params["temperature"],
            top_p=params["top_p"],
            top_k=params["top_k"],
            repetition_penalty=params["repetition_penalty"],
            cfg_weight=params["cfg_weight"],
            exaggeration=params["exaggeration"],
            audio_prompt_path=None,  # already prepared via prepare_conditionals
            norm_loudness=params["norm_loudness"],
        )

        audio = wav.squeeze(0).detach().cpu().numpy().astype("float32")
        fx_settings = VoiceFXSettings.from_payload(assignment.fx_payload)
        if fx_settings:
            audio = self.post_processor.apply(audio, self.sample_rate, fx_settings)

        return audio, self.sample_rate

    # ------------------------------------------------------------------ #
    @staticmethod
    def _resolve_numeric(extra: Dict, key: str, default_value: float) -> float:
        value = extra.get(key)
        if value is None:
            return default_value
        try:
            return float(value)
        except (TypeError, ValueError):
            return default_value

    # ------------------------------------------------------------------ #
    def _resolve_generation_params(self, extra: Dict) -> Dict[str, float]:
        return {
            "temperature": self._resolve_numeric(extra, "temperature", self.temperature),
            "top_p": self._resolve_numeric(extra, "top_p", self.top_p),
            "top_k": int(self._resolve_numeric(extra, "top_k", self.top_k)),
            "repetition_penalty": self._resolve_numeric(
                extra, "repetition_penalty", self.repetition_penalty
            ),
            "cfg_weight": self._resolve_numeric(extra, "cfg_weight", self.cfg_weight),
            "exaggeration": self._resolve_numeric(extra, "exaggeration", self.exaggeration),
            "norm_loudness": bool(extra.get("norm_loudness", self.norm_loudness)),
        }

    # ------------------------------------------------------------------ #
    def _resolve_device(self, device: str) -> str:
        candidate = (device or "auto").strip().lower()
        if candidate == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if candidate.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("CUDA device requested but no GPU is available.")
        return candidate

    # ------------------------------------------------------------------ #
    def _normalize_prompt_path(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        trimmed = path.strip()
        return trimmed or None

    # ------------------------------------------------------------------ #
    def _resolve_prompt_path(self, path_str: str) -> Path:
        candidate = Path(path_str)
        if candidate.is_file():
            return candidate
        fallback = Path("data/voice_prompts") / path_str
        if fallback.is_file():
            return fallback
        raise FileNotFoundError(
            f"Chatterbox Turbo reference clip not found: {path_str}. "
            "Ensure the file exists or update chatterbox_local_default_prompt."
        )

    # ------------------------------------------------------------------ #
    def _ensure_tokenizer_buffers(self) -> None:
        s3gen = getattr(self.model, "s3gen", None)
        tokenizer = getattr(s3gen, "tokenizer", None)
        if tokenizer is None:
            return
        try:
            tokenizer.float()
        except Exception:
            logger.debug("Tokenizer.float() failed; continuing with manual buffer casts", exc_info=True)
        mel_filters = getattr(tokenizer, "_mel_filters", None)
        if isinstance(mel_filters, torch.Tensor) and mel_filters.dtype != torch.float32:
            tokenizer._mel_filters = mel_filters.float()
            logger.debug("Coerced tokenizer _mel_filters to float32")
        window = getattr(tokenizer, "window", None)
        if isinstance(window, torch.Tensor) and window.dtype != torch.float32:
            tokenizer.window = window.float()
            logger.debug("Coerced tokenizer window to float32")
        # ensure internal buffers dict also updated (some versions reference _buffers directly)
        buffers = getattr(tokenizer, "_buffers", None)
        if isinstance(buffers, dict):
            buf = buffers.get("_mel_filters")
            if isinstance(buf, torch.Tensor) and buf.dtype != torch.float32:
                buffers["_mel_filters"] = buf.float()
            buf = buffers.get("window")
            if isinstance(buf, torch.Tensor) and buf.dtype != torch.float32:
                buffers["window"] = buf.float()

    def _coerce_tokenizer_buffers(self) -> None:
        """Downcast S3 tokenizer buffers to float32 to match audio tensors."""
        try:
            self._ensure_tokenizer_buffers()
        except Exception:  # pragma: no cover - defensive
            logger.debug("Unable to coerce tokenizer filter dtype", exc_info=True)


__all__ = [
    "ChatterboxTurboLocalEngine",
    "CHATTERBOX_TURBO_SAMPLE_RATE",
]
