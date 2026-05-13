"""
test_07_durations.py

Verifica que los campos duration_s se han calculado correctamente:
  - operations.duration_s  = (exited  - entered)   en segundos
  - stoppages.duration_s   = (endtime - starttime)  en segundos

SQLite no tiene función nativa de diferencia de timestamps, así que se usa
strftime('%s', ...) para convertir a Unix epoch y restar.

Tolerancia: ±1 segundo (diferencias de redondeo de milisegundos al parsear).
"""

import pytest
from conftest import query_scalar

TOLERANCE_S = 1.0  # segundos de margen por redondeo de ms


# ─────────────────────────────────────────────────────────────────────────────
# operations.duration_s
# ─────────────────────────────────────────────────────────────────────────────

class TestOperationsDuration:

    def test_duration_no_null_when_both_timestamps_present(self, con):
        """Si entered y exited existen, duration_s no debe ser NULL."""
        n = query_scalar(
            con,
            """
            SELECT COUNT(*)
            FROM operations
            WHERE entered IS NOT NULL
              AND exited  IS NOT NULL
              AND duration_s IS NULL
            """,
        )
        assert n == 0, (
            f"operations: {n:,} filas con entered+exited presentes pero duration_s NULL. "
            "Ejecuta scripts/add_temporal_features.py."
        )

    def test_duration_matches_timestamp_diff(self, con):
        """
        duration_s debe coincidir (±TOLERANCE_S) con (exited - entered) en segundos.
        Usa strftime('%s') para el cálculo en SQLite.
        La diferencia real incluye milisegundos; la tolerancia cubre esa imprecisión.
        """
        bad = query_scalar(
            con,
            f"""
            SELECT COUNT(*)
            FROM operations
            WHERE entered IS NOT NULL
              AND exited   IS NOT NULL
              AND duration_s IS NOT NULL
              AND ABS(
                  duration_s
                  - (
                      CAST(strftime('%s', exited)  AS REAL)
                      - CAST(strftime('%s', entered) AS REAL)
                      + (
                          CAST(substr(exited,  21, 3) AS REAL) / 1000.0
                        - CAST(substr(entered, 21, 3) AS REAL) / 1000.0
                      )
                  )
              ) > {TOLERANCE_S}
            """,
        )
        assert bad == 0, (
            f"operations.duration_s: {bad:,} valores difieren de (exited - entered) "
            f"por más de {TOLERANCE_S} s."
        )

    def test_duration_non_negative(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM operations WHERE duration_s IS NOT NULL AND duration_s < 0",
        )
        assert n == 0, f"operations.duration_s: {n:,} valores negativos"

    def test_duration_zero_only_when_equal_timestamps(self, con):
        """
        duration_s = 0 sólo es válido si entered == exited exactamente.
        Un valor 0 con timestamps distintos indica un error de cálculo.
        """
        n = query_scalar(
            con,
            """
            SELECT COUNT(*)
            FROM operations
            WHERE duration_s = 0
              AND entered != exited
            """,
        )
        assert n == 0, (
            f"operations: {n:,} filas con duration_s = 0 pero entered ≠ exited"
        )


# ─────────────────────────────────────────────────────────────────────────────
# stoppages.duration_s
# ─────────────────────────────────────────────────────────────────────────────

class TestStoppagesDuration:

    def test_duration_no_null_when_both_timestamps_present(self, con):
        """Si starttime y endtime existen, duration_s no debe ser NULL."""
        n = query_scalar(
            con,
            """
            SELECT COUNT(*)
            FROM stoppages
            WHERE starttime IS NOT NULL
              AND endtime    IS NOT NULL
              AND duration_s IS NULL
            """,
        )
        assert n == 0, (
            f"stoppages: {n:,} filas con starttime+endtime presentes pero duration_s NULL."
        )

    def test_duration_matches_timestamp_diff(self, con):
        """
        duration_s debe coincidir (±TOLERANCE_S) con (endtime - starttime) en segundos.
        """
        bad = query_scalar(
            con,
            f"""
            SELECT COUNT(*)
            FROM stoppages
            WHERE starttime IS NOT NULL
              AND endtime    IS NOT NULL
              AND duration_s IS NOT NULL
              AND ABS(
                  duration_s
                  - (
                      CAST(strftime('%s', endtime)   AS REAL)
                      - CAST(strftime('%s', starttime) AS REAL)
                      + (
                          CAST(substr(endtime,   21, 3) AS REAL) / 1000.0
                        - CAST(substr(starttime, 21, 3) AS REAL) / 1000.0
                      )
                  )
              ) > {TOLERANCE_S}
            """,
        )
        assert bad == 0, (
            f"stoppages.duration_s: {bad:,} valores difieren de (endtime - starttime) "
            f"por más de {TOLERANCE_S} s."
        )

    def test_duration_non_negative(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM stoppages WHERE duration_s IS NOT NULL AND duration_s < 0",
        )
        assert n == 0, f"stoppages.duration_s: {n:,} valores negativos"

    def test_duration_zero_only_when_equal_timestamps(self, con):
        n = query_scalar(
            con,
            """
            SELECT COUNT(*)
            FROM stoppages
            WHERE duration_s = 0
              AND starttime != endtime
            """,
        )
        assert n == 0, (
            f"stoppages: {n:,} filas con duration_s = 0 pero starttime ≠ endtime"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Coherencia cruzada
# ─────────────────────────────────────────────────────────────────────────────

def test_operations_avg_duration_reasonable(con):
    """
    La duración media de una operación debe estar en un rango plausible:
    entre 10 segundos y 4 horas (14,400 s).
    Un valor fuera de ese rango sugiere errores sistemáticos en las fechas.
    """
    avg = query_scalar(
        con,
        "SELECT AVG(duration_s) FROM operations WHERE duration_s IS NOT NULL AND duration_s >= 0",
    )
    assert avg is not None, "No se pudo calcular AVG de operations.duration_s"
    assert 10 <= avg <= 14_400, (
        f"operations.duration_s media = {avg:.1f} s — fuera del rango esperado [10 s, 4 h]"
    )


def test_stoppages_avg_duration_reasonable(con):
    """
    La duración media de una parada debe estar entre 1 segundo y 8 horas (28,800 s).
    """
    avg = query_scalar(
        con,
        "SELECT AVG(duration_s) FROM stoppages WHERE duration_s IS NOT NULL AND duration_s >= 0",
    )
    assert avg is not None, "No se pudo calcular AVG de stoppages.duration_s"
    assert 1 <= avg <= 28_800, (
        f"stoppages.duration_s media = {avg:.1f} s — fuera del rango esperado [1 s, 8 h]"
    )
