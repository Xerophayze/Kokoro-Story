@echo off
echo ========================================
echo Starting TTS-Story
echo ========================================
echo.

REM Check if venv exists (check both .venv and venv)
set "VENV_PATH="
if exist ".venv\Scripts\activate.bat" (
    set "VENV_PATH=.venv"
) else if exist "venv\Scripts\activate.bat" (
    set "VENV_PATH=venv"
) else (
    echo ERROR: Virtual environment not found
    echo Please run setup.bat first
    pause
    exit /b 1
)

REM Activate virtual environment
call %VENV_PATH%\Scripts\activate.bat

REM Ensure Rubber Band CLI is on PATH if bundled
set "RB_EXE=%~dp0tools\rubberband\rubberband.exe"
if exist "%RB_EXE%" (
    set "PATH=%~dp0tools\rubberband;%PATH%"
    echo Rubber Band CLI ready: %RB_EXE%
) else (
    echo WARNING: Rubber Band CLI not found (expected %RB_EXE%)
    echo          Pitch/tempo FX will fall back to lower-quality processing.
)

REM Skip CUDA check at startup (can hang on some systems)
REM CUDA availability will be detected when the app starts

echo.
echo Starting Flask server...
echo Open your browser to: http://localhost:5000
echo Press Ctrl+C to stop the server
echo.

REM Start the application
python app.py

pause
