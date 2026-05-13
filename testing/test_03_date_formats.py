"""
test_03_date_formats.py

Verifica que todos los campos de timestamp siguen el formato ISO 8601
normalizado: YYYY-MM-DDTHH:MM:SS.mmmZ

Columnas auditadas:
  - concerns.timestamp
  - operations.entered / operations.exited
  - tools.timestamp
  - stoppages.starttime / stoppages.endtime
"""

import pytest
from conftest import query_scalar

# Patrón SQLite (GLOB): 19 chars de fecha/hora + punto + 3 dígitos + Z
# Equivale al regex: ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$
ISO8601_GLOB = "????-??-??T??:??:??.???Z"

# Columnas a validar por tabla
TIMESTAMP_COLS = [
    ("concerns",   "timestamp"),
    ("operations", "entered"),
    ("operations", "exited"),
    ("tools",      "timestamp"),
    ("stoppages",  "starttime"),
    ("stoppages",  "endtime"),
]


@pytest.mark.parametrize("table,col", TIMESTAMP_COLS, ids=[f"{t}.{c}" for t, c in TIMESTAMP_COLS])
def test_timestamp_format_iso8601(con, table, col):
    """
    Ningún valor no-nulo debe incumplir el patrón YYYY-MM-DDTHH:MM:SS.mmmZ.
    Usa GLOB de SQLite para la comprobación eficiente sin cargar datos en Python.
    """
    bad_count = query_scalar(
        con,
        f"""
        SELECT COUNT(*)
        FROM {table}
        WHERE {col} IS NOT NULL
          AND {col} NOT GLOB '{ISO8601_GLOB}'
        """,
    )
    assert bad_count == 0, (
        f"{table}.{col}: {bad_count:,} valores no cumplen el formato ISO 8601 "
        f"'{ISO8601_GLOB}'. Ejecuta scripts/normalize_timestamps.py."
    )


@pytest.mark.parametrize("table,col", TIMESTAMP_COLS, ids=[f"{t}.{c}" for t, c in TIMESTAMP_COLS])
def test_timestamp_no_null(con, table, col):
    """
    Los campos de timestamp no deben contener NULLs (son campos obligatorios).
    """
    null_count = query_scalar(
        con,
        f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL",
    )
    assert null_count == 0, (
        f"{table}.{col}: {null_count:,} valores NULL encontrados."
    )


def test_timestamps_within_valid_range(con):
    """
    Los timestamps deben estar en el rango conocido del dataset:
    entre 2024-01-01 y 2026-12-31.
    Fechas fuera de rango indican datos corruptos o errores de normalización.
    """
    checks = [
        ("concerns",   "timestamp"),
        ("operations", "entered"),
        ("tools",      "timestamp"),
        ("stoppages",  "starttime"),
    ]
    for table, col in checks:
        out_of_range = query_scalar(
            con,
            f"""
            SELECT COUNT(*)
            FROM {table}
            WHERE {col} IS NOT NULL
              AND ({col} < '2024-01-01T00:00:00.000Z'
                OR {col} > '2026-12-31T23:59:59.999Z')
            """,
        )
        assert out_of_range == 0, (
            f"{table}.{col}: {out_of_range:,} timestamps fuera del rango "
            "2024-01-01 – 2026-12-31."
        )


def test_entered_before_exited(con):
    """operations.entered debe ser siempre <= operations.exited (sin operaciones invertidas)."""
    inverted = query_scalar(
        con,
        """
        SELECT COUNT(*)
        FROM operations
        WHERE entered IS NOT NULL AND exited IS NOT NULL
          AND entered > exited
        """,
    )
    assert inverted == 0, (
        f"operations: {inverted:,} filas con entered > exited (tiempo invertido)."
    )


def test_starttime_before_endtime(con):
    """stoppages.starttime debe ser siempre <= stoppages.endtime."""
    inverted = query_scalar(
        con,
        """
        SELECT COUNT(*)
        FROM stoppages
        WHERE starttime IS NOT NULL AND endtime IS NOT NULL
          AND starttime > endtime
        """,
    )
    assert inverted == 0, (
        f"stoppages: {inverted:,} filas con starttime > endtime (parada invertida)."
    )
