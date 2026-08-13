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
    [double]$MinimumFreeCommitGB = -1,
    [ValidateSet('', 'all', 'allowlist', 'none')]
    [string]$CustomNodeLoading = '',
    [string]$AllowedCustomNodeFoldersBase64 = '',
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
    -Port $Port `
    -ResourcePolicy $ResourcePolicy `
    -MinimumFreeCommitGB $MinimumFreeCommitGB `
    -CustomNodeLoading $CustomNodeLoading `
    -AllowedCustomNodeFoldersBase64 $AllowedCustomNodeFoldersBase64

Assert-BackendPrerequisites $config
Assert-BackendResourcePolicySupport $config
Assert-BackendCustomNodePolicySupport $config
$config.MemorySnapshot = Get-SystemMemorySnapshot
Set-BackendEffectiveMinimumFreeCommit $config

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
        supervisor_stderr_log = Get-BackendSupervisorStderrLog $config
        pid_file = $pidFile
        launcher_pid_file = $launcherPidFile
    }
    $payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config
    Write-BackendMessage -Json:$Json -Payload $payload -Message "Dry run: ComfyUI backend would start on $($config.HostAddress):$($config.Port)."
    exit 0
}

Assert-BackendSystemMemoryAdmission $config

Ensure-Directory $config.RuntimeDir
Ensure-Directory $config.LogsDir

$stdoutLog = Get-BackendStdoutLog $config
$stderrLog = Get-BackendStderrLog $config
$supervisorStderrLog = Get-BackendSupervisorStderrLog $config
$exitCodeFile = Get-BackendExitCodeFile $config
$logStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$previousStdoutLog = Move-ExistingBackendLog -Path $stdoutLog -Stamp $logStamp
$previousStderrLog = Move-ExistingBackendLog -Path $stderrLog -Stamp $logStamp
$previousSupervisorStderrLog = Move-ExistingBackendLog `
    -Path $supervisorStderrLog `
    -Stamp $logStamp
Remove-Item -LiteralPath $exitCodeFile -Force -ErrorAction SilentlyContinue

$previousPythonIoEncoding = $env:PYTHONIOENCODING
$env:PYTHONIOENCODING = 'utf-8'
try {
    $supervisorPath = Join-Path $PSScriptRoot 'backend_supervisor.ps1'
    $argumentsJson = ConvertTo-Json -InputObject ([object[]]$arguments) -Compress
    $argumentsBase64 = [Convert]::ToBase64String(
        [Text.Encoding]::UTF8.GetBytes($argumentsJson)
    )
    $supervisorArguments = @(
        '-NoProfile',
        '-ExecutionPolicy',
        'Bypass',
        '-File',
        $supervisorPath,
        '-PythonExe',
        $config.PythonExe,
        '-WorkingDirectory',
        $config.ComfyUIRoot,
        '-StdoutLog',
        $stdoutLog,
        '-StderrLog',
        $stderrLog,
        '-SupervisorStderrLog',
        $supervisorStderrLog,
        '-ExitCodeFile',
        $exitCodeFile,
        '-ArgumentsBase64',
        $argumentsBase64,
        '-ProfileName',
        $config.ProfileName,
        '-ComfyUIRoot',
        $config.ComfyUIRoot,
        '-SharedBasePath',
        $config.SharedBasePath,
        '-CustomNodeLoading',
        $config.CustomNodeLoading,
        '-AllowedCustomNodeFoldersBase64',
        $config.AllowedCustomNodeFoldersBase64,
        '-AcceleratorMutexName',
        $config.AcceleratorMutexName,
        '-Port',
        [string]$config.Port
    )
    $powerShellExe = (Get-Process -Id $PID).Path
    $supervisorStartInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $supervisorStartInfo.FileName = $powerShellExe
    $supervisorStartInfo.WorkingDirectory = $PSScriptRoot
    # Shell execution detaches the long-lived supervisor from this command's
    # redirected stdout/stderr handles. Without that detachment, callers that
    # capture this script's output wait for the supervisor lifetime even after
    # this script has returned its JSON result.
    $supervisorStartInfo.UseShellExecute = $true
    $supervisorStartInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $supervisorStartInfo.Arguments = ConvertTo-WindowsCommandLine $supervisorArguments
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $supervisorStartInfo
    if (-not $process.Start()) {
        throw "Failed to start the ComfyUI backend supervisor process."
    }
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
        $process.Refresh()
        if ($process.HasExited) {
            $process.WaitForExit()
            $supervisorExitCode = $null
            if (Test-Path -LiteralPath $exitCodeFile -PathType Leaf) {
                $recordedExitCode = (Get-Content -LiteralPath $exitCodeFile -Raw).Trim()
                if ($recordedExitCode -match '^-?\d+$') {
                    $supervisorExitCode = [int]$recordedExitCode
                }
            }
            if ($null -eq $supervisorExitCode) {
                try {
                    $supervisorExitCode = $process.ExitCode
                }
                catch {
                    $supervisorExitCode = 'unknown'
                }
            }
            if ([string]::IsNullOrWhiteSpace([string]$supervisorExitCode)) {
                $supervisorExitCode = 'unknown'
            }
            $failurePrefix = ''
            if ([string]$supervisorExitCode -match '^-?\d+$') {
                $nativeCrashCodes = @(
                    [int64]-1073741819,
                    [int64]-1073740791,
                    [int64]-1073740940,
                    [int64]-1073741676
                )
                if ($nativeCrashCodes -contains [int64]$supervisorExitCode) {
                    $failurePrefix = '[PIXELLE_NATIVE_STARTUP_CRASH] '
                }
            }
            Start-Sleep -Milliseconds 100
            $diagnosticTail = Get-BackendDiagnosticTail -Paths @(
                $supervisorStderrLog,
                $stderrLog,
                $stdoutLog
            )
            $diagnosticSuffix = if ($diagnosticTail) {
                "`nRecent diagnostic output:`n$diagnosticTail"
            }
            else {
                ''
            }
            throw (
                $failurePrefix +
                "ComfyUI backend supervisor PID $($process.Id) exited with code " +
                "$supervisorExitCode before $($config.HostAddress):$($config.Port) " +
                "started listening. Check logs: $supervisorStderrLog ; " +
                "$stderrLog$diagnosticSuffix"
            )
        }
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
                previous_supervisor_stderr_log = $previousSupervisorStderrLog
            }
            $payload = Add-BackendProfilePayloadFields -Payload $payload -Config $config
            Write-BackendMessage -Json:$Json -Payload $payload -Message "Started ComfyUI backend on $($config.HostAddress):$($config.Port) with listener PID $listenerPid."
            exit 0
        }
    } while ((Get-Date) -lt $deadline)

    $diagnosticTail = Get-BackendDiagnosticTail -Paths @(
        $supervisorStderrLog,
        $stderrLog,
        $stdoutLog
    )
    $diagnosticSuffix = if ($diagnosticTail) {
        "`nRecent diagnostic output:`n$diagnosticTail"
    }
    else {
        ''
    }
    throw (
        "[PIXELLE_STARTUP_TIMEOUT] Started ComfyUI backend supervisor PID " +
        "$($process.Id), but it did not " +
        "listen on $($config.HostAddress):$($config.Port) within " +
        "$ReadyTimeoutSeconds seconds. Check logs: $supervisorStderrLog ; " +
        "$stderrLog$diagnosticSuffix"
    )
}
catch {
    if (-not $started) {
        Stop-ProcessTreeOwnedByLaunch $process.Id
        Remove-BackendPidFiles $config
    }
    throw
}
