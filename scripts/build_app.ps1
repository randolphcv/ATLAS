$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Create the repository virtual environment before building.'
}

Push-Location $PSScriptRoot
try {
    & $python .\generate_icon.py
    if ($LASTEXITCODE -ne 0) {
        throw "Icon generation failed with exit code $LASTEXITCODE."
    }
    & $python -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath (Join-Path $repo 'dist') `
        --workpath (Join-Path $repo 'build') `
        .\ATLAS_Beacon.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

$artifact = Join-Path $repo 'dist\ATLAS Beacon\ATLAS Beacon.exe'
if (-not (Test-Path -LiteralPath $artifact)) {
    throw "Expected executable was not created: $artifact"
}

$distribution = Split-Path -Parent $artifact
Copy-Item `
    -LiteralPath (Join-Path $PSScriptRoot 'README_APP.txt') `
    -Destination (Join-Path $distribution 'README FIRST.txt') `
    -Force

Write-Host "Built: $artifact"

$package = Join-Path $repo 'dist\ATLAS-Beacon-0.3.0-win64.zip'
if (Test-Path -LiteralPath $package) {
    Remove-Item -LiteralPath $package -Force
}
Compress-Archive -LiteralPath $distribution -DestinationPath $package
Write-Host "Packaged: $package"
