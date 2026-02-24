@echo off
REM ============================================
REM Hotel Munich PMS - Service Control
REM ============================================
REM Usage:
REM   service_control.bat status       - Show status of all services
REM   service_control.bat start-all    - Start all services
REM   service_control.bat stop-all     - Stop all services
REM   service_control.bat restart-all  - Restart all services
REM   service_control.bat restart-backend  - Restart only backend
REM   service_control.bat restart-pc       - Restart only PC frontend
REM   service_control.bat restart-mobile   - Restart only mobile frontend
REM ============================================

set "SCRIPT_DIR=%~dp0"
set "NSSM=%SCRIPT_DIR%nssm.exe"

if "%1"=="" goto usage

if "%1"=="status" goto status
if "%1"=="start-all" goto start_all
if "%1"=="stop-all" goto stop_all
if "%1"=="restart-all" goto restart_all
if "%1"=="restart-backend" goto restart_backend
if "%1"=="restart-pc" goto restart_pc
if "%1"=="restart-mobile" goto restart_mobile
goto usage

:status
echo.
echo === HOTEL MUNICH SERVICE STATUS ===
echo.
echo --- Backend (FastAPI port 8000) ---
sc query HotelMunich_Backend | findstr "STATE"
echo.
echo --- PC Frontend (Streamlit port 8501) ---
sc query HotelMunich_PC | findstr "STATE"
echo.
echo --- Mobile Frontend (Next.js port 3000) ---
sc query HotelMunich_Mobile | findstr "STATE"
echo.

REM Quick health check
echo --- API Health Check ---
curl -s http://localhost:8000/health 2>nul
if %errorlevel% neq 0 (
    echo [WARN] Backend API no responde
)
echo.
echo.
goto end

:start_all
echo Iniciando todos los servicios...
"%NSSM%" start HotelMunich_Backend
timeout /t 3 >nul
"%NSSM%" start HotelMunich_PC
timeout /t 2 >nul
"%NSSM%" start HotelMunich_Mobile
echo [OK] Servicios iniciados
goto end

:stop_all
echo Deteniendo todos los servicios...
"%NSSM%" stop HotelMunich_Mobile
"%NSSM%" stop HotelMunich_PC
"%NSSM%" stop HotelMunich_Backend
echo [OK] Servicios detenidos
goto end

:restart_all
echo Reiniciando todos los servicios...
"%NSSM%" restart HotelMunich_Backend
timeout /t 3 >nul
"%NSSM%" restart HotelMunich_PC
timeout /t 2 >nul
"%NSSM%" restart HotelMunich_Mobile
timeout /t 3 >nul
echo [OK] Servicios reiniciados
echo.
echo Verificando health...
curl -s http://localhost:8000/health 2>nul
echo.
goto end

:restart_backend
echo Reiniciando Backend...
"%NSSM%" restart HotelMunich_Backend
timeout /t 3 >nul
echo [OK] Backend reiniciado
curl -s http://localhost:8000/health 2>nul
echo.
goto end

:restart_pc
echo Reiniciando PC Frontend...
"%NSSM%" restart HotelMunich_PC
echo [OK] PC Frontend reiniciado
goto end

:restart_mobile
echo Reiniciando Mobile Frontend...
"%NSSM%" restart HotelMunich_Mobile
echo [OK] Mobile Frontend reiniciado
goto end

:usage
echo.
echo Hotel Munich PMS - Service Control
echo.
echo Uso: service_control.bat [comando]
echo.
echo Comandos:
echo   status           Muestra el estado de todos los servicios
echo   start-all        Inicia todos los servicios
echo   stop-all         Detiene todos los servicios
echo   restart-all      Reinicia todos los servicios
echo   restart-backend  Reinicia solo el backend (FastAPI)
echo   restart-pc       Reinicia solo el frontend PC (Streamlit)
echo   restart-mobile   Reinicia solo el frontend mobile (Next.js)
echo.

:end
