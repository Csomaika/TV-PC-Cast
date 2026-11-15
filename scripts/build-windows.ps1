[CmdletBinding()]
param(
    [string]$Python = 'python',
    [string]$InnoCompiler = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    [string]$Version
)

$ErrorActionPreference = 'Stop'
$pythonCommand = (Get-Command $Python -CommandType Application).Source
$compilerPath = (Resolve-Path -LiteralPath $InnoCompiler).Path
$repository = Split-Path $PSScriptRoot -Parent

Push-Location -LiteralPath $repository
try {
    $applicationVersion = & $pythonCommand -c 'from tvpc_cast import VERSION; print(VERSION)'
    if ($LASTEXITCODE -ne 0 -or $applicationVersion -cnotmatch '^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$') {
        throw 'Could not determine the application version from tvpc_cast.py'
    }
    if ($Version -and $Version -cne $applicationVersion) {
        throw "Release tag version ($Version) differs from application version ($applicationVersion)"
    }

    & $pythonCommand -m PyInstaller --noconfirm --clean --onedir --windowed --noupx --name TVPCCast `
        --add-data 'web:web' --collect-submodules mss tvpc_cast.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }

    Copy-Item -LiteralPath 'LICENSE' -Destination 'dist/TVPCCast/LICENSE.txt'
    & (Join-Path $PSScriptRoot 'collect-codec-sources.ps1') `
        -OutputDirectory (Join-Path $repository 'dist') `
        -BundleDirectory (Join-Path $repository 'dist/TVPCCast') `
        -Python $pythonCommand

    & $compilerPath "/DAppVersion=$applicationVersion" 'installer.iss'
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed ($LASTEXITCODE)" }

    Compress-Archive -Path 'dist/TVPCCast' -DestinationPath 'dist/TVPCCast-Portable.zip' -Force
    $packages = 'dist/TVPCCast-Setup.exe', 'dist/TVPCCast-Portable.zip', 'dist/TVPCCast-Codec-Sources.zip'
    Get-FileHash -Algorithm SHA256 -LiteralPath $packages |
        ForEach-Object { '{0}  {1}' -f $_.Hash.ToLowerInvariant(), (Split-Path $_.Path -Leaf) } |
        Set-Content -Encoding ascii -LiteralPath 'dist/SHA256SUMS.txt'
}
finally {
    Pop-Location
}
