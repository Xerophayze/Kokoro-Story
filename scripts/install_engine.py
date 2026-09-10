#!/usr/bin/env python3
"""Install or safely remove one optional TTS engine."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE_REQUIREMENTS = ROOT / "requirements-engines"
ISOLATED_ENGINES = {
    "kokoro": "kokoro.txt",
    "voxcpm_local": "voxcpm_local.txt",
    "pocket_tts": "pocket_tts.txt",
    "qwen3": "qwen3.txt",
    "kitten_tts": "kitten_tts.txt",
    "edge_tts": "edge_tts.txt",
    "audio8_tts": "audio8_tts.txt",
    "breeze_tts_2": "breeze_tts_2.txt",
}
TORCH_ENGINES = {"kokoro", "voxcpm_local", "pocket_tts", "qwen3", "audio8_tts"}
ISOLATED_AUDIO_RUNTIME = [
    "numpy", "soundfile>=0.12.1", "pydub>=0.25.1", "librosa==0.11.0",
    "resampy>=0.4.2", "pyrubberband>=0.4.0", "scipy>=1.11.0",
]
SUPPORTED_ENGINES = {
    *ISOLATED_ENGINES,
    "chatterbox_turbo_local",
    "omnivoice",
    "index_tts",
    "dots_tts",
}
MAIN_ENV_PACKAGES = {
    "kokoro": ["kokoro"],
    "voxcpm_local": ["voxcpm"],
    "pocket_tts": ["pocket-tts"],
    "qwen3": ["qwen-tts"],
    "kitten_tts": ["kittentts"],
    "edge_tts": ["edge-tts"],
    "audio8_tts": [],
    "breeze_tts_2": [],
}
ENGINE_MODEL_PATHS = {
    "voxcpm_local": [ROOT / "models" / "voxcpm"],
    "qwen3": [ROOT / "models" / "qwen3"],
    "kitten_tts": [ROOT / "models" / "kitten_tts"],
    "omnivoice": [ROOT / "models" / "omnivoice"],
}
ENGINE_HF_REPOS = {
    "kokoro": ["hexgrad/Kokoro-82M"],
    "chatterbox_turbo_local": ["ResembleAI/chatterbox-turbo"],
    "pocket_tts": ["kyutai/pocket-tts", "kyutai/pocket-tts-without-voice-cloning"],
    "breeze_tts_2": ["BreezeBlue/Breeze-TTS-2"],
}


def run(command: list[str], *, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess:
    print(f"\n> {subprocess.list2cmdline([str(part) for part in command])}", flush=True)
    return subprocess.run([str(part) for part in command], cwd=str(cwd), check=check)


def _remove_readonly(func, path, _exc_info) -> None:
    os.chmod(path, 0o700)
    func(path)


def remove_path(path: Path, *, allowed_root: Path, dry_run: bool = False) -> None:
    resolved = path.resolve()
    root = allowed_root.resolve()
    if resolved == root or root not in resolved.parents:
        raise RuntimeError(f"Refusing to remove a path outside the expected engine/cache directory: {resolved}")
    if not path.exists() and not path.is_symlink():
        return
    print(f"{'Would remove' if dry_run else 'Removing'}: {path}", flush=True)
    if dry_run:
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, onerror=_remove_readonly)
    else:
        path.unlink(missing_ok=True)


def huggingface_hub_roots() -> list[Path]:
    roots: list[Path] = []
    explicit_hub = os.environ.get("HF_HUB_CACHE")
    if explicit_hub:
        roots.append(Path(explicit_hub).expanduser())
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        roots.append(Path(hf_home).expanduser() / "hub")
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    roots.append(
        (Path(xdg_cache).expanduser() if xdg_cache else Path.home() / ".cache")
        / "huggingface" / "hub"
    )
    unique: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def remove_huggingface_repos(engine: str, *, dry_run: bool = False) -> None:
    for repo_id in ENGINE_HF_REPOS.get(engine, []):
        cache_name = "models--" + repo_id.replace("/", "--")
        for hub_root in huggingface_hub_roots():
            remove_path(hub_root / cache_name, allowed_root=hub_root, dry_run=dry_run)


def remove_isolated_runtime(engine: str, *, dry_run: bool = False) -> None:
    directories = {
        "chatterbox_turbo_local": "chatterbox",
        "omnivoice": "omnivoice",
        "index_tts": "index-tts",
        "dots_tts": "dots-tts",
        "kokoro": "kokoro",
        "voxcpm_local": "voxcpm_local",
        "pocket_tts": "pocket_tts",
        "qwen3": "qwen3",
        "kitten_tts": "kitten_tts",
        "edge_tts": "edge_tts",
        "audio8_tts": "audio8_tts",
        "breeze_tts_2": "breeze_tts_2",
    }
    engine_dir = ROOT / "engines" / directories[engine]
    preserved_by_engine = {
        "chatterbox_turbo_local": {"chatterbox_worker.py"},
        "omnivoice": {"omnivoice_worker.py", "requirements.txt"},
        "index_tts": {"tts_worker.py"},
        "dots_tts": {"dots_tts_worker.py"},
    }
    preserved = preserved_by_engine.get(engine, set())
    if not engine_dir.exists():
        return
    for child in engine_dir.iterdir():
        if child.name in preserved:
            continue
        remove_path(child, allowed_root=engine_dir, dry_run=dry_run)


def uninstall(engine: str, *, dry_run: bool = False) -> None:
    if engine not in SUPPORTED_ENGINES:
        raise ValueError(f"Unsupported engine: {engine}")
    print(f"Removing optional TTS engine: {engine}", flush=True)
    print("Shared PyTorch/audio libraries and all TTS-Story projects, output, and voice samples will be kept.", flush=True)
    if engine == "chatterbox_turbo_local":
        # Remove the package left by older TTS-Story releases. Its dependencies
        # remain because they may be shared; the current runtime is isolated.
        if dry_run:
            print("Would remove legacy main-environment package: chatterbox-tts", flush=True)
        else:
            run([sys.executable, "-m", "pip", "uninstall", "-y", "chatterbox-tts"])
        remove_isolated_runtime(engine, dry_run=dry_run)
    elif engine in ISOLATED_ENGINES:
        packages = MAIN_ENV_PACKAGES[engine]
        if dry_run:
            print("Would remove isolated runtime and legacy main package(s): " + ", ".join(packages), flush=True)
        elif packages:
            run([sys.executable, "-m", "pip", "uninstall", "-y", *packages])
        remove_isolated_runtime(engine, dry_run=dry_run)
    else:
        remove_isolated_runtime(engine, dry_run=dry_run)
    for model_path in ENGINE_MODEL_PATHS.get(engine, []):
        remove_path(model_path, allowed_root=ROOT, dry_run=dry_run)
    remove_huggingface_repos(engine, dry_run=dry_run)
    print("\nENGINE_UNINSTALL_COMPLETE", flush=True)


def python_in(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_venv(venv_dir: Path) -> Path:
    python = python_in(venv_dir)
    healthy = python.is_file() and subprocess.run(
        [str(python), "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0
    if not healthy:
        if venv_dir.exists():
            print(f"Existing isolated environment cannot start; recreating: {venv_dir}", flush=True)
            shutil.rmtree(venv_dir, onerror=_remove_readonly)
        print(f"Creating isolated environment: {venv_dir}", flush=True)
        venv.EnvBuilder(with_pip=True).create(venv_dir)
    run([str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    return python


def has_nvidia() -> bool:
    return shutil.which("nvidia-smi") is not None and subprocess.run(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def is_blackwell() -> bool:
    if not has_nvidia():
        return False
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,compute_cap", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        check=False,
    )
    value = result.stdout.lower()
    return "rtx 50" in value or "blackwell" in value or any(
        part.strip().startswith("12.") for part in value.split(",")
    )


def torch_works(python: Path = Path(sys.executable)) -> bool:
    return subprocess.run(
        [str(python), "-c", "import torch; print(torch.__version__)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def install_torch(python: Path = Path(sys.executable), *, isolated_28: bool = False) -> None:
    if torch_works(python) and not isolated_28:
        print("A working PyTorch installation is already available; keeping it.", flush=True)
        return
    pip = [str(python), "-m", "pip", "install", "--upgrade"]
    if sys.platform == "darwin":
        version = "2.8.0" if isolated_28 else "2.6.0"
        run([*pip, f"torch=={version}", f"torchaudio=={version}"])
    elif has_nvidia():
        use_28 = isolated_28 or is_blackwell()
        version = "2.8.0" if use_28 else "2.6.0"
        index = "https://download.pytorch.org/whl/cu128" if use_28 else "https://download.pytorch.org/whl/cu124"
        packages = [f"torch=={version}", f"torchaudio=={version}"]
        if not isolated_28:
            packages.append("torchvision==0.23.0" if use_28 else "torchvision==0.21.0")
        run([*pip, *packages, "--index-url", index])
    else:
        version = "2.8.0" if isolated_28 else "2.6.0"
        run([*pip, f"torch=={version}", f"torchaudio=={version}", "--index-url", "https://download.pytorch.org/whl/cpu"])


def install_isolated_engine(engine: str) -> None:
    engine_dir = ROOT / "engines" / engine
    if engine == "breeze_tts_2":
        if not (engine_dir / ".license_accepted").is_file():
            raise RuntimeError(
                "Breeze TTS 2 requires acceptance of the BreezeBlue Research and "
                "Non-Commercial License in Settings before installation."
            )
        if sys.platform == "darwin" or not has_nvidia():
            raise RuntimeError(
                "The official Breeze TTS 2 runtime currently requires an NVIDIA CUDA GPU."
            )
        python = ensure_venv(engine_dir / ".venv")
        runtime_dir = engine_dir / "runtime"
        if not (runtime_dir / "breeze_infer" / "runtime.py").is_file():
            if runtime_dir.exists():
                shutil.rmtree(runtime_dir, onerror=_remove_readonly)
            runtime_dir.parent.mkdir(parents=True, exist_ok=True)
            run([
                "git", "clone", "--depth", "1",
                "https://github.com/breezeblue-ai/breeze-tts.git",
                str(runtime_dir),
            ])
        run([
            str(python), "-m", "pip", "install", "--upgrade",
            "torch==2.9.1", "torchaudio==2.9.1",
            "--index-url", "https://download.pytorch.org/whl/cu128",
        ])
        run([str(python), "-m", "pip", "install", *ISOLATED_AUDIO_RUNTIME])
        requirement = ENGINE_REQUIREMENTS / ISOLATED_ENGINES[engine]
        run([str(python), "-m", "pip", "install", "-r", str(requirement)])
        worker = ROOT / "engines" / "isolated_engine_worker.py"
        run([str(python), str(worker), "--engine", engine, "--check-env"])
        (engine_dir / ".ready").touch()
        print(
            "Breeze TTS 2 is installed in its isolated environment. "
            "The non-commercial model files download on first use.",
            flush=True,
        )
        return
    python = ensure_venv(engine_dir / ".venv")
    if engine in TORCH_ENGINES:
        install_torch(python)
    run([str(python), "-m", "pip", "install", *ISOLATED_AUDIO_RUNTIME])
    requirement = ENGINE_REQUIREMENTS / ISOLATED_ENGINES[engine]
    run([str(python), "-m", "pip", "install", "-r", str(requirement)])
    runtime_name = {
        "qwen3": "qwen3_custom",
        "pocket_tts": "pocket_tts",
    }.get(engine, engine)
    worker = ROOT / "engines" / "isolated_engine_worker.py"
    run([str(python), str(worker), "--engine", runtime_name, "--check-env"])
    (engine_dir / ".ready").touch()
    if engine == "qwen3":
        run([str(python), str(ROOT / "scripts/flash_attention_setup.py"), "install"], check=False)
    print(f"{engine} is installed in its isolated environment. Model files download on first use.", flush=True)


def install_omnivoice() -> None:
    engine_dir = ROOT / "engines/omnivoice"
    python = ensure_venv(engine_dir / ".venv")
    run([str(python), "-m", "pip", "install", "omnivoice", "soundfile", "huggingface-hub"])
    install_torch(python, isolated_28=True)
    run([str(python), "-c", "import omnivoice, torch, torchaudio, soundfile, huggingface_hub"])
    (engine_dir / ".omnivoice_ready").touch()
    print("OmniVoice is installed. Model files download on first use.", flush=True)


def install_chatterbox() -> None:
    engine_dir = ROOT / "engines" / "chatterbox"
    python = ensure_venv(engine_dir / ".venv")
    install_torch(python)
    requirement = ENGINE_REQUIREMENTS / "chatterbox_turbo_local.txt"
    run([str(python), "-m", "pip", "install", "-r", str(requirement)])
    worker = engine_dir / "chatterbox_worker.py"
    if not worker.is_file():
        raise RuntimeError("The TTS-Story Chatterbox worker is missing. Update TTS-Story and retry.")
    run([str(python), str(worker), "--check-env"])
    (engine_dir / ".chatterbox_ready").touch()
    print("Chatterbox Turbo is installed in its isolated environment. Model files download on first use.", flush=True)


def install_index_tts() -> None:
    engine_dir = ROOT / "engines/index-tts"
    if not (engine_dir / "pyproject.toml").is_file():
        temporary = ROOT / "data/install/index-tts-source"
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1")
        subprocess.run(["git", "clone", "https://github.com/index-tts/index-tts.git", str(temporary)], check=True, env=env)
        shutil.copytree(temporary, engine_dir, dirs_exist_ok=True)
        shutil.rmtree(temporary, ignore_errors=True)
    run([sys.executable, "-m", "pip", "install", "--upgrade", "uv"])
    run([sys.executable, "-m", "uv", "sync"], cwd=engine_dir)
    if not (engine_dir / "tts_worker.py").is_file():
        raise RuntimeError("The TTS-Story IndexTTS worker is missing. Update TTS-Story and retry.")
    (engine_dir / ".indextts_ready").touch()
    print("IndexTTS is installed. Model files download on first use.", flush=True)


def install_dots_tts() -> None:
    engine_dir = ROOT / "engines/dots-tts"
    repo_dir = engine_dir / "repo"
    if not (repo_dir / "pyproject.toml").is_file():
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "https://github.com/rednote-hilab/dots.tts.git", str(repo_dir)])
    python = ensure_venv(engine_dir / ".venv")
    install_torch(python, isolated_28=True)
    constraints = repo_dir / "constraints/recommended.txt"
    dependencies = [
        "transformers", "huggingface-hub", "loguru", "langcodes[data]", "einops",
        "librosa", "soundfile", "numpy", "pydantic", "PyYAML", "safetensors",
        "torchdiffeq", "tqdm", "lingua-language-detector",
    ]
    run([str(python), "-m", "pip", "install", "-c", str(constraints), *dependencies])
    run([str(python), "-m", "pip", "install", "-e", str(repo_dir), "--no-deps"])
    run([str(python), str(engine_dir / "dots_tts_worker.py"), "--check-env"])
    (engine_dir / ".dots_tts_ready").touch()
    print("Dot.TTS is installed. Model files download on first use.", flush=True)


def install(engine: str) -> None:
    if engine not in SUPPORTED_ENGINES:
        raise ValueError(f"Unsupported engine: {engine}")
    print(f"Installing optional TTS engine: {engine}", flush=True)
    if engine in ISOLATED_ENGINES:
        install_isolated_engine(engine)
    elif engine == "chatterbox_turbo_local":
        install_chatterbox()
    elif engine == "omnivoice":
        install_omnivoice()
    elif engine == "index_tts":
        install_index_tts()
    elif engine == "dots_tts":
        install_dots_tts()
    print("\nENGINE_INSTALL_COMPLETE", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true", help="remove the selected engine and its model files")
    parser.add_argument("--dry-run", action="store_true", help="show removal actions without changing files")
    parser.add_argument(
        "--accept-breeze-license",
        action="store_true",
        help="record acceptance of the BreezeBlue Research and Non-Commercial License",
    )
    parser.add_argument("engine", choices=sorted(SUPPORTED_ENGINES))
    parser.add_argument('--breeze-runtime', choices=['pytorch', 'q8'], default='pytorch')
    args = parser.parse_args()
    try:
        if args.engine == "breeze_tts_2" and args.accept_breeze_license:
            license_marker = ROOT / "engines" / "breeze_tts_2" / ".license_accepted"
            license_marker.parent.mkdir(parents=True, exist_ok=True)
            license_marker.write_text(
                "Accepted BreezeBlue Research and Non-Commercial License via installer.\n",
                encoding="utf-8",
            )
        if args.uninstall:
            uninstall(args.engine, dry_run=args.dry_run)
        elif args.engine == 'breeze_tts_2' and args.breeze_runtime == 'q8':
            from install_breeze_q8 import install as install_q8
            install_q8()
            print('\nENGINE_INSTALL_COMPLETE', flush=True)
        else:
            install(args.engine)
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"\nENGINE_INSTALL_FAILED: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
