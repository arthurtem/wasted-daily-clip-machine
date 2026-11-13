"""Tests for the facecam layout decision rules and box geometry."""

from __future__ import annotations

import pytest

from clipmachine.facecam import (
    FacecamError,
    build_cam_box,
    decide_kind,
    largest_cluster,
    preset_cam_box,
)


def test_three_of_fifteen_faces_is_no_cam() -> None:
    """Faces in under half the frames mean there is no facecam."""
    assert decide_kind(3, 15, 0.01) == "no_cam"


def test_fourteen_small_faces_is_cam_top() -> None:
    """A steady small face is a boxed facecam."""
    assert decide_kind(14, 15, 0.01) == "cam_top"


def test_large_faces_is_full_face() -> None:
    """Faces covering more than 6% of the frame are a full-screen camera."""
    assert decide_kind(14, 15, 0.12) == "full_face"


def test_half_coverage_boundary() -> None:
    """Exactly half of the frames is enough to keep looking for a cam."""
    assert decide_kind(7, 15, 0.01) == "no_cam"
    assert decide_kind(8, 15, 0.01) == "cam_top"


def test_corner_box_snaps_to_top_left_edges() -> None:
    """An expanded box near the top-left corner snaps to both edges."""
    assert build_cam_box((100, 100, 100, 100), 1920, 1080) == (0, 0, 260, 240)


def test_centered_box_is_not_snapped() -> None:
    """A face away from the frame edges keeps its expanded box."""
    assert build_cam_box((860, 490, 100, 100), 1920, 1080) == (780, 420, 260, 240)


def test_right_edge_is_snapped() -> None:
    """A box whose right edge is near the frame edge snaps right."""
    assert build_cam_box((1700, 490, 100, 100), 1920, 1080) == (1660, 420, 260, 240)


def test_box_is_clamped_inside_the_frame() -> None:
    """An oversized expansion is clamped to the frame bounds."""
    assert build_cam_box((1800, 980, 100, 100), 1920, 1080) == (1660, 840, 260, 240)


def test_preset_boxes_for_corners() -> None:
    """Corner overrides use 28% width by 30% height presets."""
    assert preset_cam_box("top-left", 1920, 1080) == (0, 0, 536, 324)
    assert preset_cam_box("top-right", 1920, 1080) == (1384, 0, 536, 324)
    assert preset_cam_box("bottom-left", 1920, 1080) == (0, 756, 536, 324)
    assert preset_cam_box("bottom-right", 1920, 1080) == (1384, 756, 536, 324)


def test_unknown_corner_override_raises() -> None:
    """An unsupported override is rejected."""
    with pytest.raises(FacecamError, match="unknown corner override"):
        preset_cam_box("middle", 1920, 1080)


def test_largest_cluster_separates_outliers() -> None:
    """Steady faces cluster together and a far-away face is excluded."""
    faces = [
        (index, (990 + index, 490, 100, 100), 0.9) for index in range(5)
    ]
    faces.append((5, (50, 50, 100, 100), 0.95))

    cluster = largest_cluster(faces, 1920)

    assert len(cluster) == 5
    assert all(face[1][0] >= 990 for face in cluster)


def test_missing_detections_are_treated_as_no_faces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MediaPipe can return detections=None for a frame with no face."""
    import numpy as np

    from clipmachine import facecam

    class FakeDetector:
        """Detector returning no detections."""

        def process(self, frame: object) -> object:
            """Return a result whose detections attribute is None."""

            class Result:
                detections = None

            return Result()

        def __enter__(self) -> FakeDetector:
            """Enter the detector context."""
            return self

        def __exit__(self, *exc_info: object) -> bool:
            """Leave the detector context."""
            return False

    monkeypatch.setattr(
        facecam.mp.solutions.face_detection,
        "FaceDetection",
        lambda **kwargs: FakeDetector(),
    )
    frame = np.zeros((16, 16, 3), dtype=np.uint8)

    assert facecam._detect_faces([frame], 16, 16) == []


def test_fractional_cam_box_converts_to_pixels() -> None:
    """Fractional boxes become clamped, even pixel boxes."""
    from clipmachine.facecam import fractional_cam_box

    assert fractional_cam_box((0.0, 0.25, 0.2, 0.25), 1920, 1080) == (
        0,
        270,
        384,
        270,
    )


def test_verify_cam_box_counts_faces_in_crop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verification reports the share of sampled frames with a face in the box."""
    import numpy as np

    from clipmachine import facecam

    class FakeDetector:
        """Detector that finds a face every other frame."""

        def __init__(self) -> None:
            """Start with no processed frames."""
            self.calls = 0

        def process(self, frame: object) -> object:
            """Return alternating detections."""
            self.calls += 1

            class Result:
                detections = (
                    [object()] if self.calls % 2 else []
                )

            return Result()

        def __enter__(self) -> FakeDetector:
            """Enter the detector context."""
            return self

        def __exit__(self, *exc_info: object) -> bool:
            """Leave the detector context."""
            return False

    monkeypatch.setattr(
        facecam.mp.solutions.face_detection,
        "FaceDetection",
        lambda **kwargs: FakeDetector(),
    )
    frames = [
        np.zeros((100, 100, 3), dtype=np.uint8) for _ in range(4)
    ]

    assert facecam.verify_cam_box(frames, (0, 0, 50, 50)) == 0.5


def test_layout_serializes_verification_fields() -> None:
    """Stored layout JSON includes the override source and verification result."""
    from clipmachine.facecam import Layout

    payload = Layout(
        "cam_top", (0, 0, 100, 100), 0.9, None, "box", 0.75, False
    ).as_dict()

    assert payload["source"] == "box"
    assert payload["face_ratio"] == 0.75
    assert payload["needs_review"] is False
