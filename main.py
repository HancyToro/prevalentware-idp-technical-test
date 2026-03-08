"""Receipt extractor — CLI entry point.

Processes all supported images in an input directory through a two-step
pipeline:

1. **Orientation detection & correction** — exclusively via Tesseract OSD
   (``src.orientation``).
2. **Data extraction** — via the OpenCode Zen vision API
   (``src.extractor``).

Results are consolidated into a single Excel file (``src.excel_writer``).

Usage example::

    python main.py --input-dir ./images --output-file ./output/receipts_extracted.xlsx

Run ``python main.py --help`` for the full list of options.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from src.excel_writer import generate_excel
from src.extractor import MODELS, extract_receipt_data
from src.orientation import get_image_files, process_image_orientation

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

_LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"


def _setup_logging(verbose: bool) -> None:
    """Configure root logging for the pipeline.

    Args:
        verbose: When ``True`` sets the root level to ``DEBUG``; otherwise
            uses ``INFO``.
    """
    level: int = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        datefmt=_LOG_DATE_FORMAT,
    )


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    """Build and return the parsed CLI arguments.

    Returns:
        An :class:`argparse.Namespace` with attributes: ``input_dir``,
        ``output_file``, ``model``, ``verbose``, and ``timeout``.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "Extract structured data from receipt images using OpenCode Zen "
            "and export the results to an Excel file."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--input-dir",
        default="./images",
        metavar="DIR",
        help="Directory containing the receipt images to process.",
    )
    parser.add_argument(
        "--output-file",
        default="./output/receipts_extracted.xlsx",
        metavar="FILE",
        help="Destination path for the generated Excel file.",
    )
    parser.add_argument(
        "--model",
        default="sonnet-4.6",
        choices=list(MODELS.keys()),
        help="OpenCode Zen model to use for data extraction.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG-level logging output.",
    )
    parser.add_argument(
        "--timeout",
        default=120.0,
        type=float,
        metavar="SECONDS",
        help="HTTP timeout in seconds for each API call.",
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def main() -> int:
    """Run the full receipt extraction pipeline.

    Returns:
        Exit code:

        * ``0`` — all images processed successfully.
        * ``1`` — fatal error (missing API key, no images found, Excel write
          failure, or every image failed).
        * ``2`` — partial success (at least one image succeeded and at least
          one failed).
    """
    args: argparse.Namespace = _parse_args()
    _setup_logging(args.verbose)
    logger: logging.Logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # 1. Load environment variables
    # ------------------------------------------------------------------
    load_dotenv()

    api_key: str | None = os.environ.get("OPENCODE_API_KEY")
    if not api_key:
        logger.error(
            "OPENCODE_API_KEY is not set. "
            "Add it to your .env file or export it as an environment variable."
        )
        return 1

    # ------------------------------------------------------------------
    # 2. Discover images
    # ------------------------------------------------------------------
    try:
        image_files = get_image_files(args.input_dir)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1

    if not image_files:
        logger.error(
            "No supported image files found in '%s'.", args.input_dir
        )
        return 1

    total: int = len(image_files)
    logger.info("Found %d image(s) to process in '%s'.", total, args.input_dir)
    logger.info("Model: %s  |  Timeout: %.0fs", args.model, args.timeout)

    # ------------------------------------------------------------------
    # 3. Process each image
    # ------------------------------------------------------------------
    all_records: list[dict[str, object]] = []
    error_count: int = 0
    t_pipeline_start: float = time.time()

    for idx, image_path in enumerate(image_files, start=1):
        logger.info(
            "[%d/%d] Processing '%s'", idx, total, image_path.name
        )
        t_image_start: float = time.time()

        try:
            # Step 1 — Orientation detection & correction
            logger.info("  Step 1: Detecting orientation with Tesseract OSD...")
            corrected_image, angle = process_image_orientation(image_path)
            logger.info("  Orientation angle detected: %d°", angle)

            # Step 2 — Data extraction via OpenCode Zen
            logger.info(
                "  Step 2: Extracting data via OpenCode Zen (%s)...",
                args.model,
            )
            data: dict[str, object]
            elapsed: float
            data, elapsed = extract_receipt_data(
                api_key,
                corrected_image,
                args.model,
                args.timeout,
            )

            # Attach metadata fields
            data["source_file"] = image_path.name
            data["rotation_angle_applied"] = angle

            all_records.append(data)

            image_elapsed: float = time.time() - t_image_start
            logger.info(
                "  Done in %.2fs  (API: %.2fs | rotation: %d°)",
                image_elapsed,
                elapsed,
                angle,
            )

        except Exception as exc:  # noqa: BLE001
            error_count += 1
            logger.error(
                "  Failed to process '%s': %s", image_path.name, exc
            )
            # Keep a placeholder row so every image appears in the output
            error_record: dict[str, object] = {
                "source_file": image_path.name,
                "rotation_angle_applied": None,
                "_error": str(exc),
            }
            all_records.append(error_record)

    # ------------------------------------------------------------------
    # 4. Write Excel output
    # ------------------------------------------------------------------
    if not all_records:
        logger.error("No records to write — aborting.")
        return 1

    output_path: Path
    try:
        output_path = generate_excel(all_records, args.output_file)
        logger.info("Excel written to '%s'.", output_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to write Excel file: %s", exc)
        return 1

    # ------------------------------------------------------------------
    # 5. Summary
    # ------------------------------------------------------------------
    total_elapsed: float = time.time() - t_pipeline_start
    successful: int = total - error_count
    avg_time: float = total_elapsed / total if total > 0 else 0.0

    separator: str = "=" * 57
    print(f"\n{separator}")
    print("  Receipt Extraction — Summary")
    print(separator)
    print(f"  Total images   : {total}")
    print(f"  Successful     : {successful}")
    print(f"  Errors         : {error_count}")
    print(f"  Total time     : {total_elapsed:.1f}s")
    print(f"  Avg per image  : {avg_time:.1f}s")
    print(f"  Output file    : {output_path}")
    print(f"{separator}\n")

    # ------------------------------------------------------------------
    # 6. Exit code
    # ------------------------------------------------------------------
    if error_count == 0:
        return 0
    if error_count < total:
        return 2
    return 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(main())
