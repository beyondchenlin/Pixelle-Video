Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-PixelleRepoRoot {
    return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
}

function Resolve-BackendValue {
    param(
        [string]$Provided,
        [string]$EnvironmentName,
        [string]$Default
    )

    if ($Provided -and $Provided.Trim()) {
        return $Provided
    }

    $environmentValue = [Environment]::GetEnvironmentVariable($EnvironmentName)
    if ($environmentValue -and $environmentValue.Trim()) {
        return $environmentValue
    }

    return $Default
}

function Resolve-BackendInt {
    param(
        [int]$Provided,
        [string]$EnvironmentName,
        [int]$Default
    )

    if ($Provided -gt 0) {
        return $Provided
    }

    $environmentValue = [Environment]::GetEnvironmentVariable($EnvironmentName)
    if ($environmentValue -and $environmentValue.Trim()) {
        return [int]$environmentValue
    }

    return $Default
}

function Resolve-BackendDouble {
    param(
        [double]$Provided,
        [string]$EnvironmentName,
        [double]$Default
    )

    if ($Provided -ge 0) {
        return $Provided
    }

    $environmentValue = [Environment]::GetEnvironmentVariable($EnvironmentName)
    if ($environmentValue -and $environmentValue.Trim()) {
        return [double]::Parse(
            $environmentValue,
            [System.Globalization.CultureInfo]::InvariantCulture
        )
    }

    return $Default
}

function Get-SystemMemorySnapshot {
    try {
        $operatingSystem = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
        $computerSystem = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
        # Win32_OperatingSystem exposes the Windows commit limit and remaining
        # commit in KiB. Prefer raw performance counters when available, but do
        # not reject startup solely because that optional provider is busy.
        $commitLimitBytes = [double]$operatingSystem.TotalVirtualMemorySize * 1KB
        $freeCommitBytes = [double]$operatingSystem.FreeVirtualMemory * 1KB
        $commitSource = 'operating_system'
        try {
            $memoryPerformance = Get-CimInstance `
                Win32_PerfRawData_PerfOS_Memory `
                -ErrorAction Stop
            $performanceCommitLimit = [double]$memoryPerformance.CommitLimit
            $performanceCommitted = [double]$memoryPerformance.CommittedBytes
            if ($performanceCommitLimit -gt 0 -and
                $performanceCommitted -ge 0 -and
                $performanceCommitted -le $performanceCommitLimit) {
                $commitLimitBytes = $performanceCommitLimit
                $freeCommitBytes = $performanceCommitLimit - $performanceCommitted
                $commitSource = 'performance_counter'
            }
        }
        catch {
            # The operating-system values above are the same Windows commit
            # accounting domain and remain a valid admission-control fallback.
        }
        $committedBytes = [math]::Max(
            [double]0,
            [double]($commitLimitBytes - $freeCommitBytes)
        )
        return [ordered]@{
            total_physical_gb = [math]::Round(
                [double]$computerSystem.TotalPhysicalMemory / 1GB,
                2
            )
            free_physical_gb = [math]::Round(
                [double]$operatingSystem.FreePhysicalMemory / 1MB,
                2
            )
            total_commit_gb = [math]::Round(
                $commitLimitBytes / 1GB,
                2
            )
            committed_gb = [math]::Round($committedBytes / 1GB, 2)
            free_commit_gb = [math]::Round(
                [math]::Max([double]0, [double]$freeCommitBytes) / 1GB,
                2
            )
            commit_source = $commitSource
        }
    }
    catch {
        return $null
    }
}

function Resolve-BackendResourcePolicy {
    param(
        [string]$RequestedPolicy
    )

    $normalized = ([string]$RequestedPolicy).Trim().ToLowerInvariant()
    if ($normalized -notin @('auto', 'memory_safe', 'performance')) {
        throw "Unsupported ComfyUI resource policy: $RequestedPolicy"
    }
    if ($normalized -ne 'auto') {
        return $normalized
    }

    # Managed services share system commit with the web process, renderers, and
    # later pipeline stages. Workflow model sizes are not known at service-start
    # time, so physical-RAM thresholds cannot prove that pinned/offload buffers
    # are safe. Auto is therefore the stable safe default; performance is an
    # explicit opt-in for operators who have measured their complete workload.
    return 'memory_safe'
}

function ConvertTo-SqliteUrl {
    param([string]$DatabasePath)
    return "sqlite:///$($DatabasePath -replace '\\', '/')"
}

function Resolve-PixelleComfyUIBackendConfig {
    param(
        [string]$ProfileName,
        [string]$PythonExe,
        [string]$ComfyUIRoot,
        [string]$DataRoot,
        [string]$SharedBasePath,
        [string]$ExtraModelsConfig,
        [string]$FrontEndRoot,
        [string]$DatabaseUrl,
        [string]$RuntimeDir,
        [string]$LogsDir,
        [string]$HostAddress,
        [int]$Port,
        [string]$ResourcePolicy = '',
        [double]$MinimumFreeCommitGB = -1
    )

    $repoRoot = Get-PixelleRepoRoot
    $resolvedDataRoot = Resolve-BackendValue $DataRoot 'PIXELLE_COMFYUI_DATA_ROOT' 'E:\ComfyUIData\pixelle'
    $defaultSharedBasePath = Split-Path -Parent $resolvedDataRoot
    if (-not $defaultSharedBasePath) {
        $defaultSharedBasePath = $resolvedDataRoot
    }
    $resolvedSharedBasePath = Resolve-BackendValue $SharedBasePath 'PIXELLE_COMFYUI_SHARED_BASE_PATH' $defaultSharedBasePath
    $resolvedComfyUIRoot = Resolve-BackendValue $ComfyUIRoot 'PIXELLE_COMFYUI_ROOT' 'E:\comfyui\resources\ComfyUI'
    $defaultDatabaseUrl = ConvertTo-SqliteUrl (Join-Path $resolvedDataRoot 'user\comfyui.db')
    $resolvedProfileName = Resolve-BackendValue $ProfileName 'PIXELLE_COMFYUI_PROFILE' 'default'
    $resolvedHostAddress = Resolve-BackendValue $HostAddress 'PIXELLE_COMFYUI_HOST' '127.0.0.1'
    if ($resolvedHostAddress -ieq 'localhost') {
        $resolvedHostAddress = '127.0.0.1'
    }
    $resolvedPort = Resolve-BackendInt $Port 'PIXELLE_COMFYUI_PORT' 8000
    if ($resolvedPort -lt 1 -or $resolvedPort -gt 65535) {
        throw "ComfyUI port must be between 1 and 65535: $resolvedPort"
    }
    $requestedResourcePolicy = Resolve-BackendValue `
        $ResourcePolicy `
        'PIXELLE_COMFYUI_RESOURCE_POLICY' `
        'auto'
    $resolvedResourcePolicy = Resolve-BackendResourcePolicy `
        $requestedResourcePolicy
    $resolvedMinimumFreeCommitGB = Resolve-BackendDouble `
        $MinimumFreeCommitGB `
        'PIXELLE_COMFYUI_MINIMUM_FREE_COMMIT_GB' `
        12.0
    if ($resolvedMinimumFreeCommitGB -lt 0 -or $resolvedMinimumFreeCommitGB -gt 256) {
        throw "ComfyUI minimum free commit must be between 0 and 256 GiB: $resolvedMinimumFreeCommitGB"
    }

    return [ordered]@{
        ProfileName = $resolvedProfileName
        RepoRoot = $repoRoot
        PythonExe = Resolve-BackendValue $PythonExe 'PIXELLE_COMFYUI_PYTHON' (Join-Path $resolvedSharedBasePath '.venv\Scripts\python.exe')
        ComfyUIRoot = $resolvedComfyUIRoot
        DataRoot = $resolvedDataRoot
        SharedBasePath = $resolvedSharedBasePath
        ExtraModelsConfig = Resolve-BackendValue $ExtraModelsConfig 'PIXELLE_COMFYUI_EXTRA_MODELS_CONFIG' ''
        FrontEndRoot = Resolve-BackendValue $FrontEndRoot 'PIXELLE_COMFYUI_FRONTEND_ROOT' ''
        DatabaseUrl = Resolve-BackendValue $DatabaseUrl 'PIXELLE_COMFYUI_DATABASE_URL' $defaultDatabaseUrl
        RuntimeDir = Resolve-BackendValue $RuntimeDir 'PIXELLE_COMFYUI_RUNTIME_DIR' (Join-Path $repoRoot '_runtime\comfyui')
        LogsDir = Resolve-BackendValue $LogsDir 'PIXELLE_COMFYUI_LOGS_DIR' (Join-Path $repoRoot 'logs\comfyui')
        HostAddress = $resolvedHostAddress
        Port = $resolvedPort
        RequestedResourcePolicy = $requestedResourcePolicy
        ResourcePolicy = $resolvedResourcePolicy
        MinimumFreeCommitGB = $resolvedMinimumFreeCommitGB
        MemorySnapshot = $null
    }
}

function Get-BackendPidFile {
    param([hashtable]$Config)
    return (Join-Path $Config.RuntimeDir 'comfyui-backend.pid')
}

function Get-BackendLauncherPidFile {
    param([hashtable]$Config)
    return (Join-Path $Config.RuntimeDir 'comfyui-backend.launcher.pid')
}

function Get-BackendOwnershipFile {
    param([hashtable]$Config)
    return (Join-Path $Config.RuntimeDir 'comfyui-backend.owner.json')
}

function Get-BackendStdoutLog {
    param([hashtable]$Config)
    return (Join-Path $Config.LogsDir 'comfyui-backend.stdout.log')
}

function Get-BackendStderrLog {
    param([hashtable]$Config)
    return (Join-Path $Config.LogsDir 'comfyui-backend.stderr.log')
}

function Move-ExistingBackendLog {
    param(
        [string]$Path,
        [string]$Stamp
    )

    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }

    $directory = Split-Path -Parent $Path
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($Path)
    $extension = [System.IO.Path]::GetExtension($Path)
    $archivePath = Join-Path $directory "$baseName.$Stamp$extension"
    $suffix = 1
    while (Test-Path -LiteralPath $archivePath) {
        $archivePath = Join-Path $directory "$baseName.$Stamp.$suffix$extension"
        $suffix += 1
    }

    Move-Item -LiteralPath $Path -Destination $archivePath
    return $archivePath
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Add-BackendProfilePayloadFields {
    param(
        [System.Collections.IDictionary]$Payload,
        [hashtable]$Config
    )

    $Payload['profile'] = $Config.ProfileName
    $Payload['host'] = $Config.HostAddress
    $Payload['port'] = $Config.Port
    $Payload['data_root'] = $Config.DataRoot
    $Payload['shared_base_path'] = $Config.SharedBasePath
    $Payload['runtime_dir'] = $Config.RuntimeDir
    $Payload['logs_dir'] = $Config.LogsDir
    $Payload['database_url'] = $Config.DatabaseUrl
    $Payload['pid_file'] = Get-BackendPidFile $Config
    $Payload['launcher_pid_file'] = Get-BackendLauncherPidFile $Config
    $Payload['ownership_file'] = Get-BackendOwnershipFile $Config
    $Payload['stdout_log'] = Get-BackendStdoutLog $Config
    $Payload['stderr_log'] = Get-BackendStderrLog $Config
    $Payload['requested_resource_policy'] = $Config.RequestedResourcePolicy
    $Payload['resource_policy'] = $Config.ResourcePolicy
    $Payload['minimum_free_commit_gb'] = $Config.MinimumFreeCommitGB
    $Payload['system_memory'] = $Config.MemorySnapshot
    return $Payload
}

function Assert-BackendPrerequisites {
    param([hashtable]$Config)

    $mainPy = Join-Path $Config.ComfyUIRoot 'main.py'
    $inputDir = Join-Path $Config.DataRoot 'input'
    $outputDir = Join-Path $Config.DataRoot 'output'
    $userDir = Join-Path $Config.DataRoot 'user'

    if (-not (Test-Path -LiteralPath $Config.PythonExe -PathType Leaf)) {
        throw "ComfyUI Python executable does not exist: $($Config.PythonExe)"
    }
    if (-not (Test-Path -LiteralPath $mainPy -PathType Leaf)) {
        throw "ComfyUI main.py does not exist: $mainPy"
    }
    foreach ($directory in @($inputDir, $outputDir, $userDir, $Config.RuntimeDir, $Config.LogsDir)) {
        Ensure-Directory $directory
    }
    if ($Config.ExtraModelsConfig -and -not (Test-Path -LiteralPath $Config.ExtraModelsConfig -PathType Leaf)) {
        throw "ComfyUI extra models config does not exist: $($Config.ExtraModelsConfig)"
    }
    if ($Config.FrontEndRoot -and -not (Test-Path -LiteralPath $Config.FrontEndRoot -PathType Container)) {
        throw "ComfyUI front-end root does not exist: $($Config.FrontEndRoot)"
    }
    if (-not $Config.DatabaseUrl.StartsWith('sqlite:///')) {
        throw "ComfyUI database URL must use sqlite:///: $($Config.DatabaseUrl)"
    }
}

function Assert-BackendSystemMemoryAdmission {
    param([hashtable]$Config)

    $minimum = [double]$Config.MinimumFreeCommitGB
    if ($minimum -le 0) {
        return
    }
    $snapshot = $Config.MemorySnapshot
    if (-not $snapshot) {
        $snapshot = Get-SystemMemorySnapshot
    }
    if (-not $snapshot) {
        throw "Could not inspect Windows system memory before starting ComfyUI."
    }
    $Config.MemorySnapshot = $snapshot
    $available = [double]$snapshot.free_commit_gb
    if ($available -lt $minimum) {
        throw (
            "Refusing to start ComfyUI because available system commit is " +
            "$available GiB, below the configured minimum of $minimum GiB. " +
            "Close memory-intensive applications or increase the Windows page file."
        )
    }
}

function Assert-BackendResourcePolicySupport {
    param([hashtable]$Config)

    if ($Config.ResourcePolicy -ne 'memory_safe') {
        return
    }
    $cliArgumentsPath = Join-Path $Config.ComfyUIRoot 'comfy\cli_args.py'
    if (-not (Test-Path -LiteralPath $cliArgumentsPath -PathType Leaf)) {
        throw (
            "Configured ComfyUI cannot prove support for the memory-safe launch " +
            "contract because comfy/cli_args.py is missing: $cliArgumentsPath"
        )
    }
    $cliSource = Get-Content -LiteralPath $cliArgumentsPath -Raw
    $missingArguments = @(
        @(
            '--disable-pinned-memory',
            '--disable-async-offload',
            '--cache-none'
        ) | Where-Object {
            $cliSource.IndexOf($_, [System.StringComparison]::Ordinal) -lt 0
        }
    )
    if ($missingArguments.Count -gt 0) {
        throw (
            "Configured ComfyUI does not support the memory-safe launch contract. " +
            "Missing argument(s): $($missingArguments -join ', '). Update ComfyUI or " +
            "explicitly select resource_policy=performance after accepting the memory risk."
        )
    }
}

function Get-BackendArguments {
    param([hashtable]$Config)

    $arguments = New-Object System.Collections.Generic.List[string]
    [void]$arguments.Add((Join-Path $Config.ComfyUIRoot 'main.py'))
    [void]$arguments.Add('--user-directory')
    [void]$arguments.Add((Join-Path $Config.DataRoot 'user'))
    [void]$arguments.Add('--input-directory')
    [void]$arguments.Add((Join-Path $Config.DataRoot 'input'))
    [void]$arguments.Add('--output-directory')
    [void]$arguments.Add((Join-Path $Config.DataRoot 'output'))
    if ($Config.FrontEndRoot) {
        [void]$arguments.Add('--front-end-root')
        [void]$arguments.Add($Config.FrontEndRoot)
    }
    [void]$arguments.Add('--base-directory')
    [void]$arguments.Add($Config.SharedBasePath)
    [void]$arguments.Add('--database-url')
    [void]$arguments.Add($Config.DatabaseUrl)

    if ($Config.ExtraModelsConfig) {
        [void]$arguments.Add('--extra-model-paths-config')
        [void]$arguments.Add($Config.ExtraModelsConfig)
    }

    [void]$arguments.Add('--listen')
    [void]$arguments.Add($Config.HostAddress)
    [void]$arguments.Add('--port')
    [void]$arguments.Add([string]$Config.Port)
    [void]$arguments.Add('--normalvram')
    if ($Config.ResourcePolicy -eq 'memory_safe') {
        [void]$arguments.Add('--disable-pinned-memory')
        [void]$arguments.Add('--disable-async-offload')
        [void]$arguments.Add('--cache-none')
    }

    return [string[]]$arguments.ToArray()
}

function Get-BackendListener {
    param([hashtable]$Config)

    $hostAddress = [string]$Config.HostAddress
    return Get-NetTCPConnection `
        -LocalPort $Config.Port `
        -ErrorAction SilentlyContinue |
        Where-Object {
            $_.State -eq 'Listen' -and (
                $_.LocalAddress -eq $hostAddress -or
                $_.LocalAddress -eq '0.0.0.0' -or
                $_.LocalAddress -eq '::' -or
                $hostAddress -eq '0.0.0.0' -or
                $hostAddress -eq '::'
            )
        } |
        Select-Object -First 1
}

function Get-ProcessInfo {
    param([int]$ProcessId)
    return Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
}

function Get-CommandLineValueVariants {
    param([string]$Value)

    $variants = New-Object System.Collections.Generic.List[string]
    if (-not $Value) {
        return [string[]]$variants.ToArray()
    }

    $slashVariant = $Value.Replace('\', '/')
    $backslashVariant = $Value.Replace('/', '\')

    foreach ($candidate in @($Value, $slashVariant, $backslashVariant)) {
        if ($candidate -and -not $variants.Contains($candidate)) {
            [void]$variants.Add($candidate)
        }
    }
    return [string[]]$variants.ToArray()
}

function Test-CommandLineContainsValue {
    param(
        [string]$CommandLine,
        [string]$Value
    )

    if (-not $CommandLine -or -not $Value) {
        return $false
    }

    foreach ($variant in (Get-CommandLineValueVariants $Value)) {
        if ($CommandLine.IndexOf($variant, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            return $true
        }
    }
    return $false
}

function Test-CommandLineArgumentValue {
    param(
        [string]$CommandLine,
        [string]$Name,
        [string]$Value
    )

    if (-not $CommandLine -or -not $Name -or -not $Value) {
        return $false
    }

    $escapedName = [regex]::Escape($Name)
    foreach ($variant in (Get-CommandLineValueVariants $Value)) {
        $escapedValue = [regex]::Escape($variant)
        $pattern = '(^|\s)' + $escapedName + '(?:(?:\s+)|=)(?:"' + $escapedValue + '"|' + $escapedValue + ')(?=\s|$)'
        if ([regex]::IsMatch($CommandLine, $pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)) {
            return $true
        }
    }
    return $false
}

function Test-ManagedComfyUICommandLine {
    param(
        [hashtable]$Config,
        [string]$CommandLine
    )

    $mainPy = Join-Path $Config.ComfyUIRoot 'main.py'
    $baseDirectoryMatches = Test-CommandLineArgumentValue $CommandLine '--base-directory' $Config.SharedBasePath
    if (-not $baseDirectoryMatches -and $Config.DataRoot -and $Config.DataRoot -ne $Config.SharedBasePath) {
        $baseDirectoryMatches = Test-CommandLineArgumentValue $CommandLine '--base-directory' $Config.DataRoot
    }
    $backendMatches = (
        (Test-CommandLineContainsValue $CommandLine $mainPy) -and
        $baseDirectoryMatches -and
        (Test-CommandLineArgumentValue $CommandLine '--port' ([string]$Config.Port))
    )
    if ($backendMatches) {
        return $true
    }

    $supervisorPath = Join-Path $PSScriptRoot 'backend_supervisor.ps1'
    return (
        (Test-CommandLineContainsValue $CommandLine $supervisorPath) -and
        (Test-CommandLineArgumentValue $CommandLine '-ProfileName' $Config.ProfileName) -and
        (Test-CommandLineArgumentValue $CommandLine '-ComfyUIRoot' $Config.ComfyUIRoot) -and
        (Test-CommandLineArgumentValue $CommandLine '-SharedBasePath' $Config.SharedBasePath) -and
        (Test-CommandLineArgumentValue $CommandLine '-Port' ([string]$Config.Port))
    )
}

function Test-ManagedComfyUIProcess {
    param(
        [hashtable]$Config,
        [int]$ProcessId
    )

    $processInfo = Get-ProcessInfo $ProcessId
    if (-not $processInfo) {
        return $false
    }

    $commandLine = [string]$processInfo.CommandLine
    return Test-ManagedComfyUICommandLine $Config $commandLine
}

function Stop-BackendOwnedComfyUIProcess {
    param(
        [hashtable]$Config,
        [int]$ProcessId,
        [ValidateSet('backend', 'launcher')]
        [string]$Role
    )

    if ($ProcessId -le 0) {
        return $false
    }
    # The other owned process in the same launch tree may already have stopped
    # this identity. Absence is a successful stop confirmation, not a failure.
    if (-not (Get-ProcessInfo $ProcessId)) {
        return $true
    }
    if (-not (Test-ManagedComfyUIProcess $Config $ProcessId) -or
        -not (Test-BackendProcessOwnership $Config $ProcessId $Role)) {
        return $false
    }

    $ownershipRecord = Read-BackendOwnershipRecord $Config
    $backendPid = if ($ownershipRecord) { [int]$ownershipRecord.backend_pid } else { 0 }
    $launcherPid = if ($ownershipRecord) { [int]$ownershipRecord.launcher_pid } else { 0 }
    if ($launcherPid -and $launcherPid -eq $ProcessId) {
        $processTreeIds = @($ProcessId)
        if ($backendPid) {
            $allProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
            $backendTreeIds = @(Get-ProcessTreeIds -RootProcessId $backendPid)
            $knownTreeIds = [System.Collections.Generic.HashSet[int]]::new()
            foreach ($knownProcessId in $backendTreeIds) {
                [void]$knownTreeIds.Add([int]$knownProcessId)
            }
            # Capture grandchildren recursively before stopping any process. A
            # process that exits during the walk can re-parent its children.
            $treeExpanded = $true
            while ($treeExpanded) {
                $treeExpanded = $false
                foreach ($candidate in $allProcesses) {
                    $candidateId = [int]$candidate.ProcessId
                    if (-not $knownTreeIds.Contains($candidateId) -and
                        $knownTreeIds.Contains([int]$candidate.ParentProcessId)) {
                        [void]$knownTreeIds.Add($candidateId)
                        $treeExpanded = $true
                    }
                }
            }
            $backendTreeIds = @($knownTreeIds)
            $processTreeIds += $backendTreeIds
            for ($index = $backendTreeIds.Count - 1; $index -ge 0; $index -= 1) {
                Stop-Process -Id $backendTreeIds[$index] -Force -ErrorAction SilentlyContinue
            }
        }
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
    else {
        # Do not recursively terminate from the listener identity: an externally
        # spawned child can be re-parented beneath it and is not covered by the
        # launch ownership record. The verified launcher path is the only safe
        # boundary for descendant termination.
        $processTreeIds = @($ProcessId)
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
    $deadline = (Get-Date).AddSeconds(5)
    do {
        $remainingProcessIds = @(
            $processTreeIds | Where-Object { Get-ProcessInfo $_ }
        )
        if ($remainingProcessIds.Count -eq 0) {
            return $true
        }
        Start-Sleep -Milliseconds 100
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Get-ProcessTreeIds {
    param([int]$RootProcessId)

    if ($RootProcessId -le 0) {
        return @()
    }

    $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $descendants = New-Object System.Collections.Generic.List[int]
    $frontier = New-Object System.Collections.Generic.Queue[int]
    $frontier.Enqueue($RootProcessId)
    while ($frontier.Count -gt 0) {
        $parentId = $frontier.Dequeue()
        foreach ($child in $processes | Where-Object { [int]$_.ParentProcessId -eq $parentId }) {
            $childId = [int]$child.ProcessId
            if (-not $descendants.Contains($childId)) {
                [void]$descendants.Add($childId)
                $frontier.Enqueue($childId)
            }
        }
    }

    return @($RootProcessId) + @($descendants)
}

function Stop-ProcessTreeOwnedByLaunch {
    param([int]$RootProcessId)

    $processTreeIds = @(Get-ProcessTreeIds -RootProcessId $RootProcessId)
    if ($processTreeIds.Count -eq 0) {
        return
    }

    $descendants = @($processTreeIds | Where-Object { $_ -ne $RootProcessId })
    for ($index = $descendants.Count - 1; $index -ge 0; $index -= 1) {
        Stop-Process -Id $descendants[$index] -Force -ErrorAction SilentlyContinue
    }
    # Stop children before their verified launch root. Killing the root first can
    # re-parent descendants and make a later process-tree walk unable to confirm
    # that the complete owned service exited.
    Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
}

function Get-ProcessCreationIdentity {
    param([int]$ProcessId)

    $processInfo = Get-ProcessInfo $ProcessId
    if (-not $processInfo -or -not $processInfo.CreationDate) {
        return $null
    }
    return ([DateTime]$processInfo.CreationDate).ToUniversalTime().ToString('o')
}

function Write-BackendOwnershipRecord {
    param(
        [hashtable]$Config,
        [int]$BackendPid,
        [int]$LauncherPid
    )

    $backendCreation = Get-ProcessCreationIdentity $BackendPid
    $launcherCreation = Get-ProcessCreationIdentity $LauncherPid
    if (-not $backendCreation -or -not $launcherCreation) {
        throw "Could not capture ComfyUI process creation identity for backend PID $BackendPid and launcher PID $LauncherPid."
    }

    $ownershipFile = Get-BackendOwnershipFile $Config
    $temporaryFile = "$ownershipFile.$PID.tmp"
    $record = [ordered]@{
        version = 1
        profile = $Config.ProfileName
        host = $Config.HostAddress
        port = $Config.Port
        backend_pid = $BackendPid
        backend_creation_time_utc = $backendCreation
        launcher_pid = $LauncherPid
        launcher_creation_time_utc = $launcherCreation
    }
    try {
        $record | ConvertTo-Json -Depth 4 -Compress | Set-Content -LiteralPath $temporaryFile -Encoding UTF8
        Move-Item -LiteralPath $temporaryFile -Destination $ownershipFile -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporaryFile -PathType Leaf) {
            Remove-Item -LiteralPath $temporaryFile -Force
        }
    }
}

function Read-BackendOwnershipRecord {
    param([hashtable]$Config)

    $ownershipFile = Get-BackendOwnershipFile $Config
    if (-not (Test-Path -LiteralPath $ownershipFile -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $ownershipFile -Raw | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Test-BackendProcessOwnership {
    param(
        [hashtable]$Config,
        [int]$ProcessId,
        [ValidateSet('backend', 'launcher')]
        [string]$Role
    )

    try {
        $record = Read-BackendOwnershipRecord $Config
        if (-not $record -or [int]$record.version -ne 1) {
            return $false
        }
        if ([string]$record.profile -cne [string]$Config.ProfileName -or
            [string]$record.host -cne [string]$Config.HostAddress -or
            [int]$record.port -ne [int]$Config.Port) {
            return $false
        }

        $recordedPid = if ($Role -eq 'backend') { [int]$record.backend_pid } else { [int]$record.launcher_pid }
        $recordedCreation = if ($Role -eq 'backend') { [string]$record.backend_creation_time_utc } else { [string]$record.launcher_creation_time_utc }
        if ($recordedPid -ne $ProcessId -or -not $recordedCreation) {
            return $false
        }

        $currentCreation = Get-ProcessCreationIdentity $ProcessId
        return [bool]($currentCreation -and $currentCreation -ceq $recordedCreation)
    }
    catch {
        return $false
    }
}

function Get-BackendOwnedProcessId {
    param(
        [hashtable]$Config,
        [ValidateSet('backend', 'launcher')]
        [string]$Role
    )

    try {
        $record = Read-BackendOwnershipRecord $Config
        if (-not $record) {
            return $null
        }
        $candidate = if ($Role -eq 'backend') { [int]$record.backend_pid } else { [int]$record.launcher_pid }
        if ($candidate -le 0 -or
            -not (Test-ManagedComfyUIProcess $Config $candidate) -or
            -not (Test-BackendProcessOwnership $Config $candidate $Role)) {
            return $null
        }
        return $candidate
    }
    catch {
        return $null
    }
}

function Remove-BackendPidFiles {
    param([hashtable]$Config)

    foreach ($path in @(
        (Get-BackendPidFile $Config),
        (Get-BackendLauncherPidFile $Config),
        (Get-BackendOwnershipFile $Config)
    )) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            Remove-Item -LiteralPath $path -Force
        }
    }
}

function Read-BackendPid {
    param([hashtable]$Config)

    $pidFile = Get-BackendPidFile $Config
    return Read-BackendPidFromFile $pidFile
}

function Read-BackendLauncherPid {
    param([hashtable]$Config)

    $pidFile = Get-BackendLauncherPidFile $Config
    return Read-BackendPidFromFile $pidFile
}

function Read-BackendPidFromFile {
    param([string]$PidFile)

    if (-not (Test-Path -LiteralPath $pidFile -PathType Leaf)) {
        return $null
    }

    $rawPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    if (-not $rawPid) {
        return $null
    }

    $parsedPid = 0
    if (-not [int]::TryParse($rawPid, [ref]$parsedPid)) {
        return $null
    }

    return $parsedPid
}

function Write-BackendJson {
    param([object]$Payload)
    $Payload | ConvertTo-Json -Depth 12 -Compress
}

function Write-BackendMessage {
    param(
        [switch]$Json,
        [object]$Payload,
        [string]$Message
    )

    if ($Json) {
        Write-BackendJson $Payload
    }
    else {
        Write-Output $Message
    }
}
