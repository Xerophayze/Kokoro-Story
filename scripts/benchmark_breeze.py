"""Small isolated Breeze benchmark; never changes project audio or settings."""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engines.isolated_engine_worker import configure_cache
configure_cache("breeze_tts_2")
from src.engines.breeze_tts_2_engine import BreezeTTS2Engine
import torch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference")
    parser.add_argument("--decode-graphs", action="store_true")
    parser.add_argument('--runtime', choices=['pytorch', 'q8'], default='pytorch')
    parser.add_argument('--worker', action='store_true', help='Exercise the real persistent worker protocol')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--text', default='The door opened slowly. Nobody was there.')
    parser.add_argument('--instruction', default='Narrate quietly with cautious curiosity.')
    args = parser.parse_args()
    if args.worker:
        from src.engines.isolated_proxy import IsolatedEngineProxy
        engine = IsolatedEngineProxy('breeze_tts_2', runtime=args.runtime, fast_mode=False)
    else:
        engine = BreezeTTS2Engine(fast_mode=False, runtime=args.runtime)
    if args.runtime == 'pytorch' and not args.worker:
        engine.runtime._fast_backbone_decode = args.decode_graphs
    try:
        for attempt in range(2):
            started = time.perf_counter()
            audio = engine.generate_audio(
                args.text,
                audio_prompt_path=args.reference,
                delivery_instruction=args.instruction, seed=42,
            )
            seconds = len(audio) / engine.sample_rate
            elapsed = time.perf_counter() - started
            if args.output_dir:
                import soundfile as sf
                args.output_dir.mkdir(parents=True, exist_ok=True)
                sf.write(args.output_dir / f'{args.runtime}-{attempt}.wav', audio, engine.sample_rate)
            print(json.dumps({"runtime": args.runtime, "decode_graphs": args.decode_graphs, "attempt": attempt,
                              "worker_pid": engine._process.pid if args.worker and engine._process else None,
                              "seconds": seconds, "elapsed": elapsed, "rtf": elapsed / seconds,
                              "peak_gb": torch.cuda.max_memory_allocated() / 1024**3 if args.runtime == 'pytorch' else None}), flush=True)
    finally:
        engine.cleanup()


if __name__ == "__main__":
    main()
