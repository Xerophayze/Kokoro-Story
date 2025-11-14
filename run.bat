@echo off
echo ========================================
echo Starting Kokoro-Story
echo ========================================
echo.

REM Check if venv exists
if not exist "venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found
    echo Please run setup.bat first
    pause
    exit /b 1
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Check CUDA availability
python -c "import torch; print('CUDA Available:', torch.cuda.is_available())" 2>nul
if errorlevel 1 (
    echo WARNING: Could not check CUDA status
)

echo.
echo Starting Flask server...
echo Open your browser to: http://localhost:5000
echo Press Ctrl+C to stop the server
echo.

REM Start the application
python app.py

pause
