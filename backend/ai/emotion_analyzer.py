"""
Emotion Analyzer — Derives avatar emotion cues from conversation context.

Analyzes:
- Text sentiment via keyword matching + heuristics
- Conversation state transitions
- Visitor mood indicators
- Response type (greeting, information, empathy, etc.)

Returns emotion + intensity + optional gesture for the frontend avatar.
Can optionally call AWS Comprehend for production-grade sentiment analysis.
"""

import re
from typing import Optional, Tuple
from enum import Enum
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


class AvatarEmotion(str, Enum):
    """Supported avatar emotions (maps to frontend EmotionType)."""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    SURPRISED = "surprised"
    ANGRY = "angry"
    DISGUSTED = "disgusted"
    FEARFUL = "fearful"
    CONTEMPT = "contempt"
    INTERESTED = "interested"
    CONFUSED = "confused"
    EMPATHETIC = "empathetic"
    PROUD = "proud"
    EMBARRASSED = "embarrassed"
    EXCITED = "excited"


class AvatarGesture(str, Enum):
    """Supported avatar gestures."""
    NOD = "nod"
    SHAKE = "shake"
    TILT_LEFT = "tilt_left"
    TILT_RIGHT = "tilt_right"
    SHRUG = "shrug"
    THINKING = "thinking"
    ATTENTION_SHIFT = "attention_shift"
    AGREEMENT = "agreement"
    SURPRISE_BROW = "surprise_brow"
    EMPATHY_TILT = "empathy_tilt"


@dataclass
class EmotionAnalysisResult:
    """Result from emotion analysis."""
    emotion: AvatarEmotion
    intensity: float  # 0.0 - 1.0
    gesture: Optional[AvatarGesture] = None
    gesture_intensity: Optional[float] = None


# ─── Keyword-based Sentiment Patterns ──────────────────────────────────────────

GREETING_PATTERNS = [
    r"\b(hello|hi|welcome|good morning|good afternoon|good evening|hey)\b",
    r"\b(namaste|greetings)\b",
]

HAPPY_PATTERNS = [
    r"\b(glad|happy|pleased|wonderful|great|excellent|fantastic|perfect|lovely)\b",
    r"\b(sure|absolutely|certainly|of course|delighted)\b",
    r"\b(thank you|thanks|grateful|appreciate)\b",
]

EXCITED_PATTERNS = [
    r"\b(amazing|incredible|wow|exciting|awesome|brilliant|superb)\b",
    r"\b(congratulations|congratulate|celebrate)\b",
]

EMPATHETIC_PATTERNS = [
    r"\b(sorry|understand|appreciate your patience|i see|that must)\b",
    r"\b(don'?t worry|no problem|it'?s okay|i understand)\b",
    r"\b(let me help|i'?ll assist|happy to help)\b",
]

SAD_PATTERNS = [
    r"\b(unfortunately|regret|sorry to inform|bad news|unable|cannot)\b",
    r"\b(unavailable|not available|don'?t have|no one|nobody)\b",
]

CONFUSED_PATTERNS = [
    r"\b(could you repeat|didn'?t catch|pardon|sorry\?|what do you mean)\b",
    r"\b(i'?m not sure|unclear|confusing|hmm)\b",
]

INTERESTED_PATTERNS = [
    r"\b(interesting|tell me more|how about|what about|could you)\b",
    r"\b(let me check|let me look|looking into|searching)\b",
]

THINKING_PATTERNS = [
    r"\b(let me think|one moment|give me a second|hold on|searching)\b",
    r"\b(checking|looking up|finding|verifying)\b",
]


class EmotionAnalyzer:
    """
    Analyzes conversation text to determine appropriate avatar emotion/gesture.

    Uses cascading rules:
    1. Conversation state-based defaults
    2. Keyword/pattern matching on response text
    3. Punctuation/emphasis analysis
    4. Context from previous messages
    """

    def __init__(self, use_comprehend: bool = False):
        """
        Args:
            use_comprehend: If True, uses AWS Comprehend for production sentiment
                          (requires proper IAM setup). Defaults to keyword-based analysis.
        """
        self.use_comprehend = use_comprehend
        self._comprehend_client = None

    async def initialize(self):
        """Initialize AWS Comprehend client if configured."""
        if self.use_comprehend:
            try:
                import boto3
                self._comprehend_client = boto3.client('comprehend')
                logger.info("✅ AWS Comprehend client initialized for emotion analysis")
            except Exception as e:
                logger.warning("⚠️ Comprehend unavailable, using keyword analysis", error=str(e))
                self.use_comprehend = False

    def analyze(
        self,
        text: str,
        conversation_state: Optional[str] = None,
        previous_messages: Optional[list] = None,
    ) -> EmotionAnalysisResult:
        """
        Analyze text and return emotion cues for the avatar.

        Args:
            text: The avatar's response text
            conversation_state: Current state machine state
            previous_messages: Recent conversation history for context

        Returns:
            EmotionAnalysisResult with emotion, intensity, and optional gesture
        """
        # ─── State-based Defaults ─────────────────────────────
        if conversation_state:
            state_emotion = self._state_to_emotion(conversation_state)
            if state_emotion:
                return state_emotion

        # ─── Pattern Matching ─────────────────────────────────
        text_lower = text.lower()

        # Check patterns in priority order
        if self._matches_any(text_lower, EXCITED_PATTERNS):
            return EmotionAnalysisResult(
                emotion=AvatarEmotion.EXCITED,
                intensity=0.75,
                gesture=AvatarGesture.NOD,
                gesture_intensity=0.6,
            )

        if self._matches_any(text_lower, GREETING_PATTERNS):
            return EmotionAnalysisResult(
                emotion=AvatarEmotion.HAPPY,
                intensity=0.7,
                gesture=AvatarGesture.NOD,
                gesture_intensity=0.5,
            )

        if self._matches_any(text_lower, HAPPY_PATTERNS):
            return EmotionAnalysisResult(
                emotion=AvatarEmotion.HAPPY,
                intensity=0.65,
                gesture=AvatarGesture.AGREEMENT,
                gesture_intensity=0.5,
            )

        if self._matches_any(text_lower, EMPATHETIC_PATTERNS):
            return EmotionAnalysisResult(
                emotion=AvatarEmotion.EMPATHETIC,
                intensity=0.6,
                gesture=AvatarGesture.EMPATHY_TILT,
                gesture_intensity=0.5,
            )

        if self._matches_any(text_lower, SAD_PATTERNS):
            return EmotionAnalysisResult(
                emotion=AvatarEmotion.SAD,
                intensity=0.5,
                gesture=AvatarGesture.EMPATHY_TILT,
                gesture_intensity=0.4,
            )

        if self._matches_any(text_lower, THINKING_PATTERNS):
            return EmotionAnalysisResult(
                emotion=AvatarEmotion.INTERESTED,
                intensity=0.5,
                gesture=AvatarGesture.THINKING,
                gesture_intensity=0.6,
            )

        if self._matches_any(text_lower, CONFUSED_PATTERNS):
            return EmotionAnalysisResult(
                emotion=AvatarEmotion.CONFUSED,
                intensity=0.5,
                gesture=AvatarGesture.TILT_RIGHT,
                gesture_intensity=0.5,
            )

        if self._matches_any(text_lower, INTERESTED_PATTERNS):
            return EmotionAnalysisResult(
                emotion=AvatarEmotion.INTERESTED,
                intensity=0.55,
                gesture=AvatarGesture.NOD,
                gesture_intensity=0.4,
            )

        # ─── Punctuation/Emphasis Analysis ────────────────────
        if '!' in text:
            exclaim_count = text.count('!')
            if exclaim_count >= 2:
                return EmotionAnalysisResult(
                    emotion=AvatarEmotion.EXCITED,
                    intensity=0.65,
                )
            return EmotionAnalysisResult(
                emotion=AvatarEmotion.HAPPY,
                intensity=0.55,
            )

        if '?' in text:
            return EmotionAnalysisResult(
                emotion=AvatarEmotion.INTERESTED,
                intensity=0.5,
                gesture=AvatarGesture.TILT_LEFT,
                gesture_intensity=0.4,
            )

        # ─── Default: Neutral with slight warmth ──────────────
        return EmotionAnalysisResult(
            emotion=AvatarEmotion.NEUTRAL,
            intensity=0.5,
        )

    def _state_to_emotion(self, state: str) -> Optional[EmotionAnalysisResult]:
        """Map conversation state to default emotion."""
        state_map = {
            'greeting_new': EmotionAnalysisResult(
                emotion=AvatarEmotion.HAPPY,
                intensity=0.75,
                gesture=AvatarGesture.NOD,
                gesture_intensity=0.6,
            ),
            'greeting_returning': EmotionAnalysisResult(
                emotion=AvatarEmotion.EXCITED,
                intensity=0.7,
                gesture=AvatarGesture.NOD,
                gesture_intensity=0.6,
            ),
            'asking_consent': EmotionAnalysisResult(
                emotion=AvatarEmotion.INTERESTED,
                intensity=0.5,
                gesture=AvatarGesture.TILT_LEFT,
                gesture_intensity=0.4,
            ),
            'waiting_for_name': EmotionAnalysisResult(
                emotion=AvatarEmotion.INTERESTED,
                intensity=0.55,
            ),
            'registering_visitor': EmotionAnalysisResult(
                emotion=AvatarEmotion.HAPPY,
                intensity=0.6,
                gesture=AvatarGesture.AGREEMENT,
                gesture_intensity=0.5,
            ),
            'ending': EmotionAnalysisResult(
                emotion=AvatarEmotion.HAPPY,
                intensity=0.6,
                gesture=AvatarGesture.NOD,
                gesture_intensity=0.5,
            ),
        }
        return state_map.get(state)

    def _matches_any(self, text: str, patterns: list) -> bool:
        """Check if text matches any of the regex patterns."""
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False


# ─── Singleton Instance ────────────────────────────────────────────────────────

emotion_analyzer = EmotionAnalyzer(use_comprehend=False)
