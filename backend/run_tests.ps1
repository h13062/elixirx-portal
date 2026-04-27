Set-Location $PSScriptRoot
& venv\Scripts\activate.ps1
pytest tests/ -v --tb=short -x
pause
