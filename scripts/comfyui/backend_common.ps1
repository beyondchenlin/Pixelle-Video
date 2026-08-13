Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
. (Join-Path $PSScriptRoot 'backend_command_line.ps1')

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

function Resolve-AllowedCustomNodeFolders {
    param(
        [string]$LoadingMode,
        [string]$FoldersBase64
    )

    $normalizedMode = ([string]$LoadingMode).Trim().ToLowerInvariant()
    if ($normalizedMode -notin @('all', 'allowlist', 'none')) {
        throw "Unsupported ComfyUI custom-node loading policy: $LoadingMode"
    }

    $folders = @()
    if ($FoldersBase64 -and $FoldersBase64.Trim()) {
        try {
            $jsonBytes = [Convert]::FromBase64String($FoldersBase64.Trim())
            $json = [Text.Encoding]::UTF8.GetString($jsonBytes)
            $trimmedJson = $json.Trim()
            if (-not $trimmedJson.StartsWith('[') -or
                -not $trimmedJson.EndsWith(']')) {
                throw "Custom-node folder JSON must be an array."
            }
            $folders = ConvertFrom-Json -InputObject $json
        }
        catch {
            throw "ComfyUI custom-node folder payload is not valid base64 JSON."
        }
    }

    $normalizedFolders = New-Object System.Collections.Generic.List[string]
    $seen = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase
    )
    foreach ($rawFolder in $folders) {
        $folder = ([string]$rawFolder).Trim()
        if (-not $folder -or
            $folder -in @('.', '..') -or
            $folder -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') {
            throw "Invalid ComfyUI custom-node folder name: $rawFolder"
        }
        if (-not $seen.Add($folder)) {
            throw "Duplicate ComfyUI custom-node folder name: $folder"
        }
        [void]$normalizedFolders.Add($folder)
    }

    if ($normalizedMode -eq 'allowlist' -and $normalizedFolders.Count -eq 0) {
        throw "ComfyUI custom-node allowlist mode requires at least one folder."
    }
    if ($normalizedMode -ne 'allowlist' -and $normalizedFolders.Count -gt 0) {
        throw "ComfyUI custom-node folders are only valid in allowlist mode."
    }
    return [string[]]$normalizedFolders.ToArray()
}

function Resolve-BackendFilesystemPath {
    param(
        [string]$Path,
        [string]$BasePath
    )

    if (-not $Path -or -not $Path.Trim()) {
        return ''
    }
    $candidate = [Environment]::ExpandEnvironmentVariables($Path.Trim())
    if (-not [System.IO.Path]::IsPathRooted($candidate)) {
        $candidate = Join-Path $BasePath $candidate
    }
    return [System.IO.Path]::GetFullPath($candidate)
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

    # The managed process shares host memory with the web process, renderers, and
    # later pipeline stages. Keep page-locked host buffers disabled by default,
    # while preserving ComfyUI's model offload and execution cache: both are
    # essential for bounded memory and reuse inside a multi-item workflow batch.
    return 'memory_safe'
}

function Set-BackendEffectiveMinimumFreeCommit {
    param([System.Collections.IDictionary]$Config)

    $requested = [double]$Config.RequestedMinimumFreeCommitGB
    if ($requested -ge 0) {
        $Config.MinimumFreeCommitGB = $requested
        $Config.MinimumFreeCommitMode = 'configured'
        return
    }

    $snapshot = $Config.MemorySnapshot
    if (-not $snapshot) {
        $snapshot = Get-SystemMemorySnapshot
        $Config.MemorySnapshot = $snapshot
    }
    if (-not $snapshot) {
        return
    }

    # This is an operating-system safety reserve, not an estimate of an unknown
    # workflow's model footprint. Scale with the commit limit but keep the guard
    # bounded so capable machines are not rejected by an arbitrary fixed value.
    $adaptiveMinimum = [math]::Max(
        [double]2,
        [math]::Min([double]6, [double]$snapshot.total_commit_gb * 0.10)
    )
    $Config.MinimumFreeCommitGB = [math]::Round($adaptiveMinimum, 2)
    $Config.MinimumFreeCommitMode = 'automatic'
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
        [double]$MinimumFreeCommitGB = -1,
        [string]$CustomNodeLoading = 'all',
        [string]$AllowedCustomNodeFoldersBase64 = '',
        [string]$AcceleratorMutexName = ''
    )

    $repoRoot = Get-PixelleRepoRoot
    $resolvedDataRoot = Resolve-BackendFilesystemPath `
        (Resolve-BackendValue $DataRoot 'PIXELLE_COMFYUI_DATA_ROOT' 'E:\ComfyUIData\pixelle') `
        $repoRoot
    $defaultSharedBasePath = Split-Path -Parent $resolvedDataRoot
    if (-not $defaultSharedBasePath) {
        $defaultSharedBasePath = $resolvedDataRoot
    }
    $resolvedSharedBasePath = Resolve-BackendFilesystemPath `
        (Resolve-BackendValue $SharedBasePath 'PIXELLE_COMFYUI_SHARED_BASE_PATH' $defaultSharedBasePath) `
        $repoRoot
    $resolvedComfyUIRoot = Resolve-BackendFilesystemPath `
        (Resolve-BackendValue $ComfyUIRoot 'PIXELLE_COMFYUI_ROOT' 'E:\comfyui\resources\ComfyUI') `
        $repoRoot
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
    $resolvedCustomNodeLoading = Resolve-BackendValue `
        $CustomNodeLoading `
        'PIXELLE_COMFYUI_CUSTOM_NODE_LOADING' `
        'all'
    $resolvedCustomNodeLoading = $resolvedCustomNodeLoading.Trim().ToLowerInvariant()
    $resolvedAllowedCustomNodeFolders = Resolve-AllowedCustomNodeFolders `
        -LoadingMode $resolvedCustomNodeLoading `
        -FoldersBase64 $AllowedCustomNodeFoldersBase64
    $allowedFoldersJson = ConvertTo-Json `
        -InputObject ([object[]]@($resolvedAllowedCustomNodeFolders)) `
        -Compress
    $resolvedAllowedCustomNodeFoldersBase64 = [Convert]::ToBase64String(
        [Text.Encoding]::UTF8.GetBytes($allowedFoldersJson)
    )
    $resolvedAcceleratorMutexName = if ([string]::IsNullOrWhiteSpace($AcceleratorMutexName)) {
        'Global\Pixelle-ComfyUI-Accelerator-v1'
    }
    else {
        $AcceleratorMutexName.Trim()
    }
    if ($resolvedAcceleratorMutexName -notmatch '^(Global|Local)\\[A-Za-z0-9._-]{1,180}$') {
        throw "Invalid ComfyUI accelerator mutex name: $resolvedAcceleratorMutexName"
    }
    $resolvedMinimumFreeCommitGB = Resolve-BackendDouble `
        $MinimumFreeCommitGB `
        'PIXELLE_COMFYUI_MINIMUM_FREE_COMMIT_GB' `
        -1
    if ($resolvedMinimumFreeCommitGB -lt -1 -or $resolvedMinimumFreeCommitGB -gt 256) {
        throw "ComfyUI minimum free commit must be automatic or between 0 and 256 GiB: $resolvedMinimumFreeCommitGB"
    }

    $resolvedPythonExe = Resolve-BackendFilesystemPath `
        (Resolve-BackendValue $PythonExe 'PIXELLE_COMFYUI_PYTHON' (Join-Path $resolvedSharedBasePath '.venv\Scripts\python.exe')) `
        $repoRoot
    $resolvedExtraModelsConfig = Resolve-BackendFilesystemPath `
        (Resolve-BackendValue $ExtraModelsConfig 'PIXELLE_COMFYUI_EXTRA_MODELS_CONFIG' '') `
        $repoRoot
    $resolvedFrontEndRoot = Resolve-BackendFilesystemPath `
        (Resolve-BackendValue $FrontEndRoot 'PIXELLE_COMFYUI_FRONTEND_ROOT' '') `
        $repoRoot
    $resolvedRuntimeDir = Resolve-BackendFilesystemPath `
        (Resolve-BackendValue $RuntimeDir 'PIXELLE_COMFYUI_RUNTIME_DIR' (Join-Path $repoRoot '_runtime\comfyui')) `
        $repoRoot
    $resolvedLogsDir = Resolve-BackendFilesystemPath `
        (Resolve-BackendValue $LogsDir 'PIXELLE_COMFYUI_LOGS_DIR' (Join-Path $repoRoot 'logs\comfyui')) `
        $repoRoot

    return [ordered]@{
        ProfileName = $resolvedProfileName
        RepoRoot = $repoRoot
        PythonExe = $resolvedPythonExe
        ComfyUIRoot = $resolvedComfyUIRoot
        DataRoot = $resolvedDataRoot
        SharedBasePath = $resolvedSharedBasePath
        ExtraModelsConfig = $resolvedExtraModelsConfig
        FrontEndRoot = $resolvedFrontEndRoot
        DatabaseUrl = Resolve-BackendValue $DatabaseUrl 'PIXELLE_COMFYUI_DATABASE_URL' $defaultDatabaseUrl
        RuntimeDir = $resolvedRuntimeDir
        LogsDir = $resolvedLogsDir
        HostAddress = $resolvedHostAddress
        Port = $resolvedPort
        RequestedResourcePolicy = $requestedResourcePolicy
        ResourcePolicy = $resolvedResourcePolicy
        CustomNodeLoading = $resolvedCustomNodeLoading
        AllowedCustomNodeFolders = $resolvedAllowedCustomNodeFolders
        AllowedCustomNodeFoldersBase64 = $resolvedAllowedCustomNodeFoldersBase64
        AcceleratorMutexName = $resolvedAcceleratorMutexName
        RequestedMinimumFreeCommitGB = $resolvedMinimumFreeCommitGB
        MinimumFreeCommitGB = $resolvedMinimumFreeCommitGB
        MinimumFreeCommitMode = if ($resolvedMinimumFreeCommitGB -ge 0) { 'configured' } else { 'automatic' }
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

function Get-BackendSupervisorStderrLog {
    param([hashtable]$Config)
    return (Join-Path $Config.LogsDir 'comfyui-supervisor.stderr.log')
}

function Get-BackendExitCodeFile {
    param([hashtable]$Config)
    return (Join-Path $Config.RuntimeDir 'comfyui-backend.exit-code')
}

function Get-BackendDiagnosticTail {
    param(
        [string[]]$Paths,
        [int]$TailLines = 40,
        [int]$MaximumCharacters = 12000
    )

    $sections = New-Object System.Collections.Generic.List[string]
    foreach ($path in $Paths) {
        if (-not $path -or -not (Test-Path -LiteralPath $path -PathType Leaf)) {
            continue
        }
        try {
            $lines = @(
                Get-Content `
                    -LiteralPath $path `
                    -Encoding UTF8 `
                    -Tail $TailLines `
                    -ErrorAction Stop
            )
        }
        catch {
            continue
        }
        if ($lines.Count -eq 0) {
            continue
        }
        [void]$sections.Add("[$path]`n$($lines -join "`n")")
    }

    $tail = $sections -join "`n"
    $tail = [regex]::Replace(
        $tail,
        '(?im)(?<prefix>"?authorization"?\s*:\s*)(?:"[^"\r\n]*"|''[^''\r\n]*''|[^\r\n,;}]+)',
        '${prefix}[REDACTED]'
    )
    $tail = [regex]::Replace(
        $tail,
        '(?im)(?<prefix>"?(?:api[_-]?key|access[_-]?token|password|secret)"?\s*[:=]\s*)(?:"[^"\r\n]*"|''[^''\r\n]*''|[^\s,;}\r\n]+)',
        '${prefix}[REDACTED]'
    )
    if ($tail.Length -gt $MaximumCharacters) {
        return $tail.Substring($tail.Length - $MaximumCharacters)
    }
    return $tail
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

    # Keep enough launch history for post-mortem analysis without allowing a
    # repeatedly restarting backend to grow the log directory forever.
    $archivePattern = "$baseName.*$extension"
    @(Get-ChildItem -LiteralPath $directory -File -Filter $archivePattern |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -Skip 20) |
        Remove-Item -Force -ErrorAction SilentlyContinue
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
    $Payload['supervisor_stderr_log'] = Get-BackendSupervisorStderrLog $Config
    $Payload['exit_code_file'] = Get-BackendExitCodeFile $Config
    $Payload['requested_resource_policy'] = $Config.RequestedResourcePolicy
    $Payload['resource_policy'] = $Config.ResourcePolicy
    $Payload['custom_node_loading'] = $Config.CustomNodeLoading
    $Payload['allowed_custom_node_folders'] = @($Config.AllowedCustomNodeFolders)
    $Payload['accelerator_mutex_name'] = $Config.AcceleratorMutexName
    $Payload['minimum_free_commit_gb'] = if ([double]$Config.MinimumFreeCommitGB -ge 0) {
        $Config.MinimumFreeCommitGB
    }
    else {
        $null
    }
    $Payload['minimum_free_commit_mode'] = $Config.MinimumFreeCommitMode
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
    if ($Config.CustomNodeLoading -eq 'allowlist') {
        $candidateCustomNodeRoots = @(
            (Join-Path $Config.SharedBasePath 'custom_nodes'),
            (Join-Path $Config.ComfyUIRoot 'custom_nodes')
        )
        $customNodeRoots = New-Object System.Collections.Generic.List[string]
        $seenCustomNodeRoots = [System.Collections.Generic.HashSet[string]]::new(
            [System.StringComparer]::OrdinalIgnoreCase
        )
        foreach ($candidateRoot in $candidateCustomNodeRoots) {
            $normalizedRoot = [System.IO.Path]::GetFullPath($candidateRoot)
            if ($seenCustomNodeRoots.Add($normalizedRoot)) {
                [void]$customNodeRoots.Add($normalizedRoot)
            }
        }
        foreach ($folder in @($Config.AllowedCustomNodeFolders)) {
            $matchingRoots = @($customNodeRoots | Where-Object {
                Test-Path -LiteralPath (Join-Path $_ $folder) -PathType Container
            })
            if ($matchingRoots.Count -eq 0) {
                throw (
                    "Allowed ComfyUI custom-node folder does not exist below any " +
                    "configured custom_nodes root: $folder"
                )
            }
            if ($matchingRoots.Count -gt 1) {
                throw (
                    "Allowed ComfyUI custom-node folder is ambiguous because the " +
                    "same name exists below multiple configured custom_nodes roots: " +
                    "$folder"
                )
            }
        }
    }
}

function Assert-BackendSystemMemoryAdmission {
    param([hashtable]$Config)

    Set-BackendEffectiveMinimumFreeCommit $Config
    $minimum = [double]$Config.MinimumFreeCommitGB
    if ($minimum -lt 0) {
        throw "Could not inspect Windows system memory before starting ComfyUI."
    }
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
        @('--disable-pinned-memory') | Where-Object {
            $cliSource.IndexOf($_, [System.StringComparison]::Ordinal) -lt 0
        }
    )
    if ($missingArguments.Count -gt 0) {
        throw (
            "Configured ComfyUI does not support the memory-safe launch contract. " +
            "Missing argument(s): $($missingArguments -join ', '). Update ComfyUI or " +
            "explicitly select resource_policy=performance after accepting pinned-host-memory use."
        )
    }
}

function Assert-BackendCustomNodePolicySupport {
    param([hashtable]$Config)

    if ($Config.CustomNodeLoading -eq 'all') {
        return
    }
    $cliArgumentsPath = Join-Path $Config.ComfyUIRoot 'comfy\cli_args.py'
    if (-not (Test-Path -LiteralPath $cliArgumentsPath -PathType Leaf)) {
        throw (
            "Configured ComfyUI cannot prove support for custom-node isolation " +
            "because comfy/cli_args.py is missing: $cliArgumentsPath"
        )
    }
    $cliSource = Get-Content -LiteralPath $cliArgumentsPath -Raw
    $requiredArguments = @('--disable-all-custom-nodes')
    if ($Config.CustomNodeLoading -eq 'allowlist') {
        $requiredArguments += '--whitelist-custom-nodes'
    }
    $missingArguments = @($requiredArguments | Where-Object {
        $cliSource.IndexOf($_, [System.StringComparison]::Ordinal) -lt 0
    })
    if ($missingArguments.Count -gt 0) {
        throw (
            "Configured ComfyUI does not support the requested custom-node " +
            "isolation policy. Missing argument(s): $($missingArguments -join ', ')"
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
    }
    if ($Config.CustomNodeLoading -in @('allowlist', 'none')) {
        [void]$arguments.Add('--disable-all-custom-nodes')
    }
    if ($Config.CustomNodeLoading -eq 'allowlist') {
        [void]$arguments.Add('--whitelist-custom-nodes')
        foreach ($folder in @($Config.AllowedCustomNodeFolders)) {
            [void]$arguments.Add([string]$folder)
        }
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

function Test-CommandLineContainsToken {
    param(
        [string]$CommandLine,
        [string]$Token
    )

    if (-not $CommandLine -or -not $Token) {
        return $false
    }
    $escapedToken = [regex]::Escape($Token)
    $pattern = '(^|\s)(?:"' + $escapedToken + '"|' + $escapedToken + ')(?=\s|$)'
    return [regex]::IsMatch(
        $CommandLine,
        $pattern,
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
}

function Get-CommandLineOptionValues {
    param(
        [string]$CommandLine,
        [string]$Option
    )

    if (-not $CommandLine -or -not $Option) {
        return
    }
    $escapedOption = [regex]::Escape($Option)
    $optionPattern = '(?:^|\s)(?:"' + $escapedOption + '"|' + $escapedOption + ')(?=\s|$)'
    $optionMatches = [regex]::Matches(
        $CommandLine,
        $optionPattern,
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    if ($optionMatches.Count -ne 1) {
        return
    }

    $remaining = $CommandLine.Substring(
        $optionMatches[0].Index + $optionMatches[0].Length
    )
    $values = New-Object System.Collections.Generic.List[string]
    while ($remaining) {
        $tokenMatch = [regex]::Match(
            $remaining,
            '^\s+(?:"(?<quoted>[^"]*)"|(?<bare>\S+))'
        )
        if (-not $tokenMatch.Success) {
            break
        }
        $token = if ($tokenMatch.Groups['quoted'].Success) {
            $tokenMatch.Groups['quoted'].Value
        }
        else {
            $tokenMatch.Groups['bare'].Value
        }
        if ($token.StartsWith('-')) {
            break
        }
        [void]$values.Add($token)
        $remaining = $remaining.Substring($tokenMatch.Length)
    }
    return [string[]]$values.ToArray()
}

function Test-BackendCustomNodePolicyCommandLine {
    param(
        [hashtable]$Config,
        [string]$CommandLine
    )

    $disableAll = Test-CommandLineContainsToken `
        $CommandLine `
        '--disable-all-custom-nodes'
    $hasAllowlist = Test-CommandLineContainsToken `
        $CommandLine `
        '--whitelist-custom-nodes'
    if ($Config.CustomNodeLoading -eq 'all') {
        return [bool](-not $disableAll -and -not $hasAllowlist)
    }
    if ($Config.CustomNodeLoading -eq 'none') {
        return [bool]($disableAll -and -not $hasAllowlist)
    }
    if (-not $disableAll -or -not $hasAllowlist) {
        return $false
    }
    $actualFolders = @(
        Get-CommandLineOptionValues $CommandLine '--whitelist-custom-nodes'
    )
    $expectedFolders = @($Config.AllowedCustomNodeFolders)
    if ($actualFolders.Count -ne $expectedFolders.Count) {
        return $false
    }
    for ($index = 0; $index -lt $expectedFolders.Count; $index += 1) {
        if (-not [string]::Equals(
            [string]$actualFolders[$index],
            [string]$expectedFolders[$index],
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            return $false
        }
    }
    return $true
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
        (Test-CommandLineArgumentValue $CommandLine '--port' ([string]$Config.Port)) -and
        (Test-BackendCustomNodePolicyCommandLine $Config $CommandLine)
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
        (Test-CommandLineArgumentValue $CommandLine '-CustomNodeLoading' $Config.CustomNodeLoading) -and
        (Test-CommandLineArgumentValue $CommandLine '-AllowedCustomNodeFoldersBase64' $Config.AllowedCustomNodeFoldersBase64) -and
        (Test-CommandLineArgumentValue $CommandLine '-AcceleratorMutexName' $Config.AcceleratorMutexName) -and
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
        return $true
    }

    $descendants = @($processTreeIds | Where-Object { $_ -ne $RootProcessId })
    for ($index = $descendants.Count - 1; $index -ge 0; $index -= 1) {
        Stop-Process -Id $descendants[$index] -Force -ErrorAction SilentlyContinue
    }
    # Stop children before their verified launch root. Killing the root first can
    # re-parent descendants and make a later process-tree walk unable to confirm
    # that the complete owned service exited.
    Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue

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
