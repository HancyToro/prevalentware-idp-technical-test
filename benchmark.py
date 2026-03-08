"""Benchmark script — compares Claude Sonnet 4.6 vs an OSS model on OpenCode Zen.

Runs the full extraction pipeline (orientation correction + LLM extraction)
on every image in the input directory using two models side-by-side, then
produces three artefacts in the output directory:

* ``results.csv``              — per-image comparison table with field-agreement column.
* ``metrics_summary.json``     — aggregated metrics for both models.
* ``results_<model>.json`` × 2 — full per-image records for each model.

Usage::

    python benchmark.py --input-dir ./images --oss-model qwen3-coder --output-dir ./benchmark
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from dotenv import load_dotenv

from src.extractor import MODELS, extract_receipt_data
from src.orientation import get_image_files, process_image_orientation

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

CORE_FIELDS: list[str] = [
    "ciudad",
    "fecha",
    "numero_recibo",
    "pagado_a",
    "valor",
    "concepto",
    "valor_en_letras",
    "tipo_documento",
]

ALL_FIELDS: list[str] = [
    "ciudad",
    "fecha",
    "numero_recibo",
    "pagado_a",
    "valor",
    "concepto",
    "valor_en_letras",
    "firma_recibido",
    "cc_o_nit",
    "codigo",
    "aprobado",
    "direccion",
    "vendedor",
    "telefono_fax",
    "forma_pago",
    "cantidad",
    "detalle",
    "valor_unitario",
    "valor_total",
    "total_documento",
    "tipo_documento",
    "plantilla_detectada",
]

SONNET_MODEL: str = "sonnet-4.6"
OSS_MODELS: list[str] = [k for k in MODELS if k != SONNET_MODEL]

_LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

logger: logging.Logger = logging.getLogger(__name__)


def _to_float(value: object) -> float:
    """Safely convert an ``object``-typed value to ``float``.

    Args:
        value: Any value stored as ``object`` in a result dict.

    Returns:
        The numeric float value, or ``0.0`` if conversion fails.
    """
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def _setup_logging(verbose: bool) -> None:
    """Configure root logging.

    Args:
        verbose: When ``True`` sets root level to ``DEBUG``; otherwise ``INFO``.
    """
    level: int = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format=_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    """Build and return the parsed CLI arguments.

    Returns:
        An :class:`argparse.Namespace` with attributes: ``input_dir``,
        ``oss_model``, ``output_dir``, ``verbose``, and ``timeout``.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="benchmark.py",
        description=(
            "Compare Claude Sonnet 4.6 vs an OSS model on the same receipt "
            "images and generate a performance report."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input-dir",
        default="./images",
        metavar="DIR",
        help="Directory containing the receipt images.",
    )
    parser.add_argument(
        "--oss-model",
        default="qwen3-coder",
        choices=OSS_MODELS,
        help="Open-source model to benchmark against sonnet-4.6.",
    )
    parser.add_argument(
        "--output-dir",
        default="./benchmark",
        metavar="DIR",
        help="Directory where benchmark reports will be saved.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG-level logging.",
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
# Extraction runner
# ---------------------------------------------------------------------------


def run_extraction(
    api_key: str,
    image_files: list[Path],
    model_name: str,
    timeout: float = 120.0,
) -> list[dict[str, object]]:
    """Run the full pipeline on every image for a single model.

    For each image the function:

    1. Detects and corrects orientation via Tesseract OSD.
    2. Sends the corrected image to the OpenCode Zen API.
    3. Records success/failure, timing, and field-fill counts.

    Args:
        api_key: OpenCode Zen API key.
        image_files: Ordered list of image paths to process.
        model_name: Key into ``MODELS`` (e.g. ``"sonnet-4.6"``).
        timeout: Per-request HTTP timeout in seconds.

    Returns:
        A list of result dicts — one per image — each containing:
        ``source_file``, ``model``, ``success``, ``elapsed_seconds``,
        ``error``, ``fields_extracted``, ``core_fields_extracted``, and
        ``extracted_data``.
    """
    total: int = len(image_files)
    results: list[dict[str, object]] = []

    logger.info("── Running extraction with model '%s' (%d images) ──", model_name, total)

    for idx, image_path in enumerate(image_files, start=1):
        logger.info("[%d/%d] [%s] '%s'", idx, total, model_name, image_path.name)

        record: dict[str, object] = {
            "source_file": image_path.name,
            "model": model_name,
            "success": False,
            "elapsed_seconds": 0.0,
            "error": None,
            "fields_extracted": 0,
            "core_fields_extracted": 0,
            "extracted_data": {},
        }

        try:
            logger.debug("  Detecting orientation...")
            corrected_image, angle = process_image_orientation(image_path)

            logger.debug("  Extracting data (angle=%d°)...", angle)
            data, elapsed = extract_receipt_data(
                api_key, corrected_image, model_name, timeout
            )
            data["source_file"] = image_path.name
            data["rotation_angle_applied"] = angle

            fields_extracted: int = sum(
                1 for f in ALL_FIELDS if data.get(f) is not None
            )
            core_fields_extracted: int = sum(
                1 for f in CORE_FIELDS if data.get(f) is not None
            )

            record.update(
                {
                    "success": True,
                    "elapsed_seconds": round(elapsed, 3),
                    "fields_extracted": fields_extracted,
                    "core_fields_extracted": core_fields_extracted,
                    "extracted_data": data,
                }
            )
            logger.info(
                "  OK — %.2fs | fields: %d/%d | core: %d/%d",
                elapsed,
                fields_extracted,
                len(ALL_FIELDS),
                core_fields_extracted,
                len(CORE_FIELDS),
            )

        except Exception as exc:  # noqa: BLE001
            record["error"] = str(exc)
            logger.error("  FAILED — %s", exc)

        results.append(record)

    return results


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------


def compute_metrics(
    results: list[dict[str, object]],
    model_name: str,
) -> dict[str, object]:
    """Compute aggregated performance metrics for one model's results.

    Args:
        results: Output of :func:`run_extraction` for a single model.
        model_name: Display name used in the returned dict.

    Returns:
        A dict containing success/failure counts, timing statistics,
        field-fill rates, and failure patterns.
    """
    successful: list[dict[str, object]] = [r for r in results if r["success"]]
    failed: list[dict[str, object]] = [r for r in results if not r["success"]]
    total_imgs: int = len(results)

    times: list[float] = [_to_float(r["elapsed_seconds"]) for r in successful]
    fields_list: list[float] = [_to_float(r["fields_extracted"]) for r in successful]
    core_list: list[float] = [_to_float(r["core_fields_extracted"]) for r in successful]

    avg_fields: float = round(mean(fields_list), 1) if fields_list else 0.0
    avg_core: float = round(mean(core_list), 1) if core_list else 0.0
    core_fill_rate: float = (
        round(
            sum(core_list) / (len(successful) * len(CORE_FIELDS)) * 100,
            1,
        )
        if successful
        else 0.0
    )
    success_rate: float = (
        round(len(successful) / total_imgs * 100, 1) if total_imgs else 0.0
    )

    failure_patterns: list[str] = [
        str(r["error"]) for r in failed if r.get("error") is not None
    ]

    return {
        "model": model_name,
        "total_images": total_imgs,
        "successful": len(successful),
        "failed": len(failed),
        "success_rate_pct": success_rate,
        "time_seconds": {
            "total": round(sum(times), 2),
            "avg": round(mean(times), 2) if times else 0.0,
            "min": round(min(times), 2) if times else 0.0,
            "max": round(max(times), 2) if times else 0.0,
        },
        "avg_fields_extracted": avg_fields,
        "avg_core_fields_extracted": avg_core,
        "core_field_fill_rate_pct": core_fill_rate,
        "failure_patterns": failure_patterns,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _field_agreement(
    sonnet_data: dict[str, object],
    oss_data: dict[str, object],
) -> int:
    """Count how many core fields have the same value in both result dicts.

    Comparison is case-insensitive and strips leading/trailing whitespace.

    Args:
        sonnet_data: ``extracted_data`` dict from the sonnet result record.
        oss_data: ``extracted_data`` dict from the OSS result record.

    Returns:
        Number of ``CORE_FIELDS`` whose values agree between both models.
    """
    agreements: int = 0
    for field in CORE_FIELDS:
        v_sonnet: object = sonnet_data.get(field)
        v_oss: object = oss_data.get(field)
        if v_sonnet is None and v_oss is None:
            continue
        if v_sonnet is None or v_oss is None:
            continue
        if str(v_sonnet).strip().lower() == str(v_oss).strip().lower():
            agreements += 1
    return agreements


def generate_benchmark_report(
    sonnet_results: list[dict[str, object]],
    oss_results: list[dict[str, object]],
    oss_model: str,
    output_dir: str | Path,
) -> None:
    """Write benchmark report files to *output_dir*.

    Produces three files:

    * ``results.csv`` — one row per image with columns for both models and a
      ``field_agreement`` count.
    * ``metrics_summary.json`` — aggregated metrics for both models.
    * ``results_sonnet-4.6.json`` and ``results_<oss_model>.json`` — full
      per-image records including ``extracted_data``.

    Args:
        sonnet_results: Output of :func:`run_extraction` for ``sonnet-4.6``.
        oss_results: Output of :func:`run_extraction` for *oss_model*.
        oss_model: Name of the OSS model used (key into ``MODELS``).
        output_dir: Directory where report files will be written.  Created
            if it does not exist.
    """
    out: Path = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Build lookup dicts keyed by source_file for fast join
    sonnet_by_file: dict[str, dict[str, object]] = {
        str(r["source_file"]): r for r in sonnet_results
    }
    oss_by_file: dict[str, dict[str, object]] = {
        str(r["source_file"]): r for r in oss_results
    }

    all_files: list[str] = sorted(
        set(sonnet_by_file.keys()) | set(oss_by_file.keys())
    )

    # ------------------------------------------------------------------
    # 1. results.csv
    # ------------------------------------------------------------------
    csv_path: Path = out / "results.csv"
    csv_columns: list[str] = [
        "source_file",
        "sonnet_success",
        "sonnet_elapsed_s",
        "sonnet_fields_extracted",
        "sonnet_core_fields",
        f"{oss_model}_success",
        f"{oss_model}_elapsed_s",
        f"{oss_model}_fields_extracted",
        f"{oss_model}_core_fields",
        "field_agreement",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer: csv.DictWriter[str] = csv.DictWriter(fh, fieldnames=csv_columns)
        writer.writeheader()

        for filename in all_files:
            s_rec: dict[str, object] = sonnet_by_file.get(filename, {})
            o_rec: dict[str, object] = oss_by_file.get(filename, {})

            s_data: dict[str, object] = (
                s_rec["extracted_data"]  # type: ignore[assignment]
                if isinstance(s_rec.get("extracted_data"), dict)
                else {}
            )
            o_data: dict[str, object] = (
                o_rec["extracted_data"]  # type: ignore[assignment]
                if isinstance(o_rec.get("extracted_data"), dict)
                else {}
            )

            agreement: int = _field_agreement(s_data, o_data)

            row: dict[str, object] = {
                "source_file": filename,
                "sonnet_success": s_rec.get("success", False),
                "sonnet_elapsed_s": s_rec.get("elapsed_seconds", ""),
                "sonnet_fields_extracted": s_rec.get("fields_extracted", ""),
                "sonnet_core_fields": s_rec.get("core_fields_extracted", ""),
                f"{oss_model}_success": o_rec.get("success", False),
                f"{oss_model}_elapsed_s": o_rec.get("elapsed_seconds", ""),
                f"{oss_model}_fields_extracted": o_rec.get("fields_extracted", ""),
                f"{oss_model}_core_fields": o_rec.get("core_fields_extracted", ""),
                "field_agreement": agreement,
            }
            writer.writerow(row)  # type: ignore[arg-type]

    logger.info("Wrote %s", csv_path)

    # ------------------------------------------------------------------
    # 2. metrics_summary.json
    # ------------------------------------------------------------------
    sonnet_metrics: dict[str, object] = compute_metrics(sonnet_results, SONNET_MODEL)
    oss_metrics: dict[str, object] = compute_metrics(oss_results, oss_model)

    summary: dict[str, object] = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "models_compared": [SONNET_MODEL, oss_model],
        SONNET_MODEL: sonnet_metrics,
        oss_model: oss_metrics,
    }

    summary_path: Path = out / "metrics_summary.json"
    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    logger.info("Wrote %s", summary_path)

    # ------------------------------------------------------------------
    # 3. results_<model>.json × 2
    # ------------------------------------------------------------------
    for model_name, model_results in (
        (SONNET_MODEL, sonnet_results),
        (oss_model, oss_results),
    ):
        detail_path: Path = out / f"results_{model_name}.json"
        with detail_path.open("w", encoding="utf-8") as fh:
            json.dump(model_results, fh, ensure_ascii=False, indent=2, default=str)
        logger.info("Wrote %s", detail_path)

    # ------------------------------------------------------------------
    # Console summary table
    # ------------------------------------------------------------------
    _print_summary(sonnet_metrics, oss_metrics, oss_model, out)


def _print_summary(
    sonnet_m: dict[str, object],
    oss_m: dict[str, object],
    oss_model: str,
    output_dir: Path,
) -> None:
    """Print a side-by-side metrics table to stdout.

    Args:
        sonnet_m: Metrics dict for ``sonnet-4.6``.
        oss_m: Metrics dict for the OSS model.
        oss_model: Name of the OSS model.
        output_dir: Path where reports were saved (shown in footer).
    """
    s_times: object = sonnet_m.get("time_seconds")
    o_times: object = oss_m.get("time_seconds")

    s_avg_t: float = float(s_times["avg"]) if isinstance(s_times, dict) else 0.0  # type: ignore[index]
    o_avg_t: float = float(o_times["avg"]) if isinstance(o_times, dict) else 0.0  # type: ignore[index]
    s_total_t: float = float(s_times["total"]) if isinstance(s_times, dict) else 0.0  # type: ignore[index]
    o_total_t: float = float(o_times["total"]) if isinstance(o_times, dict) else 0.0  # type: ignore[index]

    col_w: int = max(len(SONNET_MODEL), len(oss_model), 12) + 2
    sep: str = "=" * (36 + col_w * 2)
    inner_sep: str = "-" * (36 + col_w * 2)

    def _row(label: str, s_val: str, o_val: str) -> str:
        return f"  {label:<34}{s_val:>{col_w}}{o_val:>{col_w}}"

    print(f"\n{sep}")
    print(f"  Benchmark Summary: {SONNET_MODEL}  vs  {oss_model}")
    print(sep)
    print(_row("Metric", SONNET_MODEL, oss_model))
    print(inner_sep)
    print(_row("Success rate (%)", f"{sonnet_m.get('success_rate_pct')}%", f"{oss_m.get('success_rate_pct')}%"))
    print(_row("Avg time per image (s)", f"{s_avg_t:.2f}", f"{o_avg_t:.2f}"))
    print(_row("Total time (s)", f"{s_total_t:.2f}", f"{o_total_t:.2f}"))
    print(_row("Avg fields extracted", str(sonnet_m.get("avg_fields_extracted")), str(oss_m.get("avg_fields_extracted"))))
    print(_row("Avg core fields extracted", str(sonnet_m.get("avg_core_fields_extracted")), str(oss_m.get("avg_core_fields_extracted"))))
    print(_row("Core field fill rate (%)", f"{sonnet_m.get('core_field_fill_rate_pct')}%", f"{oss_m.get('core_field_fill_rate_pct')}%"))
    print(_row("Failed images", str(sonnet_m.get("failed")), str(oss_m.get("failed"))))
    print(sep)
    print(f"  Reports saved to: {output_dir.resolve()}")
    print(f"{sep}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Run the benchmark pipeline.

    Returns:
        Exit code: ``0`` on success, ``1`` on fatal error.
    """
    args: argparse.Namespace = _parse_args()
    _setup_logging(args.verbose)

    # ------------------------------------------------------------------
    # 1. Environment
    # ------------------------------------------------------------------
    load_dotenv()
    api_key: str | None = os.environ.get("OPENCODE_API_KEY")
    if not api_key:
        logger.error(
            "OPENCODE_API_KEY is not set. Add it to your .env file."
        )
        return 1

    # ------------------------------------------------------------------
    # 2. Discover images
    # ------------------------------------------------------------------
    try:
        image_files: list[Path] = get_image_files(args.input_dir)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1

    if not image_files:
        logger.error("No supported image files found in '%s'.", args.input_dir)
        return 1

    logger.info(
        "Found %d image(s). Comparing '%s' vs '%s'.",
        len(image_files),
        SONNET_MODEL,
        args.oss_model,
    )

    # ------------------------------------------------------------------
    # 3. Run both models
    # ------------------------------------------------------------------
    sonnet_results: list[dict[str, object]] = run_extraction(
        api_key, image_files, SONNET_MODEL, args.timeout
    )
    oss_results: list[dict[str, object]] = run_extraction(
        api_key, image_files, args.oss_model, args.timeout
    )

    # ------------------------------------------------------------------
    # 4. Generate reports
    # ------------------------------------------------------------------
    try:
        generate_benchmark_report(
            sonnet_results,
            oss_results,
            args.oss_model,
            args.output_dir,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to generate benchmark report: %s", exc)
        return 1

    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(main())
