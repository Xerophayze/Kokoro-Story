# TTS-Story Documentation

## 🚀 Quick Start

**New users:** Run one command to install everything automatically:

### Windows
```bash
setup.bat
```

### Linux/macOS
```bash
chmod +x setup.sh
./setup.sh
```

**That's it!** The setup script will:
- ✅ Detect if UV is available (fast package manager)
- ✅ Offer to install UV if not found (10-100x faster than pip)
- ✅ Use UV for fast installation, or fall back to traditional pip
- ✅ Download Python 3.12 automatically (if using UV)
- ✅ Install all dependencies

Then run `run.bat` (Windows) or `python app.py` (Linux/macOS) and open http://localhost:5000

---

## 📚 Documentation

- **[Quick Start Guide](docs/QUICKSTART.md)** - Detailed installation guide
- **[Installation Options](docs/INSTALLATION_OPTIONS.md)** - Compare different setup methods
- **[Python Version Fix](docs/PYTHON_VERSION_FIX.md)** - Why Python 3.10-3.12 is required
- **[UV Setup Details](docs/UV_SETUP_SOLUTION.md)** - Technical details about UV
- **[Full README](README.md)** - Complete project documentation

---

## 🛠️ Setup Scripts

| Script | Purpose | Recommendation |
|--------|---------|----------------|
| **`setup.bat`** | Smart setup (Windows) | ⭐ **Use this** |
| **`setup.sh`** | Smart setup (Linux/macOS) | ⭐ **Use this** |
| `setup-uv.bat` | UV-only setup (Windows) | Advanced users |
| `setup-uv.sh` | UV-only setup (Linux/macOS) | Advanced users |
| **`run.bat`** | Start application (Windows) | After setup |
| **`run.sh`** | Start application (Linux/macOS) | After setup |

**Note:** The smart setup scripts (`setup.bat`/`setup.sh`) automatically detect and use UV if available, or offer to install it. You don't need to choose between scripts anymore!

---

## ❓ Common Questions

**Q: Which setup script should I use?**  
A: Just use `setup.bat` (Windows) or `setup.sh` (Linux/macOS). They're smart and will handle everything.

**Q: What if I don't want to install UV?**  
A: No problem! When prompted, choose 'N' and the script will use traditional pip installation.

**Q: I have Python 3.13 or 3.14, will it work?**  
A: If you choose to install UV (recommended), it will automatically download Python 3.12 for you. Otherwise, you'll need to install Python 3.12 manually.

**Q: What is UV?**  
A: A modern, fast Python package manager (10-100x faster than pip). See [docs/QUICKSTART.md](docs/QUICKSTART.md)

**Q: Can I use UV for other projects?**  
A: Yes! Once installed, UV works for any Python project and makes installations much faster.

---

## 🎯 Installation Flow

```
Run setup.bat or setup.sh
         ↓
    UV detected?
    ↙         ↘
  Yes          No
   ↓            ↓
Use UV    Ask to install UV?
(fast)      ↙         ↘
          Yes          No
           ↓            ↓
      Install UV   Use pip
           ↓       (traditional)
       Use UV
       (fast)
```

---

## 📖 Full Documentation

For complete project documentation, features, API endpoints, and usage instructions, see **[README.md](README.md)**
