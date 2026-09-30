"""Extracción de la ficha estructurada de un informe con el LLM.

Flujo: texto del informe (con tablas en markdown) -> LLM con salida estructurada
(JSON Schema de `Ficha`) -> validación Pydantic -> verificación contra el texto
fuente -> JSON en data/fichas/ -> SQLite.

La verificación es determinista: comprueba que cada cifra de los indicadores
aparezca literalmente en el informe. No garantiza que el modelo haya entendido
todo, pero detecta el error más dañino: un número que no está en la fuente.
"""

from __future__ import annotations

import argparse
import re
import sys

from google.genai import types

from project_agent.config import DB_PATH, FICHAS_DIR, REPORTS_DIR
from project_agent.ficha import Ficha
from project_agent.ingestion import Document, load_reports
from project_agent.llm import LLMError, generate
from project_agent.storage.repository import rebuild_db_from_json, save_ficha_json

SYSTEM_PROMPT = """\
Eres un analista de Procesa Consultores que convierte informes de cierre de proyecto en fichas estructuradas.

Reglas:
- Usa exclusivamente la información del informe. Si un dato no aparece, devuelve null (o lista vacía). No infieras ni completes con conocimiento general.
- Copia las cifras tal como aparecen (mismos valores y unidades). No recalcules ni redondees. Si el informe no reporta la variación de un indicador, deja variacion en null: no la calcules.
- Cuando el informe distinga entre una cifra preliminar y una oficial, usa la oficial en los indicadores y en el resumen, y registra la preliminar como salvedad de tipo "dato_no_oficial".
- Registra como salvedades todo lo que evite malinterpretar los datos: resultados mencionados pero no atribuibles al proyecto, áreas fuera del alcance, cifras de terceros no validadas, objetivos pendientes o trasladados a otra fase, y documentos a los que el informe remite pero cuyo contenido no incluye.
- estado_meta refleja lo que dice el informe (columna de cumplimiento o texto). Si el indicador no tenía meta, usa "sin_meta".
- En indicadores, si el informe acota el alcance de la medición (por ejemplo, una sola línea de producción), indícalo en notas.
- objetivos_cumplidos y objetivos_totales solo si el informe lo dice o se desprende directamente de su tabla de resultados. Un objetivo "parcialmente cumplido" NO cuenta como cumplido.
- sector es el macrosector (Servicios financieros, Manufactura, Salud, Retail, etc.); el detalle va en subsector.
- estado es solo la condición de cierre, sin la fecha de aceptación: por ejemplo "Cerrado" o "Cerrado con pendientes".
- metodologias lista los enfoques y técnicas concretas que el informe nombra (p. ej. Lean, VSM, TPM, SMED, clasificación ABC, punto de pedido, análisis de colas), no categorías genéricas.
- Fechas en formato AAAA-MM-DD.
- Redacta en español, de forma concisa y fiel al informe.
"""


def _llm_schema() -> dict:
    schema = Ficha.model_json_schema()
    schema["properties"].pop("archivo_fuente", None)  # lo completa el código, no el modelo
    return schema


def extract_ficha(document: Document) -> Ficha:
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_json_schema=_llm_schema(),
    )
    prompt = f"Archivo: {document.source_file}\n\nInforme:\n\n{document.full_text}"
    response = generate(prompt, config)
    if not response.text:
        raise LLMError(f"El modelo no devolvió contenido para {document.source_file}.")
    ficha = Ficha.model_validate_json(response.text)
    ficha.archivo_fuente = document.source_file
    return ficha


NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _numbers(text: str) -> set[str]:
    return {n.replace(".", ",") for n in NUMBER_RE.findall(text)}


def verify_ficha(ficha: Ficha, document: Document) -> list[str]:
    """Devuelve advertencias sobre cifras de la ficha que no existen en el informe.

    Se compara número a número (no el texto literal), para aceptar reformulaciones
    como "al menos 70%" -> "≥ 70%" y detectar solo cifras que no están en la fuente.
    """
    source_numbers = _numbers(document.full_text)
    issues = []
    if ficha.codigo_proyecto not in document.full_text:
        issues.append(f"El código {ficha.codigo_proyecto} no aparece en el informe.")
    for indicator in ficha.indicadores:
        for field in ("linea_base", "meta", "resultado", "variacion"):
            value = getattr(indicator, field)
            missing = _numbers(value or "") - source_numbers
            if missing:
                issues.append(
                    f"Indicador '{indicator.nombre}': {field}='{value}' contiene cifras que no están en el informe ({', '.join(sorted(missing))})."
                )
    if ficha.objetivos_cumplidos is not None and ficha.objetivos_totales is not None:
        if ficha.objetivos_cumplidos > ficha.objetivos_totales:
            issues.append("objetivos_cumplidos es mayor que objetivos_totales.")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera las fichas de los informes y reconstruye la base SQLite.")
    parser.add_argument("codigos", nargs="*", help="Códigos de proyecto a procesar (por defecto, todos).")
    parser.add_argument("--force", action="store_true", help="Regenera fichas aunque ya existan.")
    args = parser.parse_args(argv)

    exit_code = 0
    for document in load_reports(REPORTS_DIR):
        if args.codigos and document.project_code not in args.codigos:
            continue
        target = FICHAS_DIR / f"{document.project_code}.json"
        if target.exists() and not args.force:
            print(f"= {document.source_file}: ficha existente, se omite (usa --force para regenerar)")
            continue
        print(f"> Extrayendo {document.source_file} ...", flush=True)
        try:
            ficha = extract_ficha(document)
        except (LLMError, ValueError) as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        path = save_ficha_json(ficha)
        print(f"  Ficha guardada en {path.relative_to(FICHAS_DIR.parents[1])}")
        for issue in verify_ficha(ficha, document):
            print(f"  ADVERTENCIA: {issue}")

    count = rebuild_db_from_json(FICHAS_DIR, DB_PATH)
    print(f"Base {DB_PATH.name} reconstruida con {count} fichas.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
