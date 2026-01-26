@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "REPO_URL=https://github.com/Xerophayze/TTS-Story.git"
set "REPO_DIR=TTS-Story"
set "GIT_INSTALLER_URL=https://github.com/git-for-windows/git/releases/latest/download/Git-2.44.0-64-bit.exe"
set "GIT_INSTALLER=%TEMP%\git-installer.exe"

echo ========================================
echo TTS-Story Windows Installer
echo ========================================
echo.

echo Checking Git installation...
where git >nul 2>&1
if errorlevel 1 (
    echo Git not found. Downloading and installing Git for Windows...
    powershell -NoLogo -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13; Invoke-WebRequest -Uri '%GIT_INSTALLER_URL%' -OutFile '%GIT_INSTALLER%' -UseBasicParsing -ErrorAction Stop; } catch { Write-Error $_.Exception.Message; exit 1 }"
    if errorlevel 1 (
        echo ERROR: Failed to download Git installer.
        pause
        exit /b 1
    )

    "%GIT_INSTALLER%" /VERYSILENT /NORESTART /NOCANCEL /SP-
    if errorlevel 1 (
        echo ERROR: Git installer failed.
        pause
        exit /b 1
    )

    set "PATH=%ProgramFiles%\Git\cmd;%PATH%"
    where git >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Git installed but not found in PATH. Please restart your terminal.
        pause
        exit /b 1
    )
) else (
    echo Git is installed.
)

echo.
echo Cloning repository...
if exist "%REPO_DIR%" (
    echo Folder "%REPO_DIR%" already exists. Skipping clone.
) else (
    git clone "%REPO_URL%" "%REPO_DIR%"
    if errorlevel 1 (
        echo ERROR: Git clone failed.
        pause
        exit /b 1
    )
)

echo.
echo Running setup.bat...
if exist "%REPO_DIR%\setup.bat" (
    pushd "%REPO_DIR%"
    call setup.bat
    popd
) else (
    echo ERROR: setup.bat not found in %REPO_DIR%.
    pause
    exit /b 1
)

echo.
echo ✅ Install complete.
pause
