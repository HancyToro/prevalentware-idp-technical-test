"""Generador del PDF del plan de pipeline OCR local con Ollama.

Produce ``docs/local-ollama-ocr-plan.pdf`` con el diseño técnico completo
para reemplazar el pipeline cloud (OpenCode Zen + Sonnet 4.6) por un
pipeline local usando Ollama y modelos open-source de visión.

Uso::

    python generate_ollama_plan_pdf.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Constantes de estilo
# ---------------------------------------------------------------------------

HEADER_COLOR: Color = HexColor("#1a1a2e")
ACCENT_COLOR: Color = HexColor("#16213e")
ROW_ALT_COLOR: Color = HexColor("#f0f0f5")
GRID_COLOR: Color = HexColor("#cccccc")
METRIC_COL_COLOR: Color = HexColor("#e8e8f0")
WARNING_COLOR: Color = HexColor("#fff3cd")
SUCCESS_COLOR: Color = HexColor("#d4edda")
PHASE_COLOR: Color = HexColor("#e8eaf6")

OUTPUT_PATH: Path = Path("docs/local-ollama-ocr-plan.pdf")

# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------


def _build_styles() -> dict[str, ParagraphStyle]:
    """Construye y retorna el diccionario de estilos personalizados.

    Returns:
        Diccionario con los estilos ``title``, ``subtitle``,
        ``section_header``, ``body``, ``bullet``, ``code`` y ``footer``.
    """
    base = getSampleStyleSheet()

    title = ParagraphStyle(
        "CustomTitle",
        parent=base["Title"],
        fontSize=20,
        fontName="Helvetica-Bold",
        textColor=HEADER_COLOR,
        alignment=TA_CENTER,
        spaceAfter=6,
        leading=26,
    )

    subtitle = ParagraphStyle(
        "CustomSubtitle",
        parent=base["Normal"],
        fontSize=12,
        fontName="Helvetica",
        textColor=ACCENT_COLOR,
        alignment=TA_CENTER,
        spaceAfter=4,
        leading=16,
    )

    section_header = ParagraphStyle(
        "SectionHeader",
        parent=base["Heading2"],
        fontSize=12,
        fontName="Helvetica-Bold",
        textColor=HEADER_COLOR,
        spaceBefore=14,
        spaceAfter=6,
        leading=16,
    )

    body = ParagraphStyle(
        "CustomBody",
        parent=base["Normal"],
        fontSize=10,
        fontName="Helvetica",
        textColor=colors.black,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
        leading=15,
    )

    bullet = ParagraphStyle(
        "BulletBody",
        parent=base["Normal"],
        fontSize=10,
        fontName="Helvetica",
        textColor=colors.black,
        alignment=TA_LEFT,
        leftIndent=18,
        spaceAfter=4,
        leading=14,
    )

    code = ParagraphStyle(
        "CodeStyle",
        parent=base["Normal"],
        fontSize=9,
        fontName="Courier",
        textColor=colors.HexColor("#333333"),
        alignment=TA_LEFT,
        leftIndent=24,
        spaceAfter=3,
        leading=13,
        backColor=colors.HexColor("#f8f8f8"),
    )

    footer = ParagraphStyle(
        "Footer",
        parent=base["Normal"],
        fontSize=8,
        fontName="Helvetica",
        textColor=colors.HexColor("#666666"),
        alignment=TA_CENTER,
        spaceBefore=10,
    )

    return {
        "title": title,
        "subtitle": subtitle,
        "section_header": section_header,
        "body": body,
        "bullet": bullet,
        "code": code,
        "footer": footer,
    }


# ---------------------------------------------------------------------------
# Tablas
# ---------------------------------------------------------------------------


def _table_style_base(has_alt_rows: bool = True) -> list[object]:
    """Retorna la lista base de comandos de estilo para las tablas.

    Args:
        has_alt_rows: Si ``True`` incluye ``ROWBACKGROUNDS`` para filas alternas.

    Returns:
        Lista de tuplas de estilo compatibles con ``TableStyle``.
    """
    style: list[object] = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_COLOR),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID_COLOR),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if has_alt_rows:
        style.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT_COLOR]))
    return style


def _build_model_table() -> Table:
    """Construye la tabla comparativa de modelos Ollama.

    Returns:
        Un objeto :class:`reportlab.platypus.Table` con estilos aplicados.
    """
    headers: list[str] = ["Modelo", "Parámetros", "Visión", "Español", "VRAM mín."]
    rows: list[list[str]] = [
        ["LLaVA 1.6 34B",          "34B",  "Fuerte",     "Bueno",      "24 GB"],
        ["LLaVA 1.6 13B",          "13B",  "Bueno",      "Moderado",   "10 GB"],
        ["Moondream 2",             "1.8B", "Básico",     "Limitado",   "4 GB"],
        ["Llama 3.2 Vision 11B",   "11B",  "Bueno",      "Bueno",      "8 GB"],
        ["Llama 3.2 Vision 90B",   "90B",  "Excelente",  "Excelente",  "64 GB"],
    ]

    data: list[list[str]] = [headers] + rows
    col_widths: list[float] = [2.1 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch, 1.1 * inch]

    style_cmds: list[object] = _table_style_base()
    # Resaltar filas recomendadas (LLaVA 34B fila 1, Llama 3.2 11B fila 4)
    style_cmds += [
        ("BACKGROUND", (0, 1), (-1, 1), SUCCESS_COLOR),
        ("BACKGROUND", (0, 4), (-1, 4), PHASE_COLOR),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]

    table: Table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle(style_cmds))  # type: ignore[arg-type]
    return table


def _build_infrastructure_table() -> Table:
    """Construye la tabla de requisitos de infraestructura.

    Returns:
        Un objeto :class:`reportlab.platypus.Table` con estilos aplicados.
    """
    headers: list[str] = ["Componente", "Mínimo recomendado", "Óptimo para producción"]
    rows: list[list[str]] = [
        ["GPU",       "NVIDIA RTX 3090 (24 GB)",    "NVIDIA A100 (40/80 GB)"],
        ["RAM",       "32 GB DDR4",                 "64 GB DDR5"],
        ["CPU",       "8 núcleos",                  "16+ núcleos"],
        ["Almacenamiento", "50 GB SSD",             "200 GB NVMe SSD"],
        ["Sistema operativo", "Ubuntu 22.04 LTS",  "Ubuntu 24.04 LTS"],
        ["Ollama",    "v0.3+",                      "Última versión estable"],
        ["Python",    "3.10+",                      "3.11+"],
    ]

    data: list[list[str]] = [headers] + rows
    col_widths: list[float] = [1.8 * inch, 2.3 * inch, 2.1 * inch]

    style_cmds: list[object] = _table_style_base()
    style_cmds.append(("BACKGROUND", (0, 1), (0, -1), METRIC_COL_COLOR))
    style_cmds.append(("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"))

    table: Table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle(style_cmds))  # type: ignore[arg-type]
    return table


def _build_risks_table() -> Table:
    """Construye la tabla de riesgos y mitigaciones.

    Returns:
        Un objeto :class:`reportlab.platypus.Table` con estilos aplicados.
    """
    headers: list[str] = ["Riesgo", "Impacto", "Mitigación"]
    rows: list[list[str]] = [
        [
            "Menor precisión que Sonnet 4.6",
            "Alto",
            "Evaluar con ground truth; considerar fine-tuning con recibos propios",
        ],
        [
            "Costo de hardware elevado",
            "Medio",
            "Amortizable a partir de ~5.000 recibos/mes frente al costo cloud",
        ],
        [
            "Mantenimiento de modelos",
            "Medio",
            "Fijar versiones de modelo; proceso de actualización documentado",
        ],
        [
            "Inferencia lenta sin GPU dedicada",
            "Alto",
            "GPU mínima RTX 3090; colas de procesamiento asíncrono para batches",
        ],
        [
            "JSON inconsistente o inválido",
            "Alto",
            "Few-shot prompting, temperatura 0.1, reintentos con prompt reforzado",
        ],
        [
            "Formatos nuevos de recibo no reconocidos",
            "Medio",
            "Dataset incremental; second-pass por campos faltantes; alertas de QA",
        ],
    ]

    data: list[list[str]] = [headers] + rows
    col_widths: list[float] = [2.0 * inch, 0.85 * inch, 3.35 * inch]

    style_cmds: list[object] = _table_style_base()
    # Colorear columna de impacto
    style_cmds += [
        ("BACKGROUND", (1, 1), (1, 1), colors.HexColor("#f8d7da")),  # Alto
        ("BACKGROUND", (1, 2), (1, 2), WARNING_COLOR),               # Medio
        ("BACKGROUND", (1, 3), (1, 3), colors.HexColor("#f8d7da")),  # Alto
        ("BACKGROUND", (1, 4), (1, 4), colors.HexColor("#f8d7da")),  # Alto
        ("BACKGROUND", (1, 5), (1, 5), WARNING_COLOR),               # Medio
        ("BACKGROUND", (1, 6), (1, 6), WARNING_COLOR),               # Medio
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("FONTNAME", (1, 1), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("WORDWRAP", (0, 0), (-1, -1), "LTR"),
    ]

    table: Table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle(style_cmds))  # type: ignore[arg-type]
    return table


# ---------------------------------------------------------------------------
# Construcción del documento
# ---------------------------------------------------------------------------


def _build_document(output_path: Path) -> None:
    """Construye y guarda el PDF completo en *output_path*.

    Args:
        output_path: Ruta destino del archivo ``.pdf``.
    """
    doc: SimpleDocTemplate = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=1.0 * inch,
        rightMargin=1.0 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        title="Local OCR Pipeline Plan with Ollama",
        author="Receipt Extractor Pipeline",
    )

    styles: dict[str, ParagraphStyle] = _build_styles()
    s_title = styles["title"]
    s_sub = styles["subtitle"]
    s_h = styles["section_header"]
    s_body = styles["body"]
    s_bullet = styles["bullet"]
    s_code = styles["code"]
    s_footer = styles["footer"]

    hr: HRFlowable = HRFlowable(
        width="100%", thickness=2, color=HEADER_COLOR, spaceAfter=10
    )
    hr_thin: HRFlowable = HRFlowable(
        width="100%", thickness=1, color=GRID_COLOR, spaceAfter=6
    )

    def sp(h: float = 0.1) -> Spacer:
        return Spacer(1, h * inch)

    def sec(text: str) -> Paragraph:
        return Paragraph(text, s_h)

    def p(text: str) -> Paragraph:
        return Paragraph(text, s_body)

    def b(text: str) -> Paragraph:
        return Paragraph(f"• &nbsp; {text}", s_bullet)

    def nb(num: int, text: str) -> Paragraph:
        return Paragraph(f"<b>{num}.</b> &nbsp; {text}", s_bullet)

    def code(text: str) -> Paragraph:
        return Paragraph(text, s_code)

    story: list[object] = []

    # ------------------------------------------------------------------
    # 1. Título
    # ------------------------------------------------------------------
    story += [
        sp(0.2),
        Paragraph("Plan de Pipeline OCR Local con Ollama", s_title),
        sp(0.05),
        Paragraph("Documento de Diseño — Extracción de Datos de Recibos", s_sub),
        sp(0.15),
        hr,
        sp(0.1),
    ]

    # ------------------------------------------------------------------
    # 2. Descripción general
    # ------------------------------------------------------------------
    story += [
        sec("1. Descripción General"),
        hr_thin,
        sp(0.05),
        p(
            "Este documento describe el diseño técnico de un pipeline <b>completamente local</b> "
            "para la extracción de datos de recibos colombianos usando <b>Ollama</b> y modelos "
            "de visión open-source, como alternativa al pipeline cloud actual basado en "
            "OpenCode Zen + Claude Sonnet 4.6. El pipeline propuesto replica las mismas "
            "capacidades funcionales —corrección de orientación, extracción de 22 campos "
            "estructurados y generación de Excel— sin depender de servicios externos."
        ),
        sp(0.05),
        p("<b>Beneficios clave del enfoque local:</b>"),
        b("<b>Cero costos de API:</b> sin facturación por token ni por llamada."),
        b("<b>Privacidad total:</b> los documentos nunca salen de la infraestructura propia."),
        b("<b>Sin rate limits:</b> procesamiento ilimitado en paralelo según el hardware."),
        b("<b>Operación offline:</b> funciona sin conexión a internet."),
        b("<b>Control total:</b> versiones de modelo fijadas, sin cambios de API inesperados."),
        sp(0.1),
    ]

    # ------------------------------------------------------------------
    # 3. Arquitectura
    # ------------------------------------------------------------------
    story += [
        sec("2. Arquitectura del Pipeline"),
        hr_thin,
        sp(0.05),
        p(
            "El pipeline sigue una secuencia lineal de 9 pasos, diseñada para ser modular "
            "y reemplazable componente a componente. Cada paso produce una salida bien "
            "definida que es la entrada del siguiente:"
        ),
        sp(0.08),
    ]

    pipeline_steps: list[tuple[str, str, str]] = [
        ("1", "Image Ingestion", "Carga de imagen desde disco. Validación de extensión y accesibilidad."),
        ("2", "EXIF Handling", "Aplicación de ImageOps.exif_transpose() para corregir metadatos de cámara."),
        ("3", "Tesseract OSD", "Detección de ángulo de rotación con pytesseract (--psm 0). Exclusivo Tesseract, sin LLM."),
        ("4", "Rotation Correction", "Rotación inversa (360 - ángulo) con PIL image.rotate(expand=True)."),
        ("5", "Image Enhancement", "Preprocesamiento: CLAHE, sharpening, denoising, binarización opcional."),
        ("6", "Local LLM (Ollama)", "POST a http://localhost:11434/api/chat con imagen en base64 y prompt en español."),
        ("7", "JSON Parsing + Validation", "Parseo con estrategia de 3 pasos; validación de schema y formato."),
        ("8", "Retry / Fallback", "Hasta 2 reintentos con prompt reforzado; second-pass para campos faltantes."),
        ("9", "Excel Generation", "Escritura del registro normalizado al DataFrame consolidado y archivo .xlsx."),
    ]

    step_data: list[list[str]] = [["Paso", "Componente", "Descripción"]]
    for num, comp, desc in pipeline_steps:
        step_data.append([num, comp, desc])

    step_col_widths: list[float] = [0.5 * inch, 1.6 * inch, 4.1 * inch]
    step_style: list[object] = _table_style_base()
    step_style += [
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("FONTNAME", (1, 1), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("BACKGROUND", (0, 1), (0, -1), METRIC_COL_COLOR),
    ]
    step_table: Table = Table(step_data, colWidths=step_col_widths, repeatRows=1)
    step_table.setStyle(TableStyle(step_style))  # type: ignore[arg-type]

    story += [step_table, sp(0.15)]

    # ------------------------------------------------------------------
    # 4. Selección de modelo
    # ------------------------------------------------------------------
    story += [
        sec("3. Selección de Modelo"),
        hr_thin,
        sp(0.05),
        p(
            "Los siguientes modelos están disponibles en Ollama con capacidad de visión. "
            "La comparativa incluye parámetros, calidad de visión, soporte de español y "
            "requisito mínimo de VRAM. Las filas <b>resaltadas en verde</b> son las "
            "recomendaciones primaria y secundaria:"
        ),
        sp(0.08),
        _build_model_table(),
        sp(0.1),
        p(
            "<b>Recomendación primaria: LLaVA 1.6 34B</b> — mejor balance entre precisión "
            "de extracción, reconocimiento de manuscrito y requisitos de hardware accesibles "
            "(RTX 3090 o equivalente). Su soporte de español es sólido y su capacidad de "
            "visión es suficiente para los formatos de recibo colombianos observados."
        ),
        sp(0.05),
        p(
            "<b>Modelo de respaldo: Llama 3.2 Vision 11B</b> — opción viable para hardware "
            "con menos VRAM (8 GB). Menor precisión en campos manuscritos, pero adecuado "
            "para recibos impresos de alta calidad con validación humana integrada."
        ),
        sp(0.1),
    ]

    # ------------------------------------------------------------------
    # 5. Preprocesamiento
    # ------------------------------------------------------------------
    story += [
        sec("4. Pasos de Preprocesamiento"),
        hr_thin,
        sp(0.05),
        p(
            "Los modelos locales son más sensibles a la calidad de imagen que los modelos "
            "cloud. Un preprocesamiento robusto es crítico para maximizar la tasa de "
            "extracción. Se implementa con <b>OpenCV</b> y <b>Pillow</b>:"
        ),
        sp(0.07),
        nb(1, "<b>EXIF Transpose:</b> corrección de metadatos de orientación de cámara (PIL ImageOps.exif_transpose)."),
        nb(2, "<b>Tesseract OSD:</b> detección de ángulo de rotación y corrección (requisito eliminatorio del pipeline)."),
        nb(3, "<b>CLAHE:</b> ecualización de histograma adaptativa con límite de contraste (cv2.createCLAHE, clipLimit=2.0, tileGridSize=8×8)."),
        nb(4, "<b>Sharpening:</b> unsharp mask para realzar bordes de texto (cv2.filter2D con kernel estándar)."),
        nb(5, "<b>Denoising:</b> filtro bilateral para reducir ruido preservando bordes (cv2.bilateralFilter, d=9)."),
        nb(6, "<b>Binarización opcional:</b> umbralización de Otsu para recibos de muy bajo contraste (cv2.threshold + THRESH_OTSU)."),
        nb(7, "<b>Resize:</b> redimensionado al rango 768–1024px en el lado más largo, manteniendo proporción."),
        nb(8, "<b>Normalización de DPI:</b> asegurar mínimo 150 DPI efectivos antes de enviar al modelo."),
        sp(0.1),
    ]

    # ------------------------------------------------------------------
    # 6. Estrategia de extracción
    # ------------------------------------------------------------------
    story += [
        sec("5. Estrategia de Extracción con Ollama"),
        hr_thin,
        sp(0.05),
        p(
            "Ollama expone una API HTTP local. La llamada de extracción es un "
            "<b>POST a http://localhost:11434/api/chat</b> con el siguiente payload:"
        ),
        sp(0.06),
        code('{ "model": "llava:34b",'),
        code('  "messages": [{ "role": "system", "content": "Responde ÚNICAMENTE con JSON válido..." },'),
        code('               { "role": "user",   "content": "...", "images": ["<base64>"] }],'),
        code('  "stream": false, "options": { "temperature": 0.1 } }'),
        sp(0.1),
        p("<b>Estrategia de prompting en cuatro capas:</b>"),
        b("<b>System message:</b> instrucción explícita de JSON-only, sin markdown, sin texto adicional."),
        b("<b>Few-shot examples:</b> 1-2 ejemplos de input/output JSON para anclar el formato esperado."),
        b("<b>Temperatura 0.1:</b> minimiza variabilidad en el formato de salida."),
        b("<b>Instrucciones campo a campo:</b> si el primer intento falla, segundo prompt con descripción explícita de cada campo faltante."),
        sp(0.08),
        p("<b>Estrategia de reintentos:</b>"),
        b("Hasta <b>2 reintentos</b> por imagen con prompt progresivamente más explícito."),
        b("<b>Second-pass dirigido:</b> si quedan campos core vacíos tras el primer parseo, se hace una segunda llamada solicitando solo esos campos."),
        b("Fallback a registro vacío con flag <i>_error</i> para trazabilidad si todos los intentos fallan."),
        sp(0.1),
    ]

    # ------------------------------------------------------------------
    # 7. Estrategia de validación
    # ------------------------------------------------------------------
    story += [
        sec("6. Estrategia de Validación"),
        hr_thin,
        sp(0.05),
        p(
            "La validación se aplica en <b>6 capas</b> después del parseo JSON, antes de "
            "escribir el registro al DataFrame de salida:"
        ),
        sp(0.07),
        nb(1, "<b>Validación de schema:</b> presencia de los 22 campos esperados; campos faltantes rellenados con None."),
        nb(2, "<b>Validación de formato:</b> fecha en DD/MM/YYYY (regex), valor numérico (sin símbolos), NIT con dígito de verificación."),
        nb(3, "<b>Consistencia cruzada:</b> comprobación de que valor_en_letras es coherente con valor (conversión numérica aproximada)."),
        nb(4, "<b>Cross-check con Tesseract:</b> OCR básico con pytesseract.image_to_string() para validar campos clave (número de recibo, fecha)."),
        nb(5, "<b>Puntuación de confianza:</b> score 0–100 basado en campos core llenados; registros con score < 60 marcados para revisión."),
        nb(6, "<b>Detección de duplicados:</b> hash de (numero_recibo + fecha + valor) para detectar imágenes duplicadas en el batch."),
        sp(0.1),
    ]

    # ------------------------------------------------------------------
    # 8. Infraestructura
    # ------------------------------------------------------------------
    story += [
        sec("7. Requisitos de Infraestructura"),
        hr_thin,
        sp(0.05),
        p(
            "El pipeline local requiere hardware con GPU dedicada para inferencia en tiempo "
            "razonable. Los valores mínimos permiten operar con LLaVA 1.6 34B; "
            "los valores óptimos habilitan procesamiento en lotes con menor latencia:"
        ),
        sp(0.08),
        _build_infrastructure_table(),
        sp(0.1),
        p(
            "El stack de software incluye: <b>Ollama 0.3+</b>, <b>Python 3.10+</b>, "
            "<b>OpenCV 4.8+</b>, <b>Pillow 10+</b>, <b>pytesseract 0.3.10+</b>, "
            "<b>httpx 0.27+</b>, <b>pandas 2.0+</b> y <b>openpyxl 3.1+</b>. "
            "El despliegue recomendado utiliza <b>Docker Compose</b> con un contenedor "
            "para Ollama y otro para el pipeline Python, con volúmenes compartidos para "
            "imágenes y output."
        ),
        sp(0.1),
    ]

    # ------------------------------------------------------------------
    # 9. Riesgos y mitigaciones
    # ------------------------------------------------------------------
    story += [
        sec("8. Riesgos y Mitigaciones"),
        hr_thin,
        sp(0.05),
        p(
            "Los principales riesgos del enfoque local frente al pipeline cloud, "
            "con su impacto estimado y estrategia de mitigación:"
        ),
        sp(0.08),
        _build_risks_table(),
        sp(0.1),
    ]

    # ------------------------------------------------------------------
    # 10. Plan de rollout
    # ------------------------------------------------------------------
    story += [
        sec("9. Plan de Implementación (Rollout)"),
        hr_thin,
        sp(0.07),
    ]

    phases: list[tuple[str, Color, list[str]]] = [
        (
            "Fase 1 — Prueba de Concepto (1–2 semanas)",
            SUCCESS_COLOR,
            [
                "Instalar Ollama y descargar Llama 3.2 Vision 11B (menor costo de hardware).",
                "Adaptar src/extractor.py para llamar al endpoint local (http://localhost:11434/api/chat).",
                "Ejecutar el pipeline en 20–30 recibos de muestra y medir tasa de llenado de campos.",
                "Comparar resultados con el ground truth generado por Sonnet 4.6.",
                "Decidir si se justifica el upgrade a LLaVA 34B según resultados.",
            ],
        ),
        (
            "Fase 2 — Pipeline Completo (1–2 semanas)",
            PHASE_COLOR,
            [
                "Upgrade a LLaVA 1.6 34B si el hardware lo permite.",
                "Implementar el módulo de preprocesamiento con OpenCV (CLAHE, sharpening, denoising).",
                "Agregar validación cruzada con Tesseract (cross-check de campos clave).",
                "Construir dataset de ground truth con las 13 imágenes actuales + anotaciones manuales.",
                "Medir accuracy por campo y por tipo de documento; identificar campos problemáticos.",
            ],
        ),
        (
            "Fase 3 — Operacionalización (1 semana)",
            WARNING_COLOR,
            [
                "Dockerizar el pipeline completo (Ollama + Python en contenedores separados).",
                "Implementar cola de procesamiento asíncrono para batches grandes (ej. Celery + Redis).",
                "Agregar health checks, logging estructurado y métricas de Prometheus.",
                "Documentar proceso de actualización de modelos y rollback.",
            ],
        ),
        (
            "Fase 4 — Mejora Continua (ongoing)",
            ROW_ALT_COLOR,
            [
                "Monitorear métricas de precisión en producción; alertar si score promedio < 75.",
                "Evaluar nuevos modelos de visión publicados en Ollama cada trimestre.",
                "Considerar fine-tuning con recibos propios si el volumen supera 10.000 documentos.",
                "Mantener dataset de ground truth actualizado con nuevos formatos de recibo.",
            ],
        ),
    ]

    for phase_title, phase_color, phase_items in phases:
        phase_header_style: list[object] = [
            ("BACKGROUND", (0, 0), (-1, 0), phase_color),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("BOX", (0, 0), (-1, -1), 0.5, GRID_COLOR),
        ]
        phase_table: Table = Table(
            [[phase_title]],
            colWidths=[6.5 * inch],
        )
        phase_table.setStyle(TableStyle(phase_header_style))  # type: ignore[arg-type]
        story.append(phase_table)
        story.append(sp(0.04))
        for item in phase_items:
            story.append(b(item))
        story.append(sp(0.1))

    # ------------------------------------------------------------------
    # 11. Conclusión
    # ------------------------------------------------------------------
    story += [
        sec("10. Conclusión"),
        hr_thin,
        sp(0.05),
        p(
            "El pipeline local con Ollama es una alternativa técnicamente viable al pipeline "
            "cloud actual. Elimina los costos de API y garantiza privacidad total de los "
            "documentos, a cambio de una inversión inicial en hardware y un esfuerzo de "
            "configuración y mantenimiento no trivial."
        ),
        sp(0.05),
        p(
            "La recomendación es iniciar con la <b>Fase 1</b> en paralelo al pipeline cloud, "
            "usando Llama 3.2 Vision 11B como prueba de concepto de bajo costo. Si los "
            "resultados de precisión superan el 85% de tasa de llenado core, proceder con "
            "LLaVA 1.6 34B y las fases siguientes. En caso contrario, mantener "
            "Claude Sonnet 4.6 como modelo principal hasta que el ecosistema de modelos "
            "locales de visión madure lo suficiente para igualar su precisión en documentos "
            "manuscritos y con convenciones colombianas."
        ),
        sp(0.15),
        hr,
        sp(0.05),
        Paragraph(
            "Generado por Receipt Extractor Pipeline — Plan de Pipeline OCR Local con Ollama",
            s_footer,
        ),
    ]

    doc.build(story)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Genera el PDF del plan de pipeline OCR local con Ollama.

    Returns:
        Código de salida: ``0`` en éxito, ``1`` en error.
    """
    output: Path = OUTPUT_PATH
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generando PDF en '{output}'...")
    try:
        _build_document(output)
    except Exception as exc:  # noqa: BLE001
        print(f"Error al generar el PDF: {exc}", file=sys.stderr)
        return 1

    print(f"PDF generado exitosamente: {output.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
