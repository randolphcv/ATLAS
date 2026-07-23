$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    if (-not $env:BEACON_FFPROBE) {
        $ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue
        if (-not $ffprobe) {
            throw 'FFprobe is required for the Phase 1 acceptance suite.'
        }
        $env:BEACON_FFPROBE = $ffprobe.Source
    }
    python -m compileall -q beacon tests
    python -m unittest discover -s tests -v
}
finally {
    Pop-Location
}
