@echo off
echo ========================================
echo Kokoro-Story Setup
echo ========================================
echo.

REM Check Python installation
echo [1/6] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.9 or higher from python.org
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Found Python %PYTHON_VERSION%

REM Create virtual environment
echo.
echo [2/6] Creating virtual environment...
if exist venv (
    echo Virtual environment already exists, skipping...
) else (
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
)

REM Activate virtual environment
echo.
echo [3/6] Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo.
echo [4/6] Upgrading pip...
python -m pip install --upgrade pip --quiet

REM Install PyTorch (let pip/PyTorch auto-detect CUDA)
echo.
echo [5/6] Installing PyTorch...
echo This may take several minutes...
echo.

REM Check if CUDA is available using Python
python -c "import sys; sys.exit(0)" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not working in virtual environment
    pause
    exit /b 1
)

REM Install PyTorch with CUDA 12.1 (most compatible)
echo Installing PyTorch with CUDA 12.1 support...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

if errorlevel 1 (
    echo.
    echo PyTorch installation failed, trying CPU version...
    pip install torch torchvision torchaudio
)

REM Install other dependencies
echo.
echo [6/6] Installing other Python dependencies...
findstr /v /i "torch" requirements.txt > temp_requirements.txt
pip install -r temp_requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
del temp_requirements.txt

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
    echo espeak-ng is installed!
)

REM Verify installation
echo.
echo ========================================
echo Verifying Installation
echo ========================================
echo.
python -c "import torch; print('PyTorch Version:', torch.__version__); print('CUDA Available:', torch.cuda.is_available()); print('CUDA Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU-only')"

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
pause
