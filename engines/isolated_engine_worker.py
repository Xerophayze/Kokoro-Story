"""Generic subprocess worker for TTS engines with dedicated virtual environments."""

from __future__ import annotations

import argparse
import inspect
import json
import logging
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def emit(payload: dict) -> None:
    print("TTS_STORY_EVENT " + json.dumps(payload, ensure_ascii=False, default=str), flush=True)


def configure_cache(engine: str) -> None:
    directory = {
        "qwen3_custom": "qwen3",
        "qwen3_clone": "qwen3",
        "pocket_tts_preset": "pocket_tts",
    }.get(engine, engine)
    engine_root = ROOT / "engines" / directory
    cache = engine_root / "cache"
    models = engine_root / "models"
    cache.mkdir(parents=True, exist_ok=True)
    models.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(cache / "huggingface")
    os.environ["HF_HUB_CACHE"] = str(cache / "huggingface" / "hub")
    os.environ["TORCH_HOME"] = str(cache / "torch")
    os.environ["XDG_CACHE_HOME"] = str(cache)
    os.environ["TTS_STORY_ENGINE_MODEL_ROOT"] = str(models)
    tool_dirs = [ROOT / "tools" / "ffmpeg", ROOT / "tools" / "sox", ROOT / "tools" / "rubberband"]
    os.environ["PATH"] = os.pathsep.join(
        [str(path) for path in tool_dirs if path.is_dir()] + [os.environ.get("PATH", "")]
    )
    if engine == "kitten_tts":
        os.environ["KITTEN_TTS_CACHE_DIR"] = str(models)


def engine_class(engine: str):
    if engine == "kokoro":
        from src.engines.kokoro_engine import KokoroEngine
        return KokoroEngine
    if engine == "voxcpm_local":
        from src.engines.voxcpm_local_engine import VoxCPMLocalEngine
        return VoxCPMLocalEngine
    if engine in {"pocket_tts", "pocket_tts_preset"}:
        from src.engines.pocket_tts_engine import PocketTTSEngine
        return PocketTTSEngine
    if engine == "qwen3_custom":
        from src.engines.qwen3_custom_voice_engine import Qwen3CustomVoiceEngine
        return Qwen3CustomVoiceEngine
    if engine == "qwen3_clone":
        from src.engines.qwen3_voice_clone_engine import Qwen3VoiceCloneEngine
        return Qwen3VoiceCloneEngine
    if engine == "kitten_tts":
        from src.engines.kitten_tts_engine import KittenTTSEngine
        return KittenTTSEngine
    if engine == "edge_tts":
        from src.engines.edge_tts_engine import EdgeTTSEngine
        return EdgeTTSEngine
    if engine == "audio8_tts":
        from src.engines.audio8_tts_engine import Audio8TTSEngine
        return Audio8TTSEngine
    if engine == "breeze_tts_2":
        from src.engines.breeze_tts_2_engine import BreezeTTS2Engine
        return BreezeTTS2Engine
    raise ValueError(f"Unsupported isolated engine: {engine}")


def filtered_call(function, **kwargs):
    signature = inspect.signature(function)
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return function(**kwargs)
    return function(**{key: value for key, value in kwargs.items() if key in signature.parameters})


def run_job(job: dict, engine=None) -> None:
    engine_name = str(job["engine"])
    owns_engine = engine is None
    if owns_engine:
        configure_cache(engine_name)
        engine = engine_class(engine_name)(**(job.get("constructor") or {}))
    emit({
        "event": "engine_ready",
        "device": getattr(engine, "device", "unknown"),
        "dtype": getattr(engine, "dtype", "unknown"),
    })
    operation = job.get("operation")
    try:
        if operation == "batch":
            def progress():
                emit({"event": "progress"})

            def chunk(chunk_index, metadata, path):
                emit({
                    "event": "chunk",
                    "chunk_index": chunk_index,
                    "metadata": metadata,
                    "path": str(path),
                })

            result = filtered_call(
                engine.generate_batch,
                segments=job.get("segments") or [],
                voice_config=job.get("voice_config") or {},
                output_dir=Path(job["output_dir"]),
                speed=job.get("speed", 1.0),
                sample_rate=job.get("sample_rate"),
                parallel_workers=job.get("parallel_workers", 1),
                group_by_speaker=job.get("group_by_speaker", False),
                progress_cb=progress,
                chunk_cb=chunk,
            )
            emit({"event": "complete", "files": [str(path) for path in result]})
            return
        if operation == "audio":
            import soundfile as sf
            output_path = Path(job["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            audio = filtered_call(engine.generate_audio, **(job.get("arguments") or {}))
            if isinstance(audio, (bytes, bytearray)):
                output_path.write_bytes(bytes(audio))
            else:
                sf.write(output_path, audio, int(getattr(engine, "sample_rate", 24000)))
            emit({"event": "complete", "path": str(output_path)})
            return
        if operation == "voices" and engine_name == "edge_tts":
            emit({"event": "complete", "voices": engine.list_voices()})
            return
        raise ValueError(f"Unsupported operation: {operation}")
    finally:
        cleanup = getattr(engine, "cleanup", None)
        if owns_engine and callable(cleanup):
            cleanup()


def serve(engine_name):
    engine = None
    constructor = None
    try:
        for line in sys.stdin:
            request = json.loads(line)
            job = json.loads(Path(request["job_file"]).read_text(encoding="utf-8"))
            if job["engine"] != engine_name:
                raise ValueError("Persistent worker engine mismatch")
            if engine is None:
                constructor = job.get("constructor") or {}
                engine = engine_class(engine_name)(**constructor)
            elif constructor != (job.get("constructor") or {}):
                raise ValueError("Persistent worker configuration changed; restart required")
            run_job(job, engine=engine)
        return 0
    except Exception as exc:
        emit({"event": "error", "error": f"{type(exc).__name__}: {exc}"})
        return 1
    finally:
        if engine is not None:
            engine.cleanup()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True)
    parser.add_argument("--job-file")
    parser.add_argument("--check-env", action="store_true")
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    configure_cache(args.engine)
    if args.serve:
        return serve(args.engine)
    if args.check_env:
        cls = engine_class(args.engine)
        print(f"{args.engine} isolated environment ready: {cls.__name__}")
        return 0
    if not args.job_file:
        parser.error("--job-file is required")
    try:
        run_job(json.loads(Path(args.job_file).read_text(encoding="utf-8")))
        return 0
    except Exception as exc:
        print(f"ISOLATED_ENGINE_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
