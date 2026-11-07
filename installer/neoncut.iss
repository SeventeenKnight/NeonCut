; Inno-Setup-Skript für NeonCut – wird über  python build_exe.py  aufgerufen.

#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\NeonCut"
#endif
#ifndef OutputDir
  #define OutputDir "..\release"
#endif

[Setup]
AppId={{B3F2C7A1-5E8D-4F6A-9C2B-7D1E4A8F0C55}
AppName=NeonCut
AppVersion={#AppVersion}
AppVerName=NeonCut {#AppVersion}
AppPublisher=NeonCut
DefaultDirName={autopf}\NeonCut
DefaultGroupName=NeonCut
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutputDir}
OutputBaseFilename=NeonCut-Setup-{#AppVersion}
#ifdef IconFile
SetupIconFile={#IconFile}
#endif
UninstallDisplayIcon={app}\NeonCut.exe
UninstallDisplayName=NeonCut
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
ChangesAssociations=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
german.Assoc=.neoncut-Projektdateien mit NeonCut öffnen
english.Assoc=Open .neoncut project files with NeonCut

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "assoc"; Description: "{cm:Assoc}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\NeonCut"; Filename: "{app}\NeonCut.exe"
Name: "{autodesktop}\NeonCut"; Filename: "{app}\NeonCut.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.neoncut"; ValueType: string; ValueName: ""; ValueData: "NeonCut.Project"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\NeonCut.Project"; ValueType: string; ValueName: ""; ValueData: "NeonCut-Projekt"; Flags: uninsdeletekey; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\NeonCut.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\NeonCut.exe,0"; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\NeonCut.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\NeonCut.exe"" ""%1"""; Tasks: assoc

[Run]
Filename: "{app}\NeonCut.exe"; Description: "{cm:LaunchProgram,NeonCut}"; Flags: nowait postinstall skipifsilent
