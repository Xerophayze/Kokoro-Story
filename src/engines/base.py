"""
Common abstractions for pluggable TTS engines.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class EngineCapabilities:
    """Describes the features supported by a TTS engine implementation."""

    supports_voice_cloning: bool = False
    supports_emotion_tags: bool = False
    supported_languages: Optional[List[str]] = None


@dataclass
class VoiceAssignment:
    """Normalized per-speaker configuration coming from the UI."""

    voice: Optional[str] = None
    lang_code: Optional[str] = None
    audio_prompt_path: Optional[str] = None
    fx_payload: Optional[Dict] = None
    speed_override: Optional[float] = None
    extra: Dict = field(default_factory=dict)


class TtsEngineBase(ABC):
    """Base class that every engine adapter must implement."""

    name: str
    capabilities: EngineCapabilities

    def __init__(self, device: str = "auto"):
        self.device = device

    @property
    @abstractmethod
    def sample_rate(self) -> int:
        """Return the native sample rate of generated audio."""

    @abstractmethod
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
        """
        Render a list of text segments to individual WAV files.

        Returns the file paths that were written in chronological order.
        """

    @abstractmethod
    def cleanup(self) -> None:
        """Release cached models / GPU memory."""
