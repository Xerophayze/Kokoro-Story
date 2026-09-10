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
from .engines.omnivoice_clone_engine import OmniVoiceCloneEngine
from .engines.omnivoice_design_engine import OmniVoiceDesignEngine
from .engines.pocket_tts_engine import PocketTTSEngine
from .engines.kitten_tts_engine import KittenTTSEngine
from .engines.index_tts_engine import IndexTTSEngine, INDEX_TTS_AVAILABLE, INDEX_TTS_UNAVAILABLE_REASON
from .engines.dots_tts_engine import DotsTTSEngine, DOTS_TTS_AVAILABLE, DOTS_TTS_UNAVAILABLE_REASON
from .engines.chatterbox_turbo_replicate_engine import ChatterboxTurboReplicateEngine
from .engines.azure_speech_engine import AzureSpeechEngine
from .engines.edge_tts_engine import EdgeTTSEngine
from .engines.elevenlabs_engine import ElevenLabsEngine
from .engines.openai_tts_engine import OpenAITTSEngine
from .engines.localai_tts_engine import LocalAITTSEngine
from .engines.breeze_api_engine import BreezeAPIEngine
from .engines.isolated_proxy import ENGINE_DIRS, IsolatedEngineProxy
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
    "pocket_tts": PocketTTSEngine,
    "pocket_tts_preset": PocketTTSEngine,
    "qwen3_custom": Qwen3CustomVoiceEngine,
    "qwen3_clone": Qwen3VoiceCloneEngine,
    "omnivoice_clone": OmniVoiceCloneEngine,
    "omnivoice_design": OmniVoiceDesignEngine,
    "kitten_tts": KittenTTSEngine,
    "index_tts": IndexTTSEngine,
    "dots_tts": DotsTTSEngine,
    "azure_speech": AzureSpeechEngine,
    "edge_tts": EdgeTTSEngine,
    "elevenlabs": ElevenLabsEngine,
    "openai_tts": OpenAITTSEngine,
    "localai_tts": LocalAITTSEngine,
    "breeze_api": BreezeAPIEngine,
    "audio8_tts": IsolatedEngineProxy,
    "breeze_tts_2": IsolatedEngineProxy,
}
AVAILABLE_ENGINES = tuple(EngineRegistry.keys())


class TTSEngine(IsolatedEngineProxy):
    """
    Temporary wrapper preserving the previous class name.

    Once the multi-engine selection is fully wired, callers should import the
    desired engine explicitly or use a factory exposed by this module.
    """

    def __init__(self, **kwargs):
        super().__init__("kokoro", **kwargs)


def get_engine(engine_name: str = "kokoro", **kwargs) -> TtsEngineBase:
    """
    Factory helper to instantiate a specific engine implementation.
    """
    if engine_name in ENGINE_DIRS:
        return IsolatedEngineProxy(engine_name, **kwargs)
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
    "IndexTTSEngine",
    "INDEX_TTS_AVAILABLE",
    "INDEX_TTS_UNAVAILABLE_REASON",
    "DotsTTSEngine",
    "DOTS_TTS_AVAILABLE",
    "DOTS_TTS_UNAVAILABLE_REASON",
]
