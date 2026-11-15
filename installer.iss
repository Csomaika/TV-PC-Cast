#define AppName "TV-PC Cast"
#define AppVersion "0.1.0"
#define AppExeName "TVPCCast.exe"

[Setup]
AppId={{10E8E450-8EC8-4F79-AF63-1EA36F58AB32}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Csomaika
DefaultDirName={autopf}\TV-PC Cast
DefaultGroupName=TV-PC Cast
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir=dist
OutputBaseFilename=TVPCCast-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "dist\TVPCCast.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\TV-PC Cast"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\TV-PC Cast"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Asztali parancsikon"; Flags: unchecked

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""TV-PC Cast (Private)"" dir=in action=allow program=""{app}\TVPCCast.exe"" protocol=TCP localport=8765 profile=private"; Flags: runhidden waituntilterminated
Filename: "{app}\{#AppExeName}"; Description: "TV-PC Cast elindítása"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""TV-PC Cast (Private)"""; Flags: runhidden waituntilterminated
