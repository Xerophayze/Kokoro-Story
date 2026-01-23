@echo off
setlocal enabledelayedexpansion

REM Usage: git-sync.bat [optional commit message]
REM If you omit a commit message, a timestamp-based message is used.

for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set TODAY=%%a-%%b-%%c
for /f "tokens=1-2 delims=:." %%a in ("%time%") do set NOW=%%a%%b

if "%~1"=="" (
    set "COMMIT_MSG=Auto-sync !TODAY! !NOW!"
) else (
    set "COMMIT_MSG=%*"
)

echo === Checking repository status ===
git status
if errorlevel 1 goto :git_error

echo === Staging all changes ===
git add -A
if errorlevel 1 goto :git_error

echo === Committing with message: !COMMIT_MSG! ===
git commit -m "!COMMIT_MSG!"
if errorlevel 1 goto :commit_error

echo === Pulling latest changes (rebase) ===
git pull --rebase
if errorlevel 1 goto :git_error

echo === Pushing to origin ===
git push
if errorlevel 1 goto :git_error

echo.
echo ✅ Repository is up to date with origin.
goto :eof

:commit_error
echo.
echo ⚠️ Nothing to commit (working tree clean) or commit failed.
echo Skipping pull/push.
goto :eof

:git_error
echo.
echo ❌ Git command failed. Please review the messages above.
pause
goto :eof
