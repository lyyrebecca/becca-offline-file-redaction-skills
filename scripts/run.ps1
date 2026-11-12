# Information Cloak - PowerShell launcher (Windows 10/11)
# Usage: powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1 doctor
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$versionCheck = Join-Path $here 'pyversion.py'

function Test-Supported($Exe, [string[]]$Prefix) {
    try {
        & $Exe @Prefix $versionCheck *> $null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

$exe = $null
$prefix = @()
if ($env:LPC_BOOTSTRAP_PYTHON) {
    if (Test-Supported $env:LPC_BOOTSTRAP_PYTHON @()) { $exe = $env:LPC_BOOTSTRAP_PYTHON }
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    if (Test-Supported 'py' @('-3.12')) { $exe = 'py'; $prefix = @('-3.12') }
    elseif (Test-Supported 'py' @('-3.11')) { $exe = 'py'; $prefix = @('-3.11') }
}
if (-not $exe -and (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Test-Supported 'python' @()) { $exe = 'python' }
}

if (-not $exe) {
    Write-Host 'Python 3.11 or 3.12 was not found.'
    Write-Host 'Install Python 3.12 from https://www.python.org/downloads/windows/ and tick "Add python.exe to PATH".'
    exit 2
}

& $exe @prefix (Join-Path $here 'run.py') @args
exit $LASTEXITCODE
