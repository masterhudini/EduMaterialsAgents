$ErrorActionPreference = "Stop"

# Native Windows entry point. The implementation is shared with install.sh.
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$installer = Join-Path $repoRoot "scripts\install_plugin.py"

if (Get-Command python3 -ErrorAction SilentlyContinue) {
    & python3 $installer @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python $installer @args
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $installer @args
} else {
    throw "Python 3 is required to build and install edu-materials-agents."
}

exit $LASTEXITCODE
