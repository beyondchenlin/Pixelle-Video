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
        [string]$ExtraModelsConfig,
        [string]$FrontEndRoot,
        [string]$DatabaseUrl,
        [string]$RuntimeDir,
        [string]$LogsDir,
        [string]$HostAddress,
        [int]$Port
    )

    $repoRoot = Get-PixelleRepoRoot
    $resolvedDataRoot = Resolve-BackendValue $DataRoot 'PIXELLE_COMFYUI_DATA_ROOT' 'E:\ComfyUIData'
    $sharedBasePath = $resolvedDataRoot
    $resolvedComfyUIRoot = Resolve-BackendValue $ComfyUIRoot 'PIXELLE_COMFYUI_ROOT' 'E:\comfyui\resources\ComfyUI'
    $defaultFrontEndRoot = Join-Path $resolvedComfyUIRoot 'web_custom_versions\desktop_app'
    $defaultDatabaseUrl = ConvertTo-SqliteUrl (Join-Path $resolvedDataRoot 'user\comfyui.db')
    $resolvedProfileName = Resolve-BackendValue $ProfileName 'PIXELLE_COMFYUI_PROFILE' 'default'

    return [ordered]@{
        ProfileName = $resolvedProfileName
        RepoRoot = $repoRoot
        PythonExe = Resolve-BackendValue $PythonExe 'PIXELLE_COMFYUI_PYTHON' (Join-Path $resolvedDataRoot '.venv\Scripts\python.exe')
        ComfyUIRoot = $resolvedComfyUIRoot
        DataRoot = $resolvedDataRoot
        SharedBasePath = $sharedBasePath
        ExtraModelsConfig = Resolve-BackendValue $ExtraModelsConfig 'PIXELLE_COMFYUI_EXTRA_MODELS_CONFIG' (Join-Path $env:APPDATA 'ComfyUI\extra_models_config.yaml')
        FrontEndRoot = Resolve-BackendValue $FrontEndRoot 'PIXELLE_COMFYUI_FRONTEND_ROOT' $defaultFrontEndRoot
        DatabaseUrl = Resolve-BackendValue $DatabaseUrl 'PIXELLE_COMFYUI_DATABASE_URL' $defaultDatabaseUrl
        RuntimeDir = Resolve-BackendValue $RuntimeDir 'PIXELLE_COMFYUI_RUNTIME_DIR' (Join-Path $repoRoot '_runtime\comfyui')
        LogsDir = Resolve-BackendValue $LogsDir 'PIXELLE_COMFYUI_LOGS_DIR' (Join-Path $repoRoot 'logs\comfyui')
        HostAddress = Resolve-BackendValue $HostAddress 'PIXELLE_COMFYUI_HOST' '127.0.0.1'
        Port = Resolve-BackendInt $Port 'PIXELLE_COMFYUI_PORT' 8000
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

function Get-BackendStdoutLog {
    param([hashtable]$Config)
    return (Join-Path $Config.LogsDir 'comfyui-backend.stdout.log')
}

function Get-BackendStderrLog {
    param([hashtable]$Config)
    return (Join-Path $Config.LogsDir 'comfyui-backend.stderr.log')
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
    $Payload['runtime_dir'] = $Config.RuntimeDir
    $Payload['logs_dir'] = $Config.LogsDir
    $Payload['database_url'] = $Config.DatabaseUrl
    $Payload['pid_file'] = Get-BackendPidFile $Config
    $Payload['launcher_pid_file'] = Get-BackendLauncherPidFile $Config
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
    [void]$arguments.Add('--enable-cors-header')
    [void]$arguments.Add('*')
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
    foreach ($candidate in @($Value, ($Value -replace '\\', '/'))) {
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
    return (
        (Test-CommandLineContainsValue $CommandLine $mainPy) -and
        (Test-CommandLineArgumentValue $CommandLine '--base-directory' $Config.SharedBasePath) -and
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

function Stop-ManagedComfyUIProcess {
    param(
        [hashtable]$Config,
        [int]$ProcessId
    )

    if ($ProcessId -le 0) {
        return $false
    }
    if (-not (Test-ManagedComfyUIProcess $Config $ProcessId)) {
        return $false
    }

    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    return $true
}

function Stop-ManagedComfyUIProcessesForConfig {
    param([hashtable]$Config)

    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            Test-ManagedComfyUICommandLine $Config ([string]$_.CommandLine)
        } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

function Remove-BackendPidFiles {
    param([hashtable]$Config)

    foreach ($path in @((Get-BackendPidFile $Config), (Get-BackendLauncherPidFile $Config))) {
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
