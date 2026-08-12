param(
    [Parameter(Mandatory = $true)]
    [string]$PythonExe,
    [Parameter(Mandatory = $true)]
    [string]$WorkingDirectory,
    [Parameter(Mandatory = $true)]
    [string]$StdoutLog,
    [Parameter(Mandatory = $true)]
    [string]$StderrLog,
    [Parameter(Mandatory = $true)]
    [string]$SupervisorStderrLog,
    [Parameter(Mandatory = $true)]
    [string]$ExitCodeFile,
    [Parameter(Mandatory = $true)]
    [string]$ArgumentsBase64,
    [string]$ProfileName = 'default',
    [string]$ComfyUIRoot = '',
    [string]$SharedBasePath = '',
    [int]$Port = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

trap {
    try {
        $diagnostic = ($_ | Out-String)
        [System.IO.File]::WriteAllText(
            $SupervisorStderrLog,
            $diagnostic,
            [System.Text.UTF8Encoding]::new($false)
        )
    }
    catch {
        # The parent still observes process exit and reports the intended log path.
    }
    exit 1
}

Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;

public static class PixelleStreamPump
{
    public static async Task CopyAndFlushAsync(Stream source, Stream destination)
    {
        var buffer = new byte[4096];
        while (true)
        {
            int read = await source.ReadAsync(buffer, 0, buffer.Length).ConfigureAwait(false);
            if (read == 0)
            {
                break;
            }
            await destination.WriteAsync(buffer, 0, read).ConfigureAwait(false);
            await destination.FlushAsync().ConfigureAwait(false);
        }
    }
}

public sealed class PixelleProcessJob : IDisposable
{
    private IntPtr handle;
    private const int JobObjectExtendedLimitInformation = 9;
    private const uint JobObjectLimitKillOnJobClose = 0x00002000;

    [StructLayout(LayoutKind.Sequential)]
    private struct BasicLimitInformation
    {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct IoCounters
    {
        public ulong ReadOperationCount;
        public ulong WriteOperationCount;
        public ulong OtherOperationCount;
        public ulong ReadTransferCount;
        public ulong WriteTransferCount;
        public ulong OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct ExtendedLimitInformation
    {
        public BasicLimitInformation BasicLimitInformation;
        public IoCounters IoInfo;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr CreateJobObject(IntPtr securityAttributes, string name);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetInformationJobObject(
        IntPtr job,
        int informationClass,
        IntPtr information,
        uint informationLength
    );

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool QueryInformationJobObject(
        IntPtr job,
        int informationClass,
        IntPtr information,
        uint informationLength,
        out uint returnLength
    );

    [DllImport("kernel32.dll")]
    private static extern bool CloseHandle(IntPtr handle);

    public PixelleProcessJob()
    {
        handle = CreateJobObject(IntPtr.Zero, null);
        if (handle == IntPtr.Zero)
        {
            throw new Win32Exception(Marshal.GetLastWin32Error());
        }

        var limits = new ExtendedLimitInformation();
        limits.BasicLimitInformation.LimitFlags = JobObjectLimitKillOnJobClose;
        int length = Marshal.SizeOf(typeof(ExtendedLimitInformation));
        IntPtr pointer = Marshal.AllocHGlobal(length);
        try
        {
            Marshal.StructureToPtr(limits, pointer, false);
            if (!SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                pointer,
                (uint)length
            ))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error());
            }
        }
        finally
        {
            Marshal.FreeHGlobal(pointer);
        }
    }

    public void Assign(Process process)
    {
        if (!AssignProcessToJobObject(handle, process.Handle))
        {
            throw new Win32Exception(Marshal.GetLastWin32Error());
        }
    }

    public uint ActiveProcessCount
    {
        get
        {
            int length = Marshal.SizeOf(typeof(BasicAccountingInformation));
            IntPtr pointer = Marshal.AllocHGlobal(length);
            try
            {
                uint returnLength;
                if (!QueryInformationJobObject(
                    handle,
                    1,
                    pointer,
                    (uint)length,
                    out returnLength
                ))
                {
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                }
                var accounting = (BasicAccountingInformation)Marshal.PtrToStructure(
                    pointer,
                    typeof(BasicAccountingInformation)
                );
                return accounting.ActiveProcesses;
            }
            finally
            {
                Marshal.FreeHGlobal(pointer);
            }
        }
    }

    public void Dispose()
    {
        if (handle != IntPtr.Zero)
        {
            CloseHandle(handle);
            handle = IntPtr.Zero;
        }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct BasicAccountingInformation
    {
        public long TotalUserTime;
        public long TotalKernelTime;
        public long ThisPeriodTotalUserTime;
        public long ThisPeriodTotalKernelTime;
        public uint TotalPageFaultCount;
        public uint TotalProcesses;
        public uint ActiveProcesses;
        public uint TotalTerminatedProcesses;
    }
}
'@

$argumentsJson = [System.Text.Encoding]::UTF8.GetString(
    [System.Convert]::FromBase64String($ArgumentsBase64)
)
$decodedArguments = $argumentsJson | ConvertFrom-Json
$backendArguments = if ($decodedArguments -is [System.Array]) {
    [string[]]$decodedArguments
}
else {
    [string[]]@($decodedArguments)
}

function ConvertTo-WindowsCommandLineArgument {
    param([string]$Value)

    if ($Value -notmatch '[\s"]') {
        return $Value
    }
    $builder = [System.Text.StringBuilder]::new()
    [void]$builder.Append('"')
    $backslashCount = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq '\') {
            $backslashCount += 1
            continue
        }
        if ($character -eq '"') {
            [void]$builder.Append(('\' * ($backslashCount * 2 + 1)))
            [void]$builder.Append('"')
            $backslashCount = 0
            continue
        }
        if ($backslashCount -gt 0) {
            [void]$builder.Append(('\' * $backslashCount))
            $backslashCount = 0
        }
        [void]$builder.Append($character)
    }
    if ($backslashCount -gt 0) {
        [void]$builder.Append(('\' * ($backslashCount * 2)))
    }
    [void]$builder.Append('"')
    return $builder.ToString()
}

$job = [PixelleProcessJob]::new()
$backendProcess = $null
$backendStarted = $false
$stdoutStream = $null
$stderrStream = $null
try {
    $stdoutStream = [System.IO.FileStream]::new(
        $StdoutLog,
        [System.IO.FileMode]::Create,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::ReadWrite
    )
    $stderrStream = [System.IO.FileStream]::new(
        $StderrLog,
        [System.IO.FileMode]::Create,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::ReadWrite
    )
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $PythonExe
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.Arguments = ($backendArguments | ForEach-Object {
        ConvertTo-WindowsCommandLineArgument $_
    }) -join ' '
    $backendProcess = [System.Diagnostics.Process]::new()
    $backendProcess.StartInfo = $startInfo
    if (-not $backendProcess.Start()) {
        throw "Failed to start the configured ComfyUI process."
    }
    $backendStarted = $true
    $job.Assign($backendProcess)
    # Stream both pipes directly to disk. Reading the whole process output into
    # memory delays diagnostics and can itself exhaust memory on long generations.
    $stdoutTask = [PixelleStreamPump]::CopyAndFlushAsync(
        $backendProcess.StandardOutput.BaseStream,
        $stdoutStream
    )
    $stderrTask = [PixelleStreamPump]::CopyAndFlushAsync(
        $backendProcess.StandardError.BaseStream,
        $stderrStream
    )
    $backendProcess.WaitForExit()
    # A launcher may hand the listener to a child and exit. Keep the job handle
    # alive until every process from this launch has exited, so that stopping the
    # supervisor still terminates the complete service tree.
    while ($job.ActiveProcessCount -gt 0) {
        Start-Sleep -Milliseconds 100
    }
    [void]$stdoutTask.GetAwaiter().GetResult()
    [void]$stderrTask.GetAwaiter().GetResult()
    $backendExitCode = $backendProcess.ExitCode
    Set-Content -LiteralPath $ExitCodeFile -Value ([string]$backendExitCode) -Encoding ASCII
    exit $backendExitCode
}
finally {
    $job.Dispose()
    if ($stdoutStream) {
        $stdoutStream.Dispose()
    }
    if ($stderrStream) {
        $stderrStream.Dispose()
    }
    if ($backendStarted -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
