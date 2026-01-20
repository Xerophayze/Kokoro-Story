@echo off
setlocal enabledelayedexpansion

echo ========================================
echo TTS-Story Setup
echo ========================================
echo.

REM Check if UV is available
where uv >nul 2>&1
if %errorlevel% equ 0 (
    echo ✓ UV detected - using fast installation method
    echo.
    goto :UseUV
)

echo UV not detected. Checking installation options...
echo.
echo UV is a modern, fast Python package manager (10-100x faster than pip).
echo It can automatically download Python 3.12 for you.
echo.
choice /C YN /M "Would you like to install UV for faster setup"

if errorlevel 2 goto :TraditionalSetup
if errorlevel 1 goto :InstallUV

:InstallUV
echo.
echo [1/2] Installing UV...
echo This will download UV from https://astral.sh/uv
echo.

REM Install UV using PowerShell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"


if errorlevel 1 (
    echo.
    echo WARNING: UV installation failed.
    echo Falling back to traditional setup...
    echo.
    timeout /t 3 >nul
    goto :TraditionalSetup
)

echo.
echo ✓ UV installed successfully!
echo.

REM Add UV to PATH for current session
REM UV typically installs to %USERPROFILE%\.local\bin or %LOCALAPPDATA%\Programs\uv
set "UV_PATH_1=%USERPROFILE%\.local\bin"
set "UV_PATH_2=%LOCALAPPDATA%\Programs\uv"

REM Check which path exists and add to PATH
if exist "%UV_PATH_1%\uv.exe" (
    echo Adding UV to PATH: %UV_PATH_1%
    set "PATH=%UV_PATH_1%;%PATH%"
) else if exist "%UV_PATH_2%\uv.exe" (
    echo Adding UV to PATH: %UV_PATH_2%
    set "PATH=%UV_PATH_2%;%PATH%"
)

echo.

REM Try to use UV now that we've updated PATH
where uv >nul 2>&1
if errorlevel 1 (
    echo WARNING: UV not found in PATH even after adding common locations.
    echo UV may be installed in a non-standard location.
    echo.
    echo Please either:
    echo 1. Close this terminal and run setup.bat again (recommended)
    echo 2. Continue with traditional setup now
    echo.
    choice /C YN /M "Continue with traditional setup"
    if errorlevel 2 (
        echo.
        echo Please restart your terminal and run: setup.bat
        pause
        exit /b 0
    )
    goto :TraditionalSetup
)

echo ✓ UV is now available!
echo.


:UseUV
echo [2/2] Running UV-based setup...
echo.

REM Check if setup-uv.bat exists
if not exist "setup-uv.bat" (
    echo ERROR: setup-uv.bat not found!
    echo Falling back to traditional setup...
    goto :TraditionalSetup
)

REM Call the UV setup script
call setup-uv.bat
exit /b %errorlevel%

:TraditionalSetup
echo.
echo ========================================
echo Traditional Setup (using pip)
echo ========================================
echo.

REM Check Python installation and version
echo [1/7] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo.
    echo This project requires Python 3.10, 3.11, or 3.12
    echo.
    echo Installation options:
    echo 1. Download from python.org: https://www.python.org/downloads/
    echo 2. Install UV and run this script again (UV will download Python automatically)
    echo.
    echo See DOCS.md for detailed instructions.
    pause
    exit /b 1
)

REM Get Python version
for /f "tokens=2" %%i in ('python --version 2^>&1') do set PYTHON_VERSION=%%i
echo Found Python %PYTHON_VERSION%

REM Extract major and minor version (e.g., 3.12 from 3.12.7)
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set PYTHON_MAJOR=%%a
    set PYTHON_MINOR=%%b
)

REM Check if Python version is compatible (3.10, 3.11, or 3.12)
set PYTHON_OK=0
if "%PYTHON_MAJOR%"=="3" (
    if "%PYTHON_MINOR%"=="10" set PYTHON_OK=1
    if "%PYTHON_MINOR%"=="11" set PYTHON_OK=1
    if "%PYTHON_MINOR%"=="12" set PYTHON_OK=1
)

if "%PYTHON_OK%"=="0" (
    echo.
    echo ========================================
    echo ERROR: Incompatible Python Version
    echo ========================================
    echo.
    echo You have Python %PYTHON_VERSION%
    echo This project requires Python 3.10, 3.11, or 3.12
    echo.
    echo Python 3.13+ is not yet supported due to the kokoro package.
    echo.
    echo Recommended solution: Install UV and run this script again.
    echo UV will automatically download Python 3.12 for you.
    echo.
    echo Or install Python 3.12 from: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo ✓ Python version is compatible

REM Create virtual environment
echo.
echo [2/7] Creating virtual environment...
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
echo [3/7] Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo.
echo [4/7] Upgrading pip...
python -m pip install --upgrade pip --quiet

REM Install PyTorch
echo.
echo [5/7] Installing PyTorch...
echo This may take several minutes...
echo.

echo Installing PyTorch with CUDA 12.1 support...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

if errorlevel 1 (
    echo.
    echo PyTorch installation failed, trying CPU version...
    pip install torch torchvision torchaudio
)

REM Install other dependencies
echo.
echo [6/7] Installing other Python dependencies...
findstr /v /i "torch" requirements.txt > temp_requirements.txt
pip install -r temp_requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
del temp_requirements.txt

REM Install Chatterbox
echo.
echo [7/7] Installing Chatterbox Turbo runtime...
pip install chatterbox-tts --no-deps
if errorlevel 1 (
    echo WARNING: Failed to install chatterbox-tts
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
echo TIP: For faster package installation in the future, consider using UV!
echo      Just run this setup script again and choose 'Y' when prompted.
echo.
pause
