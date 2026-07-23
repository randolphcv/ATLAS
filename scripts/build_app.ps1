param(
    [string]$OutputRoot = ''
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Create the repository virtual environment before building.'
}

$version = (& $python -c 'from beacon import __version__; print(__version__)').Trim()
if (-not $version) {
    throw 'Could not resolve the Beacon package version.'
}

if (-not $OutputRoot) {
    $OutputRoot = Join-Path $repo 'dist'
}
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
$allowedDistRoot = [System.IO.Path]::GetFullPath((Join-Path $repo 'dist'))
if (-not $OutputRoot.StartsWith($allowedDistRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputRoot must stay within $allowedDistRoot"
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
        --distpath $OutputRoot `
        --workpath (Join-Path $repo 'build') `
        .\ATLAS_Beacon.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

$artifact = Join-Path $OutputRoot 'ATLAS Beacon\ATLAS Beacon.exe'
if (-not (Test-Path -LiteralPath $artifact)) {
    throw "Expected executable was not created: $artifact"
}

$distribution = Split-Path -Parent $artifact
Copy-Item `
    -LiteralPath (Join-Path $PSScriptRoot 'README_APP.txt') `
    -Destination (Join-Path $distribution 'README FIRST.txt') `
    -Force

$blockedCapabilities = @(
    'fastapi',
    'pydantic',
    'qtcharts',
    'qtdatavisualization',
    'qtpdf',
    'qtquick3d',
    'qtvirtualkeyboard',
    'qtwebengine',
    'uvicorn',
    'virtualkeyboard',
    'webengine'
)
$unexpected = @(
    Get-ChildItem -LiteralPath $distribution -Recurse -File |
        Where-Object {
            $candidate = $_.FullName.ToLowerInvariant()
            @($blockedCapabilities | Where-Object { $candidate.Contains($_) }).Count -gt 0
        }
)
if ($unexpected.Count -gt 0) {
    $relative = $unexpected |
        ForEach-Object { $_.FullName.Substring($distribution.Length + 1) }
    throw "Unexpected capability in desktop bundle: $($relative -join ', ')"
}

$requiredRuntime = @(
    (Join-Path $distribution '_internal\PySide6\Qt6Multimedia.dll'),
    (Join-Path $distribution '_internal\PySide6\qml\QtMultimedia\quickmultimediaplugin.dll')
)
foreach ($required in $requiredRuntime) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required multimedia runtime is missing: $required"
    }
}

Write-Host "Built: $artifact"

$package = Join-Path $repo "dist\ATLAS-Beacon-$version-win64.zip"
if (Test-Path -LiteralPath $package) {
    Remove-Item -LiteralPath $package -Force
}
Compress-Archive -LiteralPath $distribution -DestinationPath $package
Write-Host "Packaged: $package"
