from .pixelle_edge_tts import (
    PixelleEdgeTTS,
    PixelleFloatInput,
    PixelleOmniVoiceTranscribe,
)

NODE_CLASS_MAPPINGS = {
    "PixelleEdgeTTS": PixelleEdgeTTS,
    "PixelleFloatInput": PixelleFloatInput,
    "PixelleOmniVoiceTranscribe": PixelleOmniVoiceTranscribe,
}


NODE_DISPLAY_NAME_MAPPINGS = {
    "PixelleEdgeTTS": "Pixelle Edge TTS",
    "PixelleFloatInput": "Pixelle Float Input",
    "PixelleOmniVoiceTranscribe": "Pixelle OmniVoice Transcribe",
}
