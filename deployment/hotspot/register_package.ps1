param(
    [Parameter(Mandatory = $true)]
    [string] $InstallRoot,
    [string] $PackageVersion,
    [switch] $Unregister
)

$ErrorActionPreference = 'Stop'
$packageName = 'IDFrame.LocalHotspot'
$packagePath = Join-Path $InstallRoot 'IDFrameHotspot.identity.msix'
$certificatePath = Join-Path $InstallRoot 'Assets\IDFramePackage.cer'

if ($Unregister) {
    Get-AppxPackage -Name $packageName -ErrorAction SilentlyContinue |
        Remove-AppxPackage -ErrorAction Stop
    if (Test-Path -LiteralPath $certificatePath) {
        $certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
            $certificatePath
        )
        Get-ChildItem Cert:\CurrentUser\TrustedPeople |
            Where-Object Thumbprint -eq $certificate.Thumbprint |
            Remove-Item -ErrorAction SilentlyContinue
    }
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

Import-Certificate -FilePath $certificatePath `
    -CertStoreLocation Cert:\CurrentUser\TrustedPeople | Out-Null

try {
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
    if (-not $existingPackage) {
        $certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
            $certificatePath
        )
        Get-ChildItem Cert:\CurrentUser\TrustedPeople |
            Where-Object Thumbprint -eq $certificate.Thumbprint |
            Remove-Item -ErrorAction SilentlyContinue
    }
    throw
}
