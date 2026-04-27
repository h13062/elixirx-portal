@echo off
cd /d %~dp0
call venv\Scripts\activate

if "%1"=="" (
    pytest tests/ -v --tb=short
) else (
    pytest tests/ -v --tb=short -m "sprint%1"
)
pause
