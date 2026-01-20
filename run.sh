#!/usr/bin/env bash
set -e

echo "========================================"
echo "Starting TTS-Story"
echo "========================================"
echo

# Check that virtual environment exists (check both .venv and venv)
VENV_PATH=""
if [ -f ".venv/bin/activate" ]; then
  VENV_PATH=".venv"
elif [ -f "venv/bin/activate" ]; then
  VENV_PATH="venv"
else
  echo "ERROR: Virtual environment not found."
  echo "Please run ./setup.sh first."
  exit 1
fi

# Activate virtual environment
# shellcheck disable=SC1091
source "$VENV_PATH/bin/activate"

# Check CUDA availability (optional)
python - << 'EOF'
try:
    import torch
    print("CUDA Available:", torch.cuda.is_available())
except Exception as e:
    print("WARNING: Could not check CUDA status:", e)
EOF

echo
echo "Starting Flask server..."
echo "Open your browser to: http://localhost:5000"
echo "Press Ctrl+C to stop the server"
echo

# Start the application
python app.py
