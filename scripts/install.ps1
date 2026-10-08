# Local installer. Never launches AutoCAD or changes system PATH.
[CmdletBinding()]
param(
    [switch]$SkipCodexRegistration,
    [switch]$RegisterCodex,
    [string]$PythonCommand = 'py',
    [string[]]$PythonArguments = @('-3'),
    [string]$SaveRoot = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'AutoCAD Engineering MCP')
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $Executable (exit $LASTEXITCODE)" }
}

try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'This installer requires Windows 10/11.'
    }
    if ($SkipCodexRegistration -and $RegisterCodex) { throw 'Choose one registration mode.' }
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
    $Venv = Join-Path $ProjectRoot '.venv'
    $Marker = Join-Path $Venv '.autocad-mcp-venv'
    $VenvPython = Join-Path $Venv 'Scripts\python.exe'
    $SaveRoot = [IO.Path]::GetFullPath($SaveRoot)
    Get-Command $PythonCommand -ErrorAction Stop | Out-Null
    Invoke-Checked $PythonCommand ($PythonArguments + @('-c', 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ required"'))
    if (Test-Path $Venv) {
        $VenvItem = Get-Item -LiteralPath $Venv -Force
        if (($VenvItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Refusing to install into a junction/symlink virtual environment.'
        }
        if (-not (Test-Path $Marker) -or (Get-Content $Marker -Raw).Trim() -ne 'autocad-engineering-mcp v1') {
            throw 'Existing .venv is not owned by this installer. Use manual installation or choose a fresh project folder.'
        }
    } else {
        Invoke-Checked $PythonCommand ($PythonArguments + @('-m', 'venv', $Venv))
        Set-Content -LiteralPath $Marker -Value 'autocad-engineering-mcp v1' -Encoding UTF8
    }
    Invoke-Checked $VenvPython @('-m', 'pip', 'install', '--upgrade', 'pip')
    Invoke-Checked $VenvPython @('-m', 'pip', 'install', $ProjectRoot)
    Invoke-Checked $VenvPython @((Join-Path $PSScriptRoot 'check_environment.py'))
    Write-Host "Installed. Configured DWG root: $SaveRoot"
    Write-Host 'Run AutoCAD manually before calling autocad_connect.'
    Write-Host 'Registration command:'
    Write-Host ('codex mcp add autocad-engineering --env ACAD_MCP_BACKEND=com --env "ACAD_MCP_SAVE_ROOT={0}" -- "{1}" -m autocad_engineering_mcp' -f $SaveRoot, $VenvPython)
    $Codex = Get-Command 'codex' -ErrorAction SilentlyContinue
    if ($null -ne $Codex -and -not $SkipCodexRegistration) {
        $ShouldRegister = $RegisterCodex.IsPresent
        if (-not $ShouldRegister) {
            $ShouldRegister = (Read-Host 'Register this MCP server in Codex? [y/N]') -match '^(y|yes)$'
        }
        if ($ShouldRegister) {
            Invoke-Checked $Codex.Source @('mcp', 'add', 'autocad-engineering', '--env', 'ACAD_MCP_BACKEND=com',
                '--env', "ACAD_MCP_SAVE_ROOT=$SaveRoot", '--', $VenvPython, '-m', 'autocad_engineering_mcp')
            Invoke-Checked $Codex.Source @('mcp', 'list')
        }
    }
    Write-Host 'Windows/AutoCAD integration is still unverified until tested on your machine.'
} catch {
    Write-Error $_
    exit 1
}
