$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    python -m compileall -q beacon tests
    python -m unittest discover -s tests -v
}
finally {
    Pop-Location
}
