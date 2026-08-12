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
        [int]$Port
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
    return (
        (Test-CommandLineContainsValue $CommandLine $mainPy) -and
        $baseDirectoryMatches -and
        (Test-CommandLineArgumentValue $CommandLine '--port' ([string]$Config.Port))
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
    if (-not (Test-ManagedComfyUIProcess $Config $ProcessId) -or
        -not (Test-BackendProcessOwnership $Config $ProcessId $Role)) {
        return $false
    }

    $processTreeIds = @(Get-ProcessTreeIds -RootProcessId $ProcessId)
    Stop-ProcessTreeOwnedByLaunch $ProcessId
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

    Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
    $descendants = @($processTreeIds | Where-Object { $_ -ne $RootProcessId })
    for ($index = $descendants.Count - 1; $index -ge 0; $index -= 1) {
        Stop-Process -Id $descendants[$index] -Force -ErrorAction SilentlyContinue
    }
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
