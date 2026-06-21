$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

if (Get-Command python3 -ErrorAction SilentlyContinue) {
    $python = "python3"
    $prefix = @()
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = "python"
    $prefix = @()
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $python = "py"
    $prefix = @("-3")
} else {
    throw "Python 3 is required for the development environment."
}

& $python @prefix -m venv .venv
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $venvPython -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Output "Development environment ready."
Write-Output "Run tests: .venv\Scripts\python.exe -m pytest"
