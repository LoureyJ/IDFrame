#ifndef ClientDir
  #error ClientDir is required
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif
#ifndef HostURL
  #define HostURL "http://192.168.83.169:8766"
#endif

[Setup]
AppId={{4F996310-BECE-42C1-B5A5-359D8AE081C4}
AppName=IDFrame
AppVersion={#AppVersion}
AppPublisher=IDFrame Host
DefaultDirName={localappdata}\Programs\Portrait Studio
DefaultGroupName=IDFrame
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=IDFrame-Setup-{#AppVersion}
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\PortraitStudio.exe
SetupIconFile={#ClientDir}\payload\assets\portrait-studio.ico
CloseApplications=yes
RestartApplications=no

[Files]
Source: "{#ClientDir}\PortraitStudio.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ClientDir}\installed-manifest.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ClientDir}\payload\*"; DestDir: "{app}\payload"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\IDFrame"; Filename: "{app}\PortraitStudio.exe"; WorkingDir: "{app}"; IconFilename: "{app}\payload\assets\portrait-studio.ico"; AppUserModelID: "PortraitStudio.Desktop"
Name: "{group}\IDFrame"; Filename: "{app}\PortraitStudio.exe"; WorkingDir: "{app}"; IconFilename: "{app}\payload\assets\portrait-studio.ico"; AppUserModelID: "PortraitStudio.Desktop"

[Run]
Filename: "{app}\PortraitStudio.exe"; Description: "Open IDFrame"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\client.json"
Type: files; Name: "{app}\update.log"
Type: files; Name: "{app}\update.log.1"
Type: files; Name: "{app}\update.log.2"
Type: files; Name: "{app}\.client.lock"

[Code]
var
  HostPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  HostPage := CreateInputQueryPage(wpSelectDir, 'LAN update host',
    'Where should this client check for updates?',
    'Enter your host PC address and port. If the host is unavailable, the app opens with its installed version.');
  HostPage.Add('Host URL:', False);
  HostPage.Values[0] := ExpandConstant('{param:HOSTURL|{#HostURL}}');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  URL: String;
begin
  Result := True;
  if CurPageID = HostPage.ID then
  begin
    URL := Trim(HostPage.Values[0]);
    if ((Pos('http://', Lowercase(URL)) <> 1) and
        (Pos('https://', Lowercase(URL)) <> 1)) or
        (Pos('"', URL) > 0) or (Pos('\', URL) > 0) then
    begin
      MsgBox('Enter a URL such as http://192.168.83.169:8766', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  URL: String;
begin
  if CurStep = ssPostInstall then
  begin
    URL := Trim(HostPage.Values[0]);
    StringChangeEx(URL, '\', '\\', True);
    StringChangeEx(URL, '"', '\"', True);
    SaveStringToFile(ExpandConstant('{app}\client.json'),
      '{"host_url":"' + URL + '"}' + #13#10, False);
  end;
end;
