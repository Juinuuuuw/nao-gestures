param(
    [string]$Texto = '',
    [string]$Voz = 'pt-BR-AntonioNeural'
)
$ErrorActionPreference = 'Stop'
$taskPython = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'runtime\gesture-env\Scripts\python.exe'))
$taskRepo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'runtime\character-policy'))
$taskWeights = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'runtime\weights'))
$taskTextFile = Join-Path $PSScriptRoot 'examples\texto_edge.txt'
$taskOutput = Join-Path $PSScriptRoot 'examples\edge_pt'
if ($Texto) { [IO.File]::WriteAllText($taskTextFile,$Texto,(New-Object Text.UTF8Encoding($false))) }
Push-Location $PSScriptRoot
try {
    & $taskPython scripts/synthesize_edge.py --text-file $taskTextFile --out $taskOutput --voice $Voz
    if ($LASTEXITCODE -ne 0) { throw 'Falha no Edge TTS. Verifique a conexao com a internet.' }
    & $taskPython scripts/infer_emage.py --repo $taskRepo --weights (Join-Path $taskWeights 'emage') --audio (Join-Path $taskOutput 'speech.wav') --rest-model (Join-Path $taskWeights 'evaltools\smplx_models\smplx\SMPLX_NEUTRAL_2020.npz') --out $taskOutput
    if ($LASTEXITCODE -ne 0) { throw 'Falha no EMAGE.' }
    & $taskPython -m nao_gestures retarget (Join-Path $taskOutput 'emage_motion.npz') --rest-joints (Join-Path $taskOutput 'rest_joints.npy') --out $taskOutput --audio (Join-Path $taskOutput 'speech.wav')
    if ($LASTEXITCODE -ne 0) { throw 'Falha no adaptador corporal.' }
    Write-Host 'Fala e gestos gerados. Execute INICIAR_WEBOTS.ps1 para testar.' -ForegroundColor Green
} finally { Pop-Location }
