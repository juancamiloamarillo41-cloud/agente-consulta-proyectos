-- Esquema relacional de las fichas de proyecto.
-- Una fila por proyecto en `proyectos`; las listas de la ficha van en tablas hijas
-- para poder filtrarlas y agregarlas con SQL (p. ej. qué proyectos usaron SMED).

CREATE TABLE IF NOT EXISTS proyectos (
    codigo_proyecto     TEXT PRIMARY KEY,
    titulo              TEXT NOT NULL,
    cliente             TEXT NOT NULL,
    descripcion_cliente TEXT,
    sector              TEXT NOT NULL,
    subsector           TEXT,
    ubicacion           TEXT,
    fecha_inicio        TEXT,      -- ISO 8601 (YYYY-MM-DD)
    fecha_fin           TEXT,
    duracion_semanas    INTEGER,
    fecha_aceptacion    TEXT,
    estado              TEXT NOT NULL,
    gerente_proyecto    TEXT,
    equipo_consultor    TEXT,
    tamano_equipo       INTEGER,
    contraparte_cliente TEXT,
    problema            TEXT,
    resumen             TEXT,
    alcance             TEXT,
    objetivos_cumplidos INTEGER,
    objetivos_totales   INTEGER,
    archivo_fuente      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS objetivos (
    codigo_proyecto TEXT NOT NULL REFERENCES proyectos(codigo_proyecto) ON DELETE CASCADE,
    descripcion     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metodologias (
    codigo_proyecto TEXT NOT NULL REFERENCES proyectos(codigo_proyecto) ON DELETE CASCADE,
    metodologia     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS iniciativas (
    codigo_proyecto TEXT NOT NULL REFERENCES proyectos(codigo_proyecto) ON DELETE CASCADE,
    descripcion     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS indicadores (
    codigo_proyecto  TEXT NOT NULL REFERENCES proyectos(codigo_proyecto) ON DELETE CASCADE,
    nombre           TEXT NOT NULL,
    unidad           TEXT,
    linea_base       TEXT,
    meta             TEXT,
    resultado        TEXT,
    variacion        TEXT,
    linea_base_valor REAL,
    resultado_valor  REAL,
    estado_meta      TEXT NOT NULL CHECK (estado_meta IN ('cumplida', 'parcialmente_cumplida', 'no_cumplida', 'sin_meta')),
    notas            TEXT
);

CREATE TABLE IF NOT EXISTS lecciones (
    codigo_proyecto TEXT NOT NULL REFERENCES proyectos(codigo_proyecto) ON DELETE CASCADE,
    titulo          TEXT NOT NULL,
    descripcion     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recomendaciones (
    codigo_proyecto TEXT NOT NULL REFERENCES proyectos(codigo_proyecto) ON DELETE CASCADE,
    descripcion     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS salvedades (
    codigo_proyecto TEXT NOT NULL REFERENCES proyectos(codigo_proyecto) ON DELETE CASCADE,
    tipo            TEXT NOT NULL,
    descripcion     TEXT NOT NULL
);
