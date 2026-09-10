"""Build the pinned Breeze Q8 Vulkan library and fetch only Q8_0 weights."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager


@contextmanager
def short_source_path(source):
    """MSBuild shader subprojects otherwise exceed Windows MAX_PATH."""
    if sys.platform != 'win32':
        yield source
        return
    import ctypes
    drives = ctypes.windll.kernel32.GetLogicalDrives()
    letter = next((chr(i + 65) for i in range(25, 12, -1) if not drives & (1 << i)), None)
    if not letter:
        raise RuntimeError('Q8 build needs a free drive letter for a temporary short-path mapping.')
    drive = letter + ':'
    subprocess.run(['subst', drive, str(source)], check=True)
    try:
        yield Path(drive + '/')
    finally:
        subprocess.run(['subst', drive, '/D'], check=True)

SOURCE = 'https://github.com/HoppouAI/Breeze-TTS-2.cpp'
REVISION = 'a5436642d4c64304b398ceeda9b8fce4577bfdb1'
MODEL_REVISION = '81b22bad9f05b99970e30c5ee5e4bbc52fedf2f8'
MODEL_NAME = 'breeze-tts-2-q8_0.gguf'
MODEL_SIZE = 3568844480
MODEL_SHA256 = 'a02bcc4b69b0601032727f8040c4942149b1b73aa0f69022fe5aaa6a8f0ef879'


def model_valid(path):
    if not path.is_file() or path.stat().st_size != MODEL_SIZE:
        return False
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(8 * 1024**2), b''):
            digest.update(block)
    return digest.hexdigest() == MODEL_SHA256


def download_model(directory):
    import requests
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / MODEL_NAME
    print('Verifying/downloading pinned Q8_0 model (3.57 GB)...', flush=True)
    if model_valid(target):
        print('Q8 model checksum verified; keeping existing download.', flush=True)
        return
    partial = target.with_suffix('.gguf.part')
    if model_valid(partial):
        partial.replace(target)
        return
    if partial.exists() and partial.stat().st_size >= MODEL_SIZE:
        partial.unlink()
    url = f'https://huggingface.co/HoppouAI/Breeze-TTS-2.cpp/resolve/{MODEL_REVISION}/{MODEL_NAME}'
    for attempt in range(3):
        offset = partial.stat().st_size if partial.exists() else 0
        try:
            headers = {'Range': f'bytes={offset}-'} if offset else {}
            with requests.get(url, headers=headers, stream=True, timeout=(20, 60)) as response:
                response.raise_for_status()
                resume = offset > 0 and response.status_code == 206
                if resume and not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                    raise RuntimeError('Q8 download returned an unexpected byte range')
                if not resume:
                    offset = 0
                last = 0
                with partial.open('ab' if resume else 'wb') as output:
                    for block in response.iter_content(1024**2):
                        if not block:
                            continue
                        output.write(block)
                        offset += len(block)
                        if offset > MODEL_SIZE:
                            raise RuntimeError('Q8 download is larger than the pinned model')
                        if time.monotonic() - last > 5:
                            print(f'Q8 download: {100 * offset / MODEL_SIZE:.1f}% ({offset // 1024**2} MiB)', flush=True)
                            last = time.monotonic()
            if not model_valid(partial):
                partial.unlink(missing_ok=True)
                raise RuntimeError('Q8 checksum mismatch; download discarded')
            partial.replace(target)
            print('Q8 download complete; SHA-256 verified.', flush=True)
            return
        except (requests.RequestException, RuntimeError) as exc:
            if attempt == 2:
                raise RuntimeError(f'Q8 model download failed: {exc}') from exc
            print(f'Q8 download retry {attempt + 1}/2: {type(exc).__name__}', flush=True)
    raise RuntimeError('Q8 download did not complete')


def build_tools():
    cmake = shutil.which('cmake')
    if sys.platform == 'win32':
        vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
        if vswhere.is_file():
            location = subprocess.check_output([
                str(vswhere), '-latest', '-products', '*', '-requires',
                'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath',
            ], text=True).strip()
            candidate = Path(location) / 'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
            if not cmake and location and candidate.is_file():
                cmake = str(candidate)
        sdk = os.environ.get('VULKAN_SDK')
        if not sdk:
            roots = sorted(Path('C:/VulkanSDK').glob('*'), reverse=True) if Path('C:/VulkanSDK').exists() else []
            sdk = next((str(p) for p in roots if (p / 'Bin/glslc.exe').is_file()), None)
        if sdk:
            os.environ['VULKAN_SDK'] = sdk
        if not sdk or not (Path(sdk) / 'Bin/glslc.exe').is_file():
            raise RuntimeError(
                'Breeze Q8 needs the Vulkan SDK (including glslc). Install the Windows SDK from '
                'https://vulkan.lunarg.com/sdk/home, then restart TTS-Story and retry Install Q8. '
                'The GPU driver alone is not the SDK. Also install Visual Studio 2022 Build Tools '
                'with Desktop development with C++ and CMake tools.'
            )
    elif sys.platform == 'darwin':
        raise RuntimeError('Breeze Q8 Vulkan installation is currently supported on Windows and Linux only.')
    elif not shutil.which('glslc'):
        raise RuntimeError('Install CMake, a C++17 compiler, Vulkan development headers and glslc, then retry Q8. See https://vulkan.lunarg.com/sdk/home')
    if not cmake:
        raise RuntimeError('CMake is required to build Breeze Q8. Install CMake and a C++17 compiler, then restart and retry.')
    return cmake


def install():
    from install_engine import ROOT, run, ensure_venv, ISOLATED_AUDIO_RUNTIME
    root = ROOT / 'engines/breeze_tts_2'
    if not (root / '.license_accepted').is_file():
        raise RuntimeError('Accept the Breeze license in Settings before installing Q8.')
    cmake = build_tools()
    source = root / 'cpp-runtime'
    if not (source / '.git').is_dir():
        run(['git', 'clone', SOURCE, str(source)])
    run(['git', 'fetch', 'origin', REVISION], cwd=source)
    run(['git', 'checkout', '--detach', REVISION], cwd=source)
    run(['git', 'submodule', 'update', '--init', '--recursive'], cwd=source)
    patch = ROOT / 'scripts/patches/breeze-q8-backend.patch'
    if subprocess.run(['git', 'apply', '--reverse', '--check', str(patch)], cwd=source,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
        run(['git', 'apply', str(patch)], cwd=source)
    with short_source_path(source) as short:
        build = short / 'q8-build'
        args = [cmake, '-S', str(short), '-B', str(build), '-DCMAKE_BUILD_TYPE=Release',
                '-DBREEZE_VULKAN=ON', '-DBREEZE_CUDA=OFF', '-DBREEZE_BUILD_CLI=OFF',
                '-DBREEZE_BUILD_SERVER=OFF', '-DBREEZE_BUILD_SHARED=ON', '-DBUILD_SHARED_LIBS=OFF']
        if sys.platform == 'win32':
            args += ['-G', 'Visual Studio 17 2022', '-A', 'x64']
        run(args)
        run([cmake, '--build', str(build), '--config', 'Release', '--target', 'breeze', '--parallel', '4'])
    build = source / 'q8-build'
    name = 'breeze.dll' if sys.platform == 'win32' else 'libbreeze.so'
    library = next(build.rglob(name), None)
    if not library:
        raise RuntimeError(f'Build did not produce {name}')
    destination = root / 'q8/bin'
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(library, destination / name)
    python = ensure_venv(root / '.venv')
    run([str(python), '-m', 'pip', 'install', *ISOLATED_AUDIO_RUNTIME])
    run([str(python), '-c',
         'import ctypes; from src.engines.breeze_q8 import library_path; '
         'lib=ctypes.CDLL(str(library_path())); assert lib.breeze_generate; assert lib.breeze_init; assert lib.breeze_backend_name'])
    download_model(root / 'models')
    (root / 'q8/build.json').write_text(json.dumps({'source': SOURCE, 'revision': REVISION, 'model_revision': MODEL_REVISION}), encoding='utf-8')
    (root / '.q8_ready').touch()
    (root / '.ready').touch()
    print('Breeze Q8 installed. Select Q8 GGUF in Breeze Settings and save. Restart the backend before use.', flush=True)
