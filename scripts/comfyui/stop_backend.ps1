param(
    [string]$PythonExe = '',
    [string]$ComfyUIRoot = '',
    [string]$DataRoot = '',
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
    -PythonExe $PythonExe `
    -ComfyUIRoot $ComfyUIRoot `
    -DataRoot $DataRoot `
    -ExtraModelsConfig $ExtraModelsConfig `
    -FrontEndRoot $FrontEndRoot `
    -DatabaseUrl $DatabaseUrl `
    -RuntimeDir $RuntimeDir `
    -LogsDir $LogsDir `
    -HostAddress $HostAddress `
    -Port $Port

$pidFile = Get-BackendPidFile $config
$launcherPidFile = Get-BackendLauncherPidFile $config
if (-not (Test-Path -LiteralPath $pidFile -PathType Leaf)) {
    $payload = [ordered]@{
        stopped = $false
        reason = 'pid_file_missing'
        pid_file = $pidFile
        launcher_pid_file = $launcherPidFile
    }
    Write-BackendMessage -Json:$Json -Payload $payload -Message "No managed ComfyUI backend PID file found: $pidFile"
    exit 0
}

$managedPid = Read-BackendPid $config
$launcherPid = Read-BackendLauncherPid $config
if (-not $managedPid) {
    Remove-BackendPidFiles $config
    $payload = [ordered]@{
        stopped = $false
        reason = 'pid_file_invalid'
        pid_file = $pidFile
        launcher_pid_file = $launcherPidFile
    }
    Write-BackendMessage -Json:$Json -Payload $payload -Message "Removed invalid ComfyUI backend PID file: $pidFile"
    exit 0
}

$processInfo = Get-ProcessInfo $managedPid
if (-not $processInfo) {
    Remove-BackendPidFiles $config
    $payload = [ordered]@{
        stopped = $false
        reason = 'process_missing'
        pid = $managedPid
        launcher_pid = $launcherPid
        pid_file = $pidFile
        launcher_pid_file = $launcherPidFile
    }
    Write-BackendMessage -Json:$Json -Payload $payload -Message "ComfyUI backend PID $managedPid is no longer running. Removed stale PID file."
    exit 0
}

if (-not (Test-ManagedComfyUIProcess $config $managedPid)) {
    throw "PID file points to PID $managedPid, but that process is not the Pixelle-managed ComfyUI backend. Refusing to stop it. Command line: $($processInfo.CommandLine)"
}

$listener = Get-BackendListener $config
$listenerPid = $null
$stoppedListener = $false
if ($listener) {
    $listenerPid = [int]$listener.OwningProcess
    if ($listenerPid -ne $managedPid) {
        if (-not (Test-ManagedComfyUIProcess $config $listenerPid)) {
            $listenerInfo = Get-ProcessInfo $listenerPid
            $listenerCommandLine = if ($listenerInfo) { $listenerInfo.CommandLine } else { 'unknown' }
            throw "Port $($config.HostAddress):$($config.Port) is owned by PID $listenerPid, but that process is not the Pixelle-managed ComfyUI backend. Refusing to stop it. Command line: $listenerCommandLine"
        }
        Stop-ManagedComfyUIProcess $config $listenerPid | Out-Null
        $stoppedListener = $true
    }
}

Stop-ManagedComfyUIProcess $config $managedPid | Out-Null
if ($listenerPid -and $listenerPid -eq $managedPid) {
    $stoppedListener = $true
}

$stoppedLauncher = $false
if ($launcherPid -and $launcherPid -ne $managedPid) {
    $launcherInfo = Get-ProcessInfo $launcherPid
    if ($launcherInfo) {
        if (-not (Test-ManagedComfyUIProcess $config $launcherPid)) {
            throw "Launcher PID file points to PID $launcherPid, but that process is not the Pixelle-managed ComfyUI backend. Refusing to stop it. Command line: $($launcherInfo.CommandLine)"
        }
        Stop-ManagedComfyUIProcess $config $launcherPid | Out-Null
        $stoppedLauncher = $true
    }
}

Remove-BackendPidFiles $config

$payload = [ordered]@{
    stopped = $true
    pid = $managedPid
    listener_pid = $listenerPid
    stopped_listener = $stoppedListener
    launcher_pid = $launcherPid
    stopped_launcher = $stoppedLauncher
    pid_file = $pidFile
    launcher_pid_file = $launcherPidFile
}
Write-BackendMessage -Json:$Json -Payload $payload -Message "Stopped Pixelle-managed ComfyUI backend PID $managedPid."
