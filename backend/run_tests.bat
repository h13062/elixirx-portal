@echo off
cd /d %~dp0
call venv\Scripts\activate
pytest tests/ -v --tb=short -x
pause
