param(
    [Parameter(Mandatory = $true)]
    [string] $InstallRoot,
    [string] $PackageVersion,
    [string] $SuccessMarker,
    [switch] $TrustMachine,
    [switch] $RemoveMachineTrust,
    [switch] $Unregister
)

$ErrorActionPreference = 'Stop'
$packageName = 'IDFrame.LocalHotspot'
$packagePath = Join-Path $InstallRoot 'IDFrameHotspot.identity.msix'
$certificatePath = Join-Path $InstallRoot 'Assets\IDFramePackage.cer'
$machineStore = 'Cert:\LocalMachine\TrustedPeople'
$userStore = 'Cert:\CurrentUser\TrustedPeople'

function Write-SuccessMarker {
    # Let Inno Setup confirm the privileged certificate action completed.
    if ($SuccessMarker) {
        Set-Content -LiteralPath $SuccessMarker -Value 'ok' -Encoding ASCII
    }
}

function Write-RegistrationError($errorRecord) {
    # Keep the underlying Windows deployment error available after a setup failure.
    $details = $errorRecord | Out-String
    $logPath = Join-Path $InstallRoot 'IDFrame-hotspot-registration.log'
    [System.IO.File]::AppendAllText(
        $logPath,
        "[$(Get-Date -Format o)] $details`r`n",
        [System.Text.Encoding]::UTF8
    )
}

$certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
    $certificatePath
)

if ($TrustMachine) {
    $hadMachineCertificate = [bool](Get-ChildItem $machineStore |
        Where-Object Thumbprint -eq $certificate.Thumbprint)
    try {
        Import-Certificate -FilePath $certificatePath `
            -CertStoreLocation $machineStore | Out-Null
        Write-SuccessMarker
        exit 0
    } catch {
        if (-not $hadMachineCertificate) {
            Get-ChildItem $machineStore |
                Where-Object Thumbprint -eq $certificate.Thumbprint |
                Remove-Item -ErrorAction SilentlyContinue
        }
        Write-RegistrationError $_
        throw
    }
}

if ($RemoveMachineTrust) {
    Get-ChildItem $machineStore |
        Where-Object Thumbprint -eq $certificate.Thumbprint |
        Remove-Item -ErrorAction Stop
    Write-SuccessMarker
    exit 0
}

if ($Unregister) {
    Get-AppxPackage -Name $packageName -ErrorAction SilentlyContinue |
        Remove-AppxPackage -ErrorAction Stop
    Get-ChildItem $userStore |
        Where-Object Thumbprint -eq $certificate.Thumbprint |
        Remove-Item -ErrorAction SilentlyContinue
    exit 0
}

if ([Environment]::OSVersion.Version.Build -lt 19041) {
    throw 'Automatic hotspot support requires Windows 10 version 2004 or later.'
}

$existingPackage = Get-AppxPackage -Name $packageName -ErrorAction SilentlyContinue
if ($existingPackage -and $PackageVersion -and
    ([version]$existingPackage.Version -ge [version]$PackageVersion)) {
    exit 0
}

$hadUserCertificate = [bool](Get-ChildItem $userStore |
    Where-Object Thumbprint -eq $certificate.Thumbprint)

try {
    Import-Certificate -FilePath $certificatePath `
        -CertStoreLocation $userStore | Out-Null

    try {
        Add-AppxPackage -Path $packagePath -ExternalLocation $InstallRoot -ErrorAction Stop
    } catch {
        # A same-version repair may reject an already registered package. Replace
        # only this IDFrame package, then retry the registration once.
        if ($_.Exception.HResult -ne -2147009285) { throw }
        Get-AppxPackage -Name $packageName -ErrorAction SilentlyContinue |
            Remove-AppxPackage -ErrorAction Stop
        Add-AppxPackage -Path $packagePath -ExternalLocation $InstallRoot -ErrorAction Stop
    }
} catch {
    if (-not $existingPackage -and -not $hadUserCertificate) {
        Get-ChildItem $userStore |
            Where-Object Thumbprint -eq $certificate.Thumbprint |
            Remove-Item -ErrorAction SilentlyContinue
    }
    Write-RegistrationError $_
    $logPath = Join-Path $InstallRoot 'IDFrame-hotspot-registration.log'
    throw "Could not register the IDFrame hotspot package. Details were saved to $logPath"
}
