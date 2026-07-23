$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Create the repository virtual environment before verification.'
}

Push-Location $repo
try {
    if (-not $env:BEACON_FFPROBE) {
        $ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue
        if (-not $ffprobe) {
            $ffprobePath = Get-ChildItem `
                -LiteralPath (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages') `
                -Filter ffprobe.exe `
                -Recurse `
                -ErrorAction SilentlyContinue |
                Select-Object -First 1 -ExpandProperty FullName
            if (-not $ffprobePath) {
                throw 'FFprobe is required for the acceptance suite.'
            }
            $env:BEACON_FFPROBE = $ffprobePath
        }
        else {
            $env:BEACON_FFPROBE = $ffprobe.Source
        }
    }
    & $python -m compileall -q beacon tests
    if ($LASTEXITCODE -ne 0) {
        throw "Python compilation failed with exit code $LASTEXITCODE."
    }
    & $python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw "Tests failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
