from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_config_is_ignored_and_sync_never_force_adds_it():
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    sync_script = (PROJECT_ROOT / "sync-to-git.bat").read_text(encoding="utf-8")

    assert "config.json" in gitignore
    assert 'add -f "%SCRIPT_DIR%\\config.json"' not in sync_script
    assert "--scrub-only" not in sync_script
    assert "config.json is local-only" in sync_script
    assert "--working-tree" in sync_script
    assert sync_script.index("--working-tree") < sync_script.index(" add -A")


def test_platform_updaters_preserve_legacy_tracked_config():
    windows_updater = (PROJECT_ROOT / "install-update.bat").read_text(encoding="utf-8")
    unix_updater = (PROJECT_ROOT / "install-update.sh").read_text(encoding="utf-8")

    assert windows_updater.count("call :pull_updates") == 2
    assert "git restore --source=HEAD --staged --worktree -- config.json" in windows_updater
    assert unix_updater.count("pull_updates") >= 3
    assert "git restore --source=HEAD --staged --worktree -- config.json" in unix_updater
