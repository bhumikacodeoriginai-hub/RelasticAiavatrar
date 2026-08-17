"""
Application configuration using Pydantic Settings.
Loads from environment variables and .env file.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Main application settings."""

    # Application
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "development"
    app_secret_key: str = "change-this-in-production"

    # AWS Configuration
    aws_region: str = "ap-south-1"
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None

    # AWS Bedrock
    bedrock_model_id: str = "meta.llama3-70b-instruct-v1:0"
    bedrock_max_tokens: int = 512
    bedrock_temperature: float = 0.5
    bedrock_top_p: float = 0.9

    # AWS Polly
    polly_voice_id: str = "Kajal"
    polly_engine: str = "neural"
    polly_language_code: str = "en-IN"

    # AWS Transcribe
    transcribe_language_code: str = "en-IN"

    # Database (MySQL)
    database_host: str = "localhost"
    database_port: int = 3306
    database_user: str = "ai_receptionist"
    database_password: str = "change-in-production"
    database_name: str = "ai_receptionist"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Face Recognition
    face_similarity_threshold: float = 0.60
    face_embedding_model: str = "buffalo_l"
    max_faces_per_frame: int = 10
    min_face_size: int = 80
    min_detection_confidence: float = 0.5
    min_face_quality: float = 0.3
    recognition_cooldown_seconds: float = 7.0

    # Camera
    camera_index: int = 0
    camera_width: int = 1280
    camera_height: int = 720
    camera_fps: int = 30

    # Person Detection
    person_detection_confidence: float = 0.5
    person_debounce_frames: int = 5

    # Avatar
    avatar_model_path: str = "./models/avatar"

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Session
    session_timeout_seconds: int = 300  # 5 minutes no activity = end session
    departure_timeout_seconds: int = 30  # 30s no person = consider departed

    # VAD
    vad_aggressiveness: int = 2
    vad_silence_timeout_ms: int = 1500
    vad_min_speech_ms: int = 300

    @property
    def database_url(self) -> str:
        """MySQL async connection URL."""
        return (
            f"mysql+aiomysql://{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )

    @property
    def database_url_sync(self) -> str:
        """MySQL sync connection URL (for migrations)."""
        return (
            f"mysql+pymysql://{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
