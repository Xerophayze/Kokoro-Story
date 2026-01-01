"""
TTS Engine - Local GPU inference using Kokoro
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

import numpy as np
import soundfile as sf
import torch

try:
    from kokoro import KPipeline
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False
    logging.warning("Kokoro not installed. Local TTS will not be available.")

from .audio_effects import AudioPostProcessor, VoiceFXSettings
from .custom_voice_store import CUSTOM_CODE_PREFIX, get_custom_voice_by_code

DEFAULT_SAMPLE_RATE = 24000


class TTSEngine:
    """Local TTS engine using Kokoro"""
    
    def __init__(self, device: str = "auto"):
        """
        Initialize TTS engine
        
        Args:
            device: Device to use ("cuda", "cpu", or "auto")
        """
        if not KOKORO_AVAILABLE:
            raise ImportError("Kokoro is not installed. Run: pip install kokoro>=0.9.4")
            
        # Determine device
        if device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
            
        logging.info(f"Initializing TTS engine on {self.device}")
        
        # Initialize pipeline and custom voice caches
        self.pipelines: Dict[str, KPipeline] = {}
        self.custom_voice_cache: Dict[str, torch.FloatTensor] = {}
        self.post_processor = AudioPostProcessor()
        
    def _get_pipeline(self, lang_code: str) -> KPipeline:
        """
        Get or create pipeline for language
        
        Args:
            lang_code: Language code
            
        Returns:
            KPipeline instance
        """
        if lang_code not in self.pipelines:
            logging.info(f"Creating pipeline for lang_code: {lang_code}")
            self.pipelines[lang_code] = KPipeline(lang_code=lang_code)
            
        return self.pipelines[lang_code]
        
    def generate_audio(
        self,
        text: str,
        voice: str,
        lang_code: str = "a",
        speed: float = 1.0,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        output_path: Optional[str] = None,
        fx_settings: Optional[VoiceFXSettings] = None,
        max_samples: Optional[int] = None,
    ) -> np.ndarray:
        """
        Generate audio from text
        
        Args:
            text: Input text
            voice: Voice name (e.g., "af_heart")
            lang_code: Language code (default: "a")
            speed: Speech speed (default: 1.0)
            output_path: Optional path to save audio file
            
        Returns:
            Audio array (numpy)
        """
        pipeline = self._get_pipeline(lang_code)
        voice_input = self._resolve_voice_input(pipeline, voice, lang_code)
        
        # Generate audio
        logging.info(f"Generating audio: voice={voice}, lang={lang_code}, speed={speed}")
        
        generator = pipeline(
            text,
            voice=voice_input,
            speed=speed,
            split_pattern=r'\n+'
        )
        
        # Collect all audio chunks
        audio_chunks = []
        total_samples = 0
        for i, (gs, ps, audio) in enumerate(generator):
            logging.debug(f"Chunk {i}: {len(audio)} samples")
            audio_chunks.append(audio)
            total_samples += len(audio)
            if max_samples and max_samples > 0 and total_samples >= max_samples:
                break
            
        # Concatenate chunks
        if len(audio_chunks) == 0:
            logging.warning("No audio generated")
            return np.array([])
            
        full_audio = np.concatenate(audio_chunks)
        
        if max_samples and max_samples > 0 and full_audio.shape[0] > max_samples:
            full_audio = full_audio[:max_samples]

        # Save if output path provided
        if fx_settings:
            full_audio = self.post_processor.apply(full_audio, sample_rate, fx_settings)
        
        if output_path:
            sf.write(output_path, full_audio, sample_rate)
            logging.info(f"Audio saved to {output_path}")
        
        return full_audio
        
    def generate_batch(
        self,
        segments: List[Dict],
        voice_config: Dict[str, Dict],
        output_dir: str,
        speed: float = 1.0,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        progress_cb=None,
    ) -> List[str]:
        """
        Generate audio for multiple segments
        
        Args:
            segments: List of segments with 'speaker', 'text', 'chunks'
            voice_config: Dict mapping speaker IDs to voice configs
            output_dir: Directory to save audio files
            speed: Speech speed
            
        Returns:
            List of output file paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_files = []
        chunk_index = 0
        
        for seg_idx, segment in enumerate(segments):
            speaker = segment["speaker"]
            chunks = segment["chunks"]
            
            # Get voice config for this speaker
            voice_info = voice_config.get(speaker)
            if not voice_info:
                voice_info = voice_config.get("default", {
                    "voice": "af_heart",
                    "lang_code": "a"
                })
            voice_info = voice_info or {
                "voice": "af_heart",
                "lang_code": "a"
            }
            
            voice = voice_info["voice"]
            lang_code = voice_info["lang_code"]
            fx_settings = VoiceFXSettings.from_payload(voice_info.get("fx"))
            
            logging.info(f"Processing segment {seg_idx + 1}/{len(segments)}: "
                        f"speaker={speaker}, chunks={len(chunks)}")
            
            # Generate audio for each chunk
            for chunk_idx, chunk_text in enumerate(chunks):
                output_path = output_dir / f"chunk_{chunk_index:04d}.wav"
                
                try:
                    self.generate_audio(
                        text=chunk_text,
                        voice=voice,
                        lang_code=lang_code,
                        speed=speed,
                        sample_rate=sample_rate,
                        output_path=str(output_path),
                        fx_settings=fx_settings,
                    )
                    
                    output_files.append(str(output_path))
                    chunk_index += 1
                    if callable(progress_cb):
                        progress_cb()
                    
                except Exception as e:
                    logging.error(f"Error generating chunk {chunk_index}: {e}")
                    raise
                    
        logging.info(f"Generated {len(output_files)} audio files")
        return output_files

    def _resolve_voice_input(
        self,
        pipeline: KPipeline,
        voice: str,
        lang_code: str
    ) -> Union[str, torch.FloatTensor]:
        """
        Resolve incoming voice identifier into either a Kokoro voice string or a blended tensor.

        Returns:
            Union[str, torch.FloatTensor]: A standard voice name or a blended embedding tensor.
        """
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

    def _blend_custom_voice(
        self,
        pipeline: KPipeline,
        components: List[Union[str, Dict[str, Union[str, float]]]]
    ) -> torch.FloatTensor:
        """
        Blend multiple Kokoro voices into a single embedding tensor.

        Args:
            pipeline: Active KPipeline for the appropriate language.
            components: Sequence of component voice definitions. Each component can be a
                plain string (voice name) or a dict containing:
                    - voice (required): Kokoro base voice ID (e.g., af_heart)
                    - weight/ratio (optional): Relative mix ratio (defaults to 1.0)

        Returns:
            torch.FloatTensor: Blended voice pack tensor.
        """
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

            try:
                pack = pipeline.load_voice(comp_voice)
            except Exception as exc:
                raise ValueError(f"Failed to load component voice '{comp_voice}': {exc}") from exc

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

        # Reshape weights for broadcasting across embedding dimensions
        while len(weight_tensor.shape) < len(stacked.shape):
            weight_tensor = weight_tensor.unsqueeze(-1)

        blended = torch.sum(stacked * weight_tensor, dim=0)
        return blended
        
    def cleanup(self):
        """Clean up resources"""
        self.pipelines.clear()
        self.custom_voice_cache.clear()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
    def get_device_info(self) -> Dict:
        """Get device information"""
        info = {
            "device": self.device,
            "cuda_available": torch.cuda.is_available()
        }
        
        if torch.cuda.is_available():
            info["cuda_device_name"] = torch.cuda.get_device_name(0)
            info["cuda_memory_allocated"] = torch.cuda.memory_allocated(0)
            info["cuda_memory_reserved"] = torch.cuda.memory_reserved(0)
            
        return info

    def clear_custom_voice_cache(self, voice_code: Optional[str] = None) -> int:
        """
        Remove cached blended tensors for all or specific custom voices.

        Args:
            voice_code: Optional custom voice code (e.g., "custom_<id>").
                When omitted, the entire cache is cleared.

        Returns:
            int: Number of cache entries removed.
        """
        if not self.custom_voice_cache:
            return 0

        if not voice_code:
            removed = len(self.custom_voice_cache)
            self.custom_voice_cache.clear()
            return removed

        suffix = f":{voice_code}"
        original = len(self.custom_voice_cache)
        self.custom_voice_cache = {
            key: value for key, value in self.custom_voice_cache.items()
            if not key.endswith(suffix)
        }
        return original - len(self.custom_voice_cache)
