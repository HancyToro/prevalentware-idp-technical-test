# Technical Test - Receipt Data Extraction (Python + OpenCode)

## Objective

Fork this repository and build a Python solution that processes all images in `./images`, extracts structured data from **"recibos de caja menor"** (and equivalent small-receipt formats in this dataset), and generates a consolidated Excel file.

You will receive an **OpenCode Zen API key** for this test.

## Mandatory Requirements

1. **Use OpenCode Harness (required)**
   - The extraction step must use **OpenCode harness**.
   - Use model **`sonnet-4.6`** for document field extraction.
   - Submissions that do not use OpenCode harness for extraction will not be considered valid.

2. **Rotation handling with Tesseract only (required)**
   - Before sending each image to the model, detect orientation with **Tesseract** (for example OSD).
   - If rotated, correct the image orientation programmatically.
   - Rotation detection/correction must **not** be delegated to an LLM.

3. **Processing flow (required)**
   - For each image:
     1. Detect orientation with Tesseract.
     2. Rotate image if needed.
     3. Send corrected image to OpenCode harness (`sonnet-4.6`) with a prompt.
     4. Parse extracted fields.
   - After all images are processed, generate one consolidated Excel file.

4. **AI-first workflow transparency (required)**
   - This technical test is expected to be built **100% using AI assistance**.
   - You must store:
     - The prompts you used during development.
     - The conversation history used during development.
   - These artifacts will be reviewed in a follow-up interview, so make sure to have them available. You can also submit conversation history to the repository.

5. **Benchmark against one OpenCode OSS model (required)**
   - In addition to `sonnet-4.6`, run the same extraction task with **one open-source model available in OpenCode**.
   - Build a benchmark comparison between `sonnet-4.6` and your chosen model using the same input images and a comparable prompt strategy.
   - Provide a written performance analysis considering accuracy, failure patterns, consistency, speed/cost tradeoffs, and your own architecture and engineering recommendations (which model would you chosse in real life and why).
   - The analysis must be delivered as a **PDF file** and committed to the repository.

6. **Local OCR pipeline proposal with Ollama (required, planning only)**
   - Provide a written plan describing how you would solve the same problem with a **local pipeline** using **Ollama + an open-source model**.
   - This is a design/planning deliverable only (do not implement this pipeline in code for this test).
   - The plan must be delivered as a **PDF file** and committed to the repository.

## Input

- Folder: `./images`
- File types: receipt photos with mixed orientation and mixed templates.

## Fields to Extract

Your parser must cover the fields present across the receipt formats in this dataset.

### Core fields (always expected in output schema)

- `ciudad`
- `fecha`
- `numero_recibo`
- `pagado_a`
- `valor`
- `concepto`
- `valor_en_letras`

### Additional fields observed in the provided formats

Include these when present; leave empty/null when not available in a specific image:

- `firma_recibido`
- `cc_o_nit`
- `codigo`
- `aprobado`
- `direccion`
- `vendedor`
- `telefono_fax`
- `forma_pago` (e.g., contado/plazo/credito)
- `cantidad`
- `detalle`
- `valor_unitario`
- `valor_total`
- `total_documento`
- `tipo_documento` (e.g., recibo de caja menor / cuenta de cobro / recibo de pago / remision / pedido)

Recommended extra metadata columns:

- `source_file`
- `plantilla_detectada`
- `rotation_angle_applied`

## Output

- Excel file (for example: `./output/receipts_extracted.xlsx`)
- One row per image.
- Stable schema across all rows.

## Evaluation Notes

- We will run your solution with **other images that use the same formats but different content**.
- We will evaluate primarily on:
  - Field extraction accuracy on unseen images.
  - Correct rotation detection/correction using Tesseract.
  - Correct usage of OpenCode harness + `sonnet-4.6`.
  - Benchmark quality and rigor for `sonnet-4.6` vs chosen OpenCode OSS model.
  - Depth and practicality of the Ollama local OCR pipeline plan.
  - Reliability and clarity of your implementation.
  - Quality/completeness of AI prompts and conversation logs.

## Deliverables

Please submit at least:

1. Source code.
2. `requirements.txt`.
3. Run instructions (`README` section or separate doc).
4. Generated Excel output example.
5. AI usage evidence (optional in the repo but required in the interview):
   - `ai/prompts.md` (or equivalent)
   - `ai/conversations/` (exports/logs/transcripts)
6. Benchmark deliverables:
   - `benchmark/results.*` with comparison table/metrics
   - `benchmark/analysis.pdf` with written conclusions and recommendation
7. Local OCR planning deliverable:
   - `docs/local-ollama-ocr-plan.pdf` describing architecture, components, model choice, preprocessing steps, extraction strategy, validation strategy, risks, and rollout plan

## Run Interface (minimum)

Provide a command similar to:

```bash
python main.py --input-dir ./images --output-file ./output/receipts_extracted.xlsx
```

Your code must be reproducible from a clean environment.

## Important Constraints

- Do not commit API keys.
- The model extraction step must go through **OpenCode harness**.
- The orientation step must be solved with **Tesseract**, not with an LLM.
- The benchmark must compare `sonnet-4.6` with one selected OpenCode OSS model.
- The Ollama pipeline section is required as a **written plan only**; implementation is out of scope.
- The Ollama plan and the model comparison analysis must be submitted as a PDF and committed into the repository.
- Share the repository fork to the GitHub user `danyel117`.
