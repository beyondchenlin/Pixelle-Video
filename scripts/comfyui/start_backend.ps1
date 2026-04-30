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
    [int]$ReadyTimeoutSeconds = 90,
    [switch]$DryRun,
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

Assert-BackendPrerequisites $config

$arguments = Get-BackendArguments $config
$listener = Get-BackendListener $config
$pidFile = Get-BackendPidFile $config
$launcherPidFile = Get-BackendLauncherPidFile $config
$managedPid = Read-BackendPid $config

if ($listener) {
    $ownerPid = [int]$listener.OwningProcess
    if ($managedPid -and $managedPid -eq $ownerPid -and (Test-ManagedComfyUIProcess $config $ownerPid)) {
        $payload = [ordered]@{
            started = $false
            already_running = $true
            pid = $ownerPid
            launched_pid = Read-BackendLauncherPid $config
            host = $config.HostAddress
            port = $config.Port
            pid_file = $pidFile
            launcher_pid_file = $launcherPidFile
        }
        Write-BackendMessage -Json:$Json -Payload $payload -Message "ComfyUI backend is already running on $($config.HostAddress):$($config.Port) with PID $ownerPid."
        exit 0
    }

    $processInfo = Get-ProcessInfo $ownerPid
    $processName = if ($processInfo) { $processInfo.Name } else { 'unknown' }
    $commandLine = if ($processInfo) { $processInfo.CommandLine } else { 'unknown' }
    throw "Port $($config.HostAddress):$($config.Port) is already in use by PID $ownerPid ($processName). Refusing to start another ComfyUI backend. Command line: $commandLine"
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
    Write-BackendMessage -Json:$Json -Payload $payload -Message "Dry run: ComfyUI backend would start on $($config.HostAddress):$($config.Port)."
    exit 0
}

Ensure-Directory $config.RuntimeDir
Ensure-Directory $config.LogsDir

$stdoutLog = Get-BackendStdoutLog $config
$stderrLog = Get-BackendStderrLog $config

$process = Start-Process `
    -FilePath $config.PythonExe `
    -ArgumentList $arguments `
    -WorkingDirectory $config.ComfyUIRoot `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -WindowStyle Hidden `
    -PassThru

Set-Content -LiteralPath $pidFile -Value ([string]$process.Id) -Encoding ASCII
Set-Content -LiteralPath $launcherPidFile -Value ([string]$process.Id) -Encoding ASCII

$started = $false
try {
    $deadline = (Get-Date).AddSeconds($ReadyTimeoutSeconds)
    do {
        Start-Sleep -Milliseconds 500
        $listener = Get-BackendListener $config
        if ($listener) {
            $listenerPid = [int]$listener.OwningProcess
            if (-not (Test-ManagedComfyUIProcess $config $listenerPid)) {
                $processInfo = Get-ProcessInfo $listenerPid
                $commandLine = if ($processInfo) { $processInfo.CommandLine } else { 'unknown' }
                throw "Port $($config.HostAddress):$($config.Port) became occupied by PID $listenerPid, but it is not this ComfyUI backend. Command line: $commandLine"
            }

            Set-Content -LiteralPath $pidFile -Value ([string]$listenerPid) -Encoding ASCII
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
            }
            Write-BackendMessage -Json:$Json -Payload $payload -Message "Started ComfyUI backend on $($config.HostAddress):$($config.Port) with listener PID $listenerPid."
            exit 0
        }
    } while ((Get-Date) -lt $deadline)

    throw "Started ComfyUI backend PID $($process.Id), but it did not listen on $($config.HostAddress):$($config.Port) within $ReadyTimeoutSeconds seconds. Check logs: $stdoutLog ; $stderrLog"
}
catch {
    if (-not $started) {
        Stop-ManagedComfyUIProcessesForConfig $config
        Remove-BackendPidFiles $config
    }
    throw
}
