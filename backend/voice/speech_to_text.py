"""
Speech-to-Text module.
Clean abstraction over multiple STT providers.

Primary: Browser Web Speech API (frontend-based, sends text via WebSocket)
Future: AWS Transcribe Streaming (server-side, processes raw audio)

The browser-based approach is the production path for this application.
"""

import asyncio
from typing import Optional, Callable, Awaitable, AsyncGenerator, Protocol
from abc import ABC, abstractmethod
import structlog

from config import settings

logger = structlog.get_logger()


# ============================================================
# STT Provider Interface
# ============================================================

class SpeechToTextProvider(ABC):
    """Abstract base class for STT providers."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the provider."""
        pass

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes) -> Optional[str]:
        """Transcribe audio bytes to text."""
        pass

    @property
    @abstractmethod
    def is_initialized(self) -> bool:
        """Whether the provider is ready."""
        pass


# ============================================================
# Browser-based STT (Primary - Production)
# ============================================================

class BrowserSpeechProvider(SpeechToTextProvider):
    """
    Browser-based Speech-to-Text using Web Speech API.
    
    The browser captures audio via the microphone, the Web Speech API
    performs recognition locally/in-cloud, and the frontend sends
    transcribed text to the backend via WebSocket.
    
    This is the recommended production approach because:
    - Zero backend audio processing overhead
    - No AWS Transcribe costs
    - Low latency (browser handles streaming)
    - Works with any browser that supports Web Speech API
    """

    def __init__(self):
        self._initialized = True  # Always ready (browser does the work)
        self.language = settings.transcribe_language_code

    async def initialize(self) -> None:
        """No initialization needed — browser handles everything."""
        logger.info("Browser Speech Provider ready", language=self.language)

    async def transcribe(self, audio_bytes: bytes) -> Optional[str]:
        """Not applicable — browser sends text directly via WebSocket."""
        return None

    @property
    def is_initialized(self) -> bool:
        return True

    def get_frontend_config(self) -> dict:
        """
        Get configuration for the Web Speech API on the frontend.
        Frontend uses these settings in the useSpeechRecognition hook.
        """
        return {
            "language": self.language,
            "continuous": True,
            "interimResults": True,
            "maxAlternatives": 1,
        }

    @staticmethod
    async def process_transcript(
        transcript: str,
        is_final: bool,
        confidence: float = 1.0
    ) -> Optional[str]:
        """
        Process a transcript received from the browser's Web Speech API.
        Called when WebSocket receives a speech message from the client.

        Args:
            transcript: Transcribed text from the browser
            is_final: Whether this is a final (not interim) transcript
            confidence: Recognition confidence (0-1)

        Returns:
            Cleaned transcript text, or None if invalid
        """
        if not transcript or not transcript.strip():
            return None

        cleaned = transcript.strip()

        # Only process final transcripts with reasonable length
        if is_final and len(cleaned) >= 1:
            return cleaned

        return None


# ============================================================
# AWS Transcribe Streaming (Future Production)
# ============================================================

class AWSTranscribeStreamingProvider(SpeechToTextProvider):
    """
    AWS Transcribe Streaming STT provider.
    Processes raw audio on the server side.
    
    NOTE: This is for future production use when server-side audio
    processing is needed (e.g., non-browser clients, IP phones).
    Currently NOT the active provider.
    """

    def __init__(self):
        self._initialized = False
        self.language_code = settings.transcribe_language_code
        self.region = settings.aws_region
        self.sample_rate = 16000
        self.client = None

    async def initialize(self) -> None:
        """Initialize AWS Transcribe Streaming client."""
        try:
            import boto3

            def _create_client():
                session = boto3.Session(
                    region_name=self.region,
                    aws_access_key_id=settings.aws_access_key_id,
                    aws_secret_access_key=settings.aws_secret_access_key
                )
                return session.client("transcribe")

            self.client = await asyncio.to_thread(_create_client)
            self._initialized = True
            logger.info(
                "AWS Transcribe Streaming provider initialized",
                language=self.language_code,
                region=self.region
            )
        except Exception as e:
            logger.error("Failed to initialize AWS Transcribe", error=str(e))
            raise

    async def transcribe(self, audio_bytes: bytes) -> Optional[str]:
        """
        Transcribe audio bytes using AWS Transcribe.
        For streaming, use transcribe_stream instead.
        """
        if not self._initialized:
            return None

        # AWS Transcribe batch requires S3 upload — not suitable for real-time
        # Use streaming API for real-time transcription
        logger.warning("Batch transcription not supported — use streaming")
        return None

    async def transcribe_stream(
        self, audio_stream: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[str, None]:
        """
        Stream audio to AWS Transcribe and yield transcripts.
        
        NOTE: Full implementation requires amazon-transcribe-streaming-sdk
        which handles the WebSocket connection to Transcribe Streaming API.
        """
        if not self._initialized:
            return

        # This would use amazon-transcribe-streaming-sdk in production:
        # from amazon_transcribe.client import TranscribeStreamingClient
        # async with TranscribeStreamingClient(region=self.region) as client:
        #     stream = await client.start_stream_transcription(...)
        #     ...

        logger.info("AWS Transcribe Streaming: Not yet fully integrated")
        yield ""

    @property
    def is_initialized(self) -> bool:
        return self._initialized


# ============================================================
# Main STT Service (facade)
# ============================================================

class SpeechToText:
    """
    Main Speech-to-Text service.
    Uses BrowserSpeechProvider as the primary (and currently production) provider.
    Can be switched to AWSTranscribeStreamingProvider for server-side processing.
    """

    def __init__(self, provider: Optional[str] = "browser"):
        """
        Initialize with the specified provider.
        
        Args:
            provider: "browser" (default) or "aws_transcribe"
        """
        if provider == "aws_transcribe":
            self._provider = AWSTranscribeStreamingProvider()
        else:
            self._provider = BrowserSpeechProvider()

        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the active provider."""
        await self._provider.initialize()
        self._initialized = self._provider.is_initialized
        logger.info(
            "STT service initialized",
            provider=type(self._provider).__name__
        )

    async def transcribe(self, audio_bytes: bytes) -> Optional[str]:
        """Transcribe audio bytes (if supported by active provider)."""
        return await self._provider.transcribe(audio_bytes)

    @property
    def provider(self) -> SpeechToTextProvider:
        """Get the active provider."""
        return self._provider

    def get_frontend_config(self) -> dict:
        """Get frontend configuration for browser-based STT."""
        if isinstance(self._provider, BrowserSpeechProvider):
            return self._provider.get_frontend_config()
        return {"language": settings.transcribe_language_code}

    async def health_check(self) -> bool:
        """Check if STT is available."""
        return self._provider.is_initialized
