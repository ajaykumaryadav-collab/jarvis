@echo off
setlocal

echo ========================================
echo         Project JARVIS Launcher
echo ========================================

:: Try to find Python 3.11 or 3.12 via the Windows Python Launcher (py.exe)
:: to avoid build issues with Python 3.14
set PYTHON_EXE=python
py -3.11 -V >nul 2>&1
if %ERRORLEVEL% EQU 0 set PYTHON_EXE=py -3.11
py -3.12 -V >nul 2>&1
if %ERRORLEVEL% EQU 0 set PYTHON_EXE=py -3.12

echo [INFO] Selected Python interpreter: %PYTHON_EXE%

IF NOT EXIST ".venv" (
    echo [INFO] Creating virtual environment...
    %PYTHON_EXE% -m venv .venv
)

echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [INFO] Installing/Updating dependencies...
:: First install pytorch with CUDA 12.1 as per requirements
.venv\Scripts\python.exe -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
:: Then install the rest
.venv\Scripts\python.exe -m pip install -r requirements.txt

echo [INFO] Downloading pre-trained wake word models...
.venv\Scripts\python.exe -c "import openwakeword; openwakeword.utils.download_models()"

echo.
echo [INFO] Starting JARVIS...
echo ========================================
.venv\Scripts\python.exe main.py

pause
