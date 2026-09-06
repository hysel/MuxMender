<# Audit runtime prerequisites. -Install enables per-package confirmation; never changes drivers or media. #>
[CmdletBinding()]
param([switch]$Install, [switch]$IncludeGit)
$ErrorActionPreference = 'Stop'

function Refresh-MuxPath {
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path','User')
}

function Find-MuxPython {
    foreach ($launcher in @('py','python')) {
        $command = Get-Command $launcher -ErrorAction SilentlyContinue
        if (-not $command) { continue }
        if ($launcher -eq 'python' -and $command.Source -like '*\Microsoft\WindowsApps\*') { continue }
        $arguments = @()
        if ($launcher -eq 'py') { $arguments += '-3' }
        $arguments += @('-c','import sys; assert sys.version_info >= (3,10); print(sys.executable)')
        try {
            $result = & $command.Source @arguments 2>$null
            if ($LASTEXITCODE -eq 0 -and $result) {
                $candidate = ([string]($result | Select-Object -Last 1)).Trim()
                if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
            }
        } catch { continue }
    }
    return $null
}

function Install-MuxPackage([string]$Package) {
    Write-Host "Missing prerequisite: $Package" -ForegroundColor Yellow
    if (-not $Install) { Write-Host 'Audit only. Rerun with -Install to approve installation.'; return }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'Install Microsoft App Installer from Microsoft Store to obtain WinGet, then retry. No software was installed by this script.'
    }
    $answer = Read-Host "Download/install $Package through WinGet? Type YES to approve"
    if ($answer -cne 'YES') { Write-Host 'Skipped; no install performed.'; return }
    & winget install --id $Package --exact --source winget
    if ($LASTEXITCODE -ne 0) { throw "Installation did not complete for $Package. Review installer output." }
    Refresh-MuxPath
}

Refresh-MuxPath
Write-Host 'MuxMender prerequisite audit — no driver changes, encoding, or media operations.'
$pythonExe = Find-MuxPython
if (-not $pythonExe) { Install-MuxPackage 'Python.Python.3.13'; $pythonExe = Find-MuxPython }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    Install-MuxPackage 'Gyan.FFmpeg'
}
if ($IncludeGit -and -not (Get-Command git -ErrorAction SilentlyContinue)) { Install-MuxPackage 'Git.Git' }

if ($pythonExe) { Write-Host "Python: $pythonExe" } else { Write-Warning 'Python 3.10+ not detected.' }
foreach ($tool in @('ffmpeg','ffprobe')) {
    $command = Get-Command $tool -ErrorAction SilentlyContinue
    if ($command) { Write-Host ($tool + ': ' + $command.Source) } else { Write-Warning "$tool not found. A new PowerShell window may be needed after installation." }
}
Write-Host 'Native Dolby Vision helpers and dovi_tool are optional and are not installed here.'
if ($pythonExe -and (Get-Command ffmpeg -ErrorAction SilentlyContinue) -and (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    & $pythonExe (Join-Path $PSScriptRoot 'muxmender.py') --check-dependencies --hardware auto
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Dependency/hardware inspection needs attention; do not start encoding yet.' }
}
Write-Host 'To open the local workflow: python webui.py'
