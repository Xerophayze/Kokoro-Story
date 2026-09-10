"""Persistent Breeze TTS 2 worker used for reference-free casting previews."""

from __future__ import annotations

import gc
import json
import logging
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = ROOT / "engines" / "breeze_tts_2"
CACHE_ROOT = ENGINE_ROOT / "cache"
MODEL_ROOT = ENGINE_ROOT / "models"
os.environ.setdefault("HF_HOME", str(CACHE_ROOT / "huggingface"))
os.environ.setdefault("HF_HUB_CACHE", str(CACHE_ROOT / "huggingface" / "hub"))
os.environ.setdefault("TORCH_HOME", str(CACHE_ROOT / "torch"))
os.environ.setdefault("XDG_CACHE_HOME", str(CACHE_ROOT))
os.environ.setdefault("TTS_STORY_ENGINE_MODEL_ROOT", str(MODEL_ROOT))
os.environ["PATH"] = os.pathsep.join([
    str(ROOT / "tools" / "ffmpeg"),
    str(ROOT / "tools" / "sox"),
    str(ROOT / "tools" / "rubberband"),
    os.environ.get("PATH", ""),
])
sys.path.insert(0, str(ROOT))
MODEL_ROOT.mkdir(parents=True, exist_ok=True)

logging.basicConfig(stream=sys.stderr, level=logging.INFO)
ENGINE = None
ENGINE_SIGNATURE = None


def get_engine(request: dict):
    global ENGINE, ENGINE_SIGNATURE
    from src.engines.breeze_tts_2_engine import BreezeTTS2Engine

    constructor = dict(request.get("constructor") or {})
    signature = json.dumps(constructor, sort_keys=True, default=str)
    if ENGINE is not None and signature == ENGINE_SIGNATURE:
        return ENGINE
    if ENGINE is not None:
        ENGINE.cleanup()
    ENGINE = None
    gc.collect()
    if constructor.get('runtime', 'pytorch') == 'pytorch':
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    ENGINE = BreezeTTS2Engine(**constructor)
    ENGINE_SIGNATURE = signature
    return ENGINE


def generate(request: dict) -> dict:
    import soundfile as sf

    engine = get_engine(request)
    torch = None
    if engine.runtime_kind == 'pytorch':
        import torch
    if torch is not None and torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    audio = engine.generate_audio(
        request["text"],
        voice_design_prompt=request.get("instruct", ""),
        seed=int(request.get("seed", 42)),
    )
    if audio is None or len(audio) == 0:
        raise RuntimeError("No audio produced for Breeze voice-design preview")
    output = Path(request["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output, audio, int(engine.sample_rate))
    result = {
        "path": str(output),
        "sample_rate": int(engine.sample_rate),
        "elapsed_seconds": time.perf_counter() - started,
    }
    if torch is not None and torch.cuda.is_available():
        result.update({
            "cuda_allocated_mb": round(torch.cuda.memory_allocated() / 1024**2, 1),
            "cuda_reserved_mb": round(torch.cuda.memory_reserved() / 1024**2, 1),
            "cuda_peak_allocated_mb": round(torch.cuda.max_memory_allocated() / 1024**2, 1),
        })
    gc.collect()
    return result


def main() -> int:
    for line in sys.stdin:
        request = {}
        try:
            request = json.loads(line)
            result = generate(request)
            response = {"id": request["id"], "success": True, **result}
        except Exception as exc:
            response = {
                "id": request.get("id"),
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        print("TTS_STORY_BREEZE_RESULT " + json.dumps(response), flush=True)
    if ENGINE is not None:
        ENGINE.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
