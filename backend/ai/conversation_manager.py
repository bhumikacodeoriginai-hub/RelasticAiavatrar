"""
Conversation Manager.
Orchestrates the full conversation flow between visitor and AI avatar.
The backend state machine controls business logic — Llama does NOT control
critical state transitions.
"""

import uuid
import asyncio
from typing import Optional, Dict, List, Callable, Awaitable, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import numpy as np
import structlog

from ai.bedrock import BedrockClient
from ai.prompts import PromptBuilder, VisitorContext, VisitorStatus
from vision.face_matching import FaceMatchResult, MatchResult

logger = structlog.get_logger()


class ConversationState(str, Enum):
    """
    Robust session state machine.
    The backend controls all transitions — Llama never directly changes state.
    """
    IDLE = "idle"
    PERSON_DETECTED = "person_detected"
    IDENTIFYING = "identifying"
    GREETING_NEW = "greeting_new"
    GREETING_RETURNING = "greeting_returning"
    WAITING_FOR_NAME = "waiting_for_name"
    ASKING_CONSENT = "asking_consent"
    REGISTERING_VISITOR = "registering_visitor"
    ACTIVE_CONVERSATION = "active_conversation"
    WAITING_FOR_EMPLOYEE = "waiting_for_employee"
    WAITING_FOR_APPOINTMENT = "waiting_for_appointment"
    ENDING = "ending"
    ENDED = "ended"


@dataclass
class ConversationSession:
    """Represents an active conversation session."""
    session_id: str
    state: ConversationState = ConversationState.IDLE
    visitor_context: VisitorContext = field(default_factory=VisitorContext)
    messages: List[Dict[str, str]] = field(default_factory=list)
    visitor_id: Optional[str] = None
    visit_id: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)

    # Consent tracking
    consent_granted: Optional[bool] = None  # None=not asked, True/False=answered
    consent_timestamp: Optional[datetime] = None

    # Face data (held temporarily until consent)
    pending_face_embedding: Optional[np.ndarray] = None

    # Employee meeting request
    requested_employee_name: Optional[str] = None
    requested_employee_id: Optional[str] = None

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation history."""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
        self.visitor_context.conversation_history = self.messages
        self.last_activity = datetime.utcnow()

    @property
    def message_count(self) -> int:
        return len([m for m in self.messages if m["role"] != "system"])


class ConversationManager:
    """
    Manages conversation sessions and orchestrates the AI interaction flow.

    State Machine Flow:
    ==================
    NEW VISITOR:
        IDLE → GREETING_NEW → WAITING_FOR_NAME → ASKING_CONSENT
             → REGISTERING_VISITOR (if yes) → ACTIVE_CONVERSATION
             → ACTIVE_CONVERSATION (if no, without storing face)

    RETURNING VISITOR:
        IDLE → GREETING_RETURNING → ACTIVE_CONVERSATION

    ACTIVE CONVERSATION:
        ACTIVE_CONVERSATION → WAITING_FOR_EMPLOYEE (if requests meeting)
        ACTIVE_CONVERSATION → ENDING → ENDED (if farewell)

    The backend is authoritative for:
    - State transitions
    - Consent decisions
    - Database operations
    - Employee lookup results

    Llama is responsible for:
    - Natural language responses
    - Name extraction
    - Conversational flow within states
    """

    def __init__(self, bedrock_client: BedrockClient):
        self.bedrock = bedrock_client
        self.active_sessions: Dict[str, ConversationSession] = {}
        self._on_response_callback: Optional[Callable] = None
        self._on_consent_granted_callback: Optional[Callable] = None
        self._on_consent_denied_callback: Optional[Callable] = None
        self.prompt_builder = PromptBuilder()

    def on_response(self, callback: Callable[[str, str], Awaitable[None]]) -> None:
        """Register callback for when AI generates a response."""
        self._on_response_callback = callback

    def on_consent_granted(self, callback: Callable) -> None:
        """Register callback for when visitor grants biometric consent."""
        self._on_consent_granted_callback = callback

    def on_consent_denied(self, callback: Callable) -> None:
        """Register callback for when visitor denies biometric consent."""
        self._on_consent_denied_callback = callback

    async def start_session(
        self,
        match_result: FaceMatchResult
    ) -> ConversationSession:
        """
        Start a new conversation session based on face match result.
        """
        session_id = str(uuid.uuid4())

        if match_result.status == MatchResult.MATCH_FOUND and match_result.visitor:
            # Returning visitor from database
            visitor = match_result.visitor
            visitor_context = VisitorContext(
                name=visitor.name,
                recognition_status=VisitorStatus.RETURNING,
                company=getattr(visitor, 'company', None),
                role=getattr(visitor, 'role', None),
                visit_count=getattr(visitor, 'visit_count', 0),
                last_visit=visitor.last_seen.isoformat() if getattr(visitor, 'last_seen', None) else None
            )
            initial_state = ConversationState.GREETING_RETURNING
            visitor_id = getattr(visitor, 'visitor_id', None)

        elif match_result.status == MatchResult.MATCH_FOUND and match_result.visitor_name:
            # Simulated returning visitor (for testing)
            visitor_context = VisitorContext(
                name=match_result.visitor_name,
                recognition_status=VisitorStatus.RETURNING,
                visit_count=match_result.visit_count,
            )
            initial_state = ConversationState.GREETING_RETURNING
            visitor_id = match_result.visitor_id

        else:
            # New visitor
            visitor_context = VisitorContext(
                recognition_status=VisitorStatus.NEW
            )
            initial_state = ConversationState.GREETING_NEW
            visitor_id = None

        session = ConversationSession(
            session_id=session_id,
            state=initial_state,
            visitor_context=visitor_context,
            visitor_id=visitor_id,
            # Store face embedding temporarily (only persisted if consent given)
            pending_face_embedding=match_result.embedding if match_result.embedding is not None else None,
        )

        self.active_sessions[session_id] = session
        logger.info(
            "Conversation session started",
            session_id=session_id,
            state=initial_state.value,
            visitor_name=visitor_context.name
        )

        return session

    async def generate_greeting(self, session: ConversationSession) -> str:
        """Generate the initial greeting for the visitor."""
        system_prompt = PromptBuilder.build_system_prompt(session.visitor_context)
        greeting_prompt = PromptBuilder.build_initial_greeting_prompt(
            session.visitor_context
        )

        response = await self.bedrock.generate_response(
            prompt=greeting_prompt,
            system_prompt=system_prompt,
            max_tokens=150,
            temperature=0.7
        )

        session.add_message("assistant", response)

        # State transitions after greeting
        if session.state == ConversationState.GREETING_NEW:
            session.state = ConversationState.WAITING_FOR_NAME
        elif session.state == ConversationState.GREETING_RETURNING:
            session.state = ConversationState.ACTIVE_CONVERSATION

        logger.info(
            "Greeting generated",
            session_id=session.session_id,
            new_state=session.state.value,
            response_preview=response[:60]
        )

        return response

    async def process_user_input(
        self,
        session_id: str,
        user_text: str
    ) -> str:
        """
        Process user input and generate AI response.
        The response and state transition depend on current session state.
        """
        session = self.active_sessions.get(session_id)
        if not session:
            logger.warning("Session not found", session_id=session_id)
            return "I'm sorry, could you please repeat that?"

        # Add user message to history
        session.add_message("user", user_text)

        # Route to appropriate handler based on state
        if session.state == ConversationState.WAITING_FOR_NAME:
            return await self._handle_name_input(session, user_text)
        elif session.state == ConversationState.ASKING_CONSENT:
            return await self._handle_consent_response(session, user_text)
        elif session.state == ConversationState.WAITING_FOR_EMPLOYEE:
            return await self._handle_employee_response(session, user_text)
        elif session.state == ConversationState.ENDING:
            return await self._handle_farewell(session, user_text)
        else:
            return await self._handle_conversation(session, user_text)

    async def _handle_name_input(
        self, session: ConversationSession, user_text: str
    ) -> str:
        """
        Handle when we're waiting for the visitor's name.
        Backend extracts name using Llama, then transitions to consent.
        """
        name_prompt = PromptBuilder.build_name_extraction_prompt(user_text)
        extracted_name = await self.bedrock.generate_response(
            prompt=name_prompt,
            max_tokens=30,
            temperature=0.1
        )

        # Clean the extracted name
        extracted_name = extracted_name.strip().strip('"').strip("'").strip()
        # Remove common prefixes/suffixes
        for prefix in ["My name is ", "I'm ", "I am ", "It's ", "This is "]:
            if extracted_name.lower().startswith(prefix.lower()):
                extracted_name = extracted_name[len(prefix):].strip()

        if extracted_name and extracted_name.upper() != "UNKNOWN" and len(extracted_name) > 1:
            session.visitor_context.name = extracted_name
            session.state = ConversationState.ASKING_CONSENT

            # The consent question — MUST be explicit about biometric storage
            response = (
                f"Nice to meet you, {extracted_name}! Welcome to Code Origin.AI. "
                f"Would you like me to remember your face for future visits? "
                f"This means I'll store a mathematical representation of your face "
                f"so I can greet you by name next time."
            )
        else:
            # Could not extract name — ask again
            response = (
                "I didn't quite catch your name. Could you please tell me your name?"
            )

        session.add_message("assistant", response)
        return response

    async def _handle_consent_response(
        self, session: ConversationSession, user_text: str
    ) -> str:
        """
        Handle the visitor's response to biometric consent request.
        CRITICAL: Never auto-grant consent. Only store face if explicitly agreed.
        """
        positive_indicators = [
            "yes", "sure", "okay", "ok", "yeah", "yep", "yea",
            "please", "go ahead", "fine", "absolutely", "of course",
            "why not", "sounds good", "that's fine"
        ]
        negative_indicators = [
            "no", "don't", "nope", "prefer not", "rather not",
            "not interested", "no thanks", "decline", "skip"
        ]

        user_lower = user_text.lower().strip()

        # Check for clear positive
        consent_positive = any(word in user_lower for word in positive_indicators)
        # Check for clear negative
        consent_negative = any(word in user_lower for word in negative_indicators)

        # Avoid false positives: if both match (e.g. "I don't think so, ok maybe yes"),
        # or if negative is present, treat as ambiguous/negative
        if consent_negative and not consent_positive:
            # CONSENT DENIED — do NOT store face embedding
            session.consent_granted = False
            session.consent_timestamp = datetime.utcnow()
            session.pending_face_embedding = None  # Discard
            session.state = ConversationState.ACTIVE_CONVERSATION

            response = (
                f"No problem at all, {session.visitor_context.name}! "
                f"Your privacy is important to us. I won't store any biometric data. "
                f"How can I help you today?"
            )

            # Signal consent denied
            session.add_message("system", "CONSENT_DENIED")
            if self._on_consent_denied_callback:
                await self._on_consent_denied_callback(session)

        elif consent_positive and not consent_negative:
            # CONSENT GRANTED — face embedding will be stored
            session.consent_granted = True
            session.consent_timestamp = datetime.utcnow()
            session.state = ConversationState.REGISTERING_VISITOR

            response = (
                f"Thank you, {session.visitor_context.name}! "
                f"I'll remember you for next time. How can I help you today?"
            )

            # Signal consent granted
            session.add_message("system", "CONSENT_GRANTED")
            if self._on_consent_granted_callback:
                await self._on_consent_granted_callback(session)

            # Transition to active after registration signal
            session.state = ConversationState.ACTIVE_CONVERSATION

        else:
            # AMBIGUOUS — ask again clearly
            response = (
                f"I just want to make sure, {session.visitor_context.name} — "
                f"would you like me to remember your face for future visits? "
                f"A simple yes or no is fine."
            )

        session.add_message("assistant", response)
        return response

    async def _handle_conversation(
        self, session: ConversationSession, user_text: str
    ) -> str:
        """
        Handle general conversation with the visitor.
        Detects intents (meet employee, farewell) and routes appropriately.
        """
        # Check for farewell
        farewell_indicators = ["bye", "goodbye", "see you", "leaving", "gotta go", "have to go"]
        if any(word in user_text.lower() for word in farewell_indicators):
            session.state = ConversationState.ENDING
            return await self._handle_farewell(session, user_text)

        # Check for employee meeting request
        meet_indicators = ["meet", "see", "visit", "talk to", "speak with", "looking for", "appointment with"]
        if any(phrase in user_text.lower() for phrase in meet_indicators):
            return await self._handle_employee_request(session, user_text)

        # General conversation — let Llama respond
        system_prompt = PromptBuilder.build_system_prompt(session.visitor_context)
        user_prompt = PromptBuilder.build_conversation_prompt(
            session.visitor_context, user_text
        )

        response = await self.bedrock.generate_response(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=200,
            temperature=0.6
        )

        session.add_message("assistant", response)
        return response

    async def _handle_employee_request(
        self, session: ConversationSession, user_text: str
    ) -> str:
        """
        Handle when visitor wants to meet an employee.
        Extract employee name and signal to backend for lookup.
        """
        # Use Llama to extract employee name
        extract_prompt = (
            f'Extract the employee name the visitor wants to meet from: "{user_text}"\n'
            f'Return ONLY the name. If unclear, return "UNKNOWN".\n\nEmployee name:'
        )
        extracted_name = await self.bedrock.generate_response(
            prompt=extract_prompt,
            max_tokens=30,
            temperature=0.1
        )
        extracted_name = extracted_name.strip().strip('"').strip("'").strip()

        if extracted_name and extracted_name.upper() != "UNKNOWN":
            session.requested_employee_name = extracted_name
            session.state = ConversationState.WAITING_FOR_EMPLOYEE

            # Signal to WebSocket handler to look up employee
            session.add_message("system", f"EMPLOYEE_LOOKUP:{extracted_name}")

            response = (
                f"Let me check if {extracted_name} is available. One moment please."
            )
        else:
            response = "Who would you like to meet? Could you tell me their name?"

        session.add_message("assistant", response)
        return response

    async def _handle_employee_response(
        self, session: ConversationSession, user_text: str
    ) -> str:
        """Handle conversation while waiting for employee lookup result."""
        # The employee lookup result will be injected by the WebSocket handler
        # via provide_employee_result(). If the user speaks while waiting,
        # acknowledge and continue waiting.
        response = (
            f"I'm still checking on that for you. Is there anything else I can help with in the meantime?"
        )
        session.add_message("assistant", response)
        return response

    async def provide_employee_result(
        self,
        session_id: str,
        employee_found: bool,
        employee_name: Optional[str] = None,
        employee_id: Optional[str] = None,
        availability: Optional[str] = None,
        department: Optional[str] = None,
        office_location: Optional[str] = None,
    ) -> str:
        """
        Inject employee lookup result into the conversation.
        Called by the backend service layer after database lookup.
        """
        session = self.active_sessions.get(session_id)
        if not session:
            return ""

        if employee_found and availability == "available":
            session.requested_employee_id = employee_id
            response = (
                f"{employee_name} is available"
                f"{f' in {office_location}' if office_location else ''}. "
                f"Would you like me to notify {'them' if not employee_name else employee_name} that you've arrived?"
            )
            session.state = ConversationState.ACTIVE_CONVERSATION
        elif employee_found:
            response = (
                f"I found {employee_name}"
                f"{f' in {department}' if department else ''}, "
                f"but they appear to be {availability or 'unavailable'} right now. "
                f"Would you like to leave a message or wait?"
            )
            session.state = ConversationState.ACTIVE_CONVERSATION
        else:
            response = (
                f"I wasn't able to find anyone by that name. "
                f"Could you check the spelling or tell me which department they're in?"
            )
            session.state = ConversationState.ACTIVE_CONVERSATION

        session.add_message("assistant", response)
        return response

    async def _handle_farewell(
        self, session: ConversationSession, user_text: str
    ) -> str:
        """Handle farewell conversation."""
        name = session.visitor_context.name or "visitor"

        if session.visitor_context.recognition_status == VisitorStatus.RETURNING:
            response = (
                f"Goodbye, {name}! It was great seeing you again. "
                f"Have a wonderful day!"
            )
        else:
            response = (
                f"Goodbye, {name}! It was nice meeting you. "
                f"Have a great day, and do visit us again!"
            )

        session.add_message("assistant", response)
        session.state = ConversationState.ENDED
        return response

    async def end_session(self, session_id: str) -> Optional[Dict]:
        """End a conversation session and return summary."""
        session = self.active_sessions.pop(session_id, None)
        if not session:
            return None

        session.state = ConversationState.ENDED

        summary = {
            "session_id": session.session_id,
            "visitor_id": session.visitor_id,
            "visitor_name": session.visitor_context.name,
            "message_count": session.message_count,
            "started_at": session.started_at.isoformat(),
            "ended_at": datetime.utcnow().isoformat(),
            "state_reached": session.state.value,
            "consent_granted": session.consent_granted,
        }

        logger.info("Conversation session ended", **summary)
        return summary

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get an active session by ID."""
        return self.active_sessions.get(session_id)

    def get_active_session_count(self) -> int:
        """Get count of active sessions."""
        return len(self.active_sessions)

    def get_all_sessions(self) -> Dict[str, ConversationSession]:
        """Get all active sessions."""
        return self.active_sessions
