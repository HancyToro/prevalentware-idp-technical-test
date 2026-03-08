"""Excel output module for consolidated receipt data.

Converts a list of extracted receipt records into a formatted ``.xlsx`` file
with a stable column order, auto-adjusted column widths, and a single
``Receipts`` sheet.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

import pandas as pd
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

COLUMN_ORDER: list[str] = [
    "source_file",
    "tipo_documento",
    "plantilla_detectada",
    "rotation_angle_applied",
    "ciudad",
    "fecha",
    "numero_recibo",
    "pagado_a",
    "cc_o_nit",
    "valor",
    "valor_en_letras",
    "concepto",
    "detalle",
    "cantidad",
    "valor_unitario",
    "valor_total",
    "total_documento",
    "forma_pago",
    "codigo",
    "aprobado",
    "direccion",
    "vendedor",
    "telefono_fax",
    "firma_recibido",
]

MAX_COLUMN_WIDTH: int = 50
MIN_COLUMN_WIDTH: int = 8
COLUMN_PADDING: int = 2
SHEET_NAME: str = "Receipts"

logger: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def generate_excel(
    records: list[dict[str, object]],
    output_path: str | Path,
) -> Path:
    """Generate a consolidated Excel file from a list of receipt records.

    Steps performed:

    1. Create the parent directory tree if it does not already exist.
    2. Build a :class:`pandas.DataFrame` from *records*.
    3. Reorder columns: fields listed in :data:`COLUMN_ORDER` come first
       (in that order), followed by any extra columns not in the list.
    4. Write the DataFrame to an ``.xlsx`` file using the ``openpyxl``
       engine with sheet name ``"Receipts"`` and no row index.
    5. Auto-adjust each column's width based on the longest value in that
       column (header included), capped at :data:`MAX_COLUMN_WIDTH`
       characters.

    Args:
        records: A list of dictionaries, one per processed image.  Each
            dict should contain the 22 extraction fields plus the metadata
            fields ``source_file`` and ``rotation_angle_applied``.  Missing
            keys are handled gracefully by pandas (filled with ``NaN``).
        output_path: Destination path for the ``.xlsx`` file.  Accepts
            both ``str`` and :class:`pathlib.Path`.

    Returns:
        The resolved :class:`pathlib.Path` of the generated Excel file.

    Raises:
        ValueError: If *records* is empty.
        OSError: If the output file cannot be written (e.g. permission
            denied).
    """
    path: Path = Path(output_path)

    if not records:
        raise ValueError("'records' must contain at least one entry.")

    # Create output directory tree
    path.parent.mkdir(parents=True, exist_ok=True)

    # Build DataFrame
    df: pd.DataFrame = pd.DataFrame(records)

    # Stable column ordering: COLUMN_ORDER first, then any extras
    ordered_cols: list[str] = [c for c in COLUMN_ORDER if c in df.columns]
    extra_cols: list[str] = [c for c in df.columns if c not in COLUMN_ORDER]
    df = cast(pd.DataFrame, df[ordered_cols + extra_cols])

    # Write to Excel
    with pd.ExcelWriter(path, engine="openpyxl") as writer:  # type: ignore[abstract]
        df.to_excel(writer, sheet_name=SHEET_NAME, index=False)

        worksheet: Worksheet = writer.sheets[SHEET_NAME]
        _auto_fit_columns(df, worksheet)

    logger.info(
        "Wrote %d row(s) to '%s'",
        len(df),
        path,
    )
    return path


# ---------------------------------------------------------------------------
# Private helper
# ---------------------------------------------------------------------------


def _auto_fit_columns(df: pd.DataFrame, worksheet: Worksheet) -> None:
    """Adjust column widths in *worksheet* to fit their content.

    For each column the width is set to the maximum of:

    * The length of the column header, plus :data:`COLUMN_PADDING`.
    * The length of the longest cell value (as a string), plus
      :data:`COLUMN_PADDING`.

    The result is clamped between :data:`MIN_COLUMN_WIDTH` and
    :data:`MAX_COLUMN_WIDTH`.

    Args:
        df: The DataFrame that was written to the worksheet (used to
            compute per-column value lengths).
        worksheet: The ``openpyxl`` worksheet to modify in place.
    """
    for col_idx, col_name in enumerate(df.columns, start=1):
        header_len: int = len(str(col_name))

        # Compute the longest string representation of any value in the column.
        # Series.map(len) returns NaN for empty series; guard with a default.
        col_series: pd.Series = cast(pd.Series, df[col_name])
        str_lengths: pd.Series = col_series.astype(str).map(len)
        max_data_len: int = int(str_lengths.max()) if not str_lengths.empty else 0

        raw_width: int = max(header_len, max_data_len) + COLUMN_PADDING
        col_width: int = max(MIN_COLUMN_WIDTH, min(raw_width, MAX_COLUMN_WIDTH))

        col_letter: str = get_column_letter(col_idx)
        worksheet.column_dimensions[col_letter].width = col_width
