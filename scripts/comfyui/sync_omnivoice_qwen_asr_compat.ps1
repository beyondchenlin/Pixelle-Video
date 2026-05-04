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
    [string]$QwenAsrRepo = 'https://github.com/One-sixth/Qwen3-ASR.git',
    [string]$QwenAsrCommit = '94155b4f1b3c76c7f6a492f0378c1c31c93ab93d',
    [switch]$SkipPipCheck
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'backend_common.ps1')

function Invoke-ComfyUIPip {
    param(
        [string]$Python,
        [string[]]$Arguments
    )

    Write-Host "python -m pip $($Arguments -join ' ')"
    & $Python -m pip @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "pip failed with exit code $LASTEXITCODE"
    }
}

function Invoke-ComfyUIPythonSnippet {
    param(
        [string]$Python,
        [string]$Code
    )

    $Code | & $Python -
    if ($LASTEXITCODE -ne 0) {
        throw "python verification failed with exit code $LASTEXITCODE"
    }
}

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

$python = $config.PythonExe
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "ComfyUI Python executable does not exist: $python"
}

$packageSpec = "qwen-asr @ git+$QwenAsrRepo@$QwenAsrCommit"

Write-Host "Using ComfyUI Python: $python"
Write-Host "Pinning Transformers stack for OmniVoice and Qwen3-ASR compatibility."
Invoke-ComfyUIPip -Python $python -Arguments @(
    'install',
    '--upgrade-strategy',
    'only-if-needed',
    'transformers==5.6.2',
    'accelerate==1.13.0',
    'huggingface-hub==1.12.0'
)

Write-Host "Installing Qwen-ASR runtime dependencies without changing the ComfyUI PyTorch stack."
Invoke-ComfyUIPip -Python $python -Arguments @(
    'install',
    '--upgrade-strategy',
    'only-if-needed',
    'modelscope',
    'soundfile',
    'librosa',
    'qwen-omni-utils',
    'nagisa>=0.2.12',
    'soynlp>=0.0.493',
    'sox',
    'gradio',
    'flask',
    'pytz'
)

Write-Host "Installing fixed qwen-asr source: $packageSpec"
Invoke-ComfyUIPip -Python $python -Arguments @(
    'install',
    '--force-reinstall',
    '--no-deps',
    $packageSpec
)

$verifyCode = @'
import accelerate
import huggingface_hub
import qwen_asr
import transformers
from qwen_asr import Qwen3ASRModel
from qwen_asr.core.transformers_backend.configuration_qwen3_asr import Qwen3ASRConfig

expected_versions = {
    "transformers": (transformers.__version__, "5.6.2"),
    "accelerate": (accelerate.__version__, "1.13.0"),
    "huggingface_hub": (huggingface_hub.__version__, "1.12.0"),
}
cfg = Qwen3ASRConfig()
text_config = cfg.get_text_config()
source_path = (qwen_asr.__file__ or "").replace("\\", "/")

if not hasattr(cfg, "thinker_config"):
    raise RuntimeError("Qwen3ASRConfig.thinker_config is missing")
if "_tmp/" in source_path:
    raise RuntimeError(f"qwen_asr is still loaded from a temporary editable source: {source_path}")
for package_name, (actual_version, expected_version) in expected_versions.items():
    if actual_version != expected_version:
        raise RuntimeError(f"{package_name} version mismatch: expected {expected_version}, got {actual_version}")

print("QWEN_ASR_COMPAT_OK")
print("qwen_asr", source_path)
print("Qwen3ASRModel", Qwen3ASRModel.__name__)
print("text_config", type(text_config).__name__)
print("transformers", transformers.__version__)
print("accelerate", accelerate.__version__)
print("huggingface_hub", huggingface_hub.__version__)
'@

Invoke-ComfyUIPythonSnippet -Python $python -Code $verifyCode

if (-not $SkipPipCheck) {
    Write-Host "Running pip check."
    Invoke-ComfyUIPip -Python $python -Arguments @('check')
}
