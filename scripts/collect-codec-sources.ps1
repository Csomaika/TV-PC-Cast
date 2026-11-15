[CmdletBinding()]
param(
    [string]$OutputDirectory = "$PSScriptRoot/../dist",
    [string]$BundleDirectory = "$PSScriptRoot/../dist/TVPCCast",
    [string]$Python = 'python',
    [string]$CacheDirectory = "$PSScriptRoot/../build/codec-source-cache"
)

$ErrorActionPreference = 'Stop'
& $Python (Join-Path $PSScriptRoot 'collect_codec_sources.py') $OutputDirectory $BundleDirectory $CacheDirectory
if ($LASTEXITCODE -ne 0) { throw "Collecting the corresponding codec source failed ($LASTEXITCODE)." }
