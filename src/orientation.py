"""Orientation detection and correction module using Tesseract OSD.

This module provides utilities to detect and correct image orientation
exclusively using Tesseract OSD. Rotation detection is NOT delegated to
any LLM — this is a hard requirement of the pipeline.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from PIL import Image, ImageOps
import pytesseract
from pytesseract import TesseractError

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS: set[str] = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tiff",
    ".tif",
    ".webp",
}

MIN_OSD_DIMENSION: int = 100
OSD_RESIZE_TARGET: int = 300

ROTATE_PATTERN: re.Pattern[str] = re.compile(r"Rotate:\s*(\d+)")

logger: logging.Logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def detect_rotation_angle(image: Image.Image) -> int:
    """Detect the rotation angle of an image using Tesseract OSD.

    Uses ``pytesseract.image_to_osd`` with ``--psm 0`` (orientation and
    script detection only) and parses the ``Rotate:`` field from the output.

    If the image is smaller than ``MIN_OSD_DIMENSION`` pixels in any
    dimension, it is upscaled to ``OSD_RESIZE_TARGET`` pixels on the
    shortest side before running OSD so that Tesseract can analyse it
    reliably.

    Image mode is normalised to RGB or L before the OSD call; any other
    mode (e.g. RGBA, P, CMYK) is converted to RGB first.

    Args:
        image: A PIL ``Image.Image`` object to analyse.

    Returns:
        The detected clockwise rotation angle in degrees: 0, 90, 180 or
        270.  Returns 0 if Tesseract fails or the field is absent.
    """
    img: Image.Image = image

    # Normalise colour mode
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # Upscale tiny images so Tesseract OSD has enough pixels to work with
    width, height = img.size
    if width < MIN_OSD_DIMENSION or height < MIN_OSD_DIMENSION:
        scale: float = OSD_RESIZE_TARGET / min(width, height)
        new_size: tuple[int, int] = (int(width * scale), int(height * scale))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        logger.debug(
            "Image upscaled from %dx%d to %dx%d for OSD",
            width,
            height,
            new_size[0],
            new_size[1],
        )

    try:
        osd_output: str = pytesseract.image_to_osd(img, config="--psm 0")
        match: re.Match[str] | None = ROTATE_PATTERN.search(osd_output)
        if match:
            angle: int = int(match.group(1))
            logger.info("Tesseract OSD detected rotation angle: %d°", angle)
            return angle
        logger.warning("OSD output did not contain a 'Rotate:' field")
        return 0
    except TesseractError as exc:
        logger.warning("TesseractError during OSD detection: %s", exc)
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected error during OSD detection: %s", exc)
        return 0


def correct_orientation(image: Image.Image, angle: int) -> Image.Image:
    """Rotate an image to correct its orientation based on the OSD angle.

    Tesseract OSD reports the angle by which the text *is already rotated*
    from upright.  To restore the image to the correct orientation the
    inverse rotation ``(360 - angle)`` must be applied.

    Args:
        image: A PIL ``Image.Image`` to correct.
        angle: The rotation angle detected by ``detect_rotation_angle``.
            Expected values: 0, 90, 180, 270.

    Returns:
        A new ``Image.Image`` with the orientation corrected, or the
        original image unchanged when ``angle`` is 0.
    """
    if angle == 0:
        logger.debug("No rotation correction needed (angle=0)")
        return image

    correction: int = 360 - angle
    corrected: Image.Image = image.rotate(correction, expand=True)
    logger.info(
        "Applied rotation correction: -%d° (OSD angle was %d°)",
        angle,
        angle,
    )
    return corrected


def process_image_orientation(image_path: str | Path) -> tuple[Image.Image, int]:
    """Full orientation pipeline for a single image file.

    Steps:
    1. Validate the file extension against ``SUPPORTED_EXTENSIONS``.
    2. Open the image with PIL.
    3. Apply EXIF transpose (``ImageOps.exif_transpose``) to handle camera
       metadata rotation before running Tesseract.
    4. Detect rotation angle with ``detect_rotation_angle``.
    5. Correct orientation with ``correct_orientation``.

    Args:
        image_path: Path to the image file (``str`` or ``pathlib.Path``).

    Returns:
        A tuple ``(corrected_image, angle_applied)`` where
        ``corrected_image`` is the orientation-corrected PIL image and
        ``angle_applied`` is the OSD angle that was used for correction.

    Raises:
        ValueError: If the file extension is not in ``SUPPORTED_EXTENSIONS``.
        FileNotFoundError: If the file does not exist.
    """
    path: Path = Path(image_path)

    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")

    extension: str = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported image format '{extension}'. "
            f"Supported formats: {sorted(SUPPORTED_EXTENSIONS)}"
        )

    logger.debug("Opening image: %s", path.name)
    image: Image.Image = Image.open(path)

    # Apply EXIF orientation metadata before OSD so Tesseract sees the image
    # in the orientation the camera intended, not the raw sensor orientation.
    transposed: Image.Image | None = ImageOps.exif_transpose(image)
    if transposed is not None:
        image = transposed

    angle: int = detect_rotation_angle(image)
    corrected: Image.Image = correct_orientation(image, angle)

    logger.info(
        "Processed orientation for '%s': angle=%d°",
        path.name,
        angle,
    )
    return corrected, angle


def get_image_files(input_dir: str | Path) -> list[Path]:
    """Return a sorted, deduplicated list of supported image files in a directory.

    Searches for files whose suffix (case-insensitive) matches
    ``SUPPORTED_EXTENSIONS``.  Both lowercase and uppercase extensions are
    discovered by globbing ``*.*`` and filtering by suffix.

    Args:
        input_dir: Path to the directory to scan (``str`` or
            ``pathlib.Path``).

    Returns:
        A sorted list of ``pathlib.Path`` objects for each supported image
        file found.

    Raises:
        FileNotFoundError: If ``input_dir`` does not exist or is not a
            directory.
    """
    directory: Path = Path(input_dir)

    if not directory.exists() or not directory.is_dir():
        raise FileNotFoundError(
            f"Input directory not found or is not a directory: {directory}"
        )

    seen: set[Path] = set()
    for candidate in directory.glob("*.*"):
        if candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
            seen.add(candidate)

    files: list[Path] = sorted(seen)
    logger.info(
        "Found %d supported image file(s) in '%s'",
        len(files),
        directory,
    )
    return files
