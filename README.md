# Receipt Data Extraction Pipeline

Pipeline de extracción de datos estructurados desde imágenes de recibos de caja menor colombianos. Utiliza **Tesseract OCR** para la detección y corrección de orientación, y **OpenCode Zen (Claude Sonnet 4.6)** para la extracción de campos mediante visión LLM.

---

## Requisitos del Sistema

- **Python 3.10+**
- **Tesseract OCR 5.x** instalado en el sistema
- **OpenCode Zen API Key** — obtener en [opencode.ai/auth](https://opencode.ai/auth)

### Instalación de Tesseract OCR

**Ubuntu / Debian:**
```bash
sudo apt update && sudo apt install -y tesseract-ocr tesseract-ocr-spa
```

**macOS (Homebrew):**
```bash
brew install tesseract
```

**Windows:**
Descargar el instalador desde [github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki) e instalarlo. Asegurarse de que el ejecutable esté en el `PATH` del sistema.

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/HancyToro/prevalentware-idp-technical-test.git
cd prevalentware-idp-technical-test

# 2. Crear y activar el entorno virtual
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env y reemplazar your_api_key_here con la API key de OpenCode Zen
```

---

## Uso

### Extracción principal

```bash
python main.py --input-dir ./images --output-file ./output/receipts_extracted.xlsx
```

### Opciones disponibles

| Opción | Valor por defecto | Descripción |
|---|---|---|
| `--input-dir` | `./images` | Directorio con las imágenes a procesar |
| `--output-file` | `./output/receipts_extracted.xlsx` | Archivo Excel de salida |
| `--model` | `sonnet-4.6` | Modelo a usar (`sonnet-4.6`, `qwen3-coder`, `glm-5`, `kimi-k2.5`) |
| `--timeout` | `120.0` | Timeout en segundos para cada llamada a la API |
| `--verbose` / `-v` | `False` | Activar logging de nivel DEBUG |

**Ejemplos:**

```bash
# Usar modelo OSS
python main.py --model qwen3-coder --verbose

# Timeout personalizado
python main.py --timeout 180 --input-dir ./images

# Ver ayuda completa
python main.py --help
```

### Benchmark comparativo

```bash
python benchmark.py --input-dir ./images --oss-model qwen3-coder
```

El benchmark ejecuta el pipeline completo con `sonnet-4.6` y con el modelo OSS seleccionado, y genera los siguientes reportes en `./benchmark/`:

- `results.csv` — comparación por imagen con columna `field_agreement`
- `metrics_summary.json` — métricas agregadas de ambos modelos
- `results_sonnet-4.6.json` / `results_qwen3-coder.json` — detalle completo por modelo

### Generar PDFs de análisis

```bash
# Análisis de benchmark (benchmark/analysis.pdf)
python generate_analysis_pdf.py

# Plan de pipeline OCR local con Ollama (docs/local-ollama-ocr-plan.pdf)
python generate_ollama_plan_pdf.py
```

---

## Flujo de Procesamiento

Por cada imagen en el directorio de entrada:

1. **Detección de orientación** — Tesseract OSD (`--psm 0`) detecta el ángulo de rotación de la imagen. Si la imagen es demasiado pequeña, se escala antes del análisis. La rotación **nunca se delega a un LLM**.

2. **Corrección de rotación** — Se aplica la rotación inversa `(360 - ángulo)` con PIL `image.rotate(expand=True)`. También se aplica `ImageOps.exif_transpose()` para manejar metadatos EXIF de cámara.

3. **Extracción con LLM** — La imagen corregida se codifica en base64 (máx. 1568px) y se envía a OpenCode Zen con el prompt de extracción en español. El modelo devuelve un objeto JSON con los 22 campos del schema.

4. **Parseo y normalización** — La respuesta se limpia de posibles bloques markdown, se parsea como JSON con estrategia de 3 pasos (parse directo → búsqueda por llaves → fallback vacío), y se normalizan los 22 campos esperados.

5. **Generación de Excel** — Todos los registros se consolidan en un DataFrame de pandas y se exportan a un archivo `.xlsx` con columnas ordenadas y anchos auto-ajustados.

---

## Campos Extraídos

### Campos principales

| Campo | Descripción |
|---|---|
| `ciudad` | Ciudad del recibo |
| `fecha` | Fecha en formato DD/MM/YYYY |
| `numero_recibo` | Número o código del recibo |
| `pagado_a` | Nombre de quien recibe el pago |
| `valor` | Monto numérico (sin `$` ni puntos de miles) |
| `concepto` | Descripción del pago |
| `valor_en_letras` | Monto escrito en palabras |

### Campos adicionales

`firma_recibido`, `cc_o_nit`, `codigo`, `aprobado`, `direccion`, `vendedor`, `telefono_fax`, `forma_pago`, `cantidad`, `detalle`, `valor_unitario`, `valor_total`, `total_documento`, `tipo_documento`

### Metadata por imagen

| Campo | Descripción |
|---|---|
| `source_file` | Nombre del archivo de imagen procesado |
| `plantilla_detectada` | Descripción del formato visual del recibo |
| `rotation_angle_applied` | Ángulo de corrección aplicado por Tesseract OSD |

---

## Estructura del Proyecto

```
prevalentware-idp-technical-test/
│
├── main.py                        # Punto de entrada CLI del pipeline principal
├── benchmark.py                   # Script de comparación entre modelos
├── generate_analysis_pdf.py       # Generador del PDF de análisis de benchmark
├── generate_ollama_plan_pdf.py    # Generador del PDF del plan Ollama
├── requirements.txt               # Dependencias Python
├── .env.example                   # Plantilla de variables de entorno
├── .gitignore
├── pyrightconfig.json             # Configuración de type checking (Pylance/pyright)
│
├── src/
│   ├── __init__.py                # Paquete fuente
│   ├── orientation.py             # Detección y corrección de orientación (Tesseract OSD)
│   ├── extractor.py               # Cliente API OpenCode Zen + prompt de extracción
│   └── excel_writer.py            # Generación del archivo Excel consolidado
│
├── images/                        # Imágenes de recibos de entrada (input)
├── output/                        # Archivo Excel generado (output)
│
├── benchmark/
│   ├── results.csv                # Comparación por imagen de ambos modelos
│   ├── metrics_summary.json       # Métricas agregadas del benchmark
│   ├── results_sonnet-4.6.json    # Detalle completo del modelo Sonnet
│   ├── results_qwen3-coder.json   # Detalle completo del modelo OSS
│   └── analysis.pdf               # Análisis escrito con recomendación de modelo
│
├── docs/
│   └── local-ollama-ocr-plan.pdf  # Plan de pipeline OCR local con Ollama
│
└── ai/
    ├── prompts.md                 # Prompts utilizados durante el desarrollo
    └── conversations/             # Historial de conversaciones con el agente AI
```

---

## Notas Técnicas

- **Corrección de orientación exclusiva con Tesseract:** la detección y corrección de rotación se realiza únicamente mediante `pytesseract.image_to_osd()`. Este paso **nunca se delega a un LLM** — es un requisito eliminatorio de la prueba.

- **Endpoint Anthropic-compatible para Sonnet 4.6:** las llamadas a `claude-sonnet-4-6` usan `POST https://opencode.ai/zen/v1/messages` con headers `x-api-key` y `anthropic-version: 2023-06-01`.

- **Endpoint OpenAI-compatible para modelos OSS:** los modelos `qwen3-coder`, `glm-5` y `kimi-k2.5` usan `POST https://opencode.ai/zen/v1/chat/completions` con header `Authorization: Bearer <api_key>`.

- **Redimensionado de imágenes:** antes de enviar al API, las imágenes se redimensionan a un máximo de 1568px en el lado más largo para garantizar compatibilidad con los límites de los endpoints de visión.

- **Prompt JSON-only:** el prompt de extracción instruye explícitamente al modelo a devolver únicamente un objeto JSON válido, sin bloques de código markdown ni texto adicional. El parser implementa una estrategia de 3 pasos para manejar respuestas no conformes.
