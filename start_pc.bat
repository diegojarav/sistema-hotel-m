@echo off
:: ==========================================
:: Hotel Munich - Streamlit PC Launcher
:: ==========================================
:: Uses Miniconda hotel_munich environment
:: Sets PYTHONPATH to backend folder so imports work
:: ==========================================

:: Set PYTHONPATH to include backend modules
set PYTHONPATH=%~dp0backend

cd /d "%~dp0frontend_pc"
echo.
echo ========================================
echo   Hotel Munich - Streamlit PC App
echo ========================================
echo.
echo Environment: Miniconda hotel_munich
echo PYTHONPATH: %PYTHONPATH%
echo.
A:\Miniconda\envs\hotel_munich\python.exe -m streamlit run app.py
