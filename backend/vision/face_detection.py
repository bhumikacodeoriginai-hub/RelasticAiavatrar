"""
Face Detection module using InsightFace.
Detects faces, extracts landmarks, estimates quality.
Shares model instance with FaceEmbedder to avoid duplicate loading.
"""

import asyncio
import numpy as np
from typing import List, Optional, Tuple
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


@dataclass
class DetectedFace:
    """Represents a detected face in a frame."""
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    confidence: float
    landmarks: Optional[np.ndarray] = None  # 5 facial landmarks
    face_image: Optional[np.ndarray] = None  # Cropped face region
    aligned_face: Optional[np.ndarray] = None  # Aligned face for embedding
    age: Optional[int] = None
    gender: Optional[str] = None
    quality_score: float = 1.0  # Estimated quality (0-1)

    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]

    @property
    def center(self) -> Tuple[int, int]:
        return (
            (self.bbox[0] + self.bbox[2]) // 2,
            (self.bbox[1] + self.bbox[3]) // 2
        )

    @property
    def area(self) -> int:
        return self.width * self.height


class FaceDetector:
    """
    Face detection using InsightFace (RetinaFace backbone).
    Provides high-accuracy face detection with landmark extraction
    and face quality estimation.
    """

    def __init__(
        self,
        model_name: str = "buffalo_l",
        det_size: Tuple[int, int] = (640, 640),
        det_threshold: float = 0.5,
        max_faces: int = 10,
        min_face_quality: float = 0.3,
    ):
        self.model_name = model_name
        self.det_size = det_size
        self.det_threshold = det_threshold
        self.max_faces = max_faces
        self.min_face_quality = min_face_quality
        self.app = None
        self._initialized = False

    async def initialize(self) -> None:
        """Load the InsightFace model (non-blocking)."""
        try:
            def _load():
                import insightface
                from insightface.app import FaceAnalysis

                app = FaceAnalysis(
                    name=self.model_name,
                    providers=['CPUExecutionProvider']
                )
                app.prepare(
                    ctx_id=0,
                    det_size=self.det_size,
                    det_thresh=self.det_threshold
                )
                return app

            self.app = await asyncio.get_event_loop().run_in_executor(None, _load)
            self._initialized = True
            logger.info(
                "Face detector initialized",
                model=self.model_name,
                det_size=self.det_size
            )
        except Exception as e:
            logger.error("Failed to initialize face detector", error=str(e))
            raise

    def get_model(self):
        """Get the underlying InsightFace model (for sharing with FaceEmbedder)."""
        return self.app

    def detect_faces(self, frame: np.ndarray) -> List[DetectedFace]:
        """
        Detect all faces in a frame (synchronous).

        Args:
            frame: BGR image as numpy array

        Returns:
            List of DetectedFace objects sorted by confidence
        """
        if not self._initialized:
            return []

        try:
            faces = self.app.get(frame)
            faces = faces[:self.max_faces]

            detections = []
            h, w = frame.shape[:2]

            for face in faces:
                bbox = tuple(map(int, face.bbox))
                x1, y1, x2, y2 = bbox

                # Clamp coordinates to frame
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(w, x2)
                y2 = min(h, y2)

                # Skip degenerate boxes
                if x2 <= x1 or y2 <= y1:
                    continue

                # Estimate face quality
                quality = self._estimate_quality(frame, (x1, y1, x2, y2), face)

                # Crop face region
                face_image = frame[y1:y2, x1:x2].copy() if (y2 - y1) > 0 and (x2 - x1) > 0 else None

                detected = DetectedFace(
                    bbox=(x1, y1, x2, y2),
                    confidence=float(face.det_score),
                    landmarks=face.kps if hasattr(face, 'kps') else None,
                    face_image=face_image,
                    age=int(face.age) if hasattr(face, 'age') and face.age is not None else None,
                    gender="male" if hasattr(face, 'gender') and face.gender == 1 else "female" if hasattr(face, 'gender') and face.gender is not None else None,
                    quality_score=quality
                )
                detections.append(detected)

            # Sort by confidence
            detections.sort(key=lambda d: d.confidence, reverse=True)
            return detections

        except Exception as e:
            logger.error("Error during face detection", error=str(e))
            return []

    async def detect_faces_async(self, frame: np.ndarray) -> List[DetectedFace]:
        """Non-blocking face detection."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.detect_faces, frame
        )

    def detect_faces_in_region(
        self,
        frame: np.ndarray,
        region: Tuple[int, int, int, int]
    ) -> List[DetectedFace]:
        """
        Detect faces within a specific region (e.g., person bounding box).
        Coordinates in returned DetectedFace objects are in full-frame space.

        Args:
            frame: Full frame
            region: (x1, y1, x2, y2) region to search

        Returns:
            List of DetectedFace objects with coordinates in full frame space
        """
        x1, y1, x2, y2 = region
        h, w = frame.shape[:2]

        # Clamp region to frame
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w, x2)
        y2 = min(h, y2)

        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return []

        # Detect faces in ROI
        faces = self.detect_faces(roi)

        # Adjust coordinates back to full frame space
        adjusted_faces = []
        for face in faces:
            adj_bbox = (
                face.bbox[0] + x1,
                face.bbox[1] + y1,
                face.bbox[2] + x1,
                face.bbox[3] + y1,
            )
            adjusted_landmarks = None
            if face.landmarks is not None:
                adjusted_landmarks = face.landmarks + np.array([x1, y1])

            adjusted = DetectedFace(
                bbox=adj_bbox,
                confidence=face.confidence,
                landmarks=adjusted_landmarks,
                face_image=face.face_image,
                age=face.age,
                gender=face.gender,
                quality_score=face.quality_score
            )
            adjusted_faces.append(adjusted)

        return adjusted_faces

    def get_best_face(
        self,
        faces: List[DetectedFace],
        min_quality: Optional[float] = None
    ) -> Optional[DetectedFace]:
        """
        Get the best quality face from detections.
        Filters by minimum quality and returns highest confidence.

        Args:
            faces: List of detected faces
            min_quality: Override minimum quality threshold

        Returns:
            Best DetectedFace or None
        """
        if not faces:
            return None

        quality_threshold = min_quality if min_quality is not None else self.min_face_quality

        # Filter by quality
        quality_faces = [f for f in faces if f.quality_score >= quality_threshold]

        if not quality_faces:
            # If no faces pass quality filter, return best confidence anyway
            # but log a warning
            logger.debug("No faces pass quality threshold, using best confidence")
            return faces[0]

        return quality_faces[0]  # Already sorted by confidence

    def _estimate_quality(
        self,
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
        face_obj
    ) -> float:
        """
        Estimate face quality based on size, blur, and landmarks.

        Returns:
            Quality score between 0.0 and 1.0
        """
        x1, y1, x2, y2 = bbox
        face_w = x2 - x1
        face_h = y2 - y1

        quality = 1.0

        # Penalize very small faces (likely too far away)
        if face_w < 60 or face_h < 60:
            quality *= 0.5
        elif face_w < 100 or face_h < 100:
            quality *= 0.75

        # Check for blur using Laplacian variance
        try:
            import cv2
            face_region = frame[y1:y2, x1:x2]
            if face_region.size > 0:
                gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
                laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
                # Low variance = blurry
                if laplacian_var < 50:
                    quality *= 0.3
                elif laplacian_var < 100:
                    quality *= 0.6
                elif laplacian_var < 200:
                    quality *= 0.8
        except Exception:
            pass

        # Check face angle using landmarks (if available)
        if hasattr(face_obj, 'kps') and face_obj.kps is not None:
            try:
                kps = face_obj.kps
                # 5 landmarks: left_eye, right_eye, nose, left_mouth, right_mouth
                if len(kps) >= 5:
                    left_eye = kps[0]
                    right_eye = kps[1]
                    nose = kps[2]

                    # Check horizontal symmetry (frontal vs profile)
                    eye_center_x = (left_eye[0] + right_eye[0]) / 2
                    nose_offset = abs(nose[0] - eye_center_x) / max(face_w, 1)

                    # Large offset = profile view
                    if nose_offset > 0.2:
                        quality *= 0.5
                    elif nose_offset > 0.1:
                        quality *= 0.8
            except Exception:
                pass

        # Detection confidence affects quality
        det_score = float(face_obj.det_score) if hasattr(face_obj, 'det_score') else 1.0
        quality *= min(1.0, det_score / 0.5)  # Scale: 0.5 conf → 1.0 multiplier

        return max(0.0, min(1.0, quality))

    @property
    def initialized(self) -> bool:
        return self._initialized
