# Quick Start Guide - TTS-Story

## 🚀 Fastest Installation (Recommended)

### Windows
```bash
git clone <repo-url>
cd TTS-Story
setup-uv.bat
```

### Linux/macOS
```bash
git clone <repo-url>
cd TTS-Story
chmod +x setup-uv.sh
./setup-uv.sh
```

**That's it!** The script automatically:
- ✅ Installs UV (fast package manager)
- ✅ Downloads Python 3.12 (no system installation needed!)
- ✅ Creates virtual environment
- ✅ Installs all dependencies

## What is UV?

**UV** is a modern, blazing-fast Python package and version manager:
- 🚀 **10-100x faster** than pip
- 🐍 **Auto-downloads Python** - no manual installation needed
- 🌍 **Cross-platform** - Windows, Linux, macOS
- 🔒 **Secure** - from Astral (creators of Ruff)

**Installation sources:**
- **Website:** https://astral.sh/uv
- **GitHub:** https://github.com/astral-sh/uv
- **Docs:** https://docs.astral.sh/uv/

## How It Works

### Traditional Setup (Old Way)
```
1. Download Python 3.12 from python.org
2. Install Python system-wide
3. Create venv manually
4. Wait 10+ minutes for pip to install packages
```

### UV Setup (New Way)
```
1. Run setup-uv.bat (or .sh)
2. UV downloads Python 3.12 automatically
3. UV creates venv automatically
4. UV installs packages in ~1 minute
```

## Manual UV Installation (Optional)

If you want to install UV yourself before running the setup:

### Windows (PowerShell)
```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

### Linux/macOS
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Using pip (if you already have Python)
```bash
pip install uv
```

## After Installation

### Windows
```bash
run.bat
```

### Linux/macOS
```bash
source .venv/bin/activate
python app.py
```

Then open: **http://localhost:5000**

## Troubleshooting

### "UV not found in PATH"
**Solution:** Close and reopen your terminal after UV installation.

### "Python 3.13 detected"
**Solution:** The setup script will automatically use Python 3.12 via UV, even if you have 3.13 installed.

### "espeak-ng not found"
**Solution:** Install espeak-ng:
- **Windows:** Download from https://github.com/espeak-ng/espeak-ng/releases
- **Ubuntu/Debian:** `sudo apt-get install espeak-ng`
- **macOS:** `brew install espeak-ng`

## Why UV Over Traditional Setup?

| Feature | Traditional (pip) | UV |
|---------|------------------|-----|
| **Speed** | Slow (10+ min) | Fast (1-2 min) |
| **Python Install** | Manual | Automatic |
| **Cross-Platform** | Manual setup | One script |
| **Version Management** | Manual | Automatic |
| **Disk Space** | System-wide | Isolated |

## Advanced: Using UV for Development

Once UV is installed, you can use it for all Python projects:

```bash
# Create new project with Python 3.12
uv venv --python 3.12

# Install packages (10-100x faster)
uv pip install package-name

# Install from requirements.txt
uv pip install -r requirements.txt

# List installed packages
uv pip list

# Upgrade packages
uv pip install --upgrade package-name
```

## Need Help?

- **UV Documentation:** https://docs.astral.sh/uv/
- **TTS-Story Issues:** Open an issue on GitHub
- **Python Version Issues:** See `PYTHON_VERSION_FIX.md`

---

**Note:** UV is maintained by Astral, the same team behind Ruff (the fastest Python linter). It's production-ready and used by thousands of developers worldwide.
