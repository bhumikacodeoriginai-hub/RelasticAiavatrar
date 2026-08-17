"""
Vision module for AI Avatar Receptionist.
Handles person detection, face detection, face embedding, and face matching.
"""

from vision.person_detection import PersonDetector, DetectedPerson
from vision.face_detection import FaceDetector, DetectedFace
from vision.face_embedding import FaceEmbedder
from vision.face_matching import FaceMatcher, FaceMatchResult, MatchResult
from vision.pipeline import VisionPipeline, PipelineState, PipelineResult
from vision.camera import CameraService, MockCameraService, FrameData, CameraStatus

__all__ = [
    "PersonDetector",
    "DetectedPerson",
    "FaceDetector",
    "DetectedFace",
    "FaceEmbedder",
    "FaceMatcher",
    "FaceMatchResult",
    "MatchResult",
    "VisionPipeline",
    "PipelineState",
    "PipelineResult",
    "CameraService",
    "MockCameraService",
    "FrameData",
    "CameraStatus",
]
