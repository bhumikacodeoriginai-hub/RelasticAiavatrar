"""
Text-to-Speech module using Amazon Polly.
Converts AI-generated text responses to natural-sounding speech audio.
All boto3 calls use asyncio.to_thread to avoid blocking the event loop.
"""

import asyncio
import json
from typing import Optional, AsyncGenerator
import boto3
import structlog

from config import settings

logger = structlog.get_logger()


class TextToSpeech:
    """
    Amazon Polly Text-to-Speech service.
    Converts text to audio for the AI avatar to speak.
    Supports speech marks for lip synchronization (visemes).
    """

    def __init__(self):
        self.voice_id = settings.polly_voice_id
        self.engine = settings.polly_engine
        self.language_code = settings.polly_language_code
        self.region = settings.aws_region
        self.client = None
        self._initialized = False
        self.output_format = "mp3"
        self.sample_rate = "24000"

    async def initialize(self) -> None:
        """Initialize the Amazon Polly client (non-blocking)."""
        try:
            def _create_client():
                session = boto3.Session(
                    region_name=self.region,
                    aws_access_key_id=settings.aws_access_key_id,
                    aws_secret_access_key=settings.aws_secret_access_key
                )
                return session.client("polly")

            self.client = await asyncio.to_thread(_create_client)
            self._initialized = True
            logger.info(
                "Text-to-Speech initialized",
                voice=self.voice_id,
                engine=self.engine,
                language=self.language_code
            )
        except Exception as e:
            logger.error("Failed to initialize TTS", error=str(e))
            raise

    async def synthesize(self, text: str) -> Optional[bytes]:
        """
        Convert text to speech audio (non-blocking).

        Args:
            text: Text to convert to speech

        Returns:
            Audio bytes (MP3 format) or None on error
        """
        if not self._initialized:
            logger.warning("TTS not initialized")
            return None

        if not text or not text.strip():
            return None

        try:
            def _synthesize():
                return self.client.synthesize_speech(
                    Text=text,
                    OutputFormat=self.output_format,
                    VoiceId=self.voice_id,
                    Engine=self.engine,
                    LanguageCode=self.language_code,
                    SampleRate=self.sample_rate
                )

            response = await asyncio.to_thread(_synthesize)

            audio_stream = response.get("AudioStream")
            if audio_stream:
                audio_bytes = audio_stream.read()
                logger.debug(
                    "Speech synthesized",
                    text_length=len(text),
                    audio_size=len(audio_bytes)
                )
                return audio_bytes

            return None

        except Exception as e:
            logger.error("Error synthesizing speech", error=str(e), text_preview=text[:50])
            return None

    async def synthesize_ssml(self, ssml_text: str) -> Optional[bytes]:
        """
        Convert SSML-formatted text to speech (non-blocking).
        Allows pauses, emphasis, and prosody control.
        """
        if not self._initialized:
            return None

        try:
            def _synthesize_ssml():
                return self.client.synthesize_speech(
                    Text=ssml_text,
                    TextType="ssml",
                    OutputFormat=self.output_format,
                    VoiceId=self.voice_id,
                    Engine=self.engine,
                    LanguageCode=self.language_code,
                    SampleRate=self.sample_rate
                )

            response = await asyncio.to_thread(_synthesize_ssml)

            audio_stream = response.get("AudioStream")
            if audio_stream:
                return audio_stream.read()

            return None

        except Exception as e:
            logger.error("Error synthesizing SSML speech", error=str(e))
            return None

    def text_to_ssml(self, text: str, speaking_rate: str = "medium") -> str:
        """Convert plain text to SSML with natural speech patterns."""
        # Add natural pauses after punctuation
        ssml_text = text.replace(". ", '.<break time="300ms"/> ')
        ssml_text = ssml_text.replace("? ", '?<break time="300ms"/> ')
        ssml_text = ssml_text.replace("! ", '!<break time="200ms"/> ')
        ssml_text = ssml_text.replace(", ", ',<break time="150ms"/> ')

        return f"""<speak><prosody rate="{speaking_rate}">{ssml_text}</prosody></speak>"""

    async def synthesize_chunks(
        self, text: str, chunk_size: int = 200
    ) -> AsyncGenerator[bytes, None]:
        """
        Synthesize long text in chunks for faster initial playback.
        Splits text at sentence boundaries.
        """
        sentences = []
        current = ""

        for char in text:
            current += char
            if char in ".!?" and len(current) >= chunk_size:
                sentences.append(current.strip())
                current = ""

        if current.strip():
            sentences.append(current.strip())

        if not sentences:
            sentences = [text]

        for sentence in sentences:
            audio = await self.synthesize(sentence)
            if audio:
                yield audio

    async def get_speech_marks(self, text: str) -> list:
        """
        Get speech marks for lip synchronization (visemes + word timing).
        Returns timing information for mouth shapes.

        Args:
            text: Text to get speech marks for

        Returns:
            List of speech mark dicts: {time, type, value, start, end}
        """
        if not self._initialized:
            return []

        if not text or not text.strip():
            return []

        try:
            def _get_marks():
                return self.client.synthesize_speech(
                    Text=text,
                    OutputFormat="json",
                    VoiceId=self.voice_id,
                    Engine=self.engine,
                    LanguageCode=self.language_code,
                    SpeechMarkTypes=["viseme", "word"]
                )

            response = await asyncio.to_thread(_get_marks)

            audio_stream = response.get("AudioStream")
            if audio_stream:
                content = audio_stream.read().decode('utf-8')
                marks = []
                for line in content.strip().split('\n'):
                    if line.strip():
                        marks.append(json.loads(line))
                return marks

            return []

        except Exception as e:
            logger.error("Error getting speech marks", error=str(e))
            return []

    async def health_check(self) -> bool:
        """Check if Polly is accessible."""
        try:
            audio = await self.synthesize("Hello")
            return audio is not None and len(audio) > 0
        except Exception:
            return False
