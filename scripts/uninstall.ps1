# Removes only an installer-owned virtual environment. Leaves AutoCAD and DWGs alone.
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param([switch]$RemoveCodexRegistration)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
    $Venv = Join-Path $ProjectRoot '.venv'
    $Marker = Join-Path $Venv '.autocad-mcp-venv'
    if (Test-Path $Venv) {
        $Item = Get-Item -LiteralPath $Venv -Force
        if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Refusing to remove a junction/symlink virtual environment.'
        }
        if (-not (Test-Path $Marker) -or (Get-Content $Marker -Raw).Trim() -ne 'autocad-engineering-mcp v1') {
            throw 'Refusing to remove an environment not owned by this installer.'
        }
        if ($PSCmdlet.ShouldProcess($Venv, 'Remove installer-owned environment')) {
            Remove-Item -LiteralPath $Venv -Recurse -Force
        }
    }
    if ($RemoveCodexRegistration -and $PSCmdlet.ShouldProcess('autocad-engineering', 'Remove Codex MCP registration')) {
        & codex mcp remove autocad-engineering
        if ($LASTEXITCODE -ne 0) { throw 'Could not remove Codex registration.' }
    }
    Write-Host 'Source files and drawings are retained.'
} catch {
    Write-Error $_
    exit 1
}
