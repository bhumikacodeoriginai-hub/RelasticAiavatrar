"""
Voice module for the AI Avatar Receptionist.
Handles speech-to-text, text-to-speech, and voice activity detection.

Architecture:
- STT: Primary = Browser Web Speech API (frontend), Future = AWS Transcribe Streaming
- TTS: Amazon Polly with speech marks (visemes) for lip sync
- VAD: WebRTC VAD for detecting speech start/end
"""

from voice.speech_to_text import (
    SpeechToText,
    BrowserSpeechProvider,
    AWSTranscribeStreamingProvider,
    SpeechToTextProvider,
)
from voice.text_to_speech import TextToSpeech
from voice.vad import VoiceActivityDetector, VoiceState, VoiceSegment

__all__ = [
    "SpeechToText",
    "BrowserSpeechProvider",
    "AWSTranscribeStreamingProvider",
    "SpeechToTextProvider",
    "TextToSpeech",
    "VoiceActivityDetector",
    "VoiceState",
    "VoiceSegment",
]
