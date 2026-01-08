"""
Audio Merger - Combines audio chunks into single file
"""
import logging
import os
from pathlib import Path
from typing import List, Optional
from pydub import AudioSegment
import soundfile as sf
import numpy as np


class AudioMerger:
    """Merges audio files with crossfade and optional silence controls"""
    
    def __init__(
        self,
        crossfade_ms: int = 100,
        intro_silence_ms: int = 0,
        inter_chunk_silence_ms: int = 0,
        bitrate_kbps: Optional[int] = None,
    ):
        """
        Initialize audio merger
        
        Args:
            crossfade_ms: Crossfade duration in milliseconds
            intro_silence_ms: Silence to prepend before the first chunk
            inter_chunk_silence_ms: Silence inserted between sequential chunks
        """
        self.crossfade_ms = crossfade_ms
        self.intro_silence_ms = max(0, intro_silence_ms)
        self.inter_chunk_silence_ms = max(0, inter_chunk_silence_ms)
        self.bitrate_kbps = None
        if bitrate_kbps:
            self.bitrate_kbps = max(32, min(int(bitrate_kbps), 512))
        
    def merge_wav_files(
        self,
        input_files: List[str],
        output_path: str,
        format: str = "mp3",
        cleanup_chunks: bool = True
    ) -> str:
        """
        Merge WAV files using pydub
        
        Args:
            input_files: List of input WAV file paths
            output_path: Output file path
            format: Output format ("mp3", "wav", "ogg")
            cleanup_chunks: Whether to delete WAV chunks after merging
            
        Returns:
            Path to merged audio file
        """
        if not input_files:
            raise ValueError("No input files provided")
            
        logging.info(f"Merging {len(input_files)} audio files")
        
        # Load first file
        combined = AudioSegment.from_wav(input_files[0])
        if self.intro_silence_ms > 0:
            combined = AudioSegment.silent(duration=self.intro_silence_ms) + combined
        
        # Add remaining files with crossfade
        total_files = len(input_files)
        for i, file_path in enumerate(input_files[1:], 1):
            logging.debug(f"Adding file {i}/{len(input_files) - 1}")
            next_audio = AudioSegment.from_wav(file_path)
            
            if self.crossfade_ms > 0:
                combined = combined.append(next_audio, crossfade=self.crossfade_ms)
            else:
                combined = combined + next_audio
            
            if self.inter_chunk_silence_ms > 0 and i < total_files - 1:
                combined += AudioSegment.silent(duration=self.inter_chunk_silence_ms)
                
        # Export
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        export_kwargs = {}
        if self.bitrate_kbps and format.lower() == "mp3":
            export_kwargs["bitrate"] = f"{self.bitrate_kbps}k"
        combined.export(str(output_path), format=format, **export_kwargs)
        logging.info(f"Merged audio saved to {output_path}")
        
        # Cleanup WAV chunks if requested
        if cleanup_chunks:
            logging.info(f"Cleaning up {len(input_files)} WAV chunks")
            for file_path in input_files:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logging.debug(f"Deleted chunk: {file_path}")
                except Exception as e:
                    logging.warning(f"Failed to delete chunk {file_path}: {e}")
            logging.info("Cleanup complete")
        
        return str(output_path)
        
    def merge_numpy_arrays(
        self,
        audio_arrays: List[np.ndarray],
        sample_rate: int = 24000,
        output_path: str = None
    ) -> np.ndarray:
        """
        Merge numpy audio arrays
        
        Args:
            audio_arrays: List of audio arrays
            sample_rate: Sample rate
            output_path: Optional output path
            
        Returns:
            Merged audio array
        """
        if not audio_arrays:
            raise ValueError("No audio arrays provided")
            
        logging.info(f"Merging {len(audio_arrays)} audio arrays")
        
        # Simple concatenation for numpy arrays
        merged = np.concatenate(audio_arrays)
        
        # Save if output path provided
        if output_path:
            sf.write(output_path, merged, sample_rate)
            logging.info(f"Merged audio saved to {output_path}")
            
        return merged
        
    def convert_format(
        self,
        input_path: str,
        output_path: str,
        format: str = "mp3",
        bitrate: str = "192k"
    ):
        """
        Convert audio file format
        
        Args:
            input_path: Input file path
            output_path: Output file path
            format: Output format
            bitrate: Bitrate for compressed formats
        """
        logging.info(f"Converting {input_path} to {format}")
        
        audio = AudioSegment.from_file(input_path)
        audio.export(
            output_path,
            format=format,
            bitrate=bitrate
        )
        
        logging.info(f"Converted audio saved to {output_path}")
        
    def get_duration(self, file_path: str) -> float:
        """
        Get audio duration in seconds
        
        Args:
            file_path: Audio file path
            
        Returns:
            Duration in seconds
        """
        audio = AudioSegment.from_file(file_path)
        return len(audio) / 1000.0
        
    def normalize_audio(
        self,
        input_path: str,
        output_path: str,
        target_dBFS: float = -20.0
    ):
        """
        Normalize audio levels
        
        Args:
            input_path: Input file path
            output_path: Output file path
            target_dBFS: Target loudness in dBFS
        """
        logging.info(f"Normalizing audio to {target_dBFS} dBFS")
        
        audio = AudioSegment.from_file(input_path)
        
        # Calculate change needed
        change_in_dBFS = target_dBFS - audio.dBFS
        
        # Apply normalization
        normalized = audio.apply_gain(change_in_dBFS)
        
        # Export
        normalized.export(output_path, format="wav")
        logging.info(f"Normalized audio saved to {output_path}")
