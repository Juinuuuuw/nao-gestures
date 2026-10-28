param(
    [switch]$TesteRapido,
    [switch]$Gravar,
    [switch]$SemVoz
)
$ErrorActionPreference = 'Stop'
$taskWebotsExe = Join-Path $env:LOCALAPPDATA 'Programs\Webots\msys64\mingw64\bin\webots.exe'
$taskWorld = Join-Path $PSScriptRoot 'webots\worlds\gesture_lab.wbt'
$taskPython = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'runtime\gesture-env\Scripts\python.exe'))
if (-not (Test-Path -LiteralPath $taskWebotsExe)) { throw "Webots nao encontrado: $taskWebotsExe" }
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'examples\edge_pt\trajectory.json'))) { throw 'Gere a fala e os gestos primeiro com GERAR_FALA_E_GESTOS.ps1.' }
$taskSavedEnv = @{}
foreach ($taskKey in @('NAO_LAB_QUIT','NAO_LAB_MUTE','NAO_LAB_CAPTURE','NAO_LAB_OUT')) { $taskSavedEnv[$taskKey] = [Environment]::GetEnvironmentVariable($taskKey,'Process') }
try {
    $env:NAO_LAB_QUIT = if ($TesteRapido -or $Gravar) { '1' } else { '0' }
    $env:NAO_LAB_MUTE = if ($SemVoz -or $TesteRapido -or $Gravar) { '1' } else { '0' }
    $env:NAO_LAB_CAPTURE = if ($Gravar) { '1' } else { '0' }
    $env:NAO_LAB_OUT = if ($Gravar) { 'webots/results/edge_pt' } elseif ($TesteRapido) { 'webots/results/test' } else { 'webots/results/live' }
    $taskStarted = [DateTime]::UtcNow
    $taskMode = if ($TesteRapido -or $Gravar) { '--mode=fast' } else { '--mode=realtime' }
    & $taskWebotsExe $taskMode --batch --stdout --stderr $taskWorld
    if ($LASTEXITCODE -ne 0) { throw "Webots encerrou com codigo $LASTEXITCODE" }
    $taskReportPath = Join-Path $PSScriptRoot ($env:NAO_LAB_OUT + '/simulation_report.json')
    if (-not (Test-Path -LiteralPath $taskReportPath)) { throw 'O controlador nao produziu o relatorio da simulacao.' }
    $taskReportFile = Get-Item -LiteralPath $taskReportPath
    if ($taskReportFile.LastWriteTimeUtc -lt $taskStarted) { throw 'Relatorio antigo: o controlador nao concluiu esta execucao.' }
    $taskReport = Get-Content -LiteralPath $taskReportPath -Raw | ConvertFrom-Json
    if (-not $taskReport.checks_passed) { throw "Falhou uma verificacao de movimento. Consulte $taskReportPath" }
    if ($Gravar) {
        $taskRecordedFile = Join-Path $PSScriptRoot 'webots\results\edge_pt\webots_motion.mp4'
        if (-not (Test-Path -LiteralPath $taskRecordedFile)) { throw 'O Webots nao produziu o video.' }
        if ((Get-Item -LiteralPath $taskRecordedFile).LastWriteTimeUtc -lt $taskStarted) { throw 'O video encontrado e antigo; esta gravacao falhou.' }
        & $taskPython (Join-Path $PSScriptRoot 'scripts\finish_video.py')
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao finalizar video.' }
        & $taskPython (Join-Path $PSScriptRoot 'scripts\build_report.py')
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao atualizar a pagina de resultados.' }
    }
} finally {
    foreach ($taskKey in $taskSavedEnv.Keys) { [Environment]::SetEnvironmentVariable($taskKey,$taskSavedEnv[$taskKey],'Process') }
}
