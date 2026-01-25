"""
Compatibility layer for legacy imports while the engine abstraction is introduced.
"""
from __future__ import annotations

from typing import Dict, Type

from .engines import TtsEngineBase
from .engines.chatterbox_turbo_local_engine import ChatterboxTurboLocalEngine
from .engines.voxcpm_local_engine import VoxCPMLocalEngine
from .engines.qwen3_custom_voice_engine import Qwen3CustomVoiceEngine
from .engines.qwen3_voice_clone_engine import Qwen3VoiceCloneEngine
from .engines.chatterbox_turbo_replicate_engine import ChatterboxTurboReplicateEngine
from .engines.kokoro_engine import (
    DEFAULT_SAMPLE_RATE,
    KOKORO_AVAILABLE,
    KokoroEngine,
)
from .replicate_api import ReplicateAPI

EngineRegistry: Dict[str, Type[TtsEngineBase]] = {
    "kokoro": KokoroEngine,
    "kokoro_replicate": ReplicateAPI,
    "chatterbox_turbo_local": ChatterboxTurboLocalEngine,
    "chatterbox_turbo_replicate": ChatterboxTurboReplicateEngine,
    "voxcpm_local": VoxCPMLocalEngine,
    "qwen3_custom": Qwen3CustomVoiceEngine,
    "qwen3_clone": Qwen3VoiceCloneEngine,
}
AVAILABLE_ENGINES = tuple(EngineRegistry.keys())


class TTSEngine(KokoroEngine):
    """
    Temporary wrapper preserving the previous class name.

    Once the multi-engine selection is fully wired, callers should import the
    desired engine explicitly or use a factory exposed by this module.
    """

    pass


def get_engine(engine_name: str = "kokoro", **kwargs) -> TtsEngineBase:
    """
    Factory helper to instantiate a specific engine implementation.
    """
    engine_cls = EngineRegistry.get(engine_name)
    if not engine_cls:
        raise ValueError(f"Unknown TTS engine: {engine_name}")
    return engine_cls(**kwargs)


__all__ = [
    "TTSEngine",
    "KokoroEngine",
    "KOKORO_AVAILABLE",
    "DEFAULT_SAMPLE_RATE",
    "get_engine",
    "AVAILABLE_ENGINES",
]
