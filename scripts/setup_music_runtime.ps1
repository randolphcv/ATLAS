param(
    [string]$RuntimeRoot = 'C:\ProgramData\ATLAS\MusicRuntime'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = (& py -3.11 -c 'import sys; print(sys.executable)' 2>$null).Trim()
if (-not $python -or -not (Test-Path -LiteralPath $python)) {
    throw 'Python 3.11 is required for the isolated music runtime.'
}

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
$venvPython = Join-Path $RuntimeRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $python -m venv (Join-Path $RuntimeRoot 'venv')
}

& $venvPython -m pip install --upgrade pip wheel
& $venvPython -m pip install 'setuptools==80.9.0'
& $venvPython -m pip install `
    'torch==2.7.1' 'torchaudio==2.7.1' `
    --index-url 'https://download.pytorch.org/whl/cu128'
& $venvPython -m pip install `
    'basic-pitch==0.4.0' `
    'demucs==4.0.1' `
    'librosa==0.11.0' `
    'onnxruntime==1.23.2'

Copy-Item `
    -LiteralPath (Join-Path $repo 'scripts\music_worker.py') `
    -Destination (Join-Path $RuntimeRoot 'music_worker.py') `
    -Force

& $venvPython (Join-Path $RuntimeRoot 'music_worker.py') --status
if ($LASTEXITCODE -ne 0) {
    throw "Music runtime verification failed with exit code $LASTEXITCODE."
}
