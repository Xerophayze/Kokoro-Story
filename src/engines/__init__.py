"""TTS engine implementations with lazy compatibility exports.

Importing the package should not initialize every optional local model runtime.
The application imports concrete adapters from their modules; ``__getattr__``
keeps older ``from src.engines import KokoroEngine`` usage compatible.
"""
from importlib import import_module

from .base import EngineCapabilities, TtsEngineBase


_LAZY_EXPORTS = {
    "KokoroEngine": (".kokoro_engine", "KokoroEngine"),
    "ChatterboxEngine": (".chatterbox_engine", "ChatterboxEngine"),
    "ChatterboxTurboLocalEngine": (".chatterbox_turbo_local_engine", "ChatterboxTurboLocalEngine"),
    "VoxCPMLocalEngine": (".voxcpm_local_engine", "VoxCPMLocalEngine"),
    "Qwen3CustomVoiceEngine": (".qwen3_custom_voice_engine", "Qwen3CustomVoiceEngine"),
    "Qwen3VoiceCloneEngine": (".qwen3_voice_clone_engine", "Qwen3VoiceCloneEngine"),
    "PocketTTSEngine": (".pocket_tts_engine", "PocketTTSEngine"),
    "KittenTTSEngine": (".kitten_tts_engine", "KittenTTSEngine"),
    "AzureSpeechEngine": (".azure_speech_engine", "AzureSpeechEngine"),
    "EdgeTTSEngine": (".edge_tts_engine", "EdgeTTSEngine"),
    "ElevenLabsEngine": (".elevenlabs_engine", "ElevenLabsEngine"),
    "OpenAITTSEngine": (".openai_tts_engine", "OpenAITTSEngine"),
    "LocalAITTSEngine": (".localai_tts_engine", "LocalAITTSEngine"),
    "BreezeAPIEngine": (".breeze_api_engine", "BreezeAPIEngine"),
    "Audio8TTSEngine": (".audio8_tts_engine", "Audio8TTSEngine"),
    "BreezeTTS2Engine": (".breeze_tts_2_engine", "BreezeTTS2Engine"),
}


def __getattr__(name):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute_name = target
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value

__all__ = [
    "TtsEngineBase",
    "EngineCapabilities",
    "KokoroEngine",
    "ChatterboxEngine",
    "ChatterboxTurboLocalEngine",
    "VoxCPMLocalEngine",
    "Qwen3CustomVoiceEngine",
    "Qwen3VoiceCloneEngine",
    "PocketTTSEngine",
    "KittenTTSEngine",
    "AzureSpeechEngine",
    "EdgeTTSEngine",
    "ElevenLabsEngine",
    "OpenAITTSEngine",
    "LocalAITTSEngine",
    "Audio8TTSEngine",
    "BreezeTTS2Engine",
]
