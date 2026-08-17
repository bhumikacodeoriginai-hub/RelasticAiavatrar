"""
Main FastAPI Application - AI Avatar Receptionist
=================================================

Entry point for the backend server.
Initializes all services and registers API routes.
"""

from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from config import settings
from database.database import init_db, close_db, check_db_health
from ai.bedrock import BedrockClient
from ai.conversation_manager import ConversationManager
from voice.text_to_speech import TextToSpeech
from voice.speech_to_text import SpeechToText
from voice.vad import VoiceActivityDetector
from vision.person_detection import PersonDetector
from vision.face_detection import FaceDetector
from vision.face_embedding import FaceEmbedder
from vision.face_matching import FaceMatcher
from vision.pipeline import VisionPipeline
from vision.camera import CameraService

from api.visitor import router as visitor_router
from api.conversation import router as conversation_router
from api.employee import router as employee_router
from api.websocket import router as websocket_router
from api.dashboard import router as dashboard_router
from api.auth import router as auth_router
from api.visits import router as visits_router, departure_detector

# Configure structured logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if settings.app_env == "development"
        else structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        structlog.get_config().get("min_level", 0)
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Initializes all services on startup and cleans up on shutdown.
    """
    logger.info("🚀 Starting AI Avatar Receptionist Backend...")
    app.state.start_time = datetime.utcnow()

    # Initialize Database
    try:
        await init_db()
        logger.info("✅ Database initialized (MySQL)")
    except Exception as e:
        logger.error("❌ Database initialization failed", error=str(e))

    # Initialize AWS Bedrock Client
    try:
        bedrock_client = BedrockClient()
        await bedrock_client.initialize()
        app.state.bedrock_client = bedrock_client
        logger.info("✅ AWS Bedrock client initialized")
    except Exception as e:
        logger.error("❌ Bedrock initialization failed (will retry on use)", error=str(e))
        app.state.bedrock_client = BedrockClient()

    # Initialize Conversation Manager
    conv_manager = ConversationManager(app.state.bedrock_client)
    app.state.conversation_manager = conv_manager
    logger.info("✅ Conversation manager initialized")

    # Initialize Text-to-Speech
    try:
        tts = TextToSpeech()
        await tts.initialize()
        app.state.tts = tts
        logger.info("✅ Text-to-Speech initialized")
    except Exception as e:
        logger.error("❌ TTS initialization failed (will retry on use)", error=str(e))
        app.state.tts = TextToSpeech()

    # Initialize Speech-to-Text
    try:
        stt = SpeechToText()
        await stt.initialize()
        app.state.stt = stt
        logger.info("✅ Speech-to-Text initialized")
    except Exception as e:
        logger.error("❌ STT initialization failed", error=str(e))
        app.state.stt = SpeechToText()

    # Initialize Voice Activity Detector
    try:
        vad = VoiceActivityDetector()
        await vad.initialize()
        app.state.vad = vad
        logger.info("✅ Voice Activity Detector initialized")
    except Exception as e:
        logger.error("❌ VAD initialization failed", error=str(e))
        app.state.vad = VoiceActivityDetector()

    # Initialize Vision Services
    try:
        person_detector = PersonDetector(
            confidence_threshold=settings.person_detection_confidence,
            device="cpu"
        )
        await person_detector.initialize()

        face_detector = FaceDetector(
            model_name=settings.face_embedding_model,
            det_threshold=settings.min_detection_confidence,
            max_faces=settings.max_faces_per_frame,
            min_face_quality=settings.min_face_quality,
        )
        await face_detector.initialize()

        # Share the InsightFace model instance to avoid duplicate loading
        shared_model = face_detector.get_model()

        face_embedder = FaceEmbedder(
            model_name=settings.face_embedding_model,
            shared_app=shared_model
        )
        await face_embedder.initialize(shared_app=shared_model)

        face_matcher = FaceMatcher(
            similarity_threshold=settings.face_similarity_threshold
        )

        # Create vision pipeline
        vision_pipeline = VisionPipeline(
            person_detector=person_detector,
            face_detector=face_detector,
            face_embedder=face_embedder,
            face_matcher=face_matcher,
            recognition_cooldown=settings.recognition_cooldown_seconds,
            min_face_size=settings.min_face_size,
            person_debounce_frames=settings.person_debounce_frames,
        )
        app.state.vision_pipeline = vision_pipeline
        app.state.person_detector = person_detector
        app.state.face_detector = face_detector
        app.state.face_embedder = face_embedder
        app.state.face_matcher = face_matcher

        logger.info("✅ Vision pipeline initialized (shared model instance)")
    except Exception as e:
        logger.error("❌ Vision pipeline initialization failed", error=str(e))
        logger.info("   (This is expected if models are not downloaded yet)")

    # Initialize Camera Service (optional - may not have camera)
    try:
        camera = CameraService(
            camera_index=settings.camera_index,
            width=settings.camera_width,
            height=settings.camera_height,
            fps=settings.camera_fps
        )
        app.state.camera_service = camera
        logger.info("✅ Camera service created (not started - starts with first frame)")
    except Exception as e:
        logger.error("❌ Camera service creation failed", error=str(e))

    logger.info("=" * 60)
    logger.info("🎉 AI Avatar Receptionist Backend is READY!")
    logger.info(f"   📍 Running at http://{settings.app_host}:{settings.app_port}")
    logger.info(f"   📍 API Docs at http://localhost:{settings.app_port}/docs")
    logger.info("=" * 60)

    # Start background services
    await departure_detector.start(app)

    yield  # Application runs here

    # Shutdown
    logger.info("🛑 Shutting down AI Avatar Receptionist Backend...")
    await departure_detector.stop()
    if hasattr(app.state, 'camera_service') and app.state.camera_service.is_running:
        await app.state.camera_service.stop()
    await close_db()
    logger.info("👋 Shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="AI Avatar Receptionist",
    description="""
    Intelligent AI-powered office receptionist with:
    - Face detection & recognition (InsightFace/ArcFace)
    - Voice conversation with Llama 3 70B (AWS Bedrock)
    - Realistic avatar with lip sync (Amazon Polly visemes)
    - Visitor management & registration
    - Employee directory & availability
    - Visit tracking & dashboard
    """,
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(auth_router)
app.include_router(visitor_router)
app.include_router(conversation_router)
app.include_router(employee_router)
app.include_router(visits_router)
app.include_router(websocket_router)
app.include_router(dashboard_router)


# === Health & Status Endpoints ===

@app.get("/")
async def root():
    """Root endpoint - system info."""
    return {
        "name": "AI Avatar Receptionist",
        "version": "2.0.0",
        "company": "Code Origin.AI",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint with service status details."""
    services = {}

    # Check database
    db_healthy = await check_db_health()
    services["database"] = "healthy" if db_healthy else "unhealthy"

    # Check Bedrock
    if hasattr(app.state, 'bedrock_client'):
        services["bedrock"] = "initialized" if app.state.bedrock_client._initialized else "not_initialized"
    else:
        services["bedrock"] = "not_available"

    # Check TTS
    if hasattr(app.state, 'tts'):
        services["tts"] = "initialized" if app.state.tts._initialized else "not_initialized"
    else:
        services["tts"] = "not_available"

    # Check Vision
    services["vision"] = "initialized" if hasattr(app.state, 'vision_pipeline') else "not_available"

    # Check Camera
    if hasattr(app.state, 'camera_service'):
        services["camera"] = "running" if app.state.camera_service.is_running else "stopped"
    else:
        services["camera"] = "not_available"

    overall = "healthy" if all(v not in ("unhealthy",) for v in services.values()) else "degraded"

    return {
        "status": overall,
        "services": services,
        "uptime": str(datetime.utcnow() - app.state.start_time) if hasattr(app.state, 'start_time') else "unknown"
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler - never expose internals in production."""
    logger.error("Unhandled exception", error=str(exc), path=request.url.path)
    content = {"error": "Internal server error"}
    if settings.app_env == "development":
        content["detail"] = str(exc)
    return JSONResponse(status_code=500, content=content)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower()
    )
