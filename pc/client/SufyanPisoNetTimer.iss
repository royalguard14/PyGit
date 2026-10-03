# Sufyan PisoNetTimer installer
#define AppName "Sufyan PisoNetTimer"
#define AppVersion "1.0.0"

[Setup]
AppId={{B4C0B5A7-2B4A-4D1C-9B2F-7F5E2B2B4D31}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName=C:\sufyan
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=installer
OutputBaseFilename=SufyanPisoNetTimerSetup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
Uninstallable=yes

[Files]
Source: "release\PisoNetTimer - 32826.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "release\SufyanPisoNetTimerService.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "release\uninstall_helper.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "release\detail.json"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "release\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "PisoNetTimer - 32826.exe,SufyanPisoNetTimerService.exe,uninstall_helper.exe,detail.json"

[Run]
Filename: "{app}\SufyanPisoNetTimerService.exe"; Parameters: "install"; Flags: runhidden waituntilterminated
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""Sufyan PisoNetTimer TCP 5000"""; Flags: runhidden waituntilterminated
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""Sufyan PisoNetTimer TCP 5000"" dir=in action=allow protocol=TCP localport=5000 profile=any"; Flags: runhidden waituntilterminated
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""Sufyan PisoNetTimer UDP 5050"""; Flags: runhidden waituntilterminated
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""Sufyan PisoNetTimer UDP 5050"" dir=in action=allow protocol=UDP localport=5050 profile=any"; Flags: runhidden waituntilterminated
Filename: "{app}\SufyanPisoNetTimerService.exe"; Parameters: "start"; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "{app}\SufyanPisoNetTimerService.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated
Filename: "{app}\SufyanPisoNetTimerService.exe"; Parameters: "remove"; Flags: runhidden waituntilterminated
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""Sufyan PisoNetTimer TCP 5000"""; Flags: runhidden waituntilterminated
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""Sufyan PisoNetTimer UDP 5050"""; Flags: runhidden waituntilterminated
