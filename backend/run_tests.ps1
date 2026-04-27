param(
    [string]$Sprint = "all"
)

Set-Location $PSScriptRoot
& venv\Scripts\activate.ps1

if ($Sprint -eq "all") {
    pytest tests/ -v --tb=short
} else {
    pytest tests/ -v --tb=short -m "sprint$Sprint"
}
