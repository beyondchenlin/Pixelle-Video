param(
    [string]$ProfileName = '',
    [string]$PythonExe = '',
    [string]$ComfyUIRoot = '',
    [string]$DataRoot = '',
    [string]$SharedBasePath = '',
    [string]$ExtraModelsConfig = '',
    [string]$FrontEndRoot = '',
    [string]$DatabaseUrl = '',
    [string]$RuntimeDir = '',
    [string]$LogsDir = '',
    [string]$HostAddress = '',
    [int]$Port = 0,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'backend_common.ps1')

$config = Resolve-PixelleComfyUIBackendConfig `
    -ProfileName $ProfileName `
    -PythonExe $PythonExe `
    -ComfyUIRoot $ComfyUIRoot `
    -DataRoot $DataRoot `
    -SharedBasePath $SharedBasePath `
    -ExtraModelsConfig $ExtraModelsConfig `
    -FrontEndRoot $FrontEndRoot `
    -DatabaseUrl $DatabaseUrl `
    -RuntimeDir $RuntimeDir `
    -LogsDir $LogsDir `
    -HostAddress $HostAddress `
    -Port $Port

$listener = Get-BackendListener $config
$managedPid = Read-BackendPid $config
$launcherPid = Read-BackendLauncherPid $config
if (-not $managedPid) {
    $managedPid = Get-BackendOwnedProcessId $config 'backend'
}
if (-not $launcherPid) {
    $launcherPid = Get-BackendOwnedProcessId $config 'launcher'
}
$pidFile = Get-BackendPidFile $config
$launcherPidFile = Get-BackendLauncherPidFile $config
$ownershipFile = Get-BackendOwnershipFile $config
$pidFilePresent = Test-Path -LiteralPath $pidFile -PathType Leaf
$launcherPidFilePresent = Test-Path -LiteralPath $launcherPidFile -PathType Leaf
$ownershipFilePresent = Test-Path -LiteralPath $ownershipFile -PathType Leaf

$listenerPid = $null
$listenerProcessName = $null
$listenerMatchesConfig = $false
$listenerManaged = $false
if ($listener) {
    $listenerPid = [int]$listener.OwningProcess
    $processInfo = Get-ProcessInfo $listenerPid
    if ($processInfo) {
        $listenerProcessName = $processInfo.Name
    }
    $listenerMatchesConfig = Test-ManagedComfyUIProcess $config $listenerPid
    $listenerManaged = [bool](
        $listenerMatchesConfig -and
        $managedPid -and
        $managedPid -eq $listenerPid -and
        (Test-BackendProcessOwnership $config $listenerPid 'backend')
    )
}

$payload = [ordered]@{
    host = $config.HostAddress
    port = $config.Port
    listener_present = [bool]$listener
    listener_pid = $listenerPid
    listener_process_name = $listenerProcessName
    listener_matches_profile = [bool]$listenerMatchesConfig
    listener_is_managed_backend = $listenerManaged
    pid_file_present = [bool]$pidFilePresent
    managed_pid = $managedPid
    pid_file = $pidFile
    launcher_pid_file_present = [bool]$launcherPidFilePresent
    launcher_pid = $launcherPid
    launcher_pid_file = $launcherPidFile
    ownership_file_present = [bool]$ownershipFilePresent
    ownership_file = $ownershipFile
}
$payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config

if ($Json) {
    Write-BackendJson $payload
}
elseif ($listener) {
    Write-Output "Listener: $($config.HostAddress):$($config.Port) PID $listenerPid managed=$listenerManaged"
    if ($pidFilePresent) {
        Write-Output "PID file: $pidFile -> $managedPid"
    }
}
else {
    Write-Output "No listener on $($config.HostAddress):$($config.Port)."
    if ($pidFilePresent) {
        Write-Output "PID file: $pidFile -> $managedPid"
    }
}
