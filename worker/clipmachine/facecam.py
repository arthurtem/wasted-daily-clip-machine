"""Detect streamer facecams and produce a layout for vertical rendering."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
import numpy as np
from numpy.typing import NDArray

from clipmachine.config import FACECAM_OVERRIDES

logger = logging.getLogger(__name__)

SAMPLE_FRAME_COUNT = 15
MIN_DETECTION_CONFIDENCE = 0.6
CLUSTER_DISTANCE_FRACTION = 0.08
MIN_CLUSTER_FRAME_FRACTION = 0.35
FULL_FACE_AREA_FRACTION = 0.06
CAM_WIDTH_FACTOR = 4.2
CAM_HEIGHT_FACTOR = 2.8
EDGE_SNAP_FRACTION = 0.12
REFINE_BAND_FRACTION = 0.15
MAX_FACECAM_EDGE_DISTANCE = 0.30
CROP_REGIONS = (
    (0.0, 0.0, 0.55, 0.65),
    (0.45, 0.0, 0.55, 0.65),
    (0.0, 0.35, 0.55, 0.65),
    (0.45, 0.35, 0.55, 0.65),
)
MIN_VERIFIED_FACE_FRACTION = 0.5
CORNER_OVERRIDES = frozenset(
    {"top-left", "top-right", "bottom-left", "bottom-right"}
)

Box = tuple[int, int, int, int]
DetectedFace = tuple[int, Box, float]
Frame = NDArray[np.uint8]


class FacecamError(RuntimeError):
    """Raised when the facecam layout cannot be detected."""


@dataclass(frozen=True)
class Layout:
    """The detected or overridden facecam layout for one clip."""

    kind: str
    cam_box: Box | None
    confidence: float
    debug_image_path: str | None = None
    source: str = "auto"
    face_ratio: float | None = None
    needs_review: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Serialize the layout for the clips.layout JSONB column."""
        return {
            "kind": self.kind,
            "cam_box": list(self.cam_box) if self.cam_box else None,
            "confidence": round(self.confidence, 4),
            "debug_image_path": self.debug_image_path,
            "source": self.source,
            "face_ratio": (
                round(self.face_ratio, 4) if self.face_ratio is not None else None
            ),
            "needs_review": self.needs_review,
        }


def _even(value: float | int) -> int:
    """Round down to the nearest positive even integer."""
    number = int(value)
    return max(2, number - number % 2)


def preset_cam_box(override: str, frame_w: int, frame_h: int) -> Box:
    """Return the preset facecam box for a corner override."""
    width = _even(frame_w * 0.28)
    height = _even(frame_h * 0.30)
    if override == "top-left":
        return (0, 0, width, height)
    if override == "top-right":
        return (frame_w - width, 0, width, height)
    if override == "bottom-left":
        return (0, frame_h - height, width, height)
    if override == "bottom-right":
        return (frame_w - width, frame_h - height, width, height)
    raise FacecamError(f"unknown corner override {override!r}")


def decide_kind(matched_frames: int, total_frames: int, avg_area_ratio: float) -> str:
    """Apply the facecam decision rules to cluster statistics."""
    if total_frames <= 0:
        return "no_cam"
    if matched_frames / total_frames < MIN_CLUSTER_FRAME_FRACTION:
        return "no_cam"
    if avg_area_ratio > FULL_FACE_AREA_FRACTION:
        return "full_face"
    return "cam_top"


def _face_center(box: Box) -> tuple[float, float]:
    """Return the center of a face box."""
    x, y, w, h = box
    return (x + w / 2.0, y + h / 2.0)


def fractional_cam_box(
    box: tuple[float, float, float, float], frame_w: int, frame_h: int
) -> Box:
    """Convert a fractional facecam box to clamped even pixel coordinates."""
    x_fraction, y_fraction, w_fraction, h_fraction = box
    width = _even(min(w_fraction * frame_w, float(frame_w)))
    height = _even(min(h_fraction * frame_h, float(frame_h)))
    x = int(round(x_fraction * frame_w))
    y = int(round(y_fraction * frame_h))
    x = max(0, min(x, frame_w - width))
    y = max(0, min(y, frame_h - height))
    return (x, y, width, height)


def build_cam_box(
    avg_face: tuple[float, float, float, float], frame_w: int, frame_h: int
) -> Box:
    """Expand an average face box into a clamped, corner-snapped cam box."""
    face_x, face_y, face_w, face_h = avg_face
    center_x = face_x + face_w / 2.0
    center_y = face_y + face_h / 2.0
    cam_w = _even(min(face_w * CAM_WIDTH_FACTOR, float(frame_w)))
    cam_h = _even(min(face_h * CAM_HEIGHT_FACTOR, float(frame_h)))
    left = int(round(center_x - cam_w / 2.0))
    top = int(round(center_y - cam_h / 2.0))
    left = max(0, min(left, frame_w - cam_w))
    top = max(0, min(top, frame_h - cam_h))
    right = left + cam_w
    bottom = top + cam_h

    if left <= frame_w * EDGE_SNAP_FRACTION:
        left = 0
    elif frame_w - right <= frame_w * EDGE_SNAP_FRACTION:
        left = frame_w - cam_w
    if top <= frame_h * EDGE_SNAP_FRACTION:
        top = 0
    elif frame_h - bottom <= frame_h * EDGE_SNAP_FRACTION:
        top = frame_h - cam_h
    return (left, top, cam_w, cam_h)


def _find(parent: list[int], index: int) -> int:
    """Find the union-find root for an index."""
    while parent[index] != index:
        parent[index] = parent[parent[index]]
        index = parent[index]
    return index


def _union(parent: list[int], left: int, right: int) -> None:
    """Merge two union-find sets."""
    left_root = _find(parent, left)
    right_root = _find(parent, right)
    if left_root != right_root:
        parent[right_root] = left_root


def cluster_faces(
    faces: list[DetectedFace], frame_width: int
) -> list[list[DetectedFace]]:
    """Group faces whose centers are within 8% of the frame width."""
    if not faces:
        return []
    threshold = frame_width * CLUSTER_DISTANCE_FRACTION
    parent = list(range(len(faces)))
    centers = [_face_center(face[1]) for face in faces]
    for left in range(len(faces)):
        for right in range(left + 1, len(faces)):
            dx = centers[left][0] - centers[right][0]
            dy = centers[left][1] - centers[right][1]
            if (dx * dx + dy * dy) ** 0.5 <= threshold:
                _union(parent, left, right)

    groups: dict[int, list[DetectedFace]] = {}
    for index, face in enumerate(faces):
        groups.setdefault(_find(parent, index), []).append(face)
    return list(groups.values())


def largest_cluster(
    faces: list[DetectedFace], frame_width: int
) -> list[DetectedFace]:
    """Return the cluster with the most faces."""
    clusters = cluster_faces(faces, frame_width)
    if not clusters:
        return []
    return max(clusters, key=len)


def _sample_frames(
    video_path: Path, count: int = SAMPLE_FRAME_COUNT
) -> tuple[list[Frame], int, int]:
    """Read evenly spaced frames from a video."""
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise FacecamError(f"cannot open video: {video_path}")
    try:
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        frame_w = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        frame_h = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        frames: list[Frame] = []
        if total > 0:
            positions = sorted(
                {
                    int(round(value))
                    for value in np.linspace(0, total - 1, min(count, total))
                }
            )
            for position in positions:
                capture.set(cv2.CAP_PROP_POS_FRAMES, position)
                ok, frame = capture.read()
                if ok:
                    frames.append(frame)
        else:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                frames.append(frame)
            if frames:
                positions = sorted(
                    {
                        int(round(value))
                        for value in np.linspace(
                            0, len(frames) - 1, min(count, len(frames))
                        )
                    }
                )
                frames = [frames[index] for index in positions]
        if not frames:
            raise FacecamError(f"cannot read frames from: {video_path}")
        if frame_w <= 0 or frame_h <= 0:
            frame_h, frame_w = frames[0].shape[:2]
        return frames, frame_w, frame_h
    finally:
        capture.release()


def _iou(left: Box, right: Box) -> float:
    """Return intersection-over-union for two boxes."""
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    x1 = max(lx, rx)
    y1 = max(ly, ry)
    x2 = min(lx + lw, rx + rw)
    y2 = min(ly + lh, ry + rh)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    intersection = (x2 - x1) * (y2 - y1)
    union = lw * lh + rw * rh - intersection
    return intersection / union if union else 0.0


def _detect_faces(
    frames: list[Frame], frame_w: int, frame_h: int
) -> list[DetectedFace]:
    """Detect faces in full frames and corner/quadrant crops.

    Facecam overlays are often too small for full-frame detection, so each
    sampled frame is also scanned with four overlapping crops and boxes are
    mapped back into full-frame coordinates.
    """
    faces: list[DetectedFace] = []
    regions: list[tuple[int, int, int, int]] = [(0, 0, frame_w, frame_h)]
    for x_fraction, y_fraction, w_fraction, h_fraction in CROP_REGIONS:
        x0 = int(round(x_fraction * frame_w))
        y0 = int(round(y_fraction * frame_h))
        x1 = min(frame_w, int(round((x_fraction + w_fraction) * frame_w)))
        y1 = min(frame_h, int(round((y_fraction + h_fraction) * frame_h)))
        if x1 - x0 >= 32 and y1 - y0 >= 32:
            regions.append((x0, y0, x1 - x0, y1 - y0))

    for model_selection in (0, 1):
        with mp.solutions.face_detection.FaceDetection(
            model_selection=model_selection,
            min_detection_confidence=MIN_DETECTION_CONFIDENCE,
        ) as detector:
            for index, frame in enumerate(frames):
                for x0, y0, region_w, region_h in regions:
                    crop = frame[y0 : y0 + region_h, x0 : x0 + region_w]
                    if crop.size == 0:
                        continue
                    result = detector.process(
                        cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                    )
                    for detection in result.detections or []:
                        bbox = detection.location_data.relative_bounding_box
                        rx1 = int(round(bbox.xmin * region_w)) + x0
                        ry1 = int(round(bbox.ymin * region_h)) + y0
                        rx2 = int(round((bbox.xmin + bbox.width) * region_w)) + x0
                        ry2 = int(round((bbox.ymin + bbox.height) * region_h)) + y0
                        rx1 = max(0, min(rx1, frame_w - 1))
                        ry1 = max(0, min(ry1, frame_h - 1))
                        rx2 = max(rx1 + 1, min(rx2, frame_w))
                        ry2 = max(ry1 + 1, min(ry2, frame_h))
                        box = (rx1, ry1, rx2 - rx1, ry2 - ry1)
                        score = (
                            float(detection.score[0])
                            if detection.score
                            else 0.0
                        )
                        duplicate = any(
                            face[0] == index and _iou(face[1], box) > 0.5
                            for face in faces
                        )
                        if not duplicate:
                            faces.append((index, box, score))
    return faces



def _cluster_frame_count(cluster: list[DetectedFace]) -> int:
    """Return the number of distinct sampled frames in a cluster."""
    return len({face[0] for face in cluster})


def _cluster_area_ratio(cluster: list[DetectedFace], frame_w: int, frame_h: int) -> float:
    """Return the average face area ratio for a cluster."""
    if not cluster:
        return 0.0
    area = sum(face[1][2] * face[1][3] for face in cluster) / len(cluster)
    return area / float(frame_w * frame_h)


def _cluster_edge_distance(cluster: list[DetectedFace], frame_w: int, frame_h: int) -> float:
    """Return normalized distance from the cluster center to the nearest edge."""
    if not cluster:
        return 1.0
    cx = sum(face[1][0] + face[1][2] / 2 for face in cluster) / len(cluster)
    cy = sum(face[1][1] + face[1][3] / 2 for face in cluster) / len(cluster)
    left = cx / frame_w
    right = 1.0 - left
    top = cy / frame_h
    bottom = 1.0 - top
    return max(0.0, min(left, right, top, bottom))


def choose_cam_cluster(
    clusters: list[list[DetectedFace]], frame_w: int, frame_h: int
) -> list[DetectedFace]:
    """Prefer a persistent, small, edge-adjacent face cluster (a facecam)."""
    if not clusters:
        return []
    candidates = [
        cluster
        for cluster in clusters
        if _cluster_area_ratio(cluster, frame_w, frame_h)
        <= FULL_FACE_AREA_FRACTION
        and _cluster_edge_distance(cluster, frame_w, frame_h)
        <= MAX_FACECAM_EDGE_DISTANCE
    ]
    if not candidates:
        return []
    return max(
        candidates,
        key=lambda cluster: (
            _cluster_frame_count(cluster),
            -_cluster_edge_distance(cluster, frame_w, frame_h),
        ),
    )



def _snap_side(value: int, candidates: list[int], tolerance: float) -> int:
    """Return the nearest candidate line within tolerance, else the value."""
    nearby = [line for line in candidates if abs(line - value) <= tolerance]
    if not nearby:
        return value
    return min(nearby, key=lambda line: abs(line - value))


def refine_cam_box(
    cam_box: Box, median_frame: Frame, frame_w: int, frame_h: int
) -> Box:
    """Snap each cam box side to the closest strong Canny/Hough line."""
    if median_frame.size == 0:
        return cam_box
    gray = cv2.cvtColor(median_frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=60,
        minLineLength=max(8, int(min(frame_w, frame_h) * 0.2)),
        maxLineGap=8,
    )
    if lines is None:
        return cam_box

    vertical: list[int] = []
    horizontal: list[int] = []
    for line in lines.reshape(-1, 4):
        x1, y1, x2, y2 = (int(value) for value in line)
        if abs(x2 - x1) <= 2:
            vertical.append(int(round((x1 + x2) / 2)))
        if abs(y2 - y1) <= 2:
            horizontal.append(int(round((y1 + y2) / 2)))

    x, y, w, h = cam_box
    left = _snap_side(x, vertical, frame_w * REFINE_BAND_FRACTION)
    right = _snap_side(x + w, vertical, frame_w * REFINE_BAND_FRACTION)
    top = _snap_side(y, horizontal, frame_h * REFINE_BAND_FRACTION)
    bottom = _snap_side(y + h, horizontal, frame_h * REFINE_BAND_FRACTION)

    if right - left < max(2, w // 2):
        left, right = x, x + w
    if bottom - top < max(2, h // 2):
        top, bottom = y, y + h

    left = max(0, min(left, frame_w - 2))
    top = max(0, min(top, frame_h - 2))
    new_w = _even(min(right - left, frame_w - left))
    new_h = _even(min(bottom - top, frame_h - top))
    left = min(left - left % 2, frame_w - new_w)
    top = min(top - top % 2, frame_h - new_h)
    return (left, top, new_w, new_h)


def _write_debug(
    frame: Frame,
    faces: list[DetectedFace],
    cam_box: Box | None,
    kind: str,
    path: Path,
) -> None:
    """Write a debug frame with yellow face boxes and a green cam box."""
    image = frame.copy()
    for _, (face_x, face_y, face_w, face_h), _ in faces:
        cv2.rectangle(
            image,
            (face_x, face_y),
            (face_x + face_w, face_y + face_h),
            (0, 255, 255),
            2,
        )
    if cam_box is not None:
        x, y, w, h = cam_box
        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 3)
    cv2.putText(
        image,
        kind,
        (12, 44),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image)


def verify_cam_box(frames: list[Frame], cam_box: Box) -> float:
    """Return the share of sampled frames with a face detected inside the cam box."""
    if not frames:
        return 0.0
    x, y, width, height = cam_box
    hits = 0
    with mp.solutions.face_detection.FaceDetection(
        model_selection=0,
        min_detection_confidence=MIN_DETECTION_CONFIDENCE,
    ) as detector:
        for frame in frames:
            crop = frame[y : y + height, x : x + width]
            if crop.size == 0:
                continue
            result = detector.process(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
            if result.detections:
                hits += 1
    return hits / len(frames)


def detect_layout(
    video_path: Path,
    override: str | None,
    refine_cam_edges: bool = True,
    box_override: tuple[float, float, float, float] | None = None,
) -> Layout:
    """Detect the facecam layout for a video, honoring configured overrides."""
    if override is not None and override not in FACECAM_OVERRIDES:
        raise FacecamError(f"unknown facecam override {override!r}")
    if override is not None and box_override is not None:
        raise FacecamError("set either override or box_override, not both")

    video_path = Path(video_path)
    frames, frame_w, frame_h = _sample_frames(video_path)
    middle = frames[len(frames) // 2]
    debug_path = video_path.parent / "detect.jpg"
    clip_id = video_path.parent.name

    if box_override is not None:
        cam_box = fractional_cam_box(box_override, frame_w, frame_h)
        face_ratio = verify_cam_box(frames, cam_box)
        needs_review = face_ratio < MIN_VERIFIED_FACE_FRACTION
        _write_debug(middle, [], cam_box, "cam_top", debug_path)
        logger.info(
            "clip %s layout=cam_top (facecam_box %s) face_ratio=%.2f review=%s",
            clip_id,
            cam_box,
            face_ratio,
            needs_review,
        )
        return Layout(
            "cam_top",
            cam_box,
            1.0,
            str(debug_path),
            "box",
            face_ratio,
            needs_review,
        )

    if override == "none":
        _write_debug(middle, [], None, "no_cam", debug_path)
        logger.info("clip %s layout=no_cam (override none)", clip_id)
        return Layout(
            "no_cam", None, 1.0, str(debug_path), "none"
        )

    if override is not None:
        cam_box = preset_cam_box(override, frame_w, frame_h)
        face_ratio = verify_cam_box(frames, cam_box)
        needs_review = face_ratio < MIN_VERIFIED_FACE_FRACTION
        _write_debug(middle, [], cam_box, "cam_top", debug_path)
        logger.info(
            "clip %s layout=cam_top (override %s) face_ratio=%.2f review=%s",
            clip_id,
            override,
            face_ratio,
            needs_review,
        )
        return Layout(
            "cam_top",
            cam_box,
            1.0,
            str(debug_path),
            "corner",
            face_ratio,
            needs_review,
        )

    faces = _detect_faces(frames, frame_w, frame_h)
    clusters = cluster_faces(faces, frame_w)
    cluster = choose_cam_cluster(clusters, frame_w, frame_h)
    total = len(frames)
    matched_frames = _cluster_frame_count(cluster)
    confidence = matched_frames / total if total else 0.0

    if not cluster and clusters:
        fallback = max(clusters, key=_cluster_frame_count)
        fallback_frames = _cluster_frame_count(fallback)
        fallback_area = _cluster_area_ratio(fallback, frame_w, frame_h)
        if (
            fallback_frames / total >= MIN_CLUSTER_FRAME_FRACTION
            and fallback_area > FULL_FACE_AREA_FRACTION
        ):
            cluster = fallback
            matched_frames = fallback_frames
            confidence = fallback_frames / total
            logger.info(
                "clip %s using full_face fallback cluster frames=%d area=%.3f",
                clip_id,
                fallback_frames,
                fallback_area,
            )

    if cluster:
        avg_x = sum(face[1][0] for face in cluster) / len(cluster)
        avg_y = sum(face[1][1] for face in cluster) / len(cluster)
        avg_w = sum(face[1][2] for face in cluster) / len(cluster)
        avg_h = sum(face[1][3] for face in cluster) / len(cluster)
        avg_area_ratio = (avg_w * avg_h) / float(frame_w * frame_h)
        kind = decide_kind(matched_frames, total, avg_area_ratio)
    else:
        avg_x = avg_y = avg_w = avg_h = 0.0
        avg_area_ratio = 0.0
        kind = "no_cam"

    cam_box = (
        build_cam_box((avg_x, avg_y, avg_w, avg_h), frame_w, frame_h)
        if kind == "cam_top"
        else None
    )
    if cam_box is not None and refine_cam_edges:
        median_frame = np.median(np.stack(frames), axis=0).astype(np.uint8)
        cam_box = refine_cam_box(cam_box, median_frame, frame_w, frame_h)

    face_ratio: float | None = None
    needs_review = False
    if cam_box is not None:
        face_ratio = verify_cam_box(frames, cam_box)
        needs_review = face_ratio < MIN_VERIFIED_FACE_FRACTION

    _write_debug(middle, faces, cam_box, kind, debug_path)
    logger.info(
        "clip %s layout=%s faces=%d cluster=%d confidence=%.2f cam_box=%s "
        "face_ratio=%s review=%s",
        clip_id,
        kind,
        len(faces),
        len(cluster),
        confidence,
        cam_box,
        f"{face_ratio:.2f}" if face_ratio is not None else "n/a",
        needs_review,
    )
    return Layout(
        kind,
        cam_box,
        confidence,
        str(debug_path),
        "auto",
        face_ratio,
        needs_review,
    )
