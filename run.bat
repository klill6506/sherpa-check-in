@echo off
echo ==========================================
echo  Sherpa Check-In App
echo ==========================================
echo.

:: Change to the script's directory (works from any drive)
cd /d "%~dp0"

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python from https://python.org
    pause
    exit /b 1
)

:: Check if virtual environment exists, create if not
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Install/upgrade dependencies
echo Installing dependencies...
pip install -q -r requirements.txt

:: Create .env file if it doesn't exist
if not exist ".env" (
    echo Creating default .env file...
    (
        echo SECRET_KEY=dev-secret-change-in-production
        echo ADMIN_PASSWORD=admin
        echo PORT=8001
        echo LOG_LEVEL=INFO
        echo # SMTP settings ^(uncomment and configure for email^)
        echo # SMTP_SERVER=smtp.office365.com
        echo # SMTP_PORT=587
        echo # SMTP_USERNAME=your-email@example.com
        echo # SMTP_PASSWORD=your-password
        echo # FROM_EMAIL=your-email@example.com
        echo # USE_TLS=1
    ) > .env
    echo Default .env created. Edit it to configure SMTP settings.
)

echo.
echo ==========================================
echo  Starting server on http://localhost:8001
echo  Admin panel: http://localhost:8001/admin
echo  Press Ctrl+C to stop
echo ==========================================
echo.

:: Open browser after a short delay (in background)
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8001"

:: Run the app
python app.py
