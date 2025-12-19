@echo off
REM ============================================
REM Hotel Munich LMS - Instalador de Tarea de Backup
REM ============================================
REM Este script crea una tarea programada en Windows
REM que ejecuta backup_manager.py todos los días a las 03:00 AM
REM
REM USO: Ejecutar como Administrador en la PC del cliente
REM ============================================

echo.
echo ========================================
echo  HOTEL MUNICH - INSTALADOR DE BACKUPS
echo ========================================
echo.

REM Verificar permisos de administrador
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Este script requiere permisos de Administrador.
    echo.
    echo Por favor, haz clic derecho sobre este archivo
    echo y selecciona "Ejecutar como administrador".
    echo.
    pause
    exit /b 1
)

REM Detectar la ruta actual (donde está este script)
set "SCRIPT_DIR=%~dp0"
set "BACKUP_SCRIPT=%SCRIPT_DIR%backup_manager.py"
set "TASK_NAME=HotelMunich_Backup"

echo [INFO] Directorio detectado: %SCRIPT_DIR%
echo [INFO] Script de backup: %BACKUP_SCRIPT%
echo.

REM Verificar que existe el script de Python
if not exist "%BACKUP_SCRIPT%" (
    echo [ERROR] No se encontro backup_manager.py en:
    echo         %BACKUP_SCRIPT%
    echo.
    echo Asegurate de que este archivo .bat esta en la misma
    echo carpeta que backup_manager.py
    echo.
    pause
    exit /b 1
)

REM Verificar que Python esta instalado
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no esta instalado o no esta en el PATH.
    echo.
    echo Por favor, instala Python desde https://python.org
    echo y asegurate de marcar "Add Python to PATH" durante la instalacion.
    echo.
    pause
    exit /b 1
)

echo [OK] Python encontrado
for /f "tokens=*" %%i in ('python --version') do echo      %%i
echo.

REM Eliminar tarea existente si ya existe (para poder reinstalar)
echo [INFO] Verificando si existe tarea anterior...
schtasks /query /tn "%TASK_NAME%" >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Eliminando tarea anterior...
    schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
)

REM Crear la tarea programada
echo [INFO] Creando tarea programada...
echo.

REM Opciones de schtasks:
REM   /sc DAILY       = Ejecutar diariamente
REM   /st 03:00       = A las 3:00 AM
REM   /ru SYSTEM      = Correr como cuenta SYSTEM (no requiere login)
REM   /rl HIGHEST     = Con privilegios elevados
REM   /f              = Forzar creación sin confirmar

schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "python \"%BACKUP_SCRIPT%\"" ^
    /sc DAILY ^
    /st 03:00 ^
    /ru SYSTEM ^
    /rl HIGHEST ^
    /f

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] No se pudo crear la tarea programada.
    echo         Codigo de error: %errorlevel%
    echo.
    echo Posibles causas:
    echo - No tienes permisos de administrador
    echo - El Programador de Tareas esta deshabilitado
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  [OK] INSTALACION COMPLETADA
echo ========================================
echo.
echo La tarea "%TASK_NAME%" ha sido creada.
echo.
echo Configuracion:
echo   - Hora de ejecucion: 03:00 AM (todos los dias)
echo   - Usuario: SYSTEM (no requiere sesion iniciada)
echo   - Privilegios: Elevados
echo.
echo Los backups se guardaran en:
echo   %SCRIPT_DIR%backups\
echo.
echo Los logs se guardaran en:
echo   %SCRIPT_DIR%logs\
echo.
echo ----------------------------------------
echo Para verificar la tarea:
echo   1. Abre "Programador de tareas" (taskschd.msc)
echo   2. Busca "%TASK_NAME%" en la lista
echo.
echo Para ejecutar manualmente:
echo   python "%BACKUP_SCRIPT%"
echo ----------------------------------------
echo.

REM Preguntar si desea ejecutar una prueba ahora
set /p RUNTEST="Deseas ejecutar un backup de prueba ahora? (S/N): "
if /i "%RUNTEST%"=="S" (
    echo.
    echo [INFO] Ejecutando backup de prueba...
    echo.
    python "%BACKUP_SCRIPT%"
    echo.
    echo [INFO] Prueba completada. Revisa los resultados arriba.
)

echo.
echo Presiona cualquier tecla para cerrar...
pause >nul
