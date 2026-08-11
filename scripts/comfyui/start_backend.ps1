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
    [int]$ReadyTimeoutSeconds = 90,
    [switch]$DryRun,
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

Assert-BackendPrerequisites $config

$arguments = Get-BackendArguments $config
$listener = Get-BackendListener $config
$pidFile = Get-BackendPidFile $config
$launcherPidFile = Get-BackendLauncherPidFile $config
$managedPid = Read-BackendPid $config
if (-not $managedPid) {
    $managedPid = Get-BackendOwnedProcessId $config 'backend'
}

if ($listener) {
    $ownerPid = [int]$listener.OwningProcess
    if ($managedPid -and
        $managedPid -eq $ownerPid -and
        (Test-ManagedComfyUIProcess $config $ownerPid) -and
        (Test-BackendProcessOwnership $config $ownerPid 'backend')) {
        $existingLauncherPid = Read-BackendLauncherPid $config
        if (-not $existingLauncherPid) {
            $existingLauncherPid = Get-BackendOwnedProcessId $config 'launcher'
        }
        Set-Content -LiteralPath $pidFile -Value ([string]$ownerPid) -Encoding ASCII
        if ($existingLauncherPid) {
            Set-Content -LiteralPath $launcherPidFile -Value ([string]$existingLauncherPid) -Encoding ASCII
        }
        $payload = [ordered]@{
            started = $false
            already_running = $true
            pid = $ownerPid
            launched_pid = $existingLauncherPid
            host = $config.HostAddress
            port = $config.Port
            pid_file = $pidFile
            launcher_pid_file = $launcherPidFile
        }
        $payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config
        Write-BackendMessage -Json:$Json -Payload $payload -Message "ComfyUI backend is already running on $($config.HostAddress):$($config.Port) with PID $ownerPid."
        exit 0
    }

    $processInfo = Get-ProcessInfo $ownerPid
    $processName = if ($processInfo) { $processInfo.Name } else { 'unknown' }
    throw "Port $($config.HostAddress):$($config.Port) is already in use by PID $ownerPid ($processName). Refusing to start another ComfyUI backend."
}

if ($DryRun) {
    $payload = [ordered]@{
        dry_run = $true
        would_start = $true
        python = $config.PythonExe
        working_directory = $config.ComfyUIRoot
        arguments = $arguments
        host = $config.HostAddress
        port = $config.Port
        runtime_dir = $config.RuntimeDir
        logs_dir = $config.LogsDir
        stdout_log = Get-BackendStdoutLog $config
        stderr_log = Get-BackendStderrLog $config
        pid_file = $pidFile
        launcher_pid_file = $launcherPidFile
    }
    $payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config
    Write-BackendMessage -Json:$Json -Payload $payload -Message "Dry run: ComfyUI backend would start on $($config.HostAddress):$($config.Port)."
    exit 0
}

Ensure-Directory $config.RuntimeDir
Ensure-Directory $config.LogsDir

$stdoutLog = Get-BackendStdoutLog $config
$stderrLog = Get-BackendStderrLog $config
$logStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$previousStdoutLog = Move-ExistingBackendLog -Path $stdoutLog -Stamp $logStamp
$previousStderrLog = Move-ExistingBackendLog -Path $stderrLog -Stamp $logStamp

$previousPythonIoEncoding = $env:PYTHONIOENCODING
$env:PYTHONIOENCODING = 'utf-8'
try {
    $process = Start-Process `
        -FilePath $config.PythonExe `
        -ArgumentList $arguments `
        -WorkingDirectory $config.ComfyUIRoot `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -WindowStyle Hidden `
        -PassThru
}
finally {
    if ($null -eq $previousPythonIoEncoding) {
        Remove-Item Env:\PYTHONIOENCODING -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONIOENCODING = $previousPythonIoEncoding
    }
}

$started = $false
try {
    Set-Content -LiteralPath $pidFile -Value ([string]$process.Id) -Encoding ASCII
    Set-Content -LiteralPath $launcherPidFile -Value ([string]$process.Id) -Encoding ASCII
    Write-BackendOwnershipRecord $config $process.Id $process.Id

    $deadline = (Get-Date).AddSeconds($ReadyTimeoutSeconds)
    do {
        Start-Sleep -Milliseconds 500
        $listener = Get-BackendListener $config
        if ($listener) {
            $listenerPid = [int]$listener.OwningProcess
            if (-not (Test-ManagedComfyUIProcess $config $listenerPid)) {
                throw "Port $($config.HostAddress):$($config.Port) became occupied by PID $listenerPid, but it is not the process started by this operation."
            }

            Set-Content -LiteralPath $pidFile -Value ([string]$listenerPid) -Encoding ASCII
            Write-BackendOwnershipRecord $config $listenerPid $process.Id
            $started = $true
            $payload = [ordered]@{
                started = $true
                pid = $listenerPid
                launched_pid = [int]$process.Id
                host = $config.HostAddress
                port = $config.Port
                pid_file = $pidFile
                launcher_pid_file = $launcherPidFile
                stdout_log = $stdoutLog
                stderr_log = $stderrLog
                previous_stdout_log = $previousStdoutLog
                previous_stderr_log = $previousStderrLog
            }
            $payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config
            Write-BackendMessage -Json:$Json -Payload $payload -Message "Started ComfyUI backend on $($config.HostAddress):$($config.Port) with listener PID $listenerPid."
            exit 0
        }
    } while ((Get-Date) -lt $deadline)

    throw "Started ComfyUI backend PID $($process.Id), but it did not listen on $($config.HostAddress):$($config.Port) within $ReadyTimeoutSeconds seconds. Check logs: $stdoutLog ; $stderrLog"
}
catch {
    if (-not $started) {
        Stop-ProcessTreeOwnedByLaunch $process.Id
        Remove-BackendPidFiles $config
    }
    throw
}
