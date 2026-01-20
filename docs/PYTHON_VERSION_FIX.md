# Universal Python Version Fix for TTS-Story

## Problem
The TTS-Story repository was failing to install for users with Python 3.13+ because the `kokoro` package requires Python 3.10-3.12 (`<3.13`). The README incorrectly stated "Python 3.9 or higher".

## Solution - Files Added/Modified

This fix makes the Python version requirement explicit and provides cross-platform solutions for everyone:

### 1. `.python-version` ✅
**Purpose:** Cross-platform Python version specification  
**Content:** `3.12`  
**Works with:** pyenv, pyenv-win, uv, and other version managers

### 2. `pyproject.toml` ✅
**Purpose:** Modern Python project metadata with version constraints  
**Key constraint:** `requires-python = ">=3.10,<3.13"`  
**Benefits:**
- Works with `uv`, `pip`, and modern Python tools
- Prevents installation on incompatible Python versions
- Provides clear error messages

### 3. `README.md` (Updated) ✅
**Changes:**
- ✅ Corrected Python requirement from "3.9+" to "3.10-3.12"
- ✅ Added "Python Version Management" section with 3 options:
  - **Option 1:** `uv` (recommended, cross-platform, auto-downloads Python)
  - **Option 2:** `pyenv`/`pyenv-win` (cross-platform)
  - **Option 3:** Manual installation from python.org

### 4. `setup-improved.bat` ✅
**Purpose:** Windows setup script with Python version validation  
**Features:**
- ✅ Checks Python version before installation
- ✅ Validates that Python is 3.10, 3.11, or 3.12
- ✅ Provides helpful error messages with installation options
- ✅ Prevents wasted time installing dependencies on wrong Python version

## How This Helps Everyone

### For Users with Python 3.13/3.14
- **Before:** Cryptic error during `kokoro` installation
- **After:** Clear error message upfront with installation instructions

### For New Users
- **Before:** Unclear which Python version to use
- **After:** Clear guidance with multiple installation options

### For Cross-Platform Users
- **Before:** Windows-specific instructions only
- **After:** Works on Windows, Linux, and macOS with `uv` or `pyenv`

### For CI/CD & Automation
- **Before:** No machine-readable Python version specification
- **After:** `.python-version` and `pyproject.toml` work with automated tools

## Recommended Installation Path (Cross-Platform)

### Using `uv` (Fastest & Easiest)

```bash
# Install uv (one-time)
# Windows PowerShell:
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Linux/macOS:
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone repo
git clone <repo-url>
cd TTS-Story

# uv automatically reads .python-version and downloads Python 3.12
uv venv

# Activate
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install (uv is 10-100x faster than pip)
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
uv pip install -r requirements.txt
```

### Using pyenv (Traditional)

```bash
# Install Python 3.12 (reads .python-version automatically)
pyenv install

# Create venv
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

## Files to Commit

To fix this for everyone, commit these files to the repository:

```bash
git add .python-version
git add pyproject.toml
git add README.md
git add setup-improved.bat  # Optional: can replace setup.bat
git commit -m "Fix: Add Python version constraints (3.10-3.12) and cross-platform setup instructions"
git push
```

## Why Not Just Update `requirements.txt`?

`requirements.txt` specifies **package** versions, not **Python** versions. While you can add Python version markers to individual packages, it doesn't prevent someone from trying to install with the wrong Python version upfront.

The combination of `.python-version` + `pyproject.toml` provides:
1. **Early detection** - Tools check Python version before downloading anything
2. **Cross-platform** - Works with all modern Python version managers
3. **Standard** - Follows Python packaging best practices (PEP 621)

## Summary

This fix transforms the installation experience from:
- ❌ "Why is kokoro failing to install?"
- ❌ "I wasted 10 minutes downloading PyTorch on Python 3.14"

To:
- ✅ "Clear error: Python 3.12 required"
- ✅ "Here are 3 ways to install it"
- ✅ "Works on Windows, Linux, and macOS"

The fix is **universal**, **cross-platform**, and follows **modern Python best practices**! 🎉
