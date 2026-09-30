"""Modelo de la ficha estructurada de un proyecto.

El mismo modelo Pydantic cumple tres funciones: es el esquema de salida
estructurada que se pide al LLM en la extracción, valida lo que el LLM devuelve y
define qué se guarda en SQLite. Cada grupo de campos responde a un tipo de
pregunta de consultor (ver README, sección "Diseño de la ficha").
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class EstadoMeta(str, Enum):
    CUMPLIDA = "cumplida"
    PARCIAL = "parcialmente_cumplida"
    NO_CUMPLIDA = "no_cumplida"
    SIN_META = "sin_meta"


class Indicador(BaseModel):
    nombre: str = Field(description="Nombre del indicador tal como aparece en el informe.")
    unidad: str | None = Field(None, description="Unidad de medida (%, días hábiles, min, h/mes...).")
    linea_base: str | None = Field(None, description="Valor de línea base textual, tal como en el informe.")
    meta: str | None = Field(None, description="Meta textual (p. ej. '≤ 6'). null si el informe dice 'sin meta'.")
    resultado: str | None = Field(None, description="Resultado oficial de cierre, textual.")
    variacion: str | None = Field(None, description="Variación reportada (p. ej. '-58%', '+13 pp').")
    linea_base_valor: float | None = Field(None, description="Línea base como número (34% -> 34). null si no es numérica.")
    resultado_valor: float | None = Field(None, description="Resultado como número. null si no es numérico.")
    estado_meta: EstadoMeta = Field(description="Cumplimiento de la meta según el propio informe.")
    notas: str | None = Field(None, description="Aclaraciones del informe sobre el indicador (alcance, periodo, mediciones preliminares).")


class Leccion(BaseModel):
    titulo: str = Field(description="Idea principal de la lección (normalmente la frase en negrita).")
    descripcion: str = Field(description="Explicación de la lección según el informe.")


TipoSalvedad = Literal[
    "dato_no_oficial",  # cifra preliminar o sustituida por otra oficial
    "resultado_no_atribuible",  # resultado mencionado pero no atribuible al proyecto
    "fuera_de_alcance",  # áreas, líneas o productos excluidos expresamente
    "dato_no_validado",  # cifra de terceros que la firma no validó
    "pendiente",  # objetivos o entregables trasladados a otra fase
    "documento_externo",  # información que el informe remite a otro documento no incluido
]


class Salvedad(BaseModel):
    tipo: TipoSalvedad
    descripcion: str = Field(description="Qué debe tener en cuenta quien use los datos de este proyecto.")


class Ficha(BaseModel):
    # Identificación
    codigo_proyecto: str = Field(description="Código del proyecto, p. ej. PC-2025-014.")
    titulo: str
    cliente: str = Field(description="Razón social del cliente.")
    descripcion_cliente: str | None = Field(None, description="Tamaño, cobertura o giro del cliente.")
    sector: str = Field(description="Macrosector, p. ej. 'Servicios financieros', 'Manufactura', 'Salud', 'Retail'.")
    subsector: str | None = Field(None, description="Detalle del sector según el informe.")
    ubicacion: str | None = Field(None, description="Ubicación o cobertura geográfica si el informe la indica.")

    # Ejecución
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    duracion_semanas: int | None = None
    fecha_aceptacion: date | None = Field(None, description="Fecha de aceptación por el cliente.")
    estado: str = Field(description="Estado de cierre textual, p. ej. 'Cerrado' o 'Cerrado con pendientes'.")
    gerente_proyecto: str | None = None
    equipo_consultor: str | None = Field(None, description="Composición del equipo consultor, textual.")
    tamano_equipo: int | None = Field(None, description="Número total de personas del equipo consultor.")
    contraparte_cliente: str | None = None

    # Contenido
    problema: str = Field(description="Situación inicial o problema que motivó el proyecto (2-3 frases).")
    resumen: str = Field(description="Qué se hizo y qué se logró, en 2-4 frases, con las cifras oficiales.")
    objetivos: list[str] = Field(description="Objetivos acordados con el cliente, uno por elemento.")
    alcance: str = Field(description="Qué cubrió el proyecto y qué quedó fuera.")
    metodologias: list[str] = Field(description="Enfoques y herramientas metodológicas (Lean, VSM, TPM, SMED, ABC...).")
    iniciativas: list[str] = Field(description="Iniciativas o soluciones implementadas, una por elemento.")

    # Resultados
    indicadores: list[Indicador]
    objetivos_cumplidos: int | None = Field(None, description="Cuántos objetivos se cumplieron, según el informe.")
    objetivos_totales: int | None = Field(None, description="Cuántos objetivos se acordaron.")

    # Aprendizajes
    lecciones: list[Leccion]
    recomendaciones: list[str]
    salvedades: list[Salvedad] = Field(
        description="Advertencias para no malinterpretar los datos: cifras preliminares, fuera de alcance, "
        "resultados no atribuibles, pendientes, documentos referenciados que no están en el informe."
    )

    # Trazabilidad (lo completa el código, no el modelo)
    archivo_fuente: str = ""
