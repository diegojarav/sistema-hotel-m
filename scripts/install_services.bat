@echo off
REM ============================================
REM Hotel Munich PMS - NSSM Service Installer
REM ============================================
REM Installs 3 Windows services using NSSM:
REM   1. HotelMunich_Backend  (FastAPI on port 8000)
REM   2. HotelMunich_PC       (Streamlit on port 8501)
REM   3. HotelMunich_Mobile   (Next.js on port 3000)
REM
REM PREREQUISITES:
REM   - nssm.exe must be in this scripts\ directory
REM   - Download from https://nssm.cc/download
REM   - Python (Miniconda hotel_munich env)
REM   - Node.js + npm
REM   - Run frontend_mobile: npm run build (before first install)
REM
REM USAGE: Run as Administrator
REM ============================================

echo.
echo ==========================================
echo   HOTEL MUNICH - SERVICE INSTALLER
echo ==========================================
echo.

REM Verify admin privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Este script requiere permisos de Administrador.
    echo.
    echo Haz clic derecho y selecciona "Ejecutar como administrador".
    pause
    exit /b 1
)

REM Detect directories
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "BACKEND_DIR=%PROJECT_ROOT%\backend"
set "FRONTEND_PC_DIR=%PROJECT_ROOT%\frontend_pc"
set "FRONTEND_MOBILE_DIR=%PROJECT_ROOT%\frontend_mobile"
set "LOG_DIR=%BACKEND_DIR%\logs"
set "NSSM=%SCRIPT_DIR%nssm.exe"

REM Python executable (Miniconda hotel_munich environment)
set "PYTHON_EXE=A:\Miniconda\envs\hotel_munich\python.exe"

REM Node.js (assumes npm/node are in PATH)
where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] npm no encontrado en PATH. Instala Node.js primero.
    pause
    exit /b 1
)

REM Verify NSSM exists
if not exist "%NSSM%" (
    echo [ERROR] nssm.exe no encontrado en: %NSSM%
    echo.
    echo Descarga NSSM desde https://nssm.cc/download
    echo y coloca nssm.exe en la carpeta scripts\
    pause
    exit /b 1
)

REM Verify Python exists
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python no encontrado en: %PYTHON_EXE%
    echo Verifica la ruta del entorno Miniconda hotel_munich.
    pause
    exit /b 1
)

REM Create log directory
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo [INFO] Directorio del proyecto: %PROJECT_ROOT%
echo [INFO] Python: %PYTHON_EXE%
echo [INFO] NSSM: %NSSM%
echo.

REM ==========================================
REM SERVICE 1: Backend (FastAPI + Uvicorn)
REM ==========================================
echo [1/3] Instalando HotelMunich_Backend...

REM Remove existing service if present
"%NSSM%" stop HotelMunich_Backend >nul 2>&1
"%NSSM%" remove HotelMunich_Backend confirm >nul 2>&1

"%NSSM%" install HotelMunich_Backend "%PYTHON_EXE%"
"%NSSM%" set HotelMunich_Backend AppParameters "-m uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1"
"%NSSM%" set HotelMunich_Backend AppDirectory "%BACKEND_DIR%"
"%NSSM%" set HotelMunich_Backend DisplayName "Hotel Munich - Backend API"
"%NSSM%" set HotelMunich_Backend Description "FastAPI backend server for Hotel PMS (port 8000)"
"%NSSM%" set HotelMunich_Backend Start SERVICE_AUTO_START
"%NSSM%" set HotelMunich_Backend AppStdout "%LOG_DIR%\service_backend.log"
"%NSSM%" set HotelMunich_Backend AppStderr "%LOG_DIR%\service_backend_err.log"
"%NSSM%" set HotelMunich_Backend AppStdoutCreationDisposition 4
"%NSSM%" set HotelMunich_Backend AppStderrCreationDisposition 4
"%NSSM%" set HotelMunich_Backend AppRotateFiles 1
"%NSSM%" set HotelMunich_Backend AppRotateBytes 5242880
REM Auto-restart on crash with 5 second delay
"%NSSM%" set HotelMunich_Backend AppRestartDelay 5000
"%NSSM%" set HotelMunich_Backend AppThrottle 10000
REM Environment variable for dotenv
"%NSSM%" set HotelMunich_Backend AppEnvironmentExtra PYTHONPATH=%BACKEND_DIR%

echo [OK] HotelMunich_Backend instalado
echo.

REM ==========================================
REM SERVICE 2: Frontend PC (Streamlit)
REM ==========================================
echo [2/3] Instalando HotelMunich_PC...

"%NSSM%" stop HotelMunich_PC >nul 2>&1
"%NSSM%" remove HotelMunich_PC confirm >nul 2>&1

"%NSSM%" install HotelMunich_PC "%PYTHON_EXE%"
"%NSSM%" set HotelMunich_PC AppParameters "-m streamlit run app.py --server.port 8501 --server.headless true"
"%NSSM%" set HotelMunich_PC AppDirectory "%FRONTEND_PC_DIR%"
"%NSSM%" set HotelMunich_PC DisplayName "Hotel Munich - PC Frontend"
"%NSSM%" set HotelMunich_PC Description "Streamlit PC app for reception desk (port 8501)"
"%NSSM%" set HotelMunich_PC Start SERVICE_AUTO_START
"%NSSM%" set HotelMunich_PC AppStdout "%LOG_DIR%\service_pc.log"
"%NSSM%" set HotelMunich_PC AppStderr "%LOG_DIR%\service_pc_err.log"
"%NSSM%" set HotelMunich_PC AppStdoutCreationDisposition 4
"%NSSM%" set HotelMunich_PC AppStderrCreationDisposition 4
"%NSSM%" set HotelMunich_PC AppRotateFiles 1
"%NSSM%" set HotelMunich_PC AppRotateBytes 5242880
"%NSSM%" set HotelMunich_PC AppRestartDelay 5000
"%NSSM%" set HotelMunich_PC AppThrottle 10000
"%NSSM%" set HotelMunich_PC AppEnvironmentExtra PYTHONPATH=%BACKEND_DIR%

echo [OK] HotelMunich_PC instalado
echo.

REM ==========================================
REM SERVICE 3: Frontend Mobile (Next.js)
REM ==========================================
echo [3/3] Instalando HotelMunich_Mobile...

"%NSSM%" stop HotelMunich_Mobile >nul 2>&1
"%NSSM%" remove HotelMunich_Mobile confirm >nul 2>&1

REM Get npm path
for /f "tokens=*" %%i in ('where npm') do set "NPM_PATH=%%i"

"%NSSM%" install HotelMunich_Mobile "%NPM_PATH%"
"%NSSM%" set HotelMunich_Mobile AppParameters "start"
"%NSSM%" set HotelMunich_Mobile AppDirectory "%FRONTEND_MOBILE_DIR%"
"%NSSM%" set HotelMunich_Mobile DisplayName "Hotel Munich - Mobile Frontend"
"%NSSM%" set HotelMunich_Mobile Description "Next.js mobile app for staff (port 3000)"
"%NSSM%" set HotelMunich_Mobile Start SERVICE_AUTO_START
"%NSSM%" set HotelMunich_Mobile AppStdout "%LOG_DIR%\service_mobile.log"
"%NSSM%" set HotelMunich_Mobile AppStderr "%LOG_DIR%\service_mobile_err.log"
"%NSSM%" set HotelMunich_Mobile AppStdoutCreationDisposition 4
"%NSSM%" set HotelMunich_Mobile AppStderrCreationDisposition 4
"%NSSM%" set HotelMunich_Mobile AppRotateFiles 1
"%NSSM%" set HotelMunich_Mobile AppRotateBytes 5242880
"%NSSM%" set HotelMunich_Mobile AppRestartDelay 5000
"%NSSM%" set HotelMunich_Mobile AppThrottle 10000

echo [OK] HotelMunich_Mobile instalado
echo.

REM ==========================================
REM START ALL SERVICES
REM ==========================================
echo Iniciando servicios...
echo.

"%NSSM%" start HotelMunich_Backend
timeout /t 3 >nul
"%NSSM%" start HotelMunich_PC
timeout /t 2 >nul
"%NSSM%" start HotelMunich_Mobile
timeout /t 3 >nul

echo.
echo ==========================================
echo   INSTALACION COMPLETADA
echo ==========================================
echo.
echo Servicios instalados:
echo   - HotelMunich_Backend  (http://localhost:8000)
echo   - HotelMunich_PC       (http://localhost:8501)
echo   - HotelMunich_Mobile   (http://localhost:3000)
echo.
echo Los servicios se inician automaticamente al arrancar Windows.
echo Si un servicio se cae, NSSM lo reiniciara en 5 segundos.
echo.
echo Logs en: %LOG_DIR%
echo.
echo Para verificar:
echo   sc query HotelMunich_Backend
echo   sc query HotelMunich_PC
echo   sc query HotelMunich_Mobile
echo.
echo Para controlar:
echo   scripts\service_control.bat status
echo   scripts\service_control.bat restart-all
echo.

pause
