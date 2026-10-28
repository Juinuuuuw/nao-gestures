$ErrorActionPreference = 'Stop'
$taskPython = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'runtime\gesture-env\Scripts\python.exe'))
Push-Location $PSScriptRoot
try { & $taskPython -m app.server --port 8766 } finally { Pop-Location }
