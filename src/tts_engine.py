"""
TTS Engine - Local GPU inference using Kokoro
"""
import torch
import soundfile as sf
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional
import logging

try:
    from kokoro import KPipeline
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False
    logging.warning("Kokoro not installed. Local TTS will not be available.")


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
        
        # Initialize pipeline cache
        self.pipelines = {}
        
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
        output_path: Optional[str] = None
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
        
        # Generate audio
        logging.info(f"Generating audio: voice={voice}, lang={lang_code}, speed={speed}")
        
        generator = pipeline(
            text,
            voice=voice,
            speed=speed,
            split_pattern=r'\n+'
        )
        
        # Collect all audio chunks
        audio_chunks = []
        for i, (gs, ps, audio) in enumerate(generator):
            logging.debug(f"Chunk {i}: {len(audio)} samples")
            audio_chunks.append(audio)
            
        # Concatenate chunks
        if len(audio_chunks) == 0:
            logging.warning("No audio generated")
            return np.array([])
            
        full_audio = np.concatenate(audio_chunks)
        
        # Save if output path provided
        if output_path:
            sf.write(output_path, full_audio, 24000)
            logging.info(f"Audio saved to {output_path}")
            
        return full_audio
        
    def generate_batch(
        self,
        segments: List[Dict],
        voice_config: Dict[str, Dict],
        output_dir: str,
        speed: float = 1.0
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
            voice_info = voice_config.get(speaker, {
                "voice": "af_heart",
                "lang_code": "a"
            })
            
            voice = voice_info["voice"]
            lang_code = voice_info["lang_code"]
            
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
                        output_path=str(output_path)
                    )
                    
                    output_files.append(str(output_path))
                    chunk_index += 1
                    
                except Exception as e:
                    logging.error(f"Error generating chunk {chunk_index}: {e}")
                    raise
                    
        logging.info(f"Generated {len(output_files)} audio files")
        return output_files
        
    def cleanup(self):
        """Clean up resources"""
        self.pipelines.clear()
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
