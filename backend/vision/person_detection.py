"""
Person Detection using YOLO (You Only Look Once).
Detects only humans/persons in the frame — ignores chairs, bags, laptops, etc.
All inference is run via asyncio.to_thread to avoid blocking the event loop.
"""

import asyncio
import numpy as np
from typing import List, Optional, Tuple
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


@dataclass
class DetectedPerson:
    """Represents a detected person in a frame."""
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    confidence: float
    class_id: int
    center: Tuple[int, int]
    area: int

    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]


class PersonDetector:
    """
    YOLO-based person detector.
    Only detects humans/persons (COCO class 0), ignoring all other objects.
    """

    # COCO class ID for "person" is 0
    PERSON_CLASS_ID = 0

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        confidence_threshold: float = 0.5,
        device: str = "cpu"
    ):
        self.confidence_threshold = confidence_threshold
        self.device = device
        self.model = None
        self.model_path = model_path
        self._initialized = False

    async def initialize(self) -> None:
        """Load the YOLO model (non-blocking)."""
        try:
            def _load():
                from ultralytics import YOLO
                return YOLO(self.model_path)

            self.model = await asyncio.get_event_loop().run_in_executor(None, _load)
            self._initialized = True
            logger.info(
                "Person detector initialized",
                model=self.model_path,
                device=self.device
            )
        except Exception as e:
            logger.error("Failed to initialize person detector", error=str(e))
            raise

    def detect(self, frame: np.ndarray) -> List[DetectedPerson]:
        """
        Detect persons in a video frame (synchronous - call via run_in_executor
        from async context if needed, or use detect_async).

        Args:
            frame: BGR image as numpy array

        Returns:
            List of DetectedPerson objects sorted by area (closest first)
        """
        if not self._initialized:
            return []

        try:
            results = self.model(
                frame,
                conf=self.confidence_threshold,
                classes=[self.PERSON_CLASS_ID],  # Only detect persons
                device=self.device,
                verbose=False
            )

            detections = []
            for result in results:
                if result.boxes is None:
                    continue

                for box in result.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    confidence = float(box.conf[0])
                    class_id = int(box.cls[0])

                    center_x = (x1 + x2) // 2
                    center_y = (y1 + y2) // 2
                    area = (x2 - x1) * (y2 - y1)

                    detections.append(DetectedPerson(
                        bbox=(x1, y1, x2, y2),
                        confidence=confidence,
                        class_id=class_id,
                        center=(center_x, center_y),
                        area=area
                    ))

            # Sort by area descending (largest = closest to camera)
            detections.sort(key=lambda d: d.area, reverse=True)
            return detections

        except Exception as e:
            logger.error("Error during person detection", error=str(e))
            return []

    async def detect_async(self, frame: np.ndarray) -> List[DetectedPerson]:
        """Non-blocking person detection (runs inference in thread pool)."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.detect, frame
        )

    def is_person_at_entrance(
        self,
        detections: List[DetectedPerson],
        frame_width: int,
        frame_height: int,
        min_area_ratio: float = 0.02
    ) -> bool:
        """
        Determine if a person is close enough to camera to be at the entrance.

        Args:
            detections: List of detected persons
            frame_width: Width of the frame
            frame_height: Height of the frame
            min_area_ratio: Minimum bbox area relative to frame area

        Returns:
            True if a person is at the entrance
        """
        if not detections:
            return False

        frame_area = frame_width * frame_height
        for det in detections:
            area_ratio = det.area / frame_area
            if area_ratio >= min_area_ratio:
                return True

        return False

    def get_closest_person(
        self, detections: List[DetectedPerson]
    ) -> Optional[DetectedPerson]:
        """Get the person closest to the camera (largest bounding box)."""
        if not detections:
            return None
        return detections[0]  # Already sorted by area

    @property
    def initialized(self) -> bool:
        return self._initialized
