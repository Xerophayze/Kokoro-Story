#!/bin/bash

set -e  # Exit on error

echo "========================================"
echo "TTS-Story Setup with UV"
echo "========================================"
echo ""
echo "This script will:"
echo "1. Install UV (fast Python package manager)"
echo "2. Use UV to install Python 3.12 automatically"
echo "3. Create virtual environment"
echo "4. Install all dependencies"
echo ""

# Check if uv is already installed
if command -v uv &> /dev/null; then
    echo "✓ UV is already installed"
else
    echo "[1/6] Installing UV..."
    echo "This will download and install UV from https://astral.sh/uv"
    echo ""
    
    # Install UV
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    if [ $? -ne 0 ]; then
        echo ""
        echo "========================================"
        echo "ERROR: Failed to install UV"
        echo "========================================"
        echo ""
        echo "Please install UV manually:"
        echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo ""
        echo "Or download from: https://github.com/astral-sh/uv/releases"
        echo ""
        exit 1
    fi
    
    echo ""
    echo "✓ UV installed successfully!"
    echo ""
    
    # Source the UV environment
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Verify UV is accessible
if ! command -v uv &> /dev/null; then
    echo ""
    echo "========================================"
    echo "ERROR: UV not found in PATH"
    echo "========================================"
    echo ""
    echo "UV was installed but is not in your PATH yet."
    echo "Please run:"
    echo "  export PATH=\"\$HOME/.cargo/bin:\$PATH\""
    echo "Or restart your terminal and run this script again."
    echo ""
    exit 1
fi

# Get UV version
UV_VERSION=$(uv --version)
echo "✓ Using $UV_VERSION"
echo ""

# Check if venv already exists
if [ -d ".venv" ]; then
    echo "[2/6] Virtual environment already exists"
    echo ""
    read -p "Do you want to delete and recreate it? (y/N) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removing old virtual environment..."
        rm -rf .venv
    else
        echo "Keeping existing virtual environment..."
    fi
fi

if [ ! -d ".venv" ]; then
    echo "[2/6] Creating virtual environment with Python 3.12..."
    echo "UV will automatically download Python 3.12 if needed."
    echo "This may take a few minutes on first run..."
    echo ""
    
    # Create venv with Python 3.12 (UV downloads it automatically)
    uv venv --python 3.12
    
    if [ $? -ne 0 ]; then
        echo ""
        echo "========================================"
        echo "ERROR: Failed to create virtual environment"
        echo "========================================"
        echo ""
        echo "UV could not create the virtual environment."
        echo "This might be due to network issues or permissions."
        echo ""
        exit 1
    fi
    
    echo "✓ Virtual environment created with Python 3.12"
    echo ""
fi

# Activate virtual environment
echo "[3/6] Activating virtual environment..."
source .venv/bin/activate

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to activate virtual environment"
    exit 1
fi

echo "✓ Virtual environment activated"
echo ""

# Verify Python version
echo "[4/6] Verifying Python version..."
python --version
echo ""

# Install PyTorch with CUDA support
echo "[5/6] Installing PyTorch with CUDA 12.1 support..."
echo "This may take several minutes..."
echo ""

uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

if [ $? -ne 0 ]; then
    echo ""
    echo "PyTorch CUDA installation failed, trying CPU version..."
    uv pip install torch torchvision torchaudio
fi

echo "✓ PyTorch installed"
echo ""

# Install other dependencies
echo "[6/6] Installing other dependencies..."
echo "This may take several minutes..."
echo ""

uv pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo ""
    echo "========================================"
    echo "ERROR: Failed to install dependencies"
    echo "========================================"
    echo ""
    echo "Some packages failed to install."
    echo "Please check the error messages above."
    echo ""
    exit 1
fi

echo "✓ All dependencies installed"
echo ""

# Install Chatterbox
echo "Installing Chatterbox Turbo runtime..."
uv pip install chatterbox-tts --no-deps

if [ $? -ne 0 ]; then
    echo "WARNING: Failed to install chatterbox-tts"
    echo "You can try installing it manually later with:"
    echo "  uv pip install chatterbox-tts --no-deps"
fi

# Create voice prompts folder
if [ ! -d "data/voice_prompts" ]; then
    mkdir -p "data/voice_prompts"
fi

# Check for espeak-ng
echo ""
echo "========================================"
echo "Checking espeak-ng..."
echo "========================================"
if command -v espeak-ng &> /dev/null; then
    echo "✓ espeak-ng is installed!"
else
    echo ""
    echo "WARNING: espeak-ng not found!"
    echo ""
    echo "Please install espeak-ng:"
    echo ""
    echo "Ubuntu/Debian:"
    echo "  sudo apt-get install espeak-ng"
    echo ""
    echo "macOS:"
    echo "  brew install espeak-ng"
    echo ""
    echo "Fedora/RHEL:"
    echo "  sudo dnf install espeak-ng"
    echo ""
    echo "The application will NOT work without espeak-ng!"
    echo ""
fi

# Verify installation
echo ""
echo "========================================"
echo "Verifying Installation"
echo "========================================"
echo ""
python -c "import torch; print('✓ PyTorch Version:', torch.__version__); print('✓ CUDA Available:', torch.cuda.is_available()); print('✓ CUDA Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU-only')"

echo ""
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. If espeak-ng is not installed, install it now"
echo "2. Activate the environment: source .venv/bin/activate"
echo "3. Run: python app.py"
echo "4. Open browser to: http://localhost:5000"
echo ""
echo "Note: UV is 10-100x faster than pip for future installs!"
echo ""
