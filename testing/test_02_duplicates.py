"""
test_02_duplicates.py

Verifica que no hay filas duplicadas en ninguna tabla,
usando las claves de negocio de cada una.

Claves de deduplicación (definidas en remove_duplicates.py):
  - concerns        : (vehicle_id, timestamp, point, section, cause, concern)
  - operations      : (vehicle_id, operation_id)
  - stoppages       : (vehicle_id, description, code, starttime, endtime)
  - tools           : (vehicle_id, tool, timestamp, ok)
  - vehicle_features: (vehicle_id, feature)
  - line_daily      : (line_id, date)
"""

import pytest
from conftest import query_scalar


# Definición de cada tabla: (nombre, lista de columnas clave)
DUPLICATE_CHECKS = [
    (
        "concerns",
        ["vehicle_id", "timestamp", "point", "section", "cause", "concern"],
    ),
    (
        "operations",
        ["vehicle_id", "operation_id"],
    ),
    (
        "stoppages",
        ["vehicle_id", "description", "code", "starttime", "endtime"],
    ),
    (
        "tools",
        ["vehicle_id", "tool", "timestamp", "ok"],
    ),
    (
        "vehicle_features",
        ["vehicle_id", "feature"],
    ),
    (
        "line_daily",
        ["line_id", "date"],
    ),
]


@pytest.mark.parametrize("table,key_cols", DUPLICATE_CHECKS, ids=[t for t, _ in DUPLICATE_CHECKS])
def test_no_duplicates(con, table, key_cols):
    """
    Para cada tabla, la combinación de columnas clave debe ser única.
    Si hay duplicados, el COUNT de grupos con más de 1 fila debe ser 0.
    """
    key_expr = ", ".join(key_cols)
    dup_count = query_scalar(
        con,
        f"""
        SELECT COUNT(*)
        FROM (
            SELECT {key_expr}, COUNT(*) AS n
            FROM {table}
            GROUP BY {key_expr}
            HAVING n > 1
        )
        """,
    )
    assert dup_count == 0, (
        f"Tabla '{table}': {dup_count:,} combinaciones de clave ({key_expr}) "
        "tienen más de una fila. Ejecuta scripts/remove_duplicates.py."
    )


def test_no_duplicates_total_row_count(con):
    """
    Sanity check: muestra el recuento total de filas por tabla
    para detectar regresiones (reinserciones masivas accidentales).

    Umbrales basados en los valores conocidos tras la limpieza:
      concerns        ~  84,751
      operations      ~ 2,117,067
      stoppages       ~  84,193
      tools           ~ 7,045,685
      vehicle_features ~ 4,392,768
    """
    expected_max = {
        "concerns":         100_000,
        "operations":     2_500_000,
        "stoppages":        100_000,
        "tools":          8_000_000,
        "vehicle_features": 5_000_000,
    }
    for table, max_rows in expected_max.items():
        count = query_scalar(con, f"SELECT COUNT(*) FROM {table}")
        assert count <= max_rows, (
            f"Tabla '{table}' tiene {count:,} filas — supera el máximo esperado "
            f"{max_rows:,}. ¿Se han insertado filas duplicadas?"
        )
