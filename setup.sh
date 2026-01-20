#!/bin/bash

set -e  # Exit on error

echo "========================================"
echo "TTS-Story Setup"
echo "========================================"
echo ""

# Check if UV is available
if command -v uv &> /dev/null; then
    echo "✓ UV detected - using fast installation method"
    echo ""
    USE_UV=true
else
    echo "UV not detected. Checking installation options..."
    echo ""
    echo "UV is a modern, fast Python package manager (10-100x faster than pip)."
    echo "It can automatically download Python 3.12 for you."
    echo ""
    read -p "Would you like to install UV for faster setup? (Y/n) " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
        echo ""
        echo "[1/2] Installing UV..."
        echo "This will download UV from https://astral.sh/uv"
        echo ""
        
        # Install UV
        curl -LsSf https://astral.sh/uv/install.sh | sh
        
        if [ $? -ne 0 ]; then
            echo ""
            echo "WARNING: UV installation failed."
            echo "Falling back to traditional setup..."
            echo ""
            sleep 2
            USE_UV=false
        else
            echo ""
            echo "✓ UV installed successfully!"
            echo ""
            
            # Source the UV environment
            export PATH="$HOME/.cargo/bin:$PATH"
            
            # Check if UV is now available
            if command -v uv &> /dev/null; then
                USE_UV=true
            else
                echo "UV not yet in PATH. Please run:"
                echo "  export PATH=\"\$HOME/.cargo/bin:\$PATH\""
                echo "Or restart your terminal and run: ./setup.sh"
                echo ""
                read -p "Continue with traditional setup? (Y/n) " -n 1 -r
                echo ""
                if [[ $REPLY =~ ^[Nn]$ ]]; then
                    echo ""
                    echo "Please restart your terminal and run: ./setup.sh"
                    exit 0
                fi
                USE_UV=false
            fi
        fi
    else
        USE_UV=false
    fi
fi

# Use UV setup if available
if [ "$USE_UV" = true ]; then
    echo "[2/2] Running UV-based setup..."
    echo ""
    
    # Check if setup-uv.sh exists
    if [ ! -f "setup-uv.sh" ]; then
        echo "ERROR: setup-uv.sh not found!"
        echo "Falling back to traditional setup..."
        USE_UV=false
    else
        # Make it executable and run it
        chmod +x setup-uv.sh
        ./setup-uv.sh
        exit $?
    fi
fi

# Traditional setup
echo ""
echo "========================================"
echo "Traditional Setup (using pip)"
echo "========================================"
echo ""

# Check Python installation and version
echo "[1/7] Checking Python installation..."
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "ERROR: Python is not installed or not in PATH"
    echo ""
    echo "This project requires Python 3.10, 3.11, or 3.12"
    echo ""
    echo "Installation options:"
    echo "1. Install via package manager (apt, brew, dnf, etc.)"
    echo "2. Install UV and run this script again (UV will download Python automatically)"
    echo ""
    echo "See DOCS.md for detailed instructions."
    exit 1
fi

# Use python3 if available, otherwise python
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
else
    PYTHON_CMD=python
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
echo "Found Python $PYTHON_VERSION"

# Extract major and minor version
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

# Check if Python version is compatible (3.10, 3.11, or 3.12)
PYTHON_OK=false
if [ "$PYTHON_MAJOR" = "3" ]; then
    if [ "$PYTHON_MINOR" = "10" ] || [ "$PYTHON_MINOR" = "11" ] || [ "$PYTHON_MINOR" = "12" ]; then
        PYTHON_OK=true
    fi
fi

if [ "$PYTHON_OK" = false ]; then
    echo ""
    echo "========================================"
    echo "ERROR: Incompatible Python Version"
    echo "========================================"
    echo ""
    echo "You have Python $PYTHON_VERSION"
    echo "This project requires Python 3.10, 3.11, or 3.12"
    echo ""
    echo "Python 3.13+ is not yet supported due to the kokoro package."
    echo ""
    echo "Recommended solution: Install UV and run this script again."
    echo "UV will automatically download Python 3.12 for you."
    echo ""
    echo "Or install Python 3.12 via your package manager."
    echo ""
    exit 1
fi

echo "✓ Python version is compatible"

# Create virtual environment
echo ""
echo "[2/7] Creating virtual environment..."
if [ -d "venv" ]; then
    echo "Virtual environment already exists, skipping..."
else
    $PYTHON_CMD -m venv venv
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create virtual environment"
        exit 1
    fi
fi

# Activate virtual environment
echo ""
echo "[3/7] Activating virtual environment..."
source venv/bin/activate

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to activate virtual environment"
    exit 1
fi

echo "✓ Virtual environment activated"

# Upgrade pip
echo ""
echo "[4/7] Upgrading pip..."
python -m pip install --upgrade pip --quiet

# Install PyTorch
echo ""
echo "[5/7] Installing PyTorch..."
echo "This may take several minutes..."
echo ""

echo "Installing PyTorch with CUDA 12.1 support..."
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

if [ $? -ne 0 ]; then
    echo ""
    echo "PyTorch installation failed, trying CPU version..."
    pip install torch torchvision torchaudio
fi

# Install other dependencies
echo ""
echo "[6/7] Installing other Python dependencies..."
grep -v -i "torch" requirements.txt > temp_requirements.txt
pip install -r temp_requirements.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install dependencies"
    exit 1
fi
rm temp_requirements.txt

# Install Chatterbox
echo ""
echo "[7/7] Installing Chatterbox Turbo runtime..."
pip install chatterbox-tts --no-deps
if [ $? -ne 0 ]; then
    echo "WARNING: Failed to install chatterbox-tts"
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
echo "2. Activate the environment: source venv/bin/activate"
echo "3. Run: python app.py"
echo "4. Open browser to: http://localhost:5000"
echo ""
echo "TIP: For faster package installation in the future, consider using UV!"
echo "     Just run this setup script again and choose 'Y' when prompted."
echo ""
