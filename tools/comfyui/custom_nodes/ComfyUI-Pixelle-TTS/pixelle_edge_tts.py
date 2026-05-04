import asyncio
import concurrent.futures
import os
import random
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import edge_tts
from aiohttp import ClientConnectorError, ClientResponseError, WSServerHandshakeError
from edge_tts.exceptions import NoAudioReceived

VOICE_ID_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z0-9]+)+Neural$")
DEFAULT_SAMPLE_RATE = 24000
DEFAULT_RETRY_COUNT = 2
DEFAULT_RETRY_BASE_DELAY = 1.0
MAX_RETRY_DELAY = 5.0
RETRYABLE_EDGE_TTS_ERRORS = (
    NoAudioReceived,
    WSServerHandshakeError,
    ClientResponseError,
    ClientConnectorError,
    ConnectionResetError,
    asyncio.TimeoutError,
)


def _runtime_temp_dir() -> str | None:
    runtime_root = os.environ.get("PIXELLE_VIDEO_RUNTIME_ROOT")
    if not runtime_root:
        return None
    temp_dir = Path(runtime_root) / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return str(temp_dir)


def speed_multiplier_to_rate(speed: float) -> str:
    speed_percent = int(round((float(speed) - 1.0) * 100))
    return "+0%" if speed_percent == 0 else f"{speed_percent:+d}%"


def normalize_voice_id(voice: str) -> str:
    cleaned = (voice or "").strip()
    if not cleaned:
        raise ValueError("voice must not be empty")
    if cleaned.startswith("["):
        raise ValueError("Use a real Edge voice ID instead of a display label")
    if not VOICE_ID_PATTERN.match(cleaned):
        raise ValueError(f"Invalid Edge voice ID: {cleaned}")
    return cleaned


def decode_pcm_bytes_to_audio(pcm_bytes: bytes, sample_rate: int, torch_module=None):
    if torch_module is None:
        import torch as torch_module

    waveform = torch_module.frombuffer(bytearray(pcm_bytes), dtype=torch_module.float32).clone()
    if waveform.numel() == 0:
        raise RuntimeError("decoded waveform is empty")
    if float(waveform.abs().max()) <= 0.0:
        raise RuntimeError("decoded waveform is silent")

    return {"waveform": waveform.unsqueeze(0).unsqueeze(0), "sample_rate": sample_rate}


def comfy_audio_to_mono_numpy(audio):
    import numpy as np

    if not isinstance(audio, dict) or "waveform" not in audio or "sample_rate" not in audio:
        raise ValueError("audio must be a valid ComfyUI AUDIO value")

    waveform = audio["waveform"]
    sample_rate = int(audio["sample_rate"])

    if hasattr(waveform, "detach"):
        array = np.asarray(waveform.detach().cpu().float().numpy(), dtype=np.float32)
    else:
        array = np.asarray(waveform, dtype=np.float32)

    if array.ndim == 3:
        array = array[0]
    if array.ndim == 2:
        array = array.mean(axis=0 if array.shape[0] <= array.shape[-1] else 1)
    elif array.ndim != 1:
        array = array.reshape(-1)

    if array.size == 0:
        raise ValueError("audio waveform must not be empty")

    return array.astype(np.float32, copy=False), sample_rate


def transcribe_audio_with_pipeline(pipeline, audio_np, sample_rate: int) -> str:
    result = pipeline({"array": audio_np, "sampling_rate": sample_rate})
    if isinstance(result, dict):
        return str(result.get("text", "")).strip()
    return str(result).strip()


def _run_coroutine(coro):
    def runner():
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(runner).result()


class PixelleFloatInput:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "value": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0, "step": 0.1}),
            }
        }

    RETURN_TYPES = ("FLOAT",)
    FUNCTION = "get_value"
    CATEGORY = "Pixelle/TTS"

    def get_value(self, value):
        return (float(value),)


class PixelleOmniVoiceTranscribe:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "whisper_model": (
                    "WHISPER_ASR",
                    {
                        "tooltip": (
                            "Connect OmniVoice Whisper Loader output to reuse the "
                            "same local Whisper ASR model for visible transcription."
                        ),
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "transcribe"
    CATEGORY = "Pixelle/TTS"

    def transcribe(self, audio, whisper_model):
        pipeline = whisper_model.get("pipeline") if isinstance(whisper_model, dict) else None
        if pipeline is None:
            raise ValueError("whisper_model must be a valid OmniVoice whisper_model output")

        audio_np, sample_rate = comfy_audio_to_mono_numpy(audio)
        text = transcribe_audio_with_pipeline(pipeline, audio_np, sample_rate)
        return (text,)


class PixelleEdgeTTS:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "placeholder": "Enter text to convert to speech"}),
                "voice": ("STRING", {"default": "zh-CN-YunjianNeural"}),
                "speed": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0, "step": 0.1}),
                "pitch": ("INT", {"default": 0, "min": -20, "max": 20, "step": 1}),
            }
        }

    RETURN_TYPES = ("AUDIO",)
    FUNCTION = "tts"
    CATEGORY = "Pixelle/TTS"

    async def _synthesize_bytes(self, text: str, voice: str, rate: str, pitch: int) -> bytes:
        last_error = None

        for attempt in range(DEFAULT_RETRY_COUNT + 1):
            if attempt > 0:
                exponential_delay = DEFAULT_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                jitter = random.uniform(0, DEFAULT_RETRY_BASE_DELAY)
                await asyncio.sleep(min(exponential_delay + jitter, MAX_RETRY_DELAY))

            try:
                communicate = edge_tts.Communicate(
                    text=text,
                    voice=voice,
                    rate=rate,
                    pitch=f"{pitch:+d}Hz",
                )
                audio_chunks = []
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_chunks.append(chunk["data"])

                audio_bytes = b"".join(audio_chunks)
                if not audio_bytes:
                    raise RuntimeError("Edge TTS returned no audio bytes")
                return audio_bytes
            except RETRYABLE_EDGE_TTS_ERRORS as exc:
                last_error = exc
                if attempt >= DEFAULT_RETRY_COUNT:
                    raise RuntimeError(f"Edge TTS request failed after retries: {exc}") from exc

        raise RuntimeError("Edge TTS failed without returning audio") from last_error

    def _decode_audio_bytes(self, audio_bytes: bytes):
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise RuntimeError("ffmpeg was not found in PATH")

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".mp3",
            dir=_runtime_temp_dir(),
        ) as temp_file:
            temp_file.write(audio_bytes)
            temp_path = Path(temp_file.name)

        try:
            result = subprocess.run(
                [
                    ffmpeg_path,
                    "-v",
                    "error",
                    "-i",
                    str(temp_path),
                    "-f",
                    "f32le",
                    "-acodec",
                    "pcm_f32le",
                    "-ac",
                    "1",
                    "-ar",
                    str(DEFAULT_SAMPLE_RATE),
                    "pipe:1",
                ],
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="ignore").strip()
                raise RuntimeError(f"ffmpeg decode failed: {stderr or 'unknown ffmpeg error'}")
            if not result.stdout:
                raise RuntimeError("ffmpeg decode produced no PCM output")
            return decode_pcm_bytes_to_audio(result.stdout, sample_rate=DEFAULT_SAMPLE_RATE)
        finally:
            temp_path.unlink(missing_ok=True)

    async def _generate_audio(self, text: str, voice: str, speed: float, pitch: int):
        cleaned_text = (text or "").strip()
        if not cleaned_text:
            raise ValueError("text must not be empty")

        voice_id = normalize_voice_id(voice)
        rate = speed_multiplier_to_rate(speed)
        audio_bytes = await self._synthesize_bytes(cleaned_text, voice_id, rate, pitch)
        return self._decode_audio_bytes(audio_bytes)

    def tts(self, text, voice, speed, pitch):
        return (_run_coroutine(self._generate_audio(text, voice, speed, pitch)),)
