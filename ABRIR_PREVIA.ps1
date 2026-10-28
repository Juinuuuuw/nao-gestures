$ErrorActionPreference = 'Stop'
$taskPreview = Join-Path $PSScriptRoot 'RESULTADOS.html'
if (-not (Test-Path -LiteralPath $taskPreview)) {
    $taskPreview = Join-Path $PSScriptRoot 'examples\demo\preview.html'
}
Start-Process -FilePath $taskPreview -WindowStyle Hidden
