param([switch]$SkipData, [string]$OutputRoot = '')

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Virtual environment not found. Create .venv and install requirements-dev.txt first.'
}

$buildOptions = @()
if ($OutputRoot) {
    $resolvedOutput = [IO.Path]::GetFullPath($OutputRoot)
    $workspacePath = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\') + '\'
    if (-not $resolvedOutput.StartsWith($workspacePath, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'OutputRoot must be inside this source workspace.'
    }
    $buildOptions = @('--distpath', (Join-Path $resolvedOutput 'dist'), '--workpath', (Join-Path $resolvedOutput 'build'))
}
& $python -m PyInstaller @buildOptions `
    --noconfirm `
    --clean `
    (Join-Path $PSScriptRoot 'packaging\MarmosetAtlasMapper.spec')
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: $LASTEXITCODE" }

$distRoot = Join-Path $PSScriptRoot 'dist\MarmosetAtlasMapper'
if ($OutputRoot) { $distRoot = Join-Path $resolvedOutput 'dist\MarmosetAtlasMapper' }
if (-not $SkipData) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'data') -Destination $distRoot -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'README.md') -Destination $distRoot -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'LICENSE') -Destination $distRoot -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'THIRD_PARTY_NOTICES.md') -Destination $distRoot -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'assets') -Destination $distRoot -Recurse -Force

$licenseRoot = Join-Path $distRoot 'THIRD_PARTY_LICENSES'
New-Item -ItemType Directory -Path $licenseRoot -Force | Out-Null
$sitePackages = Join-Path $PSScriptRoot '.venv\Lib\site-packages'
$licenseSources = @(
    @{ Source = 'numpy-2.5.1.dist-info\licenses'; Destination = 'NumPy' },
    @{ Source = 'pyside6_essentials-6.11.1.dist-info\licenses'; Destination = 'PySide6' },
    @{ Source = 'shiboken6-6.11.1.dist-info\licenses'; Destination = 'Shiboken6' },
    @{ Source = 'pyinstaller-6.21.0.dist-info\licenses'; Destination = 'PyInstaller' }
)
foreach ($entry in $licenseSources) {
    $source = Join-Path $sitePackages $entry.Source
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $licenseRoot $entry.Destination) -Recurse -Force
    }
}
$simpleItkLicense = Join-Path $sitePackages 'simpleitk-2.5.6.dist-info\LICENSE'
$simpleItkNotice = Join-Path $sitePackages 'simpleitk-2.5.6.dist-info\NOTICE'
if (Test-Path -LiteralPath $simpleItkLicense) {
    Copy-Item -LiteralPath $simpleItkLicense -Destination (Join-Path $licenseRoot 'SimpleITK-LICENSE.txt') -Force
}
if (Test-Path -LiteralPath $simpleItkNotice) {
    Copy-Item -LiteralPath $simpleItkNotice -Destination (Join-Path $licenseRoot 'SimpleITK-NOTICE.txt') -Force
}
Write-Host "Built: $distRoot\MarmosetAtlasMapper.exe"
