"""
WebSocket endpoints for real-time communication.
Handles:
- Real-time camera frame processing
- Live conversation (speech → AI → audio)
- Avatar animation control
- Status updates to dashboard
"""

import asyncio
import base64
import time
from typing import Dict, Set, Optional

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import structlog

from ai.conversation_manager import ConversationManager
from voice.text_to_speech import TextToSpeech
from vision.face_matching import FaceMatchResult, MatchResult
from database.database import AsyncSessionLocal
from database.repositories import VisitorRepository, VisitRepository

logger = structlog.get_logger()

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages all active WebSocket connections."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.dashboard_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info("WebSocket connected", client_id=client_id)

    async def connect_dashboard(self, websocket: WebSocket) -> None:
        """Accept a new dashboard WebSocket connection."""
        await websocket.accept()
        self.dashboard_connections.add(websocket)
        logger.info("Dashboard WebSocket connected")

    def disconnect(self, client_id: str) -> None:
        """Remove a WebSocket connection."""
        self.active_connections.pop(client_id, None)
        logger.info("WebSocket disconnected", client_id=client_id)

    def disconnect_dashboard(self, websocket: WebSocket) -> None:
        """Remove a dashboard connection."""
        self.dashboard_connections.discard(websocket)

    async def send_to_client(self, client_id: str, message: dict) -> None:
        """Send a message to a specific client."""
        ws = self.active_connections.get(client_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.error("Error sending to client", error=str(e))
                self.disconnect(client_id)

    async def broadcast_to_dashboards(self, message: dict) -> None:
        """Broadcast a message to all dashboard connections."""
        disconnected = set()
        for ws in self.dashboard_connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.add(ws)
        for ws in disconnected:
            self.dashboard_connections.discard(ws)


# Global connection manager
ws_manager = ConnectionManager()


@router.websocket("/ws/conversation/{client_id}")
async def conversation_websocket(websocket: WebSocket, client_id: str):
    """
    Main WebSocket for real-time conversation.

    Protocol (Client → Server):
        {"type": "speech", "text": "...", "is_final": true}
        {"type": "frame", "data": "<base64 image>"}
        {"type": "start_session", "match_status": "...", "visitor_id": "..."}
        {"type": "end_session", "session_id": "..."}
        {"type": "consent", "value": true/false}
        {"type": "ping"}

    Protocol (Server → Client):
        {"type": "response", "text": "...", "audio": "...", "speech_marks": [...], "state": "...", "session_id": "..."}
        {"type": "detection", "person_detected": true, "face_detected": true}
        {"type": "recognition", "status": "...", "visitor_name": "...", "confidence": 0.87}
        {"type": "state", "state": "...", "session_id": "..."}
        {"type": "error", "code": "...", "message": "..."}
        {"type": "pong"}
    """
    await ws_manager.connect(websocket, client_id)

    # Get services from app state
    app = websocket.app
    conv_manager: ConversationManager = app.state.conversation_manager
    tts: TextToSpeech = app.state.tts
    current_session_id: Optional[str] = None

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "speech":
                await _handle_speech(
                    data, client_id, current_session_id,
                    conv_manager, tts
                )

            elif msg_type == "start_session":
                current_session_id = await _handle_start_session(
                    data, client_id, conv_manager, tts
                )

            elif msg_type == "end_session":
                await _handle_end_session(
                    current_session_id, client_id, conv_manager
                )
                current_session_id = None

            elif msg_type == "consent":
                await _handle_consent(
                    data, client_id, current_session_id, conv_manager
                )

            elif msg_type == "frame":
                await _handle_frame(data, client_id, app)

            elif msg_type == "ping":
                await ws_manager.send_to_client(client_id, {"type": "pong"})

    except WebSocketDisconnect:
        ws_manager.disconnect(client_id)
        if current_session_id:
            await conv_manager.end_session(current_session_id)
        logger.info("Client disconnected", client_id=client_id)
    except Exception as e:
        logger.error("WebSocket error", error=str(e), client_id=client_id)
        ws_manager.disconnect(client_id)


async def _handle_speech(
    data: dict,
    client_id: str,
    session_id: Optional[str],
    conv_manager: ConversationManager,
    tts: TextToSpeech
):
    """Handle user speech transcription."""
    text = data.get("text", "").strip()
    is_final = data.get("is_final", True)

    if not (is_final and text and session_id):
        return

    # Process through conversation manager
    response_text = await conv_manager.process_user_input(
        session_id=session_id,
        user_text=text
    )

    # Generate audio
    audio_base64 = None
    speech_marks = None
    if response_text:
        audio_bytes = await tts.synthesize(response_text)
        if audio_bytes:
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        speech_marks = await tts.get_speech_marks(response_text)

    # Get current state
    session = conv_manager.get_session(session_id)
    state = session.state.value if session else "ended"
    visitor_name = session.visitor_context.name if session else None

    # Send response to client
    await ws_manager.send_to_client(client_id, {
        "type": "response",
        "text": response_text,
        "audio": audio_base64,
        "speech_marks": speech_marks,
        "state": state,
        "session_id": session_id,
        "visitor_name": visitor_name
    })

    # Broadcast to dashboard
    await ws_manager.broadcast_to_dashboards({
        "type": "conversation_update",
        "session_id": session_id,
        "user_text": text,
        "ai_text": response_text,
        "state": state,
        "visitor_name": visitor_name
    })


async def _handle_start_session(
    data: dict,
    client_id: str,
    conv_manager: ConversationManager,
    tts: TextToSpeech
) -> str:
    """Handle start session request. Returns new session ID."""
    match_status = data.get("match_status", "no_match")
    visitor_id = data.get("visitor_id")
    visitor_name = data.get("visitor_name")
    visit_count = data.get("visit_count", 0)

    # Build match result using real database query if visitor_id is provided
    if match_status == "match_found" and visitor_id:
        async with AsyncSessionLocal() as db:
            visitor_repo = VisitorRepository(db)
            visitor = await visitor_repo.get_by_id(visitor_id)

            if visitor:
                match_result = FaceMatchResult(
                    status=MatchResult.MATCH_FOUND,
                    visitor=visitor,
                    confidence=data.get("confidence", 0.9)
                )
            else:
                # Visitor ID not found in DB, treat as new
                match_result = FaceMatchResult(
                    status=MatchResult.NO_MATCH,
                    message="Visitor not found in database"
                )
    elif match_status == "match_found" and visitor_name:
        # Simulated session with name but no DB record
        match_result = FaceMatchResult(
            status=MatchResult.MATCH_FOUND,
            visitor_name=visitor_name,
            visitor_id=visitor_id,
            visit_count=visit_count,
            confidence=data.get("confidence", 0.9)
        )
    else:
        match_result = FaceMatchResult(
            status=MatchResult.NO_MATCH,
            message="New visitor"
        )

    # Start session
    session = await conv_manager.start_session(match_result)
    session_id = session.session_id

    # Generate greeting
    greeting = await conv_manager.generate_greeting(session)

    # Generate audio
    audio_base64 = None
    speech_marks = None
    if greeting:
        audio_bytes = await tts.synthesize(greeting)
        if audio_bytes:
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        speech_marks = await tts.get_speech_marks(greeting)

    await ws_manager.send_to_client(client_id, {
        "type": "response",
        "text": greeting,
        "audio": audio_base64,
        "speech_marks": speech_marks,
        "state": session.state.value,
        "session_id": session_id,
        "visitor_name": session.visitor_context.name
    })

    # Broadcast new session to dashboard
    await ws_manager.broadcast_to_dashboards({
        "type": "new_session",
        "session_id": session_id,
        "visitor_name": session.visitor_context.name,
        "match_status": match_status
    })

    return session_id


async def _handle_end_session(
    session_id: Optional[str],
    client_id: str,
    conv_manager: ConversationManager
):
    """Handle end session request."""
    if not session_id:
        return

    summary = await conv_manager.end_session(session_id)
    await ws_manager.send_to_client(client_id, {
        "type": "state",
        "state": "ended",
        "session_id": session_id,
        "summary": summary
    })
    await ws_manager.broadcast_to_dashboards({
        "type": "session_ended",
        "session_id": session_id,
        "summary": summary
    })


async def _handle_consent(
    data: dict,
    client_id: str,
    session_id: Optional[str],
    conv_manager: ConversationManager
):
    """Handle explicit consent response from visitor."""
    consent_value = data.get("value", False)

    if session_id:
        session = conv_manager.get_session(session_id)
        if session:
            session.consent_granted = consent_value
            logger.info(
                "Consent received",
                session_id=session_id,
                consent=consent_value
            )


async def _handle_frame(data: dict, client_id: str, app):
    """Handle camera frame for vision processing."""
    frame_data = data.get("data", "")
    if not frame_data:
        return

    try:
        import cv2
        frame_bytes = base64.b64decode(frame_data)
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None or not hasattr(app.state, 'vision_pipeline'):
            return

        # Process through vision pipeline
        from vision.camera import FrameData
        frame_obj = FrameData(
            frame=frame,
            timestamp=time.time(),
            frame_number=0,
            width=frame.shape[1],
            height=frame.shape[0]
        )

        # Pass visitor repository for face matching
        async with AsyncSessionLocal() as db:
            visitor_repo = VisitorRepository(db)
            result = await app.state.vision_pipeline.process_frame(
                frame_obj,
                visitor_repo=visitor_repo
            )

        # Send detection result
        response = {
            "type": "detection",
            "person_detected": result.person_detected,
            "face_detected": result.face_detected,
            "state": result.state.value,
            "timestamp": result.timestamp
        }

        # If a face was recognized, include recognition info
        if hasattr(result, 'recognition') and result.recognition:
            response["type"] = "recognition"
            response["status"] = result.recognition.get("status", "unknown")
            response["visitor_name"] = result.recognition.get("visitor_name")
            response["visitor_id"] = result.recognition.get("visitor_id")
            response["confidence"] = result.recognition.get("confidence")

        await ws_manager.send_to_client(client_id, response)

    except Exception as e:
        logger.error("Error processing frame", error=str(e))
        await ws_manager.send_to_client(client_id, {
            "type": "error",
            "code": "frame_processing_error",
            "message": str(e)
        })


@router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    """
    WebSocket for the management dashboard.
    Receives real-time updates about visitors, conversations, etc.
    """
    await ws_manager.connect_dashboard(websocket)

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        ws_manager.disconnect_dashboard(websocket)
    except Exception as e:
        logger.error("Dashboard WebSocket error", error=str(e))
        ws_manager.disconnect_dashboard(websocket)
