# Plan de trabajo

Agente en Python que responde preguntas sobre 4 informes de cierre de proyecto, con
fuente citada, trazabilidad de herramientas y sin inventar. Los puntos opcionales
(MCP, web, n8n, SharePoint/Power BI) quedan fuera por ahora.

## Arquitectura

```
data/informes/*.pdf|docx
        │
        ▼
 ingestion/  ── PDF (PyMuPDF) y Word (python-docx) → bloques (encabezado/texto/tabla)
        │         → fragmentos por sección con cita (archivo, sección, páginas)
        ├──────────────► search.py  (BM25)  ─────► herramienta buscar_en_informes
        │
        ▼
 extraction.py ── LLM con salida estructurada (esquema = ficha.py)
        │         → data/fichas/*.json (entregable, versionado)
        ▼
 storage/    ── SQLite (schema.sql) ───────────► herramienta consultar_fichas_sql (solo lectura)
        │
        ▼
 agent.py    ── bucle de tool use con el LLM, prompt anti-alucinación, registro de herramientas usadas
        │
        ▼
 cli.py      ── interfaz por consola (muestra respuesta + fuentes + traza)
```

## Fases

| # | Fase | Estado |
|---|------|--------|
| 0 | Estructura del repo, entorno, `.gitignore`, `.env.example` | Hecho |
| 1 | Ingesta PDF/Word con tablas y división por secciones + tests | Hecho |
| 2 | Búsqueda BM25 en texto + tests | Hecho |
| 3 | Modelo de ficha (Pydantic) + SQLite + consulta SQL de solo lectura + tests | Hecho |
| 4 | Extracción de fichas con LLM (Gemini, salida estructurada) + verificación de cifras contra el informe + comparación con ficha golden | Hecho |
| 5 | Agente: definición de herramientas, bucle de tool use, prompt de sistema, traza | Hecho |
| 6 | CLI | Hecho |
| 7 | Validación con preguntas reales de consultor (incluidas preguntas trampa) | Hecho: 14 preguntas, 2 rondas (ver VALIDACION.md) |
| 8 | README (instalación, arquitectura, supuestos, limitaciones, costo 50 consultores), video | README hecho; video pendiente |
| Opc. | Interfaz web sencilla (FastAPI + HTML) | Hecho |

## Trampas detectadas en los informes (el agente debe manejarlas)

- **Clínica (PC-2025-033):** el resumen ejecutivo dice que la espera bajó 30%, pero la
  nota de resultados aclara que 30% fue preliminar; el dato oficial es **24%**.
- **Plásticos (PC-2025-027):** los resultados son solo de la **Línea 1**. El OEE de la
  Línea 2 (~63%) lo reporta el cliente y **no fue validado**; no hay cifra de planta.
  Las paradas por cambio de formato son programadas y no entran en "paradas no programadas".
- **Cooperativa (PC-2025-014):** el +9% de monto colocado **no es atribuible** al
  proyecto (campaña comercial paralela). Se cumplieron 4 de 5 metas (abandono 11% vs ≤10%).
- **La Canasta (PC-2026-006):** "Cerrado con pendientes"; integración con proveedores
  0 de 3 (pasa a fase 2); días de inventario 31 vs ≤30 (29 sin licores). El análisis
  por local y proveedor está en un **Informe de Diagnóstico que no está disponible**:
  el agente debe decir que no tiene esa información.
- **Formato:** el enunciado dice que el informe de la Clínica viene en Word; en la
  carpeta recibida es PDF (exportado desde Word, con tablas de celdas combinadas).
  Se soportan ambos formatos.
- **Cruces útiles:** Martín Aguirre gerenció Plásticos y Clínica; Daniela Cevallos,
  Cooperativa y La Canasta. "Resistencia de mandos medios" aparece en Cooperativa y Plásticos.

## Restricción de cuota (capa gratuita de Gemini)

La capa gratuita permite unas 20 peticiones diarias por modelo. Una pregunta al
agente consume entre 2 y 4 peticiones. `llm.py` recorre una cadena de modelos
(`gemini-3.5-flash` → `3.6` → `3.7` → `3.8` → `3-flash-preview`, sin modelos lite; configurable
con `GEMINI_MODELS`) y salta de modelo cuando uno agota su cuota diaria o no está disponible
para la clave. Para el video y
la sesión de revisión conviene activar facturación en el proyecto de Google AI Studio.
