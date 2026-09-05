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
    [ValidateSet('', 'auto', 'memory_safe', 'performance')]
    [string]$ResourcePolicy = '',
    [ValidateSet('', 'normal', 'high')]
    [string]$VramMode = '',
    [double]$MinimumFreeCommitGB = -1,
    [ValidateSet('', 'all', 'allowlist', 'none')]
    [string]$CustomNodeLoading = '',
    [string]$AllowedCustomNodeFoldersBase64 = '',
    [Parameter(DontShow = $true)]
    [ValidatePattern('^$|^(Global|Local)\\[A-Za-z0-9._-]{1,180}$')]
    [string]$AcceleratorMutexName = '',
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
    -Port $Port `
    -ResourcePolicy $ResourcePolicy `
    -VramMode $VramMode `
    -MinimumFreeCommitGB $MinimumFreeCommitGB `
    -CustomNodeLoading $CustomNodeLoading `
    -AllowedCustomNodeFoldersBase64 $AllowedCustomNodeFoldersBase64 `
    -AcceleratorMutexName $AcceleratorMutexName

$pidFile = Get-BackendPidFile $config
$launcherPidFile = Get-BackendLauncherPidFile $config
$listener = Get-BackendListener $config
$managedPid = Read-BackendPid $config
$launcherPid = Read-BackendLauncherPid $config
if (-not $managedPid) {
    $managedPid = Get-BackendOwnedProcessId $config 'backend'
}
if (-not $launcherPid) {
    $launcherPid = Get-BackendOwnedProcessId $config 'launcher'
}

if (-not (Test-Path -LiteralPath $pidFile -PathType Leaf) -and -not $managedPid) {
    $listenerPid = $null
    if ($listener) {
        $listenerPid = [int]$listener.OwningProcess
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

$launcherInfo = $null
$launcherIsManagedBackend = $false
if ($launcherPid -and $launcherPid -ne $managedPid) {
    $launcherInfo = Get-ProcessInfo $launcherPid
    if ($launcherInfo) {
        $launcherIsManagedBackend = [bool](
            (Test-ManagedComfyUIProcess $config $launcherPid) -and
            (Test-BackendProcessOwnership $config $launcherPid 'launcher')
        )
    }
}
if (-not $managedPid) {
    Remove-BackendPidFiles $config
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
    $stoppedLauncher = $false
    $launcherStopFailed = $false
    if ($launcherIsManagedBackend) {
        $stoppedLauncher = Stop-BackendOwnedComfyUIProcess $config $launcherPid 'launcher'
        $launcherStopFailed = -not $stoppedLauncher
    }
    if (-not $launcherStopFailed) {
        Remove-BackendPidFiles $config
    }
    $missingReason = 'process_missing'
    if ($launcherStopFailed) {
        $missingReason = 'launcher_stop_failed'
    }
    $payload = [ordered]@{
        stopped = [bool]$stoppedLauncher
        reason = $missingReason
        pid = $managedPid
        launcher_pid = $launcherPid
        stopped_launcher = $stoppedLauncher
        pid_file = $pidFile
        launcher_pid_file = $launcherPidFile
    }
    $payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config
    Write-BackendMessage -Json:$Json -Payload $payload -Message "ComfyUI backend PID $managedPid is no longer running; reconciled its recorded launcher."
    exit 0
}

if (-not (Test-ManagedComfyUIProcess $config $managedPid)) {
    $listenerPid = if ($listener) { [int]$listener.OwningProcess } else { $null }
    Remove-BackendPidFiles $config
    $payload = [ordered]@{
        stopped = $false
        reason = 'pid_file_points_to_unmanaged_process'
        requires_manual_restart = [bool]$listener
        pid = $managedPid
        listener_pid = $listenerPid
        launcher_pid = $launcherPid
        pid_file = $pidFile
        launcher_pid_file = $launcherPidFile
    }
    $payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config
    Write-BackendMessage -Json:$Json -Payload $payload -Message "Removed stale PID files without stopping unmanaged PID $managedPid."
    exit 0
}

if (-not (Test-BackendProcessOwnership $config $managedPid 'backend')) {
    $listenerPid = if ($listener) { [int]$listener.OwningProcess } else { $null }
    Remove-BackendPidFiles $config
    $payload = [ordered]@{
        stopped = $false
        reason = 'ownership_record_missing_or_mismatch'
        requires_manual_restart = [bool]$listener
        pid = $managedPid
        listener_pid = $listenerPid
        launcher_pid = $launcherPid
        pid_file = $pidFile
        launcher_pid_file = $launcherPidFile
    }
    $payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config
    Write-BackendMessage -Json:$Json -Payload $payload -Message "Removed legacy or mismatched ownership files without stopping PID $managedPid."
    exit 0
}

$listenerPid = $null
$stoppedListener = $false
if ($listener) {
    $listenerPid = [int]$listener.OwningProcess
    if ($listenerPid -ne $managedPid) {
        $stoppedLauncher = $false
        if ($launcherPid -and $launcherPid -ne $managedPid -and $launcherInfo -and $launcherIsManagedBackend) {
            $stoppedLauncher = Stop-BackendOwnedComfyUIProcess $config $launcherPid 'launcher'
        }
        $stoppedBackend = Stop-BackendOwnedComfyUIProcess $config $managedPid 'backend'
        $launcherStopConfirmed = -not $launcherIsManagedBackend -or $stoppedLauncher
        $stopConfirmed = $stoppedBackend -and $launcherStopConfirmed
        if ($stopConfirmed) {
            Remove-BackendPidFiles $config
        }
        $stopReason = 'owned_process_stop_failed'
        if ($stopConfirmed) {
            $stopReason = 'owned_process_stopped_external_listener_preserved'
        }
        $payload = [ordered]@{
            stopped = $stopConfirmed
            reason = $stopReason
            requires_manual_restart = $true
            preserved_external_listener = $true
            pid = $managedPid
            listener_pid = $listenerPid
            stopped_listener = $false
            launcher_pid = $launcherPid
            stopped_launcher = $stoppedLauncher
            pid_file = $pidFile
            launcher_pid_file = $launcherPidFile
        }
        $payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config
        Write-BackendMessage -Json:$Json -Payload $payload -Message "Reconciled Pixelle-owned PID $managedPid and preserved the independently owned listener PID $listenerPid."
        exit 0
    }
}

$stoppedLauncher = $false
if ($launcherPid -and $launcherPid -ne $managedPid) {
    if (-not $launcherInfo) {
        $launcherInfo = Get-ProcessInfo $launcherPid
    }
    if ($launcherInfo) {
        if ($launcherIsManagedBackend) {
            $stoppedLauncher = Stop-BackendOwnedComfyUIProcess $config $launcherPid 'launcher'
        }
    }
}
$launcherStopConfirmed = -not $launcherIsManagedBackend -or $stoppedLauncher
# Only stop the listener separately when the launcher tree was absent or could
# not be stopped. A confirmed launcher-tree stop already includes its child.
$stoppedBackend = $false
if ($launcherIsManagedBackend -and $stoppedLauncher) {
    $stoppedBackend = -not [bool](Get-ProcessInfo $managedPid)
}
else {
    $stoppedBackend = Stop-BackendOwnedComfyUIProcess $config $managedPid 'backend'
}
if ($listenerPid -and $listenerPid -eq $managedPid) {
    $stoppedListener = $stoppedBackend
}

$stopConfirmed = $stoppedBackend -and $launcherStopConfirmed
if ($stopConfirmed) {
    Remove-BackendPidFiles $config
}
$stopReason = 'owned_process_stop_failed'
if ($stopConfirmed) {
    $stopReason = 'owned_process_stopped'
}

$payload = [ordered]@{
    stopped = $stopConfirmed
    reason = $stopReason
    pid = $managedPid
    listener_pid = $listenerPid
    stopped_listener = $stoppedListener
    launcher_pid = $launcherPid
    stopped_launcher = $stoppedLauncher
    pid_file = $pidFile
    launcher_pid_file = $launcherPidFile
}
$payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config
Write-BackendMessage -Json:$Json -Payload $payload -Message "Reconciled Pixelle-managed ComfyUI backend PID $managedPid; stopped=$stopConfirmed."
