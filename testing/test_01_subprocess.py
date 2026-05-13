"""
test_01_subprocess.py

Valida la columna subprocess (original) en tools.
subprocess_inferred es una columna de trabajo interna y NO se analiza aquí.

Checks:
  1. subprocess no tiene NULLs donde el valor original está disponible.
  2. Dentro de cada (vehicle_id, tool), la secuencia de subprocess original
     no tiene huecos (1, 2, 3 … sin saltos).
  3. subprocess es monotónicamente no-decreciente al ordenar por timestamp.
  4. El valor mínimo de subprocess en cada grupo es 1.
"""

from conftest import query_scalar


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — subprocess original: sin NULLs donde existe valor
# ─────────────────────────────────────────────────────────────────────────────

def test_subprocess_null_count(con):
    """
    Informa del porcentaje de NULLs en subprocess (columna original del dataset).
    Es normal que existan NULLs — sólo falla si el 100% son NULL (columna vacía).
    """
    null_count = query_scalar(con, "SELECT COUNT(*) FROM tools WHERE subprocess IS NULL")
    total = query_scalar(con, "SELECT COUNT(*) FROM tools")
    pct = null_count / total if total else 0
    print(f"\n  [INFO] subprocess NULLs: {null_count:,} / {total:,} ({pct*100:.1f}%)")
    assert pct < 1.0, "tools.subprocess es NULL en el 100% de las filas — columna vacía."


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — Sin huecos en la secuencia original (LAG diff == 0 o 1)
# ─────────────────────────────────────────────────────────────────────────────

def test_subprocess_no_gaps(con):
    """
    Dentro de cada (vehicle_id, tool), ordenado por timestamp, la diferencia
    entre valores consecutivos de subprocess debe ser 0 o 1 (nunca >1).
    Sólo se analizan filas donde subprocess no es NULL.
    """
    gap_count = query_scalar(
        con,
        """
        WITH lagged AS (
            SELECT
                subprocess,
                LAG(subprocess) OVER (
                    PARTITION BY vehicle_id, tool
                    ORDER BY timestamp
                ) AS prev_val
            FROM tools
            WHERE subprocess IS NOT NULL
        )
        SELECT COUNT(*)
        FROM lagged
        WHERE prev_val IS NOT NULL
          AND (subprocess - prev_val) > 1
        """,
    )
    assert gap_count == 0, (
        f"Se detectaron {gap_count:,} saltos (huecos) en subprocess. "
        "La secuencia debe ser continua dentro de cada (vehicle_id, tool)."
    )


def test_subprocess_starts_at_one(con):
    """
    El valor mínimo de subprocess en cada grupo (vehicle_id, tool) debe ser 1.
    Sólo se analizan grupos que tienen al menos un valor no-NULL.
    """
    bad_groups = query_scalar(
        con,
        """
        SELECT COUNT(*)
        FROM (
            SELECT MIN(subprocess) AS min_val
            FROM tools
            WHERE subprocess IS NOT NULL
            GROUP BY vehicle_id, tool
        )
        WHERE min_val != 1
        """,
    )
    assert bad_groups == 0, (
        f"{bad_groups:,} grupos (vehicle_id, tool) no empiezan en subprocess = 1."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — Monotonía con el timestamp
# ─────────────────────────────────────────────────────────────────────────────

def test_subprocess_monotone_with_timestamp(con):
    """
    Ordenando por timestamp, subprocess nunca debe decrecer dentro del mismo
    grupo (vehicle_id, tool). Sólo se analizan filas con subprocess no-NULL.
    """
    violations = query_scalar(
        con,
        """
        WITH lagged AS (
            SELECT
                subprocess,
                LAG(subprocess) OVER (
                    PARTITION BY vehicle_id, tool
                    ORDER BY timestamp
                ) AS prev_val
            FROM tools
            WHERE subprocess IS NOT NULL
        )
        SELECT COUNT(*)
        FROM lagged
        WHERE prev_val IS NOT NULL
          AND subprocess < prev_val
        """,
    )
    assert violations == 0, (
        f"{violations:,} filas tienen subprocess menor que el anterior "
        "al ordenar por timestamp. El contador no es monotónico."
    )
