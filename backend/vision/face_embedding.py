"""
Face Embedding module using InsightFace ArcFace.
Generates 512-dimensional normalized embeddings for face recognition.

IMPORTANT: This module shares the FaceAnalysis model instance with FaceDetector
to avoid loading the same large model twice in memory.
"""

import asyncio
import numpy as np
from typing import Optional, List, Tuple
import structlog

from vision.face_detection import DetectedFace

logger = structlog.get_logger()


class FaceEmbedder:
    """
    Generates face embeddings using InsightFace ArcFace model.
    Produces 512-dimensional normalized vectors for face comparison.

    Can share a FaceAnalysis instance with FaceDetector to save memory.
    """

    def __init__(self, model_name: str = "buffalo_l", shared_app=None):
        """
        Initialize the face embedder.

        Args:
            model_name: InsightFace model pack name
            shared_app: Pre-initialized FaceAnalysis instance (from FaceDetector)
                       If provided, avoids duplicate model loading.
        """
        self.model_name = model_name
        self.app = shared_app
        self._initialized = shared_app is not None
        self.embedding_size = 512

    async def initialize(self, shared_app=None) -> None:
        """
        Load the embedding model.
        If shared_app is provided, uses that instead of loading a new model.

        Args:
            shared_app: Optional pre-loaded FaceAnalysis instance
        """
        if shared_app is not None:
            self.app = shared_app
            self._initialized = True
            logger.info("Face embedder using shared model instance")
            return

        if self._initialized:
            return

        try:
            def _load():
                import insightface
                from insightface.app import FaceAnalysis

                app = FaceAnalysis(
                    name=self.model_name,
                    providers=['CPUExecutionProvider']
                )
                app.prepare(ctx_id=0, det_size=(640, 640))
                return app

            self.app = await asyncio.get_event_loop().run_in_executor(None, _load)
            self._initialized = True
            logger.info("Face embedder initialized (own model instance)", model=self.model_name)
        except Exception as e:
            logger.error("Failed to initialize face embedder", error=str(e))
            raise

    def get_embedding(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Get face embedding from a frame containing a single face.

        Args:
            frame: BGR image containing a face

        Returns:
            512-dimensional normalized numpy array or None
        """
        if not self._initialized:
            return None

        try:
            faces = self.app.get(frame)

            if not faces:
                return None

            # Get the best (highest confidence) face
            best_face = max(faces, key=lambda f: f.det_score)
            embedding = best_face.normed_embedding

            if embedding is not None:
                # Ensure normalization
                norm = np.linalg.norm(embedding)
                if norm > 0:
                    embedding = embedding / norm

            return embedding

        except Exception as e:
            logger.error("Error extracting face embedding", error=str(e))
            return None

    async def get_embedding_async(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Non-blocking embedding extraction."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.get_embedding, frame
        )

    def get_embedding_from_face(
        self,
        frame: np.ndarray,
        face: DetectedFace
    ) -> Optional[np.ndarray]:
        """
        Get face embedding using pre-detected face location.
        Uses IoU matching to correlate pre-detected face with InsightFace's detection.

        Args:
            frame: Full BGR frame
            face: DetectedFace object with bbox

        Returns:
            512-dimensional normalized numpy array or None
        """
        if not self._initialized:
            return None

        try:
            # Run InsightFace on the full frame for best quality embeddings
            faces = self.app.get(frame)

            if not faces:
                return None

            # Find the InsightFace detection that best matches our face bbox
            best_match = None
            best_iou = 0.0

            for detected in faces:
                det_bbox = tuple(map(int, detected.bbox))
                iou = self._calculate_iou(face.bbox, det_bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_match = detected

            if best_match is not None and best_iou > 0.3:
                embedding = best_match.normed_embedding
                if embedding is not None:
                    norm = np.linalg.norm(embedding)
                    if norm > 0:
                        embedding = embedding / norm
                return embedding

            return None

        except Exception as e:
            logger.error("Error extracting embedding from face", error=str(e))
            return None

    async def get_embedding_from_face_async(
        self,
        frame: np.ndarray,
        face: DetectedFace
    ) -> Optional[np.ndarray]:
        """Non-blocking face-specific embedding extraction."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.get_embedding_from_face, frame, face
        )

    def get_multiple_embeddings(
        self, frame: np.ndarray
    ) -> List[Tuple[tuple, np.ndarray]]:
        """
        Get embeddings for all faces in a frame.

        Args:
            frame: BGR image

        Returns:
            List of (bbox, embedding) tuples
        """
        if not self._initialized:
            return []

        try:
            faces = self.app.get(frame)
            results = []

            for face in faces:
                embedding = face.normed_embedding
                if embedding is not None:
                    norm = np.linalg.norm(embedding)
                    if norm > 0:
                        embedding = embedding / norm
                    bbox = tuple(map(int, face.bbox))
                    results.append((bbox, embedding))

            return results

        except Exception as e:
            logger.error("Error extracting multiple embeddings", error=str(e))
            return []

    def capture_high_quality_embedding(
        self,
        frame: np.ndarray,
        face: DetectedFace,
        min_confidence: float = 0.7
    ) -> Optional[np.ndarray]:
        """
        Capture a high-quality embedding suitable for registration.
        Applies stricter quality checks than regular matching.

        Args:
            frame: Full BGR frame
            face: DetectedFace with quality_score
            min_confidence: Minimum detection confidence for registration

        Returns:
            512-dimensional normalized embedding or None
        """
        # Check face quality
        if face.confidence < min_confidence:
            logger.info("Face confidence too low for registration",
                       confidence=face.confidence, min_required=min_confidence)
            return None

        if face.quality_score < 0.5:
            logger.info("Face quality too low for registration",
                       quality=face.quality_score)
            return None

        # Check face size (at least 100x100 for good embedding)
        if face.width < 100 or face.height < 100:
            logger.info("Face too small for registration",
                       width=face.width, height=face.height)
            return None

        # Extract embedding
        embedding = self.get_embedding_from_face(frame, face)

        if embedding is not None and embedding.shape[0] == self.embedding_size:
            logger.info("High-quality embedding captured for registration",
                       shape=embedding.shape)
            return embedding

        return None

    @staticmethod
    def _calculate_iou(bbox1: tuple, bbox2: tuple) -> float:
        """Calculate Intersection over Union between two bounding boxes."""
        x1 = max(bbox1[0], bbox2[0])
        y1 = max(bbox1[1], bbox2[1])
        x2 = min(bbox1[2], bbox2[2])
        y2 = min(bbox1[3], bbox2[3])

        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
        union = area1 + area2 - intersection

        if union == 0:
            return 0.0
        return intersection / union

    @property
    def initialized(self) -> bool:
        return self._initialized
