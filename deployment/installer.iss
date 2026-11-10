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
MinVersion=10.0.19041
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
Source: "{#ClientDir}\IDFrameHotspot.identity.msix"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ClientDir}\identity-assets\IDFramePackage.cer"; DestDir: "{app}\Assets"; Flags: ignoreversion
Source: "{#ClientDir}\identity-assets\Assets\*"; DestDir: "{app}\Assets"; Flags: ignoreversion
Source: "{#ClientDir}\register_hotspot_package.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\IDFrame"; Filename: "{app}\PortraitStudio.exe"; WorkingDir: "{app}"; IconFilename: "{app}\payload\assets\portrait-studio.ico"; AppUserModelID: "PortraitStudio.Desktop"
Name: "{group}\IDFrame"; Filename: "{app}\PortraitStudio.exe"; WorkingDir: "{app}"; IconFilename: "{app}\payload\assets\portrait-studio.ico"; AppUserModelID: "PortraitStudio.Desktop"

[Run]
Filename: "{app}\PortraitStudio.exe"; Description: "Open IDFrame"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoLogo -NoProfile -ExecutionPolicy Bypass -File ""{app}\register_hotspot_package.ps1"" -InstallRoot ""{app}"" -Unregister"; Flags: runhidden waituntilterminated; RunOnceId: "UnregisterHotspotPackage"

[UninstallDelete]
Type: files; Name: "{app}\client.json"
Type: files; Name: "{app}\update.log"
Type: files; Name: "{app}\update.log.1"
Type: files; Name: "{app}\update.log.2"
Type: files; Name: "{app}\.client.lock"

[Code]
var
  HostPage: TInputQueryWizardPage;

function RunMachineTrustAction(Action: String): Boolean;
// Elevate only the certificate trust operation; keep app installation per-user.
var
  MarkerPath: String;
  Parameters: String;
  ErrorCode: Integer;
begin
  MarkerPath := ExpandConstant('{tmp}\IDFrameMachineTrust.ok');
  DeleteFile(MarkerPath);
  Parameters := '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{app}\register_hotspot_package.ps1') +
    '" -InstallRoot "' + ExpandConstant('{app}') +
    '" ' + Action + ' -SuccessMarker "' + MarkerPath + '"';
  Result := ShellExec('runas',
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    Parameters, '', SW_HIDE, ewWaitUntilTerminated, ErrorCode) and
    FileExists(MarkerPath);
  DeleteFile(MarkerPath);
end;

procedure InitializeWizard;
// Ask for the LAN host address before installing this client.
begin
  HostPage := CreateInputQueryPage(wpSelectDir, 'LAN update host',
    'Where should this client check for updates?',
    'Enter your host PC address and port. If the host is unavailable, the app opens with its installed version.');
  HostPage.Add('Host URL:', False);
  HostPage.Values[0] := ExpandConstant('{param:HOSTURL|{#HostURL}}');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
// Validate the entered host URL before advancing the installer.
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
// Register local hotspot access, then persist the selected host URL.
var
  URL: String;
  ResultCode: Integer;
  Parameters: String;
begin
  if CurStep = ssPostInstall then
  begin
    Parameters := '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' +
      ExpandConstant('{app}\register_hotspot_package.ps1') +
      '" -InstallRoot "' + ExpandConstant('{app}') +
      '" -PackageVersion "{#AppVersion}.0"';

    if not RunMachineTrustAction('-TrustMachine') then
      RaiseException('IDFrame needs administrator approval to enable local phone transfer. ' +
        'Retry setup and approve the Windows administrator prompt. If it still fails, see ' +
        ExpandConstant('{app}\IDFrame-hotspot-registration.log') + '.');

    if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      Parameters, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or
      (ResultCode <> 0) then
      RaiseException('IDFrame could not register Windows hotspot access. ' +
        'See ' + ExpandConstant('{app}\IDFrame-hotspot-registration.log') +
        ' for the Windows deployment details.');

    URL := Trim(HostPage.Values[0]);
    StringChangeEx(URL, '\', '\\', True);
    StringChangeEx(URL, '"', '\"', True);
    SaveStringToFile(ExpandConstant('{app}\client.json'),
      '{"host_url":"' + URL + '"}' + #13#10, False);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
// Remove the machine-wide certificate when the user approves elevation.
begin
  if (CurUninstallStep = usUninstall) and
     FileExists(ExpandConstant('{app}\Assets\IDFramePackage.cer')) then
  begin
    if not RunMachineTrustAction('-RemoveMachineTrust') then
      MsgBox('IDFrame was removed, but Windows did not remove its phone-transfer ' +
        'firewall rule and machine-wide package certificate. An administrator can remove ' +
        'the IDFrame phone photo transfer rule and IDFrame Local Hotspot certificate.',
        mbInformation, MB_OK);
  end;
end;
