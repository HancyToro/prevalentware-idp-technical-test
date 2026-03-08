# Prompts Utilizados Durante el Desarrollo

Este archivo documenta todos los prompts empleados durante el desarrollo del proyecto
**Receipt Data Extraction Pipeline**, como evidencia del flujo de trabajo AI-first requerido
por la prueba técnica. Cada prompt incluye su propósito, el texto exacto utilizado y
observaciones sobre el resultado obtenido.

---

## 1. Initial Analysis Prompt

**Purpose:** Analizar los requisitos de la prueba técnica y descomponer el problema en
tareas concretas antes de escribir cualquier línea de código.

```
Lee el siguiente README de una prueba técnica y ayúdame a:

1. Identificar los requisitos ELIMINATORIOS (los que hacen inválida la entrega si no se cumplen).
2. Descomponer el trabajo en módulos Python independientes con sus responsabilidades.
3. Identificar las dependencias entre módulos.
4. Señalar los riesgos técnicos más importantes (por ejemplo: manejo de errores de Tesseract,
   variabilidad del JSON del LLM, imágenes de baja calidad).
5. Proponer un orden de implementación que minimice el riesgo.

README de la prueba:
[contenido del README pegado aquí]
```

**Resultado:** Se identificaron tres requisitos eliminatorios:
- Usar OpenCode Harness (endpoint `/zen/v1/messages`) con `sonnet-4.6`.
- Detección de orientación exclusivamente con Tesseract OSD (nunca con LLM).
- Benchmark comparativo con un modelo OSS de OpenCode.

Se definió el orden de implementación: `orientation.py` → `extractor.py` →
`excel_writer.py` → `main.py` → `benchmark.py` → PDFs → README.

---

## 2. Architecture Planning Prompt

**Purpose:** Investigar la API de OpenCode Zen, sus dos endpoints y los formatos exactos
de payload antes de implementar `src/extractor.py`.

```
Necesito implementar un cliente HTTP en Python para OpenCode Zen, que es un gateway
de modelos AI con dos endpoints:

1. Endpoint Anthropic-compatible (para Claude Sonnet 4.6):
   - URL: https://opencode.ai/zen/v1/messages
   - Auth header: "x-api-key": <api_key>
   - Header requerido: "anthropic-version": "2023-06-01"
   - Model ID: "claude-sonnet-4-6"

2. Endpoint OpenAI-compatible (para modelos OSS: qwen3-coder, glm-5, kimi-k2.5):
   - URL: https://opencode.ai/zen/v1/chat/completions
   - Auth header: "Authorization": "Bearer <api_key>"

Para cada endpoint necesito saber:
- El formato exacto del payload para enviar una imagen en base64 junto con un prompt de texto.
- El path en la respuesta JSON donde está el texto generado.
- Cómo manejar errores HTTP (4xx, 5xx) de forma robusta con httpx.

Diseña dos funciones Python (_call_anthropic y _call_openai_compatible) con type
annotations completas (Pylance standard), usando httpx.Client (no requests).
Cada función debe retornar tuple[str, float] con el texto de respuesta y los segundos
transcurridos.
```

**Resultado:** Se definió la estructura de los dos helpers `_call_anthropic` y
`_call_openai_compatible` con sus payloads, headers y rutas de extracción de respuesta.
Se decidió usar `httpx.Client` como context manager para garantizar cierre de conexiones.

---

## 3. Extraction Prompt (Producción)

**Purpose:** Prompt enviado al LLM en cada llamada de extracción. Es el núcleo del
pipeline: determina directamente la calidad y consistencia de los datos extraídos.

### Texto completo del prompt

```
Eres un experto en lectura y análisis de documentos contables colombianos,
especialmente recibos de caja menor, cuentas de cobro, remisiones y recibos de pago.

Analiza la imagen del documento y extrae todos los campos visibles.
Devuelve ÚNICAMENTE un objeto JSON válido, sin bloques de código, sin markdown,
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
- "valor", "valor_unitario", "valor_total", "total_documento": solo el número,
  sin símbolo "$" ni puntos de miles (ejemplo: 150000).
- "tipo_documento": clasifica el documento en una de estas categorías:
  "recibo de caja menor", "cuenta de cobro", "recibo de pago", "remisión", "pedido"
  u otra descripción breve si no encaja en ninguna.
- "plantilla_detectada": describe brevemente el formato visual del documento
  (ejemplo: "recibo pre-impreso con logo", "recibo manuscrito",
  "formato tabular con ítems").
- Campos con varias líneas de texto: concaténalos con " | " como separador.
- "firma_recibido": indica "Sí" si hay firma visible, "No" si no la hay.
- "aprobado": nombre o iniciales de quien aprobó, si aparece en el documento.

Extrae EXACTAMENTE lo que dice el documento, sin inventar datos.
```

### Análisis de las decisiones de diseño

#### Idioma: español

El prompt está íntegramente en español porque los documentos a analizar son recibos
colombianos con terminología contable local. Los modelos de visión responden mejor
cuando el idioma del prompt coincide con el idioma del documento: reduce ambigüedad
en nombres de campo y mejora el mapeo semántico entre el texto visible y los campos
del schema.

#### Schema JSON explícito con los 22 campos

Incluir el schema completo con todos los campos en `null` cumple tres funciones:

1. **Previene nombres de campo inventados:** sin schema, los modelos tienden a usar
   nombres propios (`importe`, `monto`, `beneficiario`) que rompen el parseo aguas
   abajo. Con el schema explícito, el modelo sabe exactamente qué nombres usar.
2. **Garantiza schema estable:** aunque el recibo no tenga un campo, ese campo aparece
   en el output como `null`, lo que hace que todos los registros del DataFrame tengan
   las mismas columnas.
3. **Reduce tokens de razonamiento:** el modelo no necesita "inventar" la estructura,
   solo rellenar los valores.

#### "ÚNICAMENTE un objeto JSON válido, sin bloques de código, sin markdown"

Esta instrucción explícita reduce los fallos de parseo. Sin ella, los modelos frecuentemente
envuelven el JSON en bloques de código markdown (` ```json ... ``` `), especialmente los
modelos OSS. Si bien el parser de `parse_extraction_response()` maneja este caso con
su estrategia de limpieza de fences, es más eficiente prevenirlo en el prompt.

#### `null` como valor por defecto (no cadena vacía, no `"N/A"`)

`null` JSON se mapea directamente a `None` en Python y a celda vacía en pandas/Excel.
Usar cadenas vacías o `"N/A"` generaría ruido en el output y complicaría la detección
de campos realmente ausentes en el benchmark.

#### Reglas de formato explícitas

- **Fecha DD/MM/YYYY:** los recibos colombianos mezclan formatos (DD/MM/YYYY, D de Mes
  de YYYY, fechas escritas en palabras). Sin la regla, cada modelo normaliza de forma
  diferente, haciendo incomParable el campo entre registros.
- **Valor sin `$` ni puntos de miles:** facilita la conversión a numérico en el pipeline
  posterior sin lógica de limpieza adicional.
- **Concatenación con ` | `:** algunos recibos tienen múltiples líneas en el mismo campo
  (varios ítems de detalle). El separador ` | ` permite reconstruir la información sin
  perder estructura.
- **`tipo_documento` con categorías fijas:** ancla la clasificación a un vocabulario
  controlado, lo que permite filtrado y agrupación en el Excel de salida.

#### "Extrae EXACTAMENTE lo que dice el documento, sin inventar datos"

Instrucción de cierre para contrarrestar la tendencia de los LLMs a "completar" o
"inferir" información que no está explícitamente en la imagen. En documentos contables,
un dato inventado es peor que un `null`.

---

## 4. Prompt Engineering Iterations

### Versión 1 — Prompt simple (descartado)

**Fecha de iteración:** primera sesión de desarrollo  
**Problema identificado:** nombres de campo inconsistentes entre imágenes

```
Analiza esta imagen de un recibo colombiano y extrae los datos en formato JSON.
Incluye: fecha, número de recibo, nombre de quien recibe, monto, concepto,
ciudad y cualquier otro campo relevante que encuentres.
```

**Problemas observados:**
- El modelo usaba nombres de campo diferentes en cada respuesta:
  `"monto"` / `"valor"` / `"importe"` / `"total"` para el mismo campo.
- Campos no solicitados explícitamente aparecían con nombres inventados.
- Algunos campos eran objetos anidados en lugar de strings.
- Sin schema fijo, el DataFrame resultante tenía columnas distintas por imagen,
  haciendo imposible la consolidación.

**Decisión:** añadir schema JSON explícito en la siguiente versión.

---

### Versión 2 — Con schema, sin reglas de formato (descartado)

**Fecha de iteración:** segunda sesión de desarrollo  
**Problema identificado:** markdown wrapping y formatos inconsistentes

```
Eres un experto en documentos contables colombianos.

Extrae los datos de la imagen y devuelve SOLO este JSON con los valores encontrados
(null si no está presente):

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
```

**Problemas observados:**
- Schema funcionó bien con Sonnet 4.6: nombres de campo consistentes.
- Con modelos OSS (qwen3-coder): respuesta envuelta en ` ```json ... ``` ` en ~15%
  de los casos.
- Fechas en formatos mixtos: `"15/03/2024"`, `"15 de marzo de 2024"`,
  `"03-15-2024"` para la misma imagen dependiendo del modelo.
- Valores monetarios incluían `"$"` y puntos: `"$150.000"` en lugar de `"150000"`.
- `tipo_documento` con valores libres no estandarizados:
  `"recibo"`, `"voucher"`, `"comprobante de pago"`.

**Decisión:** añadir reglas de formato explícitas y reforzar la instrucción de JSON-only.

---

### Versión 3 — Final con todas las reglas (en producción)

**Fecha de adopción:** tercera sesión de desarrollo  
**Estado:** en uso en `src/extractor.py` como `EXTRACTION_PROMPT`

Ver texto completo en la sección 3 de este documento.

**Mejoras respecto a v2:**
- Instrucción explícita: `"sin bloques de código, sin markdown"` → elimina el problema
  de markdown wrapping en modelos OSS.
- Regla de fecha DD/MM/YYYY con conversión explícita → fechas consistentes entre modelos.
- Regla de valor sin `$` ni puntos → valores directamente convertibles a numérico.
- Categorías fijas para `tipo_documento` → clasificación estandarizada.
- Descripción de `plantilla_detectada` → campo de metadata útil para debugging.
- Separador ` | ` para campos multi-línea → no se pierde información.
- Frase de cierre `"sin inventar datos"` → reduce alucinaciones en campos vacíos.

**Resultado con v3:**
- Sonnet 4.6: ~98% de respuestas parseables directamente, schema completo.
- Qwen3 Coder: ~85% parseables directamente, ~12% requieren limpieza de fences
  (manejado por el parser), ~3% fallback a registro vacío.

---

## 5. Benchmark Analysis Prompts

**Purpose:** Diseñar la estructura del benchmark comparativo y el análisis de resultados
entre Claude Sonnet 4.6 y Qwen3 Coder 480B.

### Prompt de diseño del benchmark

```
Necesito diseñar un benchmark comparativo entre dos modelos de visión para
extracción de datos de recibos colombianos:

- Modelo A: Claude Sonnet 4.6 (vía endpoint Anthropic-compatible de OpenCode Zen)
- Modelo B: Qwen3 Coder 480B (vía endpoint OpenAI-compatible de OpenCode Zen)

Ambos modelos reciben las mismas imágenes, el mismo prompt y el mismo schema JSON.

Define:
1. Las métricas cuantitativas más relevantes para comparar ambos modelos
   (considerando que el objetivo es precisión en campos contables).
2. Una métrica de "field agreement" para medir consistencia entre modelos en la
   misma imagen.
3. Los archivos de reporte a generar: CSV por imagen, JSON de métricas agregadas
   y JSON de detalle completo por modelo.
4. La estructura de un script benchmark.py con argparse, siguiendo las mismas
   convenciones de main.py.
```

**Resultado:** Se definieron las métricas: `success_rate`, `avg_fields_extracted`,
`core_field_fill_rate`, `time_seconds (avg/min/max/total)` y `failure_patterns`.
Se añadió `field_agreement` como cuenta de campos core con el mismo valor en ambos modelos
(comparación case-insensitive).

### Prompt de análisis comparativo para el PDF

```
Con base en los resultados del benchmark entre Claude Sonnet 4.6 y Qwen3 Coder 480B
para extracción de recibos colombianos, redacta un análisis técnico en español que incluya:

1. Resumen ejecutivo (2 párrafos): qué se comparó y hallazgos principales.
2. Análisis de precisión: fortalezas y debilidades de cada modelo.
3. Patrones de fallo observados para cada modelo.
4. Tradeoff velocidad/costo con estimaciones para 1.000 y 10.000 recibos.
5. Recomendación de arquitectura: cuál modelo usar en producción y por qué.
   Justifica con al menos 5 razones técnicas específicas al dominio (recibos colombianos).
6. Cuándo sería válido usar el modelo más barato (Qwen3).

Contexto técnico:
- Sonnet 4.6: input $3.00/1M tokens, output $15.00/1M tokens
- Qwen3 Coder: input $0.45/1M tokens, output $1.50/1M tokens
- Los recibos colombianos de caja menor mezclan texto impreso y manuscrito.
- El campo "valor_en_letras" es frecuentemente manuscrito.
```

**Resultado:** Estructura del análisis adoptada para `benchmark/analysis.pdf`, con énfasis
en la brecha de accuracy en campos manuscritos como argumento central para recomendar
Sonnet 4.6 en producción.

---

## 6. Ollama Local Pipeline Planning Prompts

**Purpose:** Diseñar el plan técnico completo para un pipeline OCR local con Ollama
como alternativa al pipeline cloud, para el entregable `docs/local-ollama-ocr-plan.pdf`.

### Prompt de planificación de arquitectura

```
Diseña un plan técnico detallado para reemplazar el pipeline cloud (OpenCode Zen +
Claude Sonnet 4.6) con un pipeline completamente local usando Ollama y modelos
open-source de visión.

El pipeline actual tiene estos pasos:
1. Detección de orientación con Tesseract OSD
2. Corrección de rotación con PIL
3. Extracción de datos con Claude Sonnet 4.6 vía API HTTP
4. Parseo y normalización del JSON
5. Generación de Excel

Para el plan local, necesito:
1. Comparativa de modelos disponibles en Ollama con capacidad de visión para
   documentos en español (con VRAM requerida).
2. Pasos de preprocesamiento adicionales recomendados para modelos locales
   (que son más sensibles a la calidad de imagen).
3. Cómo llamar a Ollama vía su API HTTP local.
4. Estrategia de prompting para modelos locales (few-shot, temperatura, reintentos).
5. Validación de la salida JSON.
6. Requisitos de hardware mínimos y recomendados.
7. Riesgos principales y sus mitigaciones.
8. Plan de rollout en fases (desde PoC hasta producción).

El contexto es extracción de recibos de caja menor colombianos, con mezcla de
texto impreso y manuscrito, formatos variados, calidad de imagen variable.
```

**Resultado:** Plan de 10 secciones adoptado para el documento
`docs/local-ollama-ocr-plan.pdf`, con LLaVA 1.6 34B como recomendación primaria y
Llama 3.2 Vision 11B como fallback. Las 4 fases del rollout van de PoC (2 semanas)
a mejora continua (ongoing).

### Prompt de selección de modelo local

```
Para un pipeline local de extracción de datos de recibos colombianos con Ollama,
compara estos modelos de visión disponibles:
- LLaVA 1.6 (13B y 34B)
- Moondream 2 (1.8B)
- Llama 3.2 Vision (11B y 90B)

Para cada uno, evalúa:
1. Capacidad de visión para documentos de baja calidad con texto manuscrito.
2. Soporte de español y comprensión de terminología contable colombiana.
3. VRAM mínima requerida.
4. Latencia esperada en RTX 3090.
5. Idoneidad para producción con recibos reales.

Recomienda el modelo primario y un fallback, justificando la elección.
```

**Resultado:** LLaVA 1.6 34B seleccionado como recomendación primaria por su balance
entre precisión en texto manuscrito y hardware accesible (RTX 3090, 24 GB VRAM).
Llama 3.2 Vision 11B como fallback para hardware con menor VRAM (8 GB).
