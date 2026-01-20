@echo off
setlocal enabledelayedexpansion

echo ========================================
echo TTS-Story Setup with UV
echo ========================================
echo.
echo This script will:
echo 1. Install UV (fast Python package manager)
echo 2. Use UV to install Python 3.12 automatically
echo 3. Create virtual environment
echo 4. Install all dependencies
echo.

REM Check if uv is already installed
where uv >nul 2>&1
if %errorlevel% equ 0 (
    echo ✓ UV is already installed
    goto :SkipUVInstall
)

echo [1/6] Installing UV...
echo This will download and install UV from https://astral.sh/uv
echo.

REM Install UV using PowerShell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"

if errorlevel 1 (
    echo.
    echo ========================================
    echo ERROR: Failed to install UV
    echo ========================================
    echo.
    echo Please install UV manually:
    echo 1. Open PowerShell as Administrator
    echo 2. Run: irm https://astral.sh/uv/install.ps1 ^| iex
    echo.
    echo Or download from: https://github.com/astral-sh/uv/releases
    echo.
    pause
    exit /b 1
)

echo.
echo ✓ UV installed successfully!
echo.
echo NOTE: You may need to restart your terminal for UV to be in your PATH.
echo      If the next step fails, close this window and run setup-uv.bat again.
echo.
pause

:SkipUVInstall

REM Verify UV is accessible
where uv >nul 2>&1
if errorlevel 1 (
    echo.
    echo ========================================
    echo ERROR: UV not found in PATH
    echo ========================================
    echo.
    echo UV was installed but is not in your PATH yet.
    echo Please close this terminal and open a new one, then run:
    echo   setup-uv.bat
    echo.
    pause
    exit /b 1
)

REM Get UV version
for /f "tokens=*" %%i in ('uv --version 2^>^&1') do set UV_VERSION=%%i
echo ✓ Using %UV_VERSION%
echo.

REM Check if venv already exists
if exist .venv (
    echo [2/6] Virtual environment already exists
    echo.
    choice /C YN /M "Do you want to delete and recreate it"
    if errorlevel 2 goto :SkipVenvCreation
    if errorlevel 1 (
        echo Removing old virtual environment...
        rmdir /s /q .venv
    )
)

echo [2/6] Creating virtual environment with Python 3.12...
echo UV will automatically download Python 3.12 if needed.
echo This may take a few minutes on first run...
echo.

REM Create venv with Python 3.12 (UV downloads it automatically)
uv venv --python 3.12

if errorlevel 1 (
    echo.
    echo ========================================
    echo ERROR: Failed to create virtual environment
    echo ========================================
    echo.
    echo UV could not create the virtual environment.
    echo This might be due to network issues or permissions.
    echo.
    pause
    exit /b 1
)

echo ✓ Virtual environment created with Python 3.12
echo.

:SkipVenvCreation

REM Activate virtual environment
echo [3/6] Activating virtual environment...
call .venv\Scripts\activate.bat

if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment
    pause
    exit /b 1
)

echo ✓ Virtual environment activated
echo.

REM Verify Python version
echo [4/6] Verifying Python version...
python --version
echo.

REM Install PyTorch with CUDA support
echo [5/6] Installing PyTorch with CUDA 12.1 support...
echo This may take several minutes...
echo.

uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

if errorlevel 1 (
    echo.
    echo PyTorch CUDA installation failed, trying CPU version...
    uv pip install torch torchvision torchaudio
)

echo ✓ PyTorch installed
echo.

REM Install other dependencies
echo [6/6] Installing other dependencies...
echo This may take several minutes...
echo.

uv pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ========================================
    echo ERROR: Failed to install dependencies
    echo ========================================
    echo.
    echo Some packages failed to install.
    echo Please check the error messages above.
    echo.
    pause
    exit /b 1
)

echo ✓ All dependencies installed
echo.

REM Install Chatterbox
echo Installing Chatterbox Turbo runtime...
uv pip install chatterbox-tts --no-deps

if errorlevel 1 (
    echo WARNING: Failed to install chatterbox-tts
    echo You can try installing it manually later with:
    echo   uv pip install chatterbox-tts --no-deps
)

REM Create voice prompts folder
if not exist "data\voice_prompts" (
    mkdir "data\voice_prompts"
)

REM Check for espeak-ng
echo.
echo ========================================
echo Checking espeak-ng...
echo ========================================
where espeak-ng >nul 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: espeak-ng not found!
    echo.
    echo Please install espeak-ng manually:
    echo 1. Download from: https://github.com/espeak-ng/espeak-ng/releases
    echo 2. Get the file: espeak-ng-X64.msi
    echo 3. Run the installer
    echo 4. Restart your terminal
    echo.
    echo The application will NOT work without espeak-ng!
    echo.
) else (
    echo ✓ espeak-ng is installed!
)

REM Verify installation
echo.
echo ========================================
echo Verifying Installation
echo ========================================
echo.
python -c "import torch; print('✓ PyTorch Version:', torch.__version__); print('✓ CUDA Available:', torch.cuda.is_available()); print('✓ CUDA Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU-only')"

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Next steps:
echo 1. If espeak-ng is not installed, install it now
echo 2. Run: run.bat
echo 3. Open browser to: http://localhost:5000
echo.
echo Note: UV is 10-100x faster than pip for future installs!
echo.
pause
