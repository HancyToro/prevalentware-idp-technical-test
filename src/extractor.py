"""Receipt data extraction module via OpenCode Zen API.

Connects to the OpenCode Zen gateway to extract structured data from receipt
images using vision-capable LLMs.  Two API flavours are supported:

* **Anthropic-compatible** — used for ``claude-sonnet-4-6``.
* **OpenAI-compatible**   — used for open-source models (qwen3-coder,
  glm-5, kimi-k2.5).

Rotation detection and correction is handled upstream by ``orientation.py``;
this module receives already-corrected PIL images.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
import time

import httpx
from PIL import Image

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

ANTHROPIC_ENDPOINT: str = "https://opencode.ai/zen/v1/messages"
OPENAI_ENDPOINT: str = "https://opencode.ai/zen/v1/chat/completions"

MODELS: dict[str, dict[str, str]] = {
    "sonnet-4.6": {
        "model_id": "claude-sonnet-4-6",
        "endpoint": ANTHROPIC_ENDPOINT,
        "api_type": "anthropic",
    },
    "qwen3-coder": {
        "model_id": "qwen3-coder",
        "endpoint": OPENAI_ENDPOINT,
        "api_type": "openai",
    },
    "glm-5": {
        "model_id": "glm-5",
        "endpoint": OPENAI_ENDPOINT,
        "api_type": "openai",
    },
    "kimi-k2.5": {
        "model_id": "kimi-k2.5",
        "endpoint": OPENAI_ENDPOINT,
        "api_type": "openai",
    },
}

EXPECTED_FIELDS: list[str] = [
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

# Pre-compiled regex to strip markdown code fences from LLM responses.
_FENCE_PATTERN: re.Pattern[str] = re.compile(r"```(?:json)?\s*|\s*```")

logger: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT: str = """Eres un experto en lectura y análisis de documentos contables colombianos, \
especialmente recibos de caja menor, cuentas de cobro, remisiones y recibos de pago.

Analiza la imagen del documento y extrae todos los campos visibles. \
Devuelve ÚNICAMENTE un objeto JSON válido, sin bloques de código, sin markdown, \
sin texto adicional antes ni después del JSON.

El JSON debe seguir EXACTAMENTE este esquema (usa null para campos ausentes):

{
  "ciudad": null,
  "fecha": null,
  "numero_recibo": null,
  "pagado_a": null,
  "valor": null,
  "concepto": null,
  "valor_en_letras": null,
  "firma_recibido": null,
  "cc_o_nit": null,
  "codigo": null,
  "aprobado": null,
  "direccion": null,
  "vendedor": null,
  "telefono_fax": null,
  "forma_pago": null,
  "cantidad": null,
  "detalle": null,
  "valor_unitario": null,
  "valor_total": null,
  "total_documento": null,
  "tipo_documento": null,
  "plantilla_detectada": null
}

Reglas de extracción:
- "fecha": formato DD/MM/YYYY. Si el documento trae otro formato, conviértelo.
- "valor", "valor_unitario", "valor_total", "total_documento": solo el número, \
sin símbolo "$" ni puntos de miles (ejemplo: 150000).
- "tipo_documento": clasifica el documento en una de estas categorías: \
"recibo de caja menor", "cuenta de cobro", "recibo de pago", "remisión", "pedido" u otra \
descripción breve si no encaja en ninguna.
- "plantilla_detectada": describe brevemente el formato visual del documento \
(ejemplo: "recibo pre-impreso con logo", "recibo manuscrito", "formato tabular con ítems").
- Campos con varias líneas de texto: concaténalos con " | " como separador.
- "firma_recibido": indica "Sí" si hay firma visible, "No" si no la hay.
- "aprobado": nombre o iniciales de quien aprobó, si aparece en el documento.

Extrae EXACTAMENTE lo que dice el documento, sin inventar datos."""

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _empty_record() -> dict[str, object]:
    """Return a dict with all 22 expected fields set to ``None``.

    Returns:
        A dictionary with every field in ``EXPECTED_FIELDS`` mapped to
        ``None``.
    """
    return {field: None for field in EXPECTED_FIELDS}


def _normalize_fields(data: dict[str, object]) -> dict[str, object]:
    """Ensure all 22 expected fields exist in *data*.

    Fields present in ``EXPECTED_FIELDS`` but missing from *data* are
    added with a ``None`` value.  Extra fields returned by the model are
    preserved.

    Args:
        data: The raw dictionary parsed from the model's JSON response.

    Returns:
        The same dictionary, guaranteed to contain every field in
        ``EXPECTED_FIELDS``.
    """
    for field in EXPECTED_FIELDS:
        if field not in data:
            data[field] = None
    return data


# ---------------------------------------------------------------------------
# Image encoding
# ---------------------------------------------------------------------------


def image_to_base64(image: Image.Image, max_size: int = 1568) -> tuple[str, str]:
    """Encode a PIL image to a base64 JPEG string suitable for API payloads.

    If either dimension exceeds *max_size*, the image is proportionally
    downscaled so the longest side equals *max_size*.  Images with an alpha
    channel or palette mode (``RGBA``, ``P``) are converted to ``RGB`` before
    encoding to avoid JPEG incompatibility.

    Args:
        image: The PIL ``Image.Image`` to encode.
        max_size: Maximum pixel count for the longest side.  Defaults to
            ``1568``, which is within the safe range for Anthropic and
            OpenAI vision endpoints.

    Returns:
        A tuple ``(base64_string, media_type)`` where ``base64_string`` is
        the UTF-8 base64-encoded JPEG and ``media_type`` is always
        ``"image/jpeg"``.
    """
    img: Image.Image = image

    # Convert modes incompatible with JPEG
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    elif img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # Downscale if the image is too large
    width: int
    height: int
    width, height = img.size
    longest: int = max(width, height)
    if longest > max_size:
        scale: float = max_size / longest
        new_width: int = int(width * scale)
        new_height: int = int(height * scale)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        logger.debug(
            "Image resized from %dx%d to %dx%d for API upload",
            width,
            height,
            new_width,
            new_height,
        )

    buffer: io.BytesIO = io.BytesIO()
    img.save(buffer, format="JPEG", quality=92)
    raw_bytes: bytes = buffer.getvalue()
    encoded: str = base64.b64encode(raw_bytes).decode("utf-8")
    logger.debug("Image encoded to base64 (%d bytes JPEG)", len(raw_bytes))
    return encoded, "image/jpeg"


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def parse_extraction_response(raw_text: str) -> dict[str, object]:
    """Parse a JSON extraction response from the model.

    Attempts three strategies in order:

    1. Strip markdown code fences and call ``json.loads`` on the result.
    2. Locate the first ``{`` and last ``}`` and parse the substring.
    3. Return an empty record and log an error.

    Args:
        raw_text: The raw text content returned by the LLM.

    Returns:
        A dictionary of extracted fields.  Falls back to
        ``_empty_record()`` if no valid JSON can be found.
    """
    # Strategy 1: strip fences and parse directly
    cleaned: str = _FENCE_PATTERN.sub("", raw_text).strip()
    try:
        result: object = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Strategy 2: find outermost { … } block
    start: int = cleaned.find("{")
    end: int = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            substring: object = json.loads(cleaned[start : end + 1])
            if isinstance(substring, dict):
                logger.debug("JSON extracted via brace-search fallback")
                return substring
        except json.JSONDecodeError:
            pass

    # Strategy 3: give up
    logger.error(
        "Failed to parse JSON from model response. Raw text (first 300 chars): %s",
        raw_text[:300],
    )
    return _empty_record()


# ---------------------------------------------------------------------------
# API call helpers
# ---------------------------------------------------------------------------


def _call_anthropic(
    api_key: str,
    model_id: str,
    endpoint: str,
    image_b64: str,
    media_type: str,
    timeout: float = 120.0,
) -> tuple[str, float]:
    """Send a vision request to an Anthropic-compatible endpoint.

    Builds a ``/messages`` payload with the image and the extraction prompt,
    posts it using ``httpx.Client``, and measures elapsed time.

    Args:
        api_key: OpenCode Zen API key.
        model_id: Anthropic model identifier (e.g. ``"claude-sonnet-4-6"``).
        endpoint: Full URL of the Anthropic-compatible messages endpoint.
        image_b64: Base64-encoded JPEG string.
        media_type: MIME type of the image (e.g. ``"image/jpeg"``).
        timeout: HTTP request timeout in seconds.

    Returns:
        A tuple ``(response_text, elapsed_seconds)``.

    Raises:
        httpx.HTTPStatusError: If the server returns a 4xx or 5xx status.
        httpx.RequestError: If a network-level error occurs.
    """
    headers: dict[str, str] = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    payload: dict[str, object] = {
        "model": model_id,
        "max_tokens": 2048,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
    }

    t_start: float = time.time()
    with httpx.Client(timeout=timeout) as client:
        response: httpx.Response = client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()

    elapsed: float = time.time() - t_start

    body: object = response.json()
    if not isinstance(body, dict):
        raise ValueError(f"Unexpected Anthropic response type: {type(body)}")

    content: object = body.get("content")
    if not isinstance(content, list) or not content:
        raise ValueError(f"Unexpected 'content' in Anthropic response: {content}")

    first_block: object = content[0]
    if not isinstance(first_block, dict):
        raise ValueError(f"Unexpected content block type: {type(first_block)}")

    text: object = first_block.get("text")
    if not isinstance(text, str):
        raise ValueError(f"No 'text' field in Anthropic content block: {first_block}")

    logger.debug("Anthropic call completed in %.2fs", elapsed)
    return text, elapsed


def _call_openai_compatible(
    api_key: str,
    model_id: str,
    endpoint: str,
    image_b64: str,
    media_type: str,
    timeout: float = 120.0,
) -> tuple[str, float]:
    """Send a vision request to an OpenAI-compatible endpoint.

    Builds a ``/chat/completions`` payload with the image encoded as a
    data-URL and the extraction prompt, posts it using ``httpx.Client``,
    and measures elapsed time.

    Args:
        api_key: OpenCode Zen API key.
        model_id: OSS model identifier (e.g. ``"qwen3-coder"``).
        endpoint: Full URL of the OpenAI-compatible completions endpoint.
        image_b64: Base64-encoded JPEG string.
        media_type: MIME type of the image (e.g. ``"image/jpeg"``).
        timeout: HTTP request timeout in seconds.

    Returns:
        A tuple ``(response_text, elapsed_seconds)``.

    Raises:
        httpx.HTTPStatusError: If the server returns a 4xx or 5xx status.
        httpx.RequestError: If a network-level error occurs.
    """
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }

    data_url: str = f"data:{media_type};base64,{image_b64}"

    payload: dict[str, object] = {
        "model": model_id,
        "max_tokens": 2048,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                    {
                        "type": "text",
                        "text": EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
    }

    t_start: float = time.time()
    with httpx.Client(timeout=timeout) as client:
        response: httpx.Response = client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()

    elapsed: float = time.time() - t_start

    body: object = response.json()
    if not isinstance(body, dict):
        raise ValueError(f"Unexpected OpenAI response type: {type(body)}")

    choices: object = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError(f"Unexpected 'choices' in OpenAI response: {choices}")

    first_choice: object = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError(f"Unexpected choice type: {type(first_choice)}")

    message: object = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError(f"No 'message' in OpenAI choice: {first_choice}")

    text: object = message.get("content")
    if not isinstance(text, str):
        raise ValueError(f"No 'content' string in OpenAI message: {message}")

    logger.debug("OpenAI-compatible call completed in %.2fs", elapsed)
    return text, elapsed


# ---------------------------------------------------------------------------
# Public extraction entry point
# ---------------------------------------------------------------------------


def extract_receipt_data(
    api_key: str,
    image: Image.Image,
    model_name: str = "sonnet-4.6",
    timeout: float = 120.0,
) -> tuple[dict[str, object], float]:
    """Extract structured receipt data from an image using the specified model.

    This is the main public entry point of the module.  It orchestrates:

    1. Validation of *model_name* against ``MODELS``.
    2. Image encoding via ``image_to_base64``.
    3. API dispatch to ``_call_anthropic`` or ``_call_openai_compatible``
       depending on the model's ``api_type``.
    4. Response parsing via ``parse_extraction_response``.
    5. Field normalisation via ``_normalize_fields``.

    Args:
        api_key: OpenCode Zen API key (value of ``OPENCODE_API_KEY``).
        image: An orientation-corrected PIL ``Image.Image``.
        model_name: Key into the ``MODELS`` dict.  Defaults to
            ``"sonnet-4.6"``.
        timeout: HTTP request timeout in seconds passed to the underlying
            ``httpx.Client``.

    Returns:
        A tuple ``(extracted_data, elapsed_seconds)`` where
        ``extracted_data`` is a normalised dictionary with all 22 expected
        fields and ``elapsed_seconds`` is the total API round-trip time.

    Raises:
        ValueError: If *model_name* is not a key in ``MODELS``.
        httpx.HTTPStatusError: If the API returns a 4xx or 5xx response.
        httpx.RequestError: If a network-level error occurs.
    """
    if model_name not in MODELS:
        raise ValueError(
            f"Unknown model '{model_name}'. "
            f"Available models: {list(MODELS.keys())}"
        )

    model_cfg: dict[str, str] = MODELS[model_name]
    model_id: str = model_cfg["model_id"]
    endpoint: str = model_cfg["endpoint"]
    api_type: str = model_cfg["api_type"]

    logger.info("Extracting receipt data with model '%s' (%s)", model_name, model_id)

    image_b64: str
    media_type: str
    image_b64, media_type = image_to_base64(image)

    raw_text: str
    elapsed: float

    if api_type == "anthropic":
        raw_text, elapsed = _call_anthropic(
            api_key, model_id, endpoint, image_b64, media_type, timeout
        )
    else:
        raw_text, elapsed = _call_openai_compatible(
            api_key, model_id, endpoint, image_b64, media_type, timeout
        )

    logger.info(
        "Model '%s' responded in %.2fs",
        model_name,
        elapsed,
    )

    parsed: dict[str, object] = parse_extraction_response(raw_text)
    normalised: dict[str, object] = _normalize_fields(parsed)
    return normalised, elapsed
