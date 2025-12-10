@echo off
echo Killing processes on ports 3000 and 8000...
echo.

REM Kill process on port 3000
echo Checking port 3000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3000') do (
    echo Found PID %%a on port 3000
    taskkill /F /PID %%a 2>nul
    if errorlevel 1 (
        echo Failed to kill PID %%a
    ) else (
        echo Successfully killed PID %%a
    )
)

echo.
REM Kill process on port 8000
echo Checking port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do (
    echo Found PID %%a on port 8000
    taskkill /F /PID %%a 2>nul
    if errorlevel 1 (
        echo Failed to kill PID %%a
    ) else (
        echo Successfully killed PID %%a
    )
)

echo.
echo Done!
pause
