from project_agent.ingestion.tables import clean_rows, rows_to_markdown


def test_collapses_phantom_columns_from_merged_cells():
    # Patrón real del PDF exportado desde Word: la etiqueta de cabecera queda en la
    # columna central del grupo y los valores al inicio, con None en las celdas cubiertas.
    raw = [
        ["", "Indicador", "", "", "Línea base", "", "", "Meta", ""],
        ["Tiempo de espera", None, None, "52 min", None, None, "≥ 20%", None, None],
        ["", None, None, "", None, None, "", None, None],
        ["", "Admisión", "", "", "14 min", "", "", "< 8 min", ""],
    ]
    assert clean_rows(raw) == [
        ["Indicador", "Línea base", "Meta"],
        ["Tiempo de espera", "52 min", "≥ 20%"],
        ["Admisión", "14 min", "< 8 min"],
    ]


def test_regular_table_is_left_untouched_except_whitespace():
    raw = [["Indicador", "Línea\nbase"], ["Tiempo de\naprobación", "12"]]
    assert clean_rows(raw) == [["Indicador", "Línea base"], ["Tiempo de aprobación", "12"]]


def test_merges_vertical_continuation_rows():
    raw = [
        ["Dato", "Detalle"],
        ["Cliente", "Clínica con 38 consultorios y"],
        ["", "60 camas"],
        ["Sector", "Salud"],
    ]
    assert clean_rows(raw) == [
        ["Dato", "Detalle"],
        ["Cliente", "Clínica con 38 consultorios y 60 camas"],
        ["Sector", "Salud"],
    ]


def test_markdown_escapes_pipes():
    markdown = rows_to_markdown([["a", "b"], ["x|y", "z"]])
    assert markdown.splitlines() == ["| a | b |", "|---|---|", "| x\\|y | z |"]
