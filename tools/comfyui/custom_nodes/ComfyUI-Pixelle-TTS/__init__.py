from .pixelle_edge_tts import (
    PixelleDurationInput,
    PixelleEdgeTTS,
    PixelleFloatInput,
    PixelleOmniVoiceTranscribe,
)


NODE_CLASS_MAPPINGS = {
    "PixelleEdgeTTS": PixelleEdgeTTS,
    "PixelleFloatInput": PixelleFloatInput,
    "PixelleDurationInput": PixelleDurationInput,
    "PixelleOmniVoiceTranscribe": PixelleOmniVoiceTranscribe,
}


NODE_DISPLAY_NAME_MAPPINGS = {
    "PixelleEdgeTTS": "Pixelle Edge TTS",
    "PixelleFloatInput": "Pixelle Float Input",
    "PixelleDurationInput": "Pixelle Duration Input",
    "PixelleOmniVoiceTranscribe": "Pixelle OmniVoice Transcribe",
}
