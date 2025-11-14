"""
Voice Manager - Handles voice configurations, mappings, and preview samples.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Dict


LANGUAGE_LABELS = {
    "american_english": "American English",
    "british_english": "British English",
    "spanish": "Spanish",
    "french": "French",
    "hindi": "Hindi",
    "japanese": "Japanese",
    "chinese": "Chinese",
    "brazilian_portuguese": "Brazilian Portuguese",
}


VOICES = {
    # American English (lang_code='a')
    "american_english": {
        "lang_code": "a",
        "voices": [
            # Female
            "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica",
            "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah",
            "af_sky",
            # Male
            "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
            "am_michael", "am_onyx", "am_puck", "am_santa",
        ],
    },

    # British English (lang_code='b')
    "british_english": {
        "lang_code": "b",
        "voices": [
            # Female
            "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
            # Male
            "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
        ],
    },

    # Spanish (lang_code='e')
    "spanish": {
        "lang_code": "e",
        "voices": [
            "ef_dora", "em_alex", "em_santa",
        ],
    },

    # French (lang_code='f')
    "french": {
        "lang_code": "f",
        "voices": [
            "ff_siwis",
        ],
    },

    # Hindi (lang_code='h')
    "hindi": {
        "lang_code": "h",
        "voices": [
            "hf_alpha", "hf_beta", "hm_omega",
        ],
    },

    # Japanese (lang_code='j')
    "japanese": {
        "lang_code": "j",
        "voices": [
            "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro",
            "jm_kumo",
        ],
    },

    # Mandarin Chinese (lang_code='z')
    "chinese": {
        "lang_code": "z",
        "voices": [
            "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
        ],
    },

    # Brazilian Portuguese (lang_code='p')
    "brazilian_portuguese": {
        "lang_code": "p",
        "voices": [
            "pf_dora", "pm_alex", "pm_santa",
        ],
    },
}

SAMPLES_DIR = Path("static/samples")
MANIFEST_PATH = SAMPLES_DIR / "manifest.json"


def load_samples_manifest() -> Dict[str, Dict]:
    """Load voice preview sample manifest if available."""
    if MANIFEST_PATH.exists():
        try:
            with MANIFEST_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            # Invalid manifest, treat as missing
            return {}
    return {}


class VoiceManager:
    """Manages voice assignments for speakers"""
    
    def __init__(self):
        self.speaker_voices = {}
        self.samples_manifest = load_samples_manifest()
        
    def assign_voice(self, speaker_id, voice_name, lang_code="a"):
        """
        Assign a voice to a speaker
        
        Args:
            speaker_id: Speaker identifier (e.g., "speaker1")
            voice_name: Voice name (e.g., "af_heart")
            lang_code: Language code (default: "a" for American English)
        """
        self.speaker_voices[speaker_id] = {
            "voice": voice_name,
            "lang_code": lang_code
        }
        
    def get_voice(self, speaker_id):
        """
        Get voice configuration for a speaker
        
        Args:
            speaker_id: Speaker identifier
            
        Returns:
            dict: Voice configuration with 'voice' and 'lang_code'
        """
        return self.speaker_voices.get(speaker_id, {
            "voice": "af_heart",
            "lang_code": "a"
        })
        
    def get_all_voices(self):
        """Get all available voices with sample metadata."""
        voices_copy = copy.deepcopy(VOICES)
        
        for language_key, config in voices_copy.items():
            samples = {}
            for voice_name in config["voices"]:
                sample_entry = self.samples_manifest.get(voice_name)
                if sample_entry:
                    samples[voice_name] = sample_entry.get("file")
            config["samples"] = samples
            config["language"] = LANGUAGE_LABELS.get(
                language_key,
                language_key.replace("_", " ").title(),
            )
        
        return voices_copy
    
    @staticmethod
    def _unique_voice_names():
        names = set()
        for config in VOICES.values():
            names.update(config["voices"])
        return names
    
    def sample_count(self) -> int:
        """Return the number of samples currently registered."""
        return len(self.samples_manifest)
    
    def total_unique_voice_count(self) -> int:
        """Return the total number of unique voice names available."""
        return len(self._unique_voice_names())
    
    def missing_samples(self):
        """Return a sorted list of voices without generated samples."""
        voices = self._unique_voice_names()
        missing = [voice for voice in voices if voice not in self.samples_manifest]
        return sorted(missing)
    
    def all_samples_present(self) -> bool:
        """Determine if every voice has a preview sample."""
        return len(self.missing_samples()) == 0
        
    def get_voices_by_language(self, language):
        """Get voices for a specific language"""
        return VOICES.get(language, {}).get("voices", [])
        
    def validate_voice(self, voice_name, lang_code):
        """
        Validate if a voice exists for the given language
        
        Args:
            voice_name: Voice name to validate
            lang_code: Language code
            
        Returns:
            bool: True if valid, False otherwise
        """
        for lang, config in VOICES.items():
            if config["lang_code"] == lang_code:
                return voice_name in config["voices"]
        return False
        
    def clear_assignments(self):
        """Clear all voice assignments"""
        self.speaker_voices = {}
        
    def get_speaker_count(self):
        """Get number of assigned speakers"""
        return len(self.speaker_voices)
        
    def export_config(self):
        """Export voice configuration as dict"""
        return self.speaker_voices.copy()
        
    def import_config(self, config):
        """Import voice configuration from dict"""
        self.speaker_voices = config.copy()
