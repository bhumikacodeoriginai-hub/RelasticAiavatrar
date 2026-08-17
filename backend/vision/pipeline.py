"""
Vision Pipeline - orchestrates the full detection workflow.

Camera Frame → Person Detection → Face Detection → Face Embedding → Face Matching

This is the state machine that determines:
- Is there a person? (vs chair, bag, etc.)
- Is the face visible?
- Is this a known or unknown person?
"""

import asyncio
from typing import Optional, Callable, Awaitable, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
import time

import numpy as np
import structlog

from vision.person_detection import PersonDetector, DetectedPerson
from vision.face_detection import FaceDetector, DetectedFace
from vision.face_embedding import FaceEmbedder
from vision.face_matching import FaceMatcher, FaceMatchResult, MatchResult
from vision.camera import FrameData

logger = structlog.get_logger()


class PipelineState(str, Enum):
    """Current state of the vision pipeline."""
    IDLE = "idle"
    PERSON_DETECTED = "person_detected"
    FACE_DETECTED = "face_detected"
    PERSON_IDENTIFIED = "person_identified"
    NEW_PERSON = "new_person"
    WAITING_FOR_REGISTRATION = "waiting_for_registration"
    IN_CONVERSATION = "in_conversation"


@dataclass
class PipelineResult:
    """Result from one pipeline processing cycle."""
    state: PipelineState
    person_detected: bool = False
    face_detected: bool = False
    detected_person: Optional[DetectedPerson] = None
    detected_face: Optional[DetectedFace] = None
    match_result: Optional[FaceMatchResult] = None
    recognition: Optional[Dict[str, Any]] = None
    frame: Optional[np.ndarray] = None
    timestamp: float = 0.0


class VisionPipeline:
    """
    Orchestrates the complete vision processing pipeline.

    Flow:
    1. Camera captures frame
    2. YOLO detects if a person is present
    3. If person found, InsightFace detects the face
    4. If face found, extract embedding
    5. Search embedding against database
    6. Return result: known person, new person, or no detection
    """

    def __init__(
        self,
        person_detector: PersonDetector,
        face_detector: FaceDetector,
        face_embedder: FaceEmbedder,
        face_matcher: FaceMatcher,
        recognition_cooldown: float = 7.0,
        min_face_size: int = 80,
        person_debounce_frames: int = 5,
        departure_frames: int = 10,
    ):
        """
        Initialize the vision pipeline.

        Args:
            person_detector: YOLO person detector
            face_detector: InsightFace face detector
            face_embedder: Face embedding generator
            face_matcher: Face matching service
            recognition_cooldown: Min seconds between re-identifying same person
            min_face_size: Minimum face bbox size (pixels) to attempt recognition
            person_debounce_frames: Frames of no-person before declaring absent
            departure_frames: Frames of no-person before calling on_person_left
        """
        self.person_detector = person_detector
        self.face_detector = face_detector
        self.face_embedder = face_embedder
        self.face_matcher = face_matcher
        self.recognition_cooldown = recognition_cooldown
        self.min_face_size = min_face_size
        self.person_debounce_frames = person_debounce_frames
        self.departure_frames = departure_frames

        self.current_state = PipelineState.IDLE
        self._last_detection_time: float = 0
        self._current_person_embedding: Optional[np.ndarray] = None
        self._on_new_person_callback: Optional[Callable] = None
        self._on_known_person_callback: Optional[Callable] = None
        self._on_person_left_callback: Optional[Callable] = None
        self._no_person_count: int = 0

    def on_new_person(self, callback: Callable[[PipelineResult], Awaitable[None]]) -> None:
        """Register callback for when a new person is detected."""
        self._on_new_person_callback = callback

    def on_known_person(self, callback: Callable[[PipelineResult], Awaitable[None]]) -> None:
        """Register callback for when a known person is detected."""
        self._on_known_person_callback = callback

    def on_person_left(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Register callback for when the person leaves."""
        self._on_person_left_callback = callback

    async def process_frame(
        self,
        frame_data: FrameData,
        visitor_repo=None
    ) -> PipelineResult:
        """
        Process a single frame through the entire pipeline.
        Uses run_in_executor for blocking CV operations.

        Args:
            frame_data: Camera frame data
            visitor_repo: VisitorRepository for face matching (optional)

        Returns:
            PipelineResult with detection state and details
        """
        frame = frame_data.frame
        result = PipelineResult(
            state=PipelineState.IDLE,
            timestamp=frame_data.timestamp,
            frame=frame
        )

        # Step 1: Person Detection (YOLO - class 0 only)
        # Run in executor to avoid blocking event loop
        persons = await asyncio.get_event_loop().run_in_executor(
            None, self.person_detector.detect, frame
        )
        closest_person = self.person_detector.get_closest_person(persons)

        if closest_person is None:
            # No person detected - debounce
            self._no_person_count += 1
            if self._no_person_count >= self.departure_frames:
                if self.current_state != PipelineState.IDLE:
                    self.current_state = PipelineState.IDLE
                    self._current_person_embedding = None
                    if self._on_person_left_callback:
                        await self._on_person_left_callback()
            return result

        # Person found - reset absence counter
        self._no_person_count = 0
        result.person_detected = True
        result.detected_person = closest_person
        result.state = PipelineState.PERSON_DETECTED

        # Check recognition cooldown (don't re-process same person too quickly)
        current_time = time.time()
        if (
            self.current_state in (PipelineState.PERSON_IDENTIFIED, PipelineState.IN_CONVERSATION)
            and current_time - self._last_detection_time < self.recognition_cooldown
        ):
            result.state = self.current_state
            return result

        # Step 2: Face Detection (within person bounding box)
        # Run in executor to avoid blocking
        faces = await asyncio.get_event_loop().run_in_executor(
            None, self.face_detector.detect_faces_in_region, frame, closest_person.bbox
        )
        best_face = self.face_detector.get_best_face(faces)

        if best_face is None:
            result.state = PipelineState.PERSON_DETECTED
            return result

        # Check minimum face size
        face_w = best_face.bbox[2] - best_face.bbox[0]
        face_h = best_face.bbox[3] - best_face.bbox[1]
        if face_w < self.min_face_size or face_h < self.min_face_size:
            # Face too small for reliable recognition
            result.state = PipelineState.PERSON_DETECTED
            result.recognition = {"status": "poor_quality", "reason": "face_too_small"}
            return result

        result.face_detected = True
        result.detected_face = best_face
        result.state = PipelineState.FACE_DETECTED

        # Step 3: Face Embedding (ArcFace 512D)
        # Run in executor to avoid blocking
        embedding = await asyncio.get_event_loop().run_in_executor(
            None, self.face_embedder.get_embedding_from_face, frame, best_face
        )

        if embedding is None:
            result.recognition = {"status": "error", "reason": "embedding_failed"}
            return result

        # Check if this is the same person we already identified
        if self._current_person_embedding is not None:
            is_same, sim = FaceMatcher.is_same_person(
                embedding, self._current_person_embedding
            )
            if is_same:
                result.state = self.current_state
                return result

        # Step 4: Face Matching (against database)
        if visitor_repo is not None:
            match_result = await self.face_matcher.match_face(embedding, visitor_repo)
            result.match_result = match_result

            if match_result.status == MatchResult.MATCH_FOUND:
                result.state = PipelineState.PERSON_IDENTIFIED
                self.current_state = PipelineState.PERSON_IDENTIFIED
                self._current_person_embedding = embedding
                self._last_detection_time = current_time

                result.recognition = {
                    "status": "match_found",
                    "visitor_id": match_result.id,
                    "visitor_name": match_result.name,
                    "confidence": match_result.confidence
                }

                if self._on_known_person_callback:
                    await self._on_known_person_callback(result)

            elif match_result.status == MatchResult.NO_MATCH:
                result.state = PipelineState.NEW_PERSON
                self.current_state = PipelineState.NEW_PERSON
                self._current_person_embedding = embedding
                self._last_detection_time = current_time

                result.recognition = {
                    "status": "unknown",
                    "visitor_id": None,
                    "visitor_name": None,
                    "confidence": 0.0
                }

                if self._on_new_person_callback:
                    await self._on_new_person_callback(result)
            else:
                result.recognition = {
                    "status": match_result.status.value,
                    "visitor_id": None,
                    "visitor_name": None,
                    "confidence": 0.0
                }
        else:
            # No database available, treat as new
            result.state = PipelineState.NEW_PERSON
            result.recognition = {"status": "unknown", "reason": "no_database"}

        return result

    def reset(self) -> None:
        """Reset the pipeline state (e.g., after person leaves)."""
        self.current_state = PipelineState.IDLE
        self._current_person_embedding = None
        self._no_person_count = 0
        self._last_detection_time = 0
        logger.info("Vision pipeline reset")

    def set_state(self, state: PipelineState) -> None:
        """Manually set the pipeline state."""
        self.current_state = state
