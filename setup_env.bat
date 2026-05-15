@echo off
setlocal enabledelayedexpansion

rem ===============================
rem Configuration
rem ===============================
set "PYTHON_CMD=python"
if not "%~1"=="" (
    set "PYTHON_CMD=%~1"
)

set "VENV_DIR=.venv"

rem ===============================
rem Check Python
rem ===============================
where "%PYTHON_CMD%" >nul 2>nul
if errorlevel 1 (
    echo Python command "%PYTHON_CMD%" not found. Please install Python 3.9+ and ensure it is on PATH.
    exit /b 1
)

rem ===============================
rem Create virtual environment
rem ===============================
if exist "%VENV_DIR%\Scripts\activate.bat" (
    echo .venv already exists. Skipping creation.
) else (
    "%PYTHON_CMD%" -m venv "%VENV_DIR%"
    echo Virtual environment created at .venv.
)

rem ===============================
rem Set pip path
rem ===============================
set "PIP_PATH="
if exist "%VENV_DIR%\Scripts\pip.exe" (
    set "PIP_PATH=%VENV_DIR%\Scripts\pip.exe"
)

if not defined PIP_PATH (
    echo pip executable not found in .venv. Please check the environment.
    exit /b 1
)

rem ===============================
rem Upgrade pip
rem ===============================
echo Upgrading pip in the virtual environment...
"%PIP_PATH%" install --upgrade pip

rem ===============================
rem Install dependencies
rem ===============================
echo Installing required packages...

"%PIP_PATH%" install openai python-dotenv pydantic requests pyyaml pandas numpy scikit-learn matplotlib seaborn tqdm

echo.
echo ===============================
echo Setup complete!
echo Activate the environment with:
echo     call .\.venv\Scripts\activate.bat
echo ===============================