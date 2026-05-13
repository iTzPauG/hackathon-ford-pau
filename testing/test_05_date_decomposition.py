"""
test_05_date_decomposition.py

Verifica que los campos ts_year, ts_month, ts_day, ts_hour (y ts_hour_min)
se han extraído correctamente del timestamp de cada tabla.

Estrategia:
  - Para tablas grandes (tools, operations) se valida con SQL puro usando
    las funciones strftime() de SQLite comparadas contra las columnas ts_*.
    Un mismatch indica que add_temporal_features.py no se ejecutó o lo hizo
    sobre datos distintos.
  - Se comprueba también que ts_hour_min concuerda con hora + minuto/60.
"""

import pytest
from conftest import query_scalar

# (tabla, columna_timestamp) — se usan para derivar ts_year/month/day/hour
TABLES_WITH_TS = [
    ("concerns",   "timestamp"),
    ("operations", "entered"),
    ("tools",      "timestamp"),
    ("stoppages",  "starttime"),
]


@pytest.mark.parametrize("table,ts_col", TABLES_WITH_TS, ids=[f"{t}" for t, _ in TABLES_WITH_TS])
def test_ts_year_matches_timestamp(con, table, ts_col):
    """ts_year debe coincidir con CAST(strftime('%Y', ts_col) AS INTEGER)."""
    bad = query_scalar(
        con,
        f"""
        SELECT COUNT(*)
        FROM {table}
        WHERE {ts_col} IS NOT NULL
          AND ts_year IS NOT NULL
          AND ts_year != CAST(strftime('%Y', {ts_col}) AS INTEGER)
        """,
    )
    assert bad == 0, f"{table}.ts_year: {bad:,} valores no coinciden con el año del timestamp"


@pytest.mark.parametrize("table,ts_col", TABLES_WITH_TS, ids=[f"{t}" for t, _ in TABLES_WITH_TS])
def test_ts_month_matches_timestamp(con, table, ts_col):
    """ts_month debe coincidir con CAST(strftime('%m', ts_col) AS INTEGER)."""
    bad = query_scalar(
        con,
        f"""
        SELECT COUNT(*)
        FROM {table}
        WHERE {ts_col} IS NOT NULL
          AND ts_month IS NOT NULL
          AND ts_month != CAST(strftime('%m', {ts_col}) AS INTEGER)
        """,
    )
    assert bad == 0, f"{table}.ts_month: {bad:,} valores no coinciden con el mes del timestamp"


@pytest.mark.parametrize("table,ts_col", TABLES_WITH_TS, ids=[f"{t}" for t, _ in TABLES_WITH_TS])
def test_ts_day_matches_timestamp(con, table, ts_col):
    """ts_day debe coincidir con CAST(strftime('%d', ts_col) AS INTEGER)."""
    bad = query_scalar(
        con,
        f"""
        SELECT COUNT(*)
        FROM {table}
        WHERE {ts_col} IS NOT NULL
          AND ts_day IS NOT NULL
          AND ts_day != CAST(strftime('%d', {ts_col}) AS INTEGER)
        """,
    )
    assert bad == 0, f"{table}.ts_day: {bad:,} valores no coinciden con el día del timestamp"


@pytest.mark.parametrize("table,ts_col", TABLES_WITH_TS, ids=[f"{t}" for t, _ in TABLES_WITH_TS])
def test_ts_hour_matches_timestamp(con, table, ts_col):
    """ts_hour debe coincidir con CAST(strftime('%H', ts_col) AS INTEGER)."""
    bad = query_scalar(
        con,
        f"""
        SELECT COUNT(*)
        FROM {table}
        WHERE {ts_col} IS NOT NULL
          AND ts_hour IS NOT NULL
          AND ts_hour != CAST(strftime('%H', {ts_col}) AS INTEGER)
        """,
    )
    assert bad == 0, f"{table}.ts_hour: {bad:,} valores no coinciden con la hora del timestamp"


@pytest.mark.parametrize("table,ts_col", TABLES_WITH_TS, ids=[f"{t}" for t, _ in TABLES_WITH_TS])
def test_ts_no_nulls_in_decomposed_cols(con, table, ts_col):
    """
    Si el timestamp no es NULL, los campos ts_year/month/day/hour tampoco
    deben ser NULL (la descomposición debe haberse ejecutado).
    """
    bad = query_scalar(
        con,
        f"""
        SELECT COUNT(*)
        FROM {table}
        WHERE {ts_col} IS NOT NULL
          AND (ts_year IS NULL OR ts_month IS NULL
               OR ts_day IS NULL OR ts_hour IS NULL)
        """,
    )
    assert bad == 0, (
        f"{table}: {bad:,} filas con timestamp válido pero campos ts_* NULL. "
        "Ejecuta scripts/add_temporal_features.py."
    )


@pytest.mark.parametrize("table,ts_col", TABLES_WITH_TS, ids=[f"{t}" for t, _ in TABLES_WITH_TS])
def test_ts_hour_min_matches(con, table, ts_col):
    """
    ts_hour_min = hour + minute/60 (redondeado a 4 decimales).
    Tolerancia: diferencia absoluta <= 0.02 (margen para float).
    """
    bad = query_scalar(
        con,
        f"""
        SELECT COUNT(*)
        FROM {table}
        WHERE {ts_col} IS NOT NULL
          AND ts_hour_min IS NOT NULL
          AND ABS(
              ts_hour_min - (
                  CAST(strftime('%H', {ts_col}) AS REAL)
                  + CAST(strftime('%M', {ts_col}) AS REAL) / 60.0
              )
          ) > 0.02
        """,
    )
    assert bad == 0, f"{table}.ts_hour_min: {bad:,} valores difieren de hora + min/60 por más de 0.02"


def test_ts_year_valid_range(con):
    """ts_year debe estar en el rango del dataset: 2024–2026."""
    for table in ["concerns", "operations", "tools", "stoppages"]:
        bad = query_scalar(
            con,
            f"SELECT COUNT(*) FROM {table} WHERE ts_year IS NOT NULL AND (ts_year < 2024 OR ts_year > 2026)",
        )
        assert bad == 0, f"{table}.ts_year: {bad:,} valores fuera del rango 2024–2026"


def test_ts_month_valid_range(con):
    """ts_month debe estar entre 1 y 12."""
    for table in ["concerns", "operations", "tools", "stoppages"]:
        bad = query_scalar(
            con,
            f"SELECT COUNT(*) FROM {table} WHERE ts_month IS NOT NULL AND (ts_month < 1 OR ts_month > 12)",
        )
        assert bad == 0, f"{table}.ts_month: {bad:,} valores fuera de [1, 12]"


def test_ts_day_valid_range(con):
    """ts_day debe estar entre 1 y 31."""
    for table in ["concerns", "operations", "tools", "stoppages"]:
        bad = query_scalar(
            con,
            f"SELECT COUNT(*) FROM {table} WHERE ts_day IS NOT NULL AND (ts_day < 1 OR ts_day > 31)",
        )
        assert bad == 0, f"{table}.ts_day: {bad:,} valores fuera de [1, 31]"


def test_ts_hour_valid_range(con):
    """ts_hour debe estar entre 0 y 23."""
    for table in ["concerns", "operations", "tools", "stoppages"]:
        bad = query_scalar(
            con,
            f"SELECT COUNT(*) FROM {table} WHERE ts_hour IS NOT NULL AND (ts_hour < 0 OR ts_hour > 23)",
        )
        assert bad == 0, f"{table}.ts_hour: {bad:,} valores fuera de [0, 23]"
