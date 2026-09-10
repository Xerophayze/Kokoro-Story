"""Reject sensitive or generated content before it is committed.

This intentionally uses only the Python standard library so it can run before
the project's optional dependencies are installed.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


SECRET_CONFIG_KEYS = {
    "breeze_api_key",
    "atlas_cloud_api_key",
    "openrouter_api_key",
    "azure_speech_key",
    "elevenlabs_api_key",
    "openai_tts_api_key",
    "localai_tts_api_key",
    "gemini_api_key",
    "replicate_api_key",
    "llm_local_api_key",
    "chatterbox_turbo_replicate_api_token",
    "huggingface_token",
    "remote_engine_management_token",
}

FORBIDDEN_EXACT_PATHS = {
    ".setup_complete",
    ".setup_state.json",
    ".setup_state.json.tmp",
    ".sync_state.json",
    "config.json",
    "config.json.syncbak",
    "data/chatterbox_voices.json",
    "data/custom_voices.json",
    "data/external_voice_archives.json",
    "data/external_voices_cache.json",
    "data/projects.json",
    "data/localai_voice_profiles.json",
    "data/engine-first-run.json",
    "jobs.db",
}

FORBIDDEN_PREFIXES = (
    ".cache/",
    ".codex/",
    ".codex-remote-attachments/",
    "data/engine-installs/",
    "data/external_voices/",
    "data/jobs/",
    "data/breeze_productions/",
    "data/prep/",
    "data/benchmarks/",
    "data/voice_prompts/",
    "engines/dots-tts/.venv/",
    "engines/dots-tts/hf-cache/",
    "engines/dots-tts/models/",
    "engines/dots-tts/repo/",
    "engines/index-tts/",
    "engines/omnivoice/.venv/",
    "models/",
    "static/audio/",
    "static/samples/",
    "tools/ffmpeg/",
    "tools/rubberband/",
    "venv.old/",
    "venv/",
)

ALLOWED_GENERATED_PLACEHOLDERS = {
    "data/voice_prompts/.gitkeep",
    "static/audio/.gitkeep",
    "static/samples/.gitkeep",
}

ALLOWED_PREFIX_EXCEPTIONS = {
    "engines/index-tts/tts_worker.py",
}

SECRET_PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{40,255})"),
    "Google API key": re.compile(rb"AIza[0-9A-Za-z_-]{35}"),
    "AWS access key": re.compile(rb"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    "OpenAI-style key": re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "Hugging Face token": re.compile(rb"hf_[A-Za-z0-9]{30,}"),
    "Replicate token": re.compile(rb"r8_[A-Za-z0-9]{30,}"),
}

CONTEXTUAL_SECRET_PATTERN = re.compile(
    rb'''(?ix)
    (
        api[_-]?(?:key|token)
        |(?:azure|gemini|openai|openrouter|atlas|replicate|elevenlabs|huggingface|hf|localai|aws|github|google)[a-z0-9_-]*[_-](?:key|token|secret)
        |access[_-]?token|auth[_-]?token|client[_-]?secret|password
    )
    ["']?\s*[:=]\s*["']([^"'\r\n]{16,})["']
    '''
)
PLACEHOLDER_SECRET_TERMS = (
    b"example",
    b"placeholder",
    b"replace-me",
    b"replace_me",
    b"your-api",
    b"your_api",
    b"your-key",
    b"your_key",
    b"dummy",
    b"fake",
)

RUNTIME_DIRECTORY_NAMES = {".venv", "venv", "venv.old", "env", "__pycache__"}

# Mirror the local settings snapshot exclusions, but also reject forced staging.
CONFIG_BACKUP_PATTERNS = (
    "config.json.*",
    "config[._-]*.bak", "config[._-]*.bak.*",
    "config[._-]*.backup", "config[._-]*.backup.*",
    "config[._-]*.old", "config[._-]*.orig", "config[._-]*.syncbak",
)


def normalize_path(path: str) -> str:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def path_problem(path: str) -> str | None:
    normalized = normalize_path(path)
    lowered = normalized.lower()
    name = PurePosixPath(lowered).name

    if lowered in FORBIDDEN_EXACT_PATHS:
        return "runtime or backup file"
    if any(fnmatch.fnmatchcase(name, pattern) for pattern in CONFIG_BACKUP_PATTERNS):
        return "local configuration backup (may contain credentials)"
    if lowered.startswith("temp_requirements_filtered") and name.endswith(".txt"):
        return "temporary dependency file"
    if lowered in ALLOWED_GENERATED_PLACEHOLDERS or lowered in ALLOWED_PREFIX_EXCEPTIONS:
        return None
    parts = PurePosixPath(lowered).parts
    if len(parts) >= 3 and parts[0] == "data" and parts[1].endswith("-benchmark"):
        return "local benchmark output"
    if any(part in RUNTIME_DIRECTORY_NAMES for part in parts):
        return "virtual environment or generated Python cache"
    if len(parts) >= 3 and parts[0] == "engines":
        if any(part in {"cache", "hf-cache", "models", "repo", "runtime", "cpp-runtime", "q8"} for part in parts[2:]):
            return "downloaded engine cache, model, or source repository"
        if name in {".ready", ".license_accepted"} or (name.startswith(".") and name.endswith("_ready")):
            return "local engine installation marker"
    if any(lowered.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
        return "generated, downloaded, or user-data directory"
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return "environment file"
    if PurePosixPath(lowered).suffix in {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx"}:
        return "database or credential file"
    return None


def content_problems(path: str, content: bytes) -> list[str]:
    problems = [label for label, pattern in SECRET_PATTERNS.items() if pattern.search(content)]
    normalized_path = normalize_path(path).lower()
    if not normalized_path.startswith("tests/"):
        for match in CONTEXTUAL_SECRET_PATTERN.finditer(content):
            candidate = match.group(2).strip().lower()
            if any(term in candidate for term in PLACEHOLDER_SECRET_TERMS):
                continue
            if any(marker in candidate for marker in (b"${", b"{{", b"<", b">")):
                continue
            if re.fullmatch(
                rb"[a-z][a-z0-9_]*(?:api_key|api_token|access_token|auth_token|client_secret)",
                candidate,
            ):
                continue
            problems.append("credential-like populated key or token setting")
            break
    if normalized_path == "config.json":
        try:
            config = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            problems.append("config.json is not valid UTF-8 JSON")
        else:
            populated = sorted(key for key in SECRET_CONFIG_KEYS if config.get(key))
            if populated:
                problems.append("populated secret setting(s): " + ", ".join(populated))
    return problems


def run_git(repo: Path, *args: str, text: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=text,
    )
    return result.stdout


def staged_paths(repo: Path) -> list[str]:
    output = run_git(repo, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    assert isinstance(output, bytes)
    return [entry.decode("utf-8", "surrogateescape") for entry in output.split(b"\0") if entry]


def staged_content(repo: Path, path: str) -> bytes:
    output = run_git(repo, "show", f":{path}")
    assert isinstance(output, bytes)
    return output


def working_tree_paths(repo: Path) -> list[str]:
    output = run_git(repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    assert isinstance(output, bytes)
    return [entry.decode("utf-8", "surrogateescape") for entry in output.split(b"\0") if entry]


def find_repo_root() -> Path:
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    raise OSError("no Git repository found in this directory or its parents")


def audit_staged(repo: Path) -> list[str]:
    failures: list[str] = []
    for path in staged_paths(repo):
        if problem := path_problem(path):
            failures.append(f"{path}: {problem}")
            continue
        content = staged_content(repo, path)
        for problem in content_problems(path, content):
            failures.append(f"{path}: {problem}")
    return failures


def audit_working_tree(repo: Path) -> list[str]:
    """Audit every tracked or unignored file before `git add` changes the index."""
    failures: list[str] = []
    for path in working_tree_paths(repo):
        candidate = repo / path
        if not candidate.exists() or candidate.is_dir():
            continue
        if problem := path_problem(path):
            failures.append(f"{path}: {problem}")
            continue
        try:
            content = candidate.read_bytes() if not candidate.is_symlink() else str(candidate.readlink()).encode()
        except OSError as exc:
            failures.append(f"{path}: could not be audited ({exc})")
            continue
        for problem in content_problems(path, content):
            failures.append(f"{path}: {problem}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true", help="audit staged additions and modifications")
    mode.add_argument(
        "--working-tree",
        action="store_true",
        help="audit tracked and unignored files before staging",
    )
    args = parser.parse_args()

    try:
        repo = find_repo_root()
        failures = audit_staged(repo) if args.staged else audit_working_tree(repo)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: repository safety check could not run: {exc}", file=sys.stderr)
        return 2

    if failures:
        print("ERROR: repository safety check found content that must not be committed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    scope = "Staged content" if args.staged else "Tracked and unignored working-tree content"
    print(f"[safety] {scope} passed the repository safety check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
