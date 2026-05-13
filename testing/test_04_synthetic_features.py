"""
test_04_synthetic_features.py

Verifica que todas las features sintéticas generadas por
create_synthetic_features.py están presentes y son coherentes.

Checks por tabla:
  operations:
    - avg_complexity_vehicle, total_complexity_vehicle: no nulos, > 0
    - shift: sólo 'mañana', 'tarde', 'noche' — ningún NULL
    - day_of_week: 0–6 — ningún NULL
    - position_in_day_line: >= 0 — ningún NULL

  tools:
    - avg_complexity_vehicle, total_complexity_vehicle: no nulos
    - shift: sólo 'mañana', 'tarde', 'noche'
    - day_of_week: 0–6
    - position_in_day_tool: >= 0
    - stoppage_time_accum_tool_day: >= 0 — ningún NULL

  line_daily:
    - vehicle_count: >= 1
    - stoppage_count: >= 0
    - stoppage_time_accum: >= 0
    - avg_complexity_historical: > 0
    - accumulated_complexity_day: > 0
    - clave (line_id, date) única
"""

import pytest
from conftest import query_scalar

VALID_SHIFTS = ("'mañana'", "'tarde'", "'noche'")


# ─────────────────────────────────────────────────────────────────────────────
# OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

class TestOperationsSyntheticFeatures:

    def test_avg_complexity_no_null(self, con):
        n = query_scalar(con, "SELECT COUNT(*) FROM operations WHERE avg_complexity_vehicle IS NULL")
        assert n == 0, f"operations.avg_complexity_vehicle: {n:,} NULLs"

    def test_total_complexity_no_null(self, con):
        n = query_scalar(con, "SELECT COUNT(*) FROM operations WHERE total_complexity_vehicle IS NULL")
        assert n == 0, f"operations.total_complexity_vehicle: {n:,} NULLs"

    def test_avg_complexity_positive(self, con):
        n = query_scalar(con, "SELECT COUNT(*) FROM operations WHERE avg_complexity_vehicle <= 0")
        assert n == 0, f"operations.avg_complexity_vehicle: {n:,} valores <= 0"

    def test_shift_no_null(self, con):
        n = query_scalar(con, "SELECT COUNT(*) FROM operations WHERE shift IS NULL")
        assert n == 0, f"operations.shift: {n:,} NULLs"

    def test_shift_valid_values(self, con):
        valid = ", ".join(VALID_SHIFTS)
        n = query_scalar(
            con,
            f"SELECT COUNT(*) FROM operations WHERE shift NOT IN ({valid})",
        )
        assert n == 0, f"operations.shift: {n:,} valores fuera de {{mañana, tarde, noche}}"

    def test_day_of_week_no_null(self, con):
        n = query_scalar(con, "SELECT COUNT(*) FROM operations WHERE day_of_week IS NULL")
        assert n == 0, f"operations.day_of_week: {n:,} NULLs"

    def test_day_of_week_range(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM operations WHERE day_of_week < 0 OR day_of_week > 6",
        )
        assert n == 0, f"operations.day_of_week: {n:,} valores fuera de [0, 6]"

    def test_position_in_day_line_no_null(self, con):
        n = query_scalar(con, "SELECT COUNT(*) FROM operations WHERE position_in_day_line IS NULL")
        assert n == 0, f"operations.position_in_day_line: {n:,} NULLs"

    def test_position_in_day_line_non_negative(self, con):
        n = query_scalar(con, "SELECT COUNT(*) FROM operations WHERE position_in_day_line < 0")
        assert n == 0, f"operations.position_in_day_line: {n:,} valores negativos"


# ─────────────────────────────────────────────────────────────────────────────
# TOOLS
# ─────────────────────────────────────────────────────────────────────────────

class TestToolsSyntheticFeatures:

    def test_avg_complexity_no_null(self, con):
        """
        Vehículos que sólo están en tools pero no en operations tendrán NULL.
        Se verifica que los que sí tienen operations no tienen NULL.
        """
        n = query_scalar(
            con,
            """
            SELECT COUNT(*)
            FROM tools t
            WHERE t.avg_complexity_vehicle IS NULL
              AND EXISTS (
                  SELECT 1 FROM operations o WHERE o.vehicle_id = t.vehicle_id
              )
            """,
        )
        assert n == 0, (
            f"tools.avg_complexity_vehicle: {n:,} filas con NULL pese a tener "
            "operaciones disponibles."
        )

    def test_shift_no_null(self, con):
        n = query_scalar(con, "SELECT COUNT(*) FROM tools WHERE shift IS NULL")
        assert n == 0, f"tools.shift: {n:,} NULLs"

    def test_shift_valid_values(self, con):
        valid = ", ".join(VALID_SHIFTS)
        n = query_scalar(con, f"SELECT COUNT(*) FROM tools WHERE shift NOT IN ({valid})")
        assert n == 0, f"tools.shift: {n:,} valores fuera de {{mañana, tarde, noche}}"

    def test_day_of_week_range(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM tools WHERE day_of_week < 0 OR day_of_week > 6",
        )
        assert n == 0, f"tools.day_of_week: {n:,} valores fuera de [0, 6]"

    def test_position_in_day_tool_non_negative(self, con):
        n = query_scalar(con, "SELECT COUNT(*) FROM tools WHERE position_in_day_tool < 0")
        assert n == 0, f"tools.position_in_day_tool: {n:,} valores negativos"

    def test_stoppage_time_no_null(self, con):
        n = query_scalar(con, "SELECT COUNT(*) FROM tools WHERE stoppage_time_accum_tool_day IS NULL")
        assert n == 0, f"tools.stoppage_time_accum_tool_day: {n:,} NULLs"

    def test_stoppage_time_non_negative(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM tools WHERE stoppage_time_accum_tool_day < 0",
        )
        assert n == 0, f"tools.stoppage_time_accum_tool_day: {n:,} valores negativos"


# ─────────────────────────────────────────────────────────────────────────────
# LINE_DAILY
# ─────────────────────────────────────────────────────────────────────────────

class TestLineDailyTable:

    def test_table_exists_and_not_empty(self, con):
        n = query_scalar(con, "SELECT COUNT(*) FROM line_daily")
        assert n > 0, "line_daily está vacía o no existe."

    def test_vehicle_count_positive(self, con):
        n = query_scalar(con, "SELECT COUNT(*) FROM line_daily WHERE vehicle_count < 1")
        assert n == 0, f"line_daily.vehicle_count: {n:,} filas con valor < 1"

    def test_stoppage_count_non_negative(self, con):
        n = query_scalar(con, "SELECT COUNT(*) FROM line_daily WHERE stoppage_count < 0")
        assert n == 0, f"line_daily.stoppage_count: {n:,} valores negativos"

    def test_stoppage_time_non_negative(self, con):
        n = query_scalar(con, "SELECT COUNT(*) FROM line_daily WHERE stoppage_time_accum < 0")
        assert n == 0, f"line_daily.stoppage_time_accum: {n:,} valores negativos"

    def test_avg_complexity_historical_positive(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM line_daily WHERE avg_complexity_historical <= 0",
        )
        assert n == 0, f"line_daily.avg_complexity_historical: {n:,} valores <= 0"

    def test_accumulated_complexity_day_positive(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM line_daily WHERE accumulated_complexity_day <= 0",
        )
        assert n == 0, f"line_daily.accumulated_complexity_day: {n:,} valores <= 0"

    def test_date_format(self, con):
        """La columna date debe seguir el formato YYYY-MM-DD."""
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM line_daily WHERE date NOT GLOB '????-??-??'",
        )
        assert n == 0, f"line_daily.date: {n:,} valores con formato incorrecto (esperado YYYY-MM-DD)"

    def test_no_duplicate_line_date(self, con):
        n = query_scalar(
            con,
            """
            SELECT COUNT(*) FROM (
                SELECT line_id, date, COUNT(*) AS c
                FROM line_daily
                GROUP BY line_id, date
                HAVING c > 1
            )
            """,
        )
        assert n == 0, f"line_daily: {n:,} combinaciones (line_id, date) duplicadas"

    def test_no_null_keys(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM line_daily WHERE line_id IS NULL OR date IS NULL",
        )
        assert n == 0, f"line_daily: {n:,} filas con line_id o date NULL"
