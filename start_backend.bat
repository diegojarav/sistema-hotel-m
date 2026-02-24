@echo off
:: ==========================================
:: Hotel Munich - Backend Launcher
:: ==========================================
:: Starts FastAPI server from backend folder
:: API docs available at http://localhost:8000/docs
:: ==========================================

cd /d "%~dp0backend"
echo.
echo ========================================
echo   Hotel Munich - Backend API Server
echo ========================================
echo.
echo Starting FastAPI backend...
echo API docs: http://localhost:8000/docs
echo.
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
