"""
Face Matching module.
Compares face embeddings against the database to identify visitors.
"""

import numpy as np
from typing import Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import structlog

logger = structlog.get_logger()


class MatchResult(str, Enum):
    """Result status of face matching."""
    NO_PERSON = "no_person"
    NO_FACE = "no_face"
    POOR_QUALITY = "poor_quality"
    MULTIPLE_FACES = "multiple_faces"
    UNKNOWN = "unknown"
    MATCH_FOUND = "match_found"
    NO_MATCH = "no_match"
    ERROR = "error"


@dataclass
class FaceMatchResult:
    """Result of a face match operation."""
    status: MatchResult
    visitor: Any = None  # Visitor model object or None
    visitor_id: Optional[str] = None
    visitor_name: Optional[str] = None
    visit_count: int = 0
    confidence: float = 0.0
    embedding: Optional[np.ndarray] = None
    message: str = ""

    @property
    def name(self) -> Optional[str]:
        """Get visitor name from either visitor object or direct field."""
        if self.visitor and hasattr(self.visitor, 'name'):
            return self.visitor.name
        return self.visitor_name

    @property
    def id(self) -> Optional[str]:
        """Get visitor ID from either visitor object or direct field."""
        if self.visitor and hasattr(self.visitor, 'visitor_id'):
            return self.visitor.visitor_id
        return self.visitor_id


class FaceMatcher:
    """
    Face matching service.
    Compares face embeddings against the visitor database using cosine similarity.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.6,
        high_confidence_threshold: float = 0.8
    ):
        self.similarity_threshold = similarity_threshold
        self.high_confidence_threshold = high_confidence_threshold

    async def match_face(
        self,
        embedding: np.ndarray,
        visitor_repo
    ) -> FaceMatchResult:
        """
        Match a face embedding against the database.

        Args:
            embedding: 512-dimensional face embedding
            visitor_repo: VisitorRepository instance for database lookup

        Returns:
            FaceMatchResult with match status and visitor info
        """
        if embedding is None:
            return FaceMatchResult(
                status=MatchResult.NO_FACE,
                message="No face embedding provided"
            )

        try:
            # Search database for matching faces
            matches = await visitor_repo.search_by_face(
                embedding=embedding,
                threshold=self.similarity_threshold,
                limit=3
            )

            if not matches:
                logger.info("No face match found - new visitor")
                return FaceMatchResult(
                    status=MatchResult.NO_MATCH,
                    embedding=embedding,
                    message="No matching face found in database"
                )

            # Get the best match
            best_visitor, best_similarity = matches[0]

            # Determine confidence level
            if best_similarity >= self.high_confidence_threshold:
                confidence_msg = "high confidence"
            else:
                confidence_msg = "moderate confidence"

            logger.info(
                "Face match found",
                visitor_id=best_visitor.visitor_id,
                name=best_visitor.name,
                similarity=best_similarity,
                confidence=confidence_msg
            )

            # Update last seen
            await visitor_repo.update_last_seen(best_visitor.visitor_id)

            return FaceMatchResult(
                status=MatchResult.MATCH_FOUND,
                visitor=best_visitor,
                visitor_id=best_visitor.visitor_id,
                visitor_name=best_visitor.name,
                visit_count=best_visitor.visit_count,
                confidence=best_similarity,
                embedding=embedding,
                message=f"Matched with {confidence_msg}: {best_visitor.name}"
            )

        except Exception as e:
            logger.error("Error during face matching", error=str(e))
            return FaceMatchResult(
                status=MatchResult.ERROR,
                embedding=embedding,
                message=f"Error during matching: {str(e)}"
            )

    @staticmethod
    def compute_similarity(
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        """Compute cosine similarity between two normalized embeddings."""
        norm1 = embedding1 / (np.linalg.norm(embedding1) + 1e-10)
        norm2 = embedding2 / (np.linalg.norm(embedding2) + 1e-10)
        similarity = float(np.dot(norm1, norm2))
        return max(0.0, min(1.0, similarity))

    @staticmethod
    def is_same_person(
        embedding1: np.ndarray,
        embedding2: np.ndarray,
        threshold: float = 0.6
    ) -> Tuple[bool, float]:
        """Quick check if two embeddings belong to the same person."""
        similarity = FaceMatcher.compute_similarity(embedding1, embedding2)
        return similarity >= threshold, similarity
