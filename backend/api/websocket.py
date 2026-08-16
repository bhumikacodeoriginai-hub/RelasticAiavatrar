"""
WebSocket endpoints for real-time communication.
Handles:
- Real-time camera frame processing
- Live conversation (speech-to-text → AI → text-to-speech)
- Avatar animation control
- Status updates to dashboard
"""

import json
import asyncio
import base64
import uuid
import time
from typing import Dict, Set, Optional

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
import structlog

from ai.conversation_manager import ConversationManager
from voice.text_to_speech import TextToSpeech
from vision.face_matching import FaceMatchResult, MatchResult

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
async def conversation_websocket(
    websocket: WebSocket,
    client_id: str,
    request: Request = None
):
    """
    Main WebSocket for real-time conversation.

    Protocol:
    Client sends:
        {"type": "speech", "text": "...", "is_final": true/false}
        {"type": "frame", "data": "<base64 image>"}
        {"type": "start_session", "match_status": "...", "person_id": "..."}
        {"type": "end_session", "session_id": "..."}

    Server sends:
        {"type": "response", "text": "...", "audio": "<base64>", "speech_marks": [...]}
        {"type": "detection", "person_detected": true, "face_detected": true, ...}
        {"type": "state", "state": "...", "session_id": "..."}
        {"type": "error", "message": "..."}
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
                # User speech transcribed by browser
                text = data.get("text", "")
                is_final = data.get("is_final", True)

                if is_final and text.strip() and current_session_id:
                    # Process through conversation manager
                    response_text = await conv_manager.process_user_input(
                        session_id=current_session_id,
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
                    session = conv_manager.get_session(current_session_id)
                    state = session.state.value if session else "ended"

                    # Send response back to client
                    await ws_manager.send_to_client(client_id, {
                        "type": "response",
                        "text": response_text,
                        "audio": audio_base64,
                        "speech_marks": speech_marks,
                        "state": state,
                        "session_id": current_session_id
                    })

                    # Broadcast to dashboard
                    await ws_manager.broadcast_to_dashboards({
                        "type": "conversation_update",
                        "session_id": current_session_id,
                        "user_text": text,
                        "ai_text": response_text,
                        "state": state,
                        "visitor_name": session.visitor_context.name if session else None
                    })

            elif msg_type == "start_session":
                # Start new conversation session
                match_status = data.get("match_status", "no_match")
                person_id = data.get("person_id")
                person_name = data.get("person_name")
                visit_count = data.get("visit_count", 0)

                # Build match result
                if match_status == "match_found" and person_id:
                    from database.models import Person
                    # Create a minimal person object for the session
                    person = type('Person', (), {
                        'person_id': uuid.UUID(person_id),
                        'name': person_name or "Visitor",
                        'company': data.get("company"),
                        'role': data.get("role"),
                        'visit_count': visit_count,
                        'last_seen': None
                    })()
                    match_result = FaceMatchResult(
                        status=MatchResult.MATCH_FOUND,
                        person=person,
                        confidence=0.9
                    )
                else:
                    match_result = FaceMatchResult(
                        status=MatchResult.NO_MATCH
                    )

                # Start session
                session = await conv_manager.start_session(match_result)
                current_session_id = session.session_id

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
                    "session_id": current_session_id
                })

                # Broadcast new session to dashboard
                await ws_manager.broadcast_to_dashboards({
                    "type": "new_session",
                    "session_id": current_session_id,
                    "visitor_name": session.visitor_context.name,
                    "match_status": match_status
                })

            elif msg_type == "end_session":
                # End current conversation
                if current_session_id:
                    summary = await conv_manager.end_session(current_session_id)
                    await ws_manager.send_to_client(client_id, {
                        "type": "state",
                        "state": "ended",
                        "session_id": current_session_id,
                        "summary": summary
                    })
                    await ws_manager.broadcast_to_dashboards({
                        "type": "session_ended",
                        "session_id": current_session_id,
                        "summary": summary
                    })
                    current_session_id = None

            elif msg_type == "frame":
                # Camera frame for processing
                frame_data = data.get("data", "")
                if frame_data:
                    # Decode base64 frame
                    try:
                        frame_bytes = base64.b64decode(frame_data)
                        nparr = np.frombuffer(frame_bytes, np.uint8)
                        import cv2
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                        if frame is not None and hasattr(app.state, 'vision_pipeline'):
                            # Process through vision pipeline
                            from vision.camera import FrameData
                            frame_obj = FrameData(
                                frame=frame,
                                timestamp=time.time(),
                                frame_number=0,
                                width=frame.shape[1],
                                height=frame.shape[0]
                            )

                            result = await app.state.vision_pipeline.process_frame(frame_obj)

                            await ws_manager.send_to_client(client_id, {
                                "type": "detection",
                                "person_detected": result.person_detected,
                                "face_detected": result.face_detected,
                                "state": result.state.value,
                                "timestamp": result.timestamp
                            })
                    except Exception as e:
                        logger.error("Error processing frame", error=str(e))

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


@router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    """
    WebSocket for the management dashboard.
    Receives real-time updates about visitors, conversations, etc.
    """
    await ws_manager.connect_dashboard(websocket)

    try:
        while True:
            # Keep connection alive with periodic pings
            data = await websocket.receive_json()

            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        ws_manager.disconnect_dashboard(websocket)
    except Exception as e:
        logger.error("Dashboard WebSocket error", error=str(e))
        ws_manager.disconnect_dashboard(websocket)
