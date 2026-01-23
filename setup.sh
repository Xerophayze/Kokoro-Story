#!/usr/bin/env bash
set -e

echo "========================================"
echo "TTS-Story Setup (Linux/macOS)"
echo "========================================"
echo

# 1/6 Check Python installation
echo "[1/6] Checking Python installation..."
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is not installed or not in PATH"
  echo "Please install Python 3.9 or higher."
  exit 1
fi

PYTHON="python3"
PYTHON_VERSION=$($PYTHON --version 2>&1)
echo "Found $PYTHON_VERSION"

# 2/6 Create virtual environment
echo
echo "[2/6] Creating virtual environment..."
if [ -d "venv" ]; then
  echo "Virtual environment already exists, skipping..."
else
  $PYTHON -m venv venv
fi

# 3/6 Activate virtual environment
echo
echo "[3/6] Activating virtual environment..."
# shellcheck disable=SC1091
source "venv/bin/activate"

# 4/6 Upgrade pip
echo
echo "[4/6] Upgrading pip..."
python -m pip install --upgrade pip --quiet

# 5/6 Install PyTorch (CUDA if available, otherwise CPU)
echo
echo "[5/6] Installing PyTorch..."
echo "This may take several minutes..."
echo

# Try CUDA 12.1 wheels first, then fall back to default (which may be CPU)
if ! pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121; then
  echo "PyTorch CUDA 12.1 install failed, trying default PyTorch (CPU or auto-detected CUDA)..."
  pip install torch torchvision torchaudio
fi

# 6/6 Install other dependencies (excluding torch packages already installed)
echo
echo "[6/6] Installing other Python dependencies..."
grep -vi "^torch" requirements.txt > temp_requirements.txt || true
pip install -r temp_requirements.txt
rm -f temp_requirements.txt

echo
echo "========================================"
echo "Checking espeak-ng..."
echo "========================================"
if ! command -v espeak-ng >/dev/null 2>&1; then
  echo
  echo "WARNING: espeak-ng not found!"
  echo
  echo "Please install espeak-ng using your package manager, for example:"
  echo "  Debian/Ubuntu: sudo apt-get install espeak-ng"
  echo "  Arch Linux:   sudo pacman -S espeak-ng"
  echo "  Fedora:       sudo dnf install espeak-ng"
  echo
  echo "The application may not work correctly without espeak-ng."
else
  echo "espeak-ng is installed!"
fi

echo
echo "========================================"
echo "Verifying Installation"
echo "========================================"
echo
python - << 'EOF'
import torch
print("PyTorch Version:", torch.__version__)
print("CUDA Available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("CUDA Device:", torch.cuda.get_device_name(0))
else:
    print("CUDA Device: CPU-only")
EOF

echo
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo
echo "Next steps:"
echo "  1. Ensure espeak-ng is installed (see instructions above)."
echo "  2. Run: ./run.sh"
echo "  3. Open browser to: http://localhost:5000"
echo
