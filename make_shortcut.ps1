# make_shortcut.ps1 -- create a Desktop shortcut for the FlipRadar desktop app.
#
# Run this ONCE from the repo directory (no elevation required):
#   powershell -ExecutionPolicy Bypass -File make_shortcut.ps1
#
# It creates 'FlipRadar.lnk' on your Desktop that launches desktop.py with
# pythonw (no console window), working directory set to this repo.

$ErrorActionPreference = "Stop"

$repoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktopPy = Join-Path $repoDir "desktop.py"

if (-not (Test-Path $desktopPy)) {
    Write-Error "desktop.py not found next to this script ($desktopPy)"
}

# Find pythonw.exe next to the 'python' on PATH.
$python = (Get-Command python).Source
$pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Warning "pythonw.exe not found next to $python; falling back to python.exe (a console window will appear)."
    $pythonw = $python
}

$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "FlipRadar.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($lnkPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "`"$desktopPy`""
$shortcut.WorkingDirectory = $repoDir
$shortcut.Description = "FlipRadar deal dashboard"
$shortcut.Save()

Write-Host "Created $lnkPath"
Write-Host "  Target : $pythonw `"$desktopPy`""
Write-Host "  Workdir: $repoDir"
