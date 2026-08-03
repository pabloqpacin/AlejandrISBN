; Inno Setup — instalador gratuito de AlejandrISBN (Windows)
; Compilar (CI o local, tras PyInstaller):
;   ISCC.exe packaging\windows\AlejandrISBN.iss /DMyAppVersion=1.0.0
;
; Salida: dist\AlejandrISBN-Setup.exe
;
; PrivilegesRequired=lowest → no pide admin; instala en %LOCALAPPDATA%\Programs\

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "AlejandrISBN"
#define MyAppPublisher "AlejandrISBN"
#define MyAppURL "https://github.com/pabloqpacin/AlejandrISBN"
#define MyAppExeName "AlejandrISBN.exe"

[Setup]
AppId={{A3E7C2B1-9F4D-4E8A-B6C1-7D2E5F8A9012}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Paths are relative to this .iss file (packaging/windows/), not the repo cwd.
OutputDir=..\..\dist
OutputBaseFilename=AlejandrISBN-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=force
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear icono en el Escritorio"; GroupDescription: "Accesos directos:"; Flags: checkedonce

[Files]
; Todo el bundle PyInstaller (exe + _internal)
Source: "..\..\dist\AlejandrISBN\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; No borramos %LOCALAPPDATA%\AlejandrISBN (datos del usuario)
Type: filesandordirs; Name: "{app}"
