[CmdletBinding()]
param(
    [string]$PackageDirectory = "$PSScriptRoot/../dist"
)

$ErrorActionPreference = 'Stop'
$packagePath = (Resolve-Path -LiteralPath $PackageDirectory).Path
$testPath = Join-Path $packagePath ('windows-smoke/' + [guid]::NewGuid().ToString('N'))
$installPath = Join-Path $testPath 'TV-PC Cast Test Install'
$portablePath = Join-Path $testPath 'TV-PC Cast Test Portable'
$registryKey = 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{10E8E450-8EC8-4F79-AF63-1EA36F58AB32}_is1'
$userRegistryKey = "HKCU:\$registryKey"
$menuShortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'TV-PC Cast.lnk'
$desktopShortcut = Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'TV-PC Cast.lnk'

function Wait-ForSuccess($Process, [int]$TimeoutSeconds, [string]$Operation) {
    try {
        if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
            throw "$Operation timed out"
        }
        if ($Process.ExitCode -ne 0) {
            throw "$Operation failed ($($Process.ExitCode))"
        }
    }
    finally {
        if (-not $Process.HasExited) { $Process.Kill() }
        $Process.Dispose()
    }
}

function Invoke-AppSmoke([string]$Executable, [string]$ReportPath) {
    $process = Start-Process -FilePath $Executable -WorkingDirectory $testPath `
        -ArgumentList @('--smoke-test', ('"' + $ReportPath + '"')) -PassThru
    Wait-ForSuccess $process 30 'GUI and capture smoke test'
    $report = Get-Content -LiteralPath $ReportPath -Raw | ConvertFrom-Json
    if ($report.ok -ne $true -or $report.gui -ne $true -or $report.capture -ne $true -or $report.rtc_codecs -ne $true) {
        throw "Application smoke test did not confirm GUI, capture and WebRTC codecs: $ReportPath"
    }
    Get-Content -LiteralPath $ReportPath
}

if ((Test-Path -LiteralPath $userRegistryKey) -or
    (Test-Path -LiteralPath $menuShortcut) -or (Test-Path -LiteralPath $desktopShortcut)) {
    throw 'The installer smoke test requires an account with no current-user copy of TV-PC Cast.'
}

New-Item -ItemType Directory -Path $testPath -Force | Out-Null
Write-Host "Windows test reports: $testPath"

Expand-Archive -LiteralPath (Join-Path $packagePath 'TVPCCast-Portable.zip') -DestinationPath $portablePath
Invoke-AppSmoke (Join-Path $portablePath 'TVPCCast/TVPCCast.exe') (Join-Path $testPath 'portable.json')

try {
    $setupPath = Join-Path $packagePath 'TVPCCast-Setup.exe'
    $setupArgs = @('/CURRENTUSER', '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-',
        ('/DIR="' + $installPath + '"'), ('/LOG="' + (Join-Path $testPath 'install.log') + '"'))
    $setup = Start-Process -FilePath $setupPath -ArgumentList $setupArgs -WindowStyle Hidden -PassThru
    Wait-ForSuccess $setup 120 'Installing TV-PC Cast'

    if (-not (Test-Path -LiteralPath $userRegistryKey)) {
        throw 'TV-PC Cast is missing from the current-user uninstall registry.'
    }

    $installedExe = Join-Path $installPath 'TVPCCast.exe'
    $shell = New-Object -ComObject WScript.Shell
    foreach ($shortcut in @($menuShortcut, $desktopShortcut)) {
        if (-not (Test-Path -LiteralPath $shortcut) -or $shell.CreateShortcut($shortcut).TargetPath -ne $installedExe) {
            throw "Missing or incorrect shortcut: $shortcut"
        }
    }

    Invoke-AppSmoke $installedExe (Join-Path $testPath 'installed.json')

    $app = Start-Process -FilePath $installedExe -WorkingDirectory $testPath -PassThru
    try {
        $deadline = [DateTime]::UtcNow.AddSeconds(30)
        do {
            $app.Refresh()
            if ($app.HasExited) { throw "Normal application launch exited ($($app.ExitCode))." }
            if ($app.MainWindowTitle -eq 'TV-PC Cast') { break }
            Start-Sleep -Milliseconds 200
        } while ([DateTime]::UtcNow -lt $deadline)
        if ($app.MainWindowTitle -ne 'TV-PC Cast') { throw 'Normal launch did not open the TV-PC Cast window.' }
        if (-not $app.CloseMainWindow()) { throw 'TV-PC Cast window could not be closed.' }
        if (-not $app.WaitForExit(15000) -or $app.ExitCode -ne 0) { throw 'TV-PC Cast did not exit cleanly.' }
    }
    finally {
        if (-not $app.HasExited) { $app.Kill() }
        $app.Dispose()
    }
}
finally {
    $uninstaller = Get-ChildItem -LiteralPath $installPath -Filter 'unins*.exe' -File -ErrorAction SilentlyContinue
    if ($uninstaller) {
        $uninstallArgs = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
            ('/LOG="' + (Join-Path $testPath 'uninstall.log') + '"'))
        $uninstall = Start-Process -FilePath $uninstaller.FullName -ArgumentList $uninstallArgs `
            -WindowStyle Hidden -PassThru
        Wait-ForSuccess $uninstall 120 'Uninstalling TV-PC Cast'
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    while ((Test-Path -LiteralPath $installPath) -and [DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 200
    }
}

foreach ($path in @($userRegistryKey, $installPath, $menuShortcut, $desktopShortcut)) {
    if (Test-Path -LiteralPath $path) { throw "Uninstall left this path behind: $path" }
}
Write-Host 'Portable launch, installation, normal GUI launch, shortcuts and uninstallation passed.'
