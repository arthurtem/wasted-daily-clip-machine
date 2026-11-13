"""Transcribe clips and build ASS captions for the vertical canvas."""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import cv2

from clipmachine.facecam import Layout, _sample_frames

logger = logging.getLogger(__name__)

WHISPER_CACHE_ENV = "WHISPER_CACHE_DIR"
DEFAULT_WHISPER_CACHE = (
    Path(__file__).resolve().parents[2] / ".cache" / "whisper"
)
MODEL_NAME = "small"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"
PAUSE_BREAK_SECONDS = 0.4
WORDS_PER_LINE = 3
ASS_FONT = "DejaVu Sans"
ASS_FONT_SIZE = 78
ASS_OUTLINE = 6
CAM_TOP_CAPTION_Y = 640
DEFAULT_CAPTION_Y = 1350
YELLOW = "&H00FFFF&"
WHITE = "&HFFFFFF&"
OCR_SAMPLE_FRAMES = 15
OCR_MIN_WORDS = 2
OCR_MIN_FRAMES = 2
OCR_MIN_CONFIDENCE = 60.0
OCR_BAND = (0.22, 0.80, 0.78, 0.98)

_MODEL: Any | None = None


def whisper_cache_dir() -> Path:
    """Resolve the faster-whisper model cache directory."""
    value = os.environ.get(WHISPER_CACHE_ENV, "").strip()
    return Path(value) if value else DEFAULT_WHISPER_CACHE


def get_model() -> Any:
    """Return a memoized faster-whisper model, downloading it into the cache."""
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel

        cache = whisper_cache_dir()
        cache.mkdir(parents=True, exist_ok=True)
        logger.info(
            "loading faster-whisper model=%s device=%s compute=%s cache=%s",
            MODEL_NAME,
            DEVICE,
            COMPUTE_TYPE,
            cache,
        )
        _MODEL = WhisperModel(
            MODEL_NAME,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
            download_root=str(cache),
        )
    return _MODEL


def transcribe(video_path: Path) -> list[dict[str, Any]]:
    """Transcribe a clip into word-timed tokens with faster-whisper."""
    model = get_model()
    segments, _info = model.transcribe(
        str(video_path), word_timestamps=True
    )
    words: list[dict[str, Any]] = []
    for segment in segments:
        for word in segment.words or []:
            text = str(word.word).strip()
            if not text:
                continue
            words.append(
                {
                    "word": text,
                    "start": float(word.start),
                    "end": float(word.end),
                }
            )
    logger.info(
        "clip %s transcribed %d words",
        Path(video_path).parent.name,
        len(words),
    )
    return words


def _looks_like_captions(word_counts: Sequence[int]) -> bool:
    """Decide whether OCR found subtitle-like text in enough frames."""
    qualifying = sum(1 for count in word_counts if count >= OCR_MIN_WORDS)
    return qualifying >= OCR_MIN_FRAMES


def _count_ocr_words(image: Any) -> int:
    """Count confident OCR words in a grayscale frame."""
    import pytesseract

    data = pytesseract.image_to_data(
        image,
        config="--psm 6",
        output_type=pytesseract.Output.DICT,
    )
    texts = data.get("text", [])
    confidences = data.get("conf", [])
    count = 0
    for text, confidence in zip(texts, confidences):
        cleaned = str(text).strip()
        if len(cleaned) < 2:
            continue
        if cleaned.isupper() and len(cleaned) >= 3:
            continue
        try:
            score = float(confidence)
        except (TypeError, ValueError):
            continue
        if score >= OCR_MIN_CONFIDENCE:
            count += 1
    return count


def has_burned_captions(video_path: Path) -> bool:
    """Heuristically detect burned-in captions by OCRing the bottom band."""
    if shutil.which("tesseract") is None:
        logger.warning(
            "tesseract is not installed; cannot detect burned-in captions"
        )
        return False

    try:
        frames, frame_w, frame_h = _sample_frames(
            Path(video_path), count=OCR_SAMPLE_FRAMES
        )
    except Exception as exc:
        logger.warning("caption OCR could not sample %s: %s", video_path, exc)
        return False

    left = int(frame_w * OCR_BAND[0])
    right = int(frame_w * OCR_BAND[2])
    top = int(frame_h * OCR_BAND[1])
    bottom = int(frame_h * OCR_BAND[3])
    counts: list[int] = []
    try:
        for frame in frames:
            crop = frame[top:bottom, left:right]
            if crop.size == 0:
                counts.append(0)
                continue
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            enlarged = cv2.resize(
                gray,
                None,
                fx=2.0,
                fy=2.0,
                interpolation=cv2.INTER_CUBIC,
            )
            counts.append(_count_ocr_words(enlarged))
    except Exception as exc:
        logger.warning("caption OCR failed for %s: %s", video_path, exc)
        return False

    detected = _looks_like_captions(counts)
    logger.info(
        "clip %s burned captions OCR counts=%s detected=%s",
        Path(video_path).parent.name,
        counts,
        detected,
    )
    return detected


def group_words(
    words: Sequence[Mapping[str, Any]],
) -> list[list[Mapping[str, Any]]]:
    """Group words into lines of 2-3, breaking on pauses longer than 0.4s."""
    lines: list[list[Mapping[str, Any]]] = []
    current: list[Mapping[str, Any]] = []
    for index, word in enumerate(words):
        current.append(word)
        if index + 1 < len(words):
            next_start = float(words[index + 1]["start"])
            pause = next_start - float(word["end"])
        else:
            pause = 0.0
        if (
            len(current) >= WORDS_PER_LINE
            or pause > PAUSE_BREAK_SECONDS
            or index + 1 == len(words)
        ):
            lines.append(current)
            current = []
    return lines


def _clean_word(value: Any) -> str:
    """Remove ASS control characters and collapse whitespace in a word."""
    text = str(value).replace("{", "").replace("}", "").replace("\\", "")
    return " ".join(text.split())


def _timestamp(seconds: float) -> str:
    """Format seconds as an ASS h:mm:ss.cc timestamp."""
    centiseconds = max(0, int(round(seconds * 100)))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{fraction:02d}"


def _line_text(
    line: Sequence[Mapping[str, Any]], active_index: int
) -> str:
    """Render one caption line with the active word in yellow."""
    parts: list[str] = []
    for index, word in enumerate(line):
        text = _clean_word(word["word"])
        if not text:
            continue
        if index == active_index:
            parts.append(f"{{\\c{YELLOW}}}{text}{{\\c{WHITE}}}")
        else:
            parts.append(text)
    return " ".join(parts)


def build_ass_text(
    words: Sequence[Mapping[str, Any]], layout: Layout
) -> str:
    """Build the ASS subtitle document for the sampled word timings."""
    caption_y = (
        CAM_TOP_CAPTION_Y
        if layout.kind == "cam_top"
        else DEFAULT_CAPTION_Y
    )
    events: list[str] = []
    for line in group_words(words):
        if not line:
            continue
        line_end = max(
            float(line[-1]["end"]), float(line[0]["start"]) + 0.1
        )
        for index, word in enumerate(line):
            start = float(word["start"])
            end = (
                float(line[index + 1]["start"])
                if index + 1 < len(line)
                else line_end
            )
            if end <= start:
                end = start + 0.1
            text = _line_text(line, index)
            if not text:
                continue
            events.append(
                "Dialogue: 0,"
                f"{_timestamp(start)},{_timestamp(end)},Caption,,0,0,0,,"
                f"{{\\an5\\pos(540,{caption_y})}}{text}"
            )

    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            (
                "Format: Name, Fontname, Fontsize, PrimaryColour, "
                "SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
                "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
                "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
                "MarginV, Encoding"
            ),
            (
                f"Style: Caption,{ASS_FONT},{ASS_FONT_SIZE},&H00FFFFFF,"
                f"&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,"
                f"1,{ASS_OUTLINE},0,5,0,0,0,1"
            ),
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            *events,
            "",
        ]
    )


def build_ass(
    words: Sequence[Mapping[str, Any]],
    layout: Layout,
    out_path: Path,
) -> Path | None:
    """Write an .ass file, or return None when there is no speech."""
    if not words:
        logger.info("no transcript words; skipping captions")
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_ass_text(words, layout), encoding="utf-8")
    logger.info("wrote captions %s", out_path)
    return out_path
