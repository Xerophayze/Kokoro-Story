@echo off
echo ========================================
echo TTS-Story Setup
echo ========================================
echo.

REM Check Python installation
echo [1/7] Checking Python installation...
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

REM Install PyTorch (let pip/PyTorch auto-detect CUDA)
echo.
echo [5/8] Installing PyTorch...
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

REM Install other dependencies (excluding torch + chatterbox runtime handled separately)
echo.
echo [6/8] Installing other Python dependencies...
findstr /v /i "torch" requirements.txt > temp_requirements.txt
pip install -r temp_requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
del temp_requirements.txt

REM Install local Chatterbox runtime
echo.
echo [7/8] Installing Chatterbox Turbo runtime...
pip install chatterbox-tts --no-deps
if errorlevel 1 (
    echo ERROR: Failed to install chatterbox-tts
    pause
    exit /b 1
)

call :EnsureVoicePromptFolder
call :InstallRubberBand

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
goto :EOF

:InstallRubberBand
echo.
echo [8/8] Installing Rubber Band CLI...
set "RB_DIR=%~dp0tools\rubberband"
set "RB_URL=https://breakfastquay.com/files/releases/rubberband-4.0.0-gpl-executable-windows.zip"
set "RB_ZIP=%TEMP%\rubberband_cli.zip"
set "RB_EXTRACT=%TEMP%\rubberband_cli_extract"

if exist "%RB_DIR%\rubberband.exe" (
    echo Rubber Band CLI already present.
    goto :EOF
)

if not exist "%~dp0tools" (
    mkdir "%~dp0tools"
) >nul 2>&1

if exist "%RB_ZIP%" del "%RB_ZIP%" >nul 2>&1
if exist "%RB_EXTRACT%" rmdir /s /q "%RB_EXTRACT%" >nul 2>&1

echo Downloading Rubber Band CLI from: %RB_URL%
powershell -NoLogo -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13; Invoke-WebRequest -Uri '%RB_URL%' -OutFile '%RB_ZIP%' -UseBasicParsing -ErrorAction Stop; } catch { Write-Error $_.Exception.Message; exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo WARNING: Failed to download Rubber Band CLI. FX will fall back to basic processing.
    goto :EOF
)

powershell -Command "Expand-Archive -Path '%RB_ZIP%' -DestinationPath '%RB_EXTRACT%' -Force" >nul 2>&1
if errorlevel 1 (
    echo WARNING: Failed to extract Rubber Band CLI archive.
    goto :EOF
)

set "RB_SOURCE="
for /f "delims=" %%F in ('dir /b /s "%RB_EXTRACT%\rubberband.exe" 2^>nul') do (
    set "RB_SOURCE=%%F"
    goto :FoundRB
)
:FoundRB
if not defined RB_SOURCE (
    echo WARNING: rubberband.exe not found in downloaded archive.
    goto :EOF
)

for %%F in ("%RB_SOURCE%") do set "RB_SOURCE_DIR=%%~dpF"
if not defined RB_SOURCE_DIR (
    echo WARNING: Unable to determine Rubber Band source directory.
    goto :EOF
)

if exist "%RB_DIR%" rmdir /s /q "%RB_DIR%" >nul 2>&1
mkdir "%RB_DIR%" >nul 2>&1
xcopy /E /I /Y "%RB_SOURCE_DIR%*.*" "%RB_DIR%\" >nul
if errorlevel 1 (
    echo WARNING: Failed to copy Rubber Band CLI files to tools directory.
    goto :EOF
)

echo Rubber Band CLI installed to %RB_DIR%.

if exist "%RB_ZIP%" del "%RB_ZIP%" >nul 2>&1
if exist "%RB_EXTRACT%" rmdir /s /q "%RB_EXTRACT%" >nul 2>&1
goto :EOF
