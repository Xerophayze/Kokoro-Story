# Installation Options Comparison

## Quick Decision Guide

**Just want it to work?** → Use `setup-uv.bat` (Windows) or `setup-uv.sh` (Linux/macOS)

**Already have Python 3.12?** → Use `setup.bat` (Windows) or manual setup

**Want maximum control?** → Manual installation

---

## Detailed Comparison

### Option 1: Automated UV Setup (Recommended) ⭐

**Files:** `setup-uv.bat` (Windows) or `setup-uv.sh` (Linux/macOS)

| Feature | Details |
|---------|---------|
| **Ease of Use** | ⭐⭐⭐⭐⭐ Single command |
| **Speed** | ⭐⭐⭐⭐⭐ 1-2 minutes total |
| **Python Install** | ✅ Automatic (downloads Python 3.12) |
| **UV Install** | ✅ Automatic |
| **Cross-Platform** | ✅ Windows, Linux, macOS |
| **System Impact** | ✅ Isolated (no system Python needed) |
| **Best For** | New users, clean installs, fastest setup |

**Pros:**
- ✅ No manual Python installation
- ✅ Works even if you have wrong Python version
- ✅ 10-100x faster package installation
- ✅ Completely automated
- ✅ Cross-platform

**Cons:**
- ⚠️ Downloads UV (~10MB) and Python 3.12 (~25MB)
- ⚠️ New tool to learn (though it's simple)

**Commands:**
```bash
# Windows
setup-uv.bat

# Linux/macOS
chmod +x setup-uv.sh
./setup-uv.sh
```

---

### Option 2: Traditional Setup

**Files:** `setup.bat` (Windows) or manual commands

| Feature | Details |
|---------|---------|
| **Ease of Use** | ⭐⭐⭐⭐ One command (if Python installed) |
| **Speed** | ⭐⭐⭐ 5-15 minutes |
| **Python Install** | ❌ Manual (must install Python 3.12 first) |
| **UV Install** | ❌ Not used |
| **Cross-Platform** | ⚠️ Windows only (setup.bat) |
| **System Impact** | ⚠️ Requires system Python 3.12 |
| **Best For** | Users who already have Python 3.12 |

**Pros:**
- ✅ Uses familiar pip
- ✅ No new tools to learn
- ✅ Works with existing Python installation

**Cons:**
- ❌ Must manually install Python 3.12 first
- ❌ Slower package installation (pip)
- ❌ Fails if wrong Python version
- ❌ Windows-only script

**Commands:**
```bash
# Windows (requires Python 3.12 already installed)
setup.bat

# Linux/macOS (manual)
python3.12 -m venv venv
source venv/bin/activate
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

---

### Option 3: Manual Installation

**Files:** None (manual commands)

| Feature | Details |
|---------|---------|
| **Ease of Use** | ⭐⭐ Multiple steps |
| **Speed** | ⭐⭐ 10-20 minutes |
| **Python Install** | ❌ Manual |
| **UV Install** | ❌ Optional |
| **Cross-Platform** | ✅ Works everywhere |
| **System Impact** | ⚠️ Depends on method |
| **Best For** | Advanced users, custom setups |

**Pros:**
- ✅ Full control over every step
- ✅ Can customize installation
- ✅ Learn how everything works

**Cons:**
- ❌ Most time-consuming
- ❌ Easy to make mistakes
- ❌ Must understand Python environments

**Commands:** See README.md "Manual Installation" section

---

## Installation Time Comparison

| Method | First-Time Install | Subsequent Installs |
|--------|-------------------|---------------------|
| **UV Setup** | ~2 minutes | ~1 minute |
| **Traditional** | ~15 minutes | ~10 minutes |
| **Manual** | ~20 minutes | ~15 minutes |

*Times assume good internet connection and modern hardware*

---

## Disk Space Comparison

| Method | Python Location | Size |
|--------|----------------|------|
| **UV Setup** | `~/.local/share/uv/python/` (Linux/macOS)<br>`%LOCALAPPDATA%\uv\python\` (Windows) | ~100MB (shared across projects) |
| **Traditional** | System-wide (`C:\Program Files\Python312\`) | ~100MB |
| **Manual** | Varies | Varies |

---

## Which Should You Choose?

### Choose **UV Setup** if:
- ✅ You want the fastest, easiest installation
- ✅ You don't have Python 3.12 installed
- ✅ You have Python 3.13+ and need 3.12
- ✅ You want isolated environments
- ✅ You value speed (10-100x faster)

### Choose **Traditional Setup** if:
- ✅ You already have Python 3.12 installed
- ✅ You prefer using pip
- ✅ You're on Windows only
- ✅ You don't want to install UV

### Choose **Manual Installation** if:
- ✅ You're an advanced user
- ✅ You need custom configuration
- ✅ You want to understand every step
- ✅ You have specific requirements

---

## FAQ

### Q: Is UV safe?
**A:** Yes! UV is created by Astral, the same team behind Ruff (the most popular Python linter). It's open-source and used by thousands of developers.

### Q: Can I use UV for other projects?
**A:** Absolutely! Once installed, UV works for any Python project and is 10-100x faster than pip.

### Q: What if I already have Python 3.14?
**A:** UV setup will download and use Python 3.12 automatically, without affecting your system Python 3.14.

### Q: Can I delete UV after installation?
**A:** Yes, but you'll need it for future package updates. UV is small (~10MB) and very useful.

### Q: Does UV work offline?
**A:** After first install, yes. UV caches Python and packages locally.

### Q: What's the `.venv` folder?
**A:** Your virtual environment. It contains Python 3.12 and all packages. You can delete and recreate it anytime.

---

## Recommendation

**For 95% of users:** Use `setup-uv.bat` or `setup-uv.sh`

It's the fastest, easiest, and most reliable method. UV is a modern, production-ready tool that makes Python development better.

**See also:**
- `QUICKSTART.md` - Quick start guide
- `UV_SETUP_SOLUTION.md` - Technical details
- `PYTHON_VERSION_FIX.md` - Why Python version matters
