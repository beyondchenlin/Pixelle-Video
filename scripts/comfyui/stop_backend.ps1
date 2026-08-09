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

$pidFile = Get-BackendPidFile $config
$launcherPidFile = Get-BackendLauncherPidFile $config
$listener = Get-BackendListener $config
$script:StoppedMatchingBackendListener = $false

function Stop-MatchingBackendListenerForReason {
    param(
        [object]$Listener,
        [string]$Reason,
        [Nullable[int]]$ManagedPid = $null,
        [Nullable[int]]$LauncherPid = $null
    )

    $listenerPid = $null
    $script:StoppedMatchingBackendListener = $false
    if ($Listener) {
        $listenerPid = [int]$Listener.OwningProcess
        if (Test-ManagedComfyUIProcess $config $listenerPid) {
            Stop-ManagedComfyUIProcess $config $listenerPid | Out-Null
            Remove-BackendPidFiles $config
            $payload = [ordered]@{
                stopped = $true
                reason = $Reason
                pid = $ManagedPid
                listener_pid = $listenerPid
                stopped_listener = $true
                launcher_pid = $LauncherPid
                stopped_launcher = $false
                pid_file = $pidFile
                launcher_pid_file = $launcherPidFile
            }
            $payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config
            Write-BackendMessage -Json:$Json -Payload $payload -Message "Stopped matching ComfyUI backend listener PID $listenerPid ($Reason)."
            $script:StoppedMatchingBackendListener = $true
            return
        }
    }
}

if (-not (Test-Path -LiteralPath $pidFile -PathType Leaf)) {
    $listenerPid = $null
    if ($listener) {
        $listenerPid = [int]$listener.OwningProcess
        Stop-MatchingBackendListenerForReason -Listener $listener -Reason 'matching_listener_without_pid_file'
        if ($script:StoppedMatchingBackendListener) {
            exit 0
        }
    }

    $payload = [ordered]@{
        stopped = $false
        reason = 'pid_file_missing'
        listener_pid = $listenerPid
        pid_file = $pidFile
        launcher_pid_file = $launcherPidFile
    }
    $payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config
    Write-BackendMessage -Json:$Json -Payload $payload -Message "No managed ComfyUI backend PID file found: $pidFile"
    exit 0
}

$managedPid = Read-BackendPid $config
$launcherPid = Read-BackendLauncherPid $config
if (-not $managedPid) {
    Remove-BackendPidFiles $config
    Stop-MatchingBackendListenerForReason -Listener $listener -Reason 'pid_file_invalid_matching_listener' -LauncherPid $launcherPid
    if ($script:StoppedMatchingBackendListener) {
        exit 0
    }
    $payload = [ordered]@{
        stopped = $false
        reason = 'pid_file_invalid'
        pid_file = $pidFile
        launcher_pid_file = $launcherPidFile
    }
    $payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config
    Write-BackendMessage -Json:$Json -Payload $payload -Message "Removed invalid ComfyUI backend PID file: $pidFile"
    exit 0
}

$processInfo = Get-ProcessInfo $managedPid
if (-not $processInfo) {
    Remove-BackendPidFiles $config
    Stop-MatchingBackendListenerForReason -Listener $listener -Reason 'process_missing_matching_listener' -ManagedPid $managedPid -LauncherPid $launcherPid
    if ($script:StoppedMatchingBackendListener) {
        exit 0
    }
    $payload = [ordered]@{
        stopped = $false
        reason = 'process_missing'
        pid = $managedPid
        launcher_pid = $launcherPid
        pid_file = $pidFile
        launcher_pid_file = $launcherPidFile
    }
    $payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config
    Write-BackendMessage -Json:$Json -Payload $payload -Message "ComfyUI backend PID $managedPid is no longer running. Removed stale PID file."
    exit 0
}

$launcherInfo = $null
$launcherIsManagedBackend = $false
if ($launcherPid -and $launcherPid -ne $managedPid) {
    $launcherInfo = Get-ProcessInfo $launcherPid
    if ($launcherInfo) {
        $launcherIsManagedBackend = Test-ManagedComfyUIProcess $config $launcherPid
    }
}

if (-not (Test-ManagedComfyUIProcess $config $managedPid)) {
    if ($listener) {
        $listenerPid = [int]$listener.OwningProcess
        if ($listenerPid -ne $managedPid) {
            Stop-MatchingBackendListenerForReason -Listener $listener -Reason 'pid_file_unmanaged_matching_listener' -ManagedPid $managedPid -LauncherPid $launcherPid
            if ($script:StoppedMatchingBackendListener) {
                exit 0
            }
        }
    }
    if (-not $listener) {
        Remove-BackendPidFiles $config
        $payload = [ordered]@{
            stopped = $false
            reason = 'pid_file_points_to_unmanaged_process_without_listener'
            pid = $managedPid
            launcher_pid = $launcherPid
            pid_file = $pidFile
            launcher_pid_file = $launcherPidFile
        }
        $payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config
        Write-BackendMessage -Json:$Json -Payload $payload -Message "Removed stale ComfyUI backend PID file pointing to unmanaged PID $managedPid."
        exit 0
    }
    throw "PID file points to PID $managedPid, but that process is not the Pixelle-managed ComfyUI backend. Refusing to stop it. Command line: $($processInfo.CommandLine)"
}

$listenerPid = $null
$stoppedListener = $false
if ($listener) {
    $listenerPid = [int]$listener.OwningProcess
    if ($listenerPid -ne $managedPid) {
        if (-not (Test-ManagedComfyUIProcess $config $listenerPid)) {
            $listenerInfo = Get-ProcessInfo $listenerPid
            $listenerCommandLine = if ($listenerInfo) { $listenerInfo.CommandLine } else { 'unknown' }
            Remove-BackendPidFiles $config
            $payload = [ordered]@{
                stopped = $false
                reason = 'listener_owned_by_unmanaged_process'
                requires_manual_restart = $true
                pid = $managedPid
                listener_pid = $listenerPid
                launcher_pid = $launcherPid
                pid_file = $pidFile
                launcher_pid_file = $launcherPidFile
                command_line = $listenerCommandLine
            }
            $payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config
            Write-BackendMessage -Json:$Json -Payload $payload -Message "Port $($config.HostAddress):$($config.Port) is owned by unmanaged PID $listenerPid. Skipped automatic stop."
            exit 0
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
    if (-not $launcherInfo) {
        $launcherInfo = Get-ProcessInfo $launcherPid
    }
    if ($launcherInfo) {
        if ($launcherIsManagedBackend) {
            Stop-ManagedComfyUIProcess $config $launcherPid | Out-Null
            $stoppedLauncher = $true
        }
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
$payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config
Write-BackendMessage -Json:$Json -Payload $payload -Message "Stopped Pixelle-managed ComfyUI backend PID $managedPid."
