"""
WebSocket endpoints for real-time communication.
Handles:
- Real-time camera frame processing
- Live conversation (speech → AI → audio)
- Visitor registration on consent
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

from ai.conversation_manager import ConversationManager, ConversationState
from voice.text_to_speech import TextToSpeech
from vision.face_matching import FaceMatchResult, MatchResult
from database.database import AsyncSessionLocal
from database.repositories import (
    VisitorRepository, VisitRepository, EmployeeRepository,
    NotificationRepository, ConversationRepository
)
from database.models import ConsentStatus

logger = structlog.get_logger()

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages all active WebSocket connections."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.dashboard_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info("WebSocket connected", client_id=client_id)

    async def connect_dashboard(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.dashboard_connections.add(websocket)
        logger.info("Dashboard WebSocket connected")

    def disconnect(self, client_id: str) -> None:
        self.active_connections.pop(client_id, None)
        logger.info("WebSocket disconnected", client_id=client_id)

    def disconnect_dashboard(self, websocket: WebSocket) -> None:
        self.dashboard_connections.discard(websocket)

    async def send_to_client(self, client_id: str, message: dict) -> None:
        ws = self.active_connections.get(client_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.error("Error sending to client", error=str(e))
                self.disconnect(client_id)

    async def broadcast_to_dashboards(self, message: dict) -> None:
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
    
    AUTHENTICATION: Requires a valid connection ticket as query parameter.
    Get a ticket from POST /api/auth/ws-ticket (requires JWT auth).
    Connect as: ws://host/ws/conversation/{client_id}?ticket=<ticket>

    Protocol (Client → Server):
        {"type": "speech", "text": "...", "is_final": true}
        {"type": "frame", "data": "<base64 image>"}
        {"type": "start_session", "match_status": "...", "visitor_id": "..."}
        {"type": "end_session"}
        {"type": "consent", "value": true/false}
        {"type": "ping"}

    Protocol (Server → Client):
        {"type": "response", "text": "...", "audio": "...", "speech_marks": [...], ...}
        {"type": "detection", "person_detected": true, "face_detected": true}
        {"type": "recognition", "status": "...", "visitor_name": "...", "confidence": ...}
        {"type": "state", "state": "...", "session_id": "..."}
        {"type": "registration", "status": "success", "visitor_id": "..."}
        {"type": "error", "code": "...", "message": "..."}
        {"type": "pong"}
    """
    # === AUTHENTICATION: Validate connection ticket ===
    ticket = websocket.query_params.get("ticket")
    if not ticket:
        await websocket.close(code=4001, reason="Missing connection ticket")
        return

    from api.auth import verify_ws_ticket
    ticket_payload = verify_ws_ticket(ticket)
    if not ticket_payload:
        await websocket.close(code=4003, reason="Invalid or expired ticket")
        return

    ws_user_id = ticket_payload.get("sub")
    ws_role = ticket_payload.get("role")
    logger.info("WebSocket authenticated", client_id=client_id, user_id=ws_user_id, role=ws_role)

    await ws_manager.connect(websocket, client_id)

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
                # Explicit consent via UI button (alternative to speech-based consent)
                await _handle_explicit_consent(
                    data, client_id, current_session_id, conv_manager, tts
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
    """Handle user speech transcription and process through conversation manager."""
    text = data.get("text", "").strip()
    is_final = data.get("is_final", True)

    if not (is_final and text and session_id):
        return

    # Process through conversation manager (handles state transitions)
    response_text = await conv_manager.process_user_input(
        session_id=session_id,
        user_text=text
    )

    # Check if consent was just granted — trigger registration
    session = conv_manager.get_session(session_id)
    if session:
        await _check_and_handle_consent_result(session, client_id)
        await _check_and_handle_employee_lookup(session, client_id, conv_manager, tts)

    # Generate audio
    audio_base64 = None
    speech_marks = None
    if response_text:
        audio_bytes = await tts.synthesize(response_text)
        if audio_bytes:
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        speech_marks = await tts.get_speech_marks(response_text)

    # Get current state
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


async def _check_and_handle_consent_result(session, client_id: str):
    """
    After conversation manager processes consent, handle registration.
    This is where the face embedding actually gets stored (or discarded).
    """
    if session.consent_granted is None:
        return  # Consent not yet decided

    # Check for CONSENT_GRANTED system message (most recent)
    recent_system_msgs = [
        m for m in session.messages
        if m.get("role") == "system" and m.get("content") in ("CONSENT_GRANTED", "CONSENT_DENIED")
    ]

    if not recent_system_msgs:
        return

    last_consent_msg = recent_system_msgs[-1]["content"]

    # Only process once — check if we already handled it
    if hasattr(session, '_consent_processed') and session._consent_processed:
        return
    session._consent_processed = True

    if last_consent_msg == "CONSENT_GRANTED" and session.pending_face_embedding is not None:
        # REGISTER VISITOR: Store name + face embedding in database
        try:
            async with AsyncSessionLocal() as db:
                visitor_repo = VisitorRepository(db)
                visitor = await visitor_repo.create(
                    name=session.visitor_context.name or "Unknown",
                    face_embedding=session.pending_face_embedding,
                    email=None,
                    phone=None,
                    company=session.visitor_context.company,
                    role=session.visitor_context.role,
                    consent_status=ConsentStatus.GRANTED.value
                )
                # Also create a visit record
                visit_repo = VisitRepository(db)
                visit = await visit_repo.create(
                    visitor_id=visitor.visitor_id
                )
                await db.commit()

                session.visitor_id = visitor.visitor_id
                session.visit_id = visit.visit_id

                logger.info(
                    "Visitor registered with consent",
                    visitor_id=visitor.visitor_id,
                    name=visitor.name
                )

            # Notify client of successful registration
            await ws_manager.send_to_client(client_id, {
                "type": "registration",
                "status": "success",
                "visitor_id": session.visitor_id,
                "visitor_name": session.visitor_context.name,
                "message": "Visitor registered successfully"
            })

        except Exception as e:
            logger.error("Failed to register visitor", error=str(e))
            await ws_manager.send_to_client(client_id, {
                "type": "registration",
                "status": "error",
                "message": "Failed to register visitor"
            })

    elif last_consent_msg == "CONSENT_DENIED":
        # Consent denied — discard embedding, still create visit without biometric
        session.pending_face_embedding = None  # Ensure it's gone

        try:
            async with AsyncSessionLocal() as db:
                # Create visitor record WITHOUT face embedding
                visitor_repo = VisitorRepository(db)
                visitor = await visitor_repo.create(
                    name=session.visitor_context.name or "Unknown",
                    face_embedding=None,  # NO biometric storage
                    consent_status=ConsentStatus.DENIED.value
                )
                # Create visit record
                visit_repo = VisitRepository(db)
                visit = await visit_repo.create(visitor_id=visitor.visitor_id)
                await db.commit()

                session.visitor_id = visitor.visitor_id
                session.visit_id = visit.visit_id

        except Exception as e:
            logger.error("Failed to create visitor record (no consent)", error=str(e))

        await ws_manager.send_to_client(client_id, {
            "type": "registration",
            "status": "consent_denied",
            "message": "Visitor registered without biometric data"
        })


async def _check_and_handle_employee_lookup(
    session, client_id: str,
    conv_manager: ConversationManager,
    tts: TextToSpeech
):
    """
    Check if conversation manager signaled an employee lookup request.
    If so, perform the lookup and inject result back.
    """
    # Check for EMPLOYEE_LOOKUP system message
    recent_system_msgs = [
        m for m in session.messages
        if m.get("role") == "system" and m.get("content", "").startswith("EMPLOYEE_LOOKUP:")
    ]

    if not recent_system_msgs:
        return

    # Get the most recent lookup request
    lookup_msg = recent_system_msgs[-1]["content"]
    employee_name = lookup_msg.replace("EMPLOYEE_LOOKUP:", "").strip()

    # Check if we already processed this lookup
    if hasattr(session, '_last_employee_lookup') and session._last_employee_lookup == employee_name:
        return
    session._last_employee_lookup = employee_name

    # Perform actual database lookup
    try:
        async with AsyncSessionLocal() as db:
            employee_repo = EmployeeRepository(db)
            employees = await employee_repo.search_by_name(employee_name)

            if employees:
                emp = employees[0]  # Best match
                # Inject result into conversation
                response = await conv_manager.provide_employee_result(
                    session_id=session.session_id,
                    employee_found=True,
                    employee_name=emp.name,
                    employee_id=emp.employee_id,
                    availability=emp.availability,
                    department=emp.department,
                    office_location=emp.office_location,
                )

                # Send the employee result response to client
                if response:
                    audio_base64 = None
                    audio_bytes = await tts.synthesize(response)
                    if audio_bytes:
                        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

                    await ws_manager.send_to_client(client_id, {
                        "type": "response",
                        "text": response,
                        "audio": audio_base64,
                        "speech_marks": await tts.get_speech_marks(response) if response else None,
                        "state": session.state.value,
                        "session_id": session.session_id,
                        "visitor_name": session.visitor_context.name
                    })
            else:
                response = await conv_manager.provide_employee_result(
                    session_id=session.session_id,
                    employee_found=False,
                )
                if response:
                    audio_bytes = await tts.synthesize(response)
                    audio_base64 = base64.b64encode(audio_bytes).decode('utf-8') if audio_bytes else None

                    await ws_manager.send_to_client(client_id, {
                        "type": "response",
                        "text": response,
                        "audio": audio_base64,
                        "speech_marks": await tts.get_speech_marks(response) if response else None,
                        "state": session.state.value,
                        "session_id": session.session_id,
                        "visitor_name": session.visitor_context.name
                    })

    except Exception as e:
        logger.error("Employee lookup failed", error=str(e))


async def _handle_explicit_consent(
    data: dict,
    client_id: str,
    session_id: Optional[str],
    conv_manager: ConversationManager,
    tts: TextToSpeech
):
    """Handle explicit consent via UI button (not speech)."""
    if not session_id:
        return

    consent_value = data.get("value", False)
    session = conv_manager.get_session(session_id)
    if not session:
        return

    # Only process if we're in the ASKING_CONSENT state
    if session.state != ConversationState.ASKING_CONSENT:
        return

    # Simulate the speech response
    if consent_value:
        response_text = await conv_manager.process_user_input(session_id, "Yes, please remember me")
    else:
        response_text = await conv_manager.process_user_input(session_id, "No, prefer not")

    # Handle registration
    await _check_and_handle_consent_result(session, client_id)

    # Generate audio and send response
    audio_base64 = None
    if response_text:
        audio_bytes = await tts.synthesize(response_text)
        if audio_bytes:
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

    await ws_manager.send_to_client(client_id, {
        "type": "response",
        "text": response_text,
        "audio": audio_base64,
        "speech_marks": await tts.get_speech_marks(response_text) if response_text else None,
        "state": session.state.value,
        "session_id": session_id,
        "visitor_name": session.visitor_context.name
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

    # Build match result
    if match_status == "match_found" and visitor_id:
        # Real returning visitor — lookup from database
        async with AsyncSessionLocal() as db:
            visitor_repo = VisitorRepository(db)
            visitor = await visitor_repo.get_by_id(visitor_id)

            if visitor:
                match_result = FaceMatchResult(
                    status=MatchResult.MATCH_FOUND,
                    visitor=visitor,
                    confidence=data.get("confidence", 0.9)
                )

                # Create a visit record for the returning visitor
                visit_repo = VisitRepository(db)
                visit = await visit_repo.create(visitor_id=visitor.visitor_id)
                await db.commit()
            else:
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

        # Build response
        response = {
            "type": "detection",
            "person_detected": result.person_detected,
            "face_detected": result.face_detected,
            "state": result.state.value,
            "timestamp": result.timestamp
        }

        # If recognition result is available, send it
        if result.recognition:
            response = {
                "type": "recognition",
                "status": result.recognition.get("status", "unknown"),
                "visitor_name": result.recognition.get("visitor_name"),
                "visitor_id": result.recognition.get("visitor_id"),
                "confidence": result.recognition.get("confidence"),
                "person_detected": result.person_detected,
                "face_detected": result.face_detected,
            }

        await ws_manager.send_to_client(client_id, response)

    except Exception as e:
        logger.error("Error processing frame", error=str(e))


@router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    """
    WebSocket for the management dashboard real-time updates.
    AUTHENTICATION: Requires a valid connection ticket as query parameter.
    """
    # === AUTHENTICATION: Validate connection ticket ===
    ticket = websocket.query_params.get("ticket")
    if not ticket:
        await websocket.close(code=4001, reason="Missing connection ticket")
        return

    from api.auth import verify_ws_ticket
    ticket_payload = verify_ws_ticket(ticket)
    if not ticket_payload:
        await websocket.close(code=4003, reason="Invalid or expired ticket")
        return

    logger.info("Dashboard WebSocket authenticated", user_id=ticket_payload.get("sub"))

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
