#define AppName "TV-PC Cast"
#ifndef AppVersion
#error Provide the application version with scripts/build-windows.ps1
#endif
#define AppExeName "TVPCCast.exe"

[Setup]
AppId={{10E8E450-8EC8-4F79-AF63-1EA36F58AB32}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Csomaika
DefaultDirName={autopf}\TV-PC Cast
DefaultGroupName=TV-PC Cast
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir=dist
OutputBaseFilename=TVPCCast-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "hungarian"; MessagesFile: "compiler:Languages\Hungarian.isl"

[Files]
Source: "dist\TVPCCast\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\TV-PC Cast"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\TV-PC Cast"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""TV-PC Cast (Private)"" dir=in"; Flags: runhidden waituntilterminated; Check: IsAdminInstallMode
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""TV-PC Cast (Private)"" dir=in action=allow program=""{app}\TVPCCast.exe"" protocol=TCP localport=8765 remoteip=localsubnet profile=private"; Flags: runhidden waituntilterminated; Check: IsAdminInstallMode
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""TV-PC Cast WebRTC (Private)"" dir=in"; Flags: runhidden waituntilterminated; Check: IsAdminInstallMode
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""TV-PC Cast WebRTC (Private)"" dir=in action=allow program=""{app}\TVPCCast.exe"" protocol=UDP remoteip=localsubnet profile=private"; Flags: runhidden waituntilterminated; Check: IsAdminInstallMode
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""TV-PC Cast (Private)"" dir=in program=""{app}\TVPCCast.exe"""; Flags: runhidden waituntilterminated; RunOnceId: "RemovePrivateFirewallRule"; Check: IsAdminInstallMode
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""TV-PC Cast WebRTC (Private)"" dir=in program=""{app}\TVPCCast.exe"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoveWebRTCPrivateFirewallRule"; Check: IsAdminInstallMode
