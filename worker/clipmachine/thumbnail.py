"""Compose branded 9:16 YouTube Shorts thumbnails from a rendered frame."""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

SIZE = (1080, 1920)
MARGIN = 72
ACCENT = (225, 29, 46)
BRAND = "WASTED DAILY"
MAX_HOOK_CHARS = 90

FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a bold font at a size, falling back to Pillow's default."""
    for path in FONT_PATHS:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize and center-crop an image to fill the target size."""
    target_w, target_h = size
    scale = max(target_w / image.width, target_h / image.height)
    resized = image.resize(
        (max(target_w, int(image.width * scale)),
         max(target_h, int(image.height * scale))),
        Image.LANCZOS,
    )
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def _scrim(size: tuple[int, int], start: int, end: int, peak: int) -> Image.Image:
    """Build a vertical black gradient mask from transparent to peak alpha."""
    mask = Image.new("L", (1, size[1]))
    span = max(1, end - start)
    for y in range(size[1]):
        if y <= start:
            alpha = 0
        else:
            alpha = min(peak, int((y - start) / span * peak))
        mask.putpixel((0, y), alpha)
    return mask.resize(size)


def _wrap(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    """Wrap text into lines that fit the given width."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_hook(
    draw: ImageDraw.ImageDraw, hook: str, max_width: int, max_lines: int
) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, list[str]]:
    """Pick the largest font size whose wrapped hook fits the space."""
    for size in (96, 88, 80, 72, 64, 56):
        font = _font(size)
        lines = _wrap(draw, hook, font, max_width)
        if len(lines) <= max_lines:
            return font, lines
    return _font(56), _wrap(draw, hook, _font(56), max_width)[:max_lines]


def _clean_hook(hook: str) -> str:
    """Trim a clip title to a thumbnail-friendly hook."""
    cleaned = " ".join(hook.split())
    if len(cleaned) > MAX_HOOK_CHARS:
        cleaned = cleaned[:MAX_HOOK_CHARS].rstrip(" .,!?-")
    return cleaned


def compose(source: Path, out_path: Path, hook: str) -> Path:
    """Compose a branded 9:16 thumbnail and return the output path."""
    image = Image.open(source).convert("RGB")
    image = _cover(image, SIZE)

    bottom = _scrim(SIZE, 1000, SIZE[1], 215)
    top = _scrim(SIZE, 0, 320, 120).transpose(Image.FLIP_TOP_BOTTOM)
    image.paste(Image.new("RGB", SIZE, (0, 0, 0)), (0, 0), bottom)
    image.paste(Image.new("RGB", SIZE, (0, 0, 0)), (0, 0), top)

    draw = ImageDraw.Draw(image)
    brand_font = _font(42)
    brand_pad = 18
    brand_width = int(draw.textlength(BRAND, font=brand_font)) + brand_pad * 2
    brand_height = 62
    draw.rounded_rectangle(
        (MARGIN, MARGIN, MARGIN + brand_width, MARGIN + brand_height),
        radius=10,
        fill=ACCENT,
    )
    draw.text(
        (MARGIN + brand_pad, MARGIN + brand_height // 2),
        BRAND,
        font=brand_font,
        fill="white",
        anchor="lm",
    )

    hook = _clean_hook(hook)
    if hook:
        max_width = SIZE[0] - MARGIN * 2
        font, lines = _fit_hook(draw, hook, max_width, 4)
        line_height = int(font.size * 1.15) if hasattr(font, "size") else 66
        total_height = line_height * len(lines)
        start_y = SIZE[1] - MARGIN - total_height
        draw.rectangle(
            (MARGIN, start_y - 10, MARGIN + 10, SIZE[1] - MARGIN),
            fill=ACCENT,
        )
        text_x = MARGIN + 34
        for index, line in enumerate(lines):
            draw.text(
                (text_x, start_y + index * line_height),
                line,
                font=font,
                fill="white",
                stroke_width=3,
                stroke_fill=(0, 0, 0),
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, format="JPEG", quality=90, optimize=True, progressive=True)
    logger.info(
        "composed thumbnail %s (%dx%d, %d bytes)",
        out_path,
        SIZE[0],
        SIZE[1],
        out_path.stat().st_size,
    )
    return out_path
