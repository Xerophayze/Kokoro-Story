#!/usr/bin/env bash
set -e

echo "========================================"
echo "Starting Kokoro-Story"
echo "========================================"
echo

# Check that virtual environment exists
if [ ! -f "venv/bin/activate" ]; then
  echo "ERROR: Virtual environment not found."
  echo "Please run ./setup.sh first."
  exit 1
fi

# Activate virtual environment
# shellcheck disable=SC1091
source "venv/bin/activate"

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
