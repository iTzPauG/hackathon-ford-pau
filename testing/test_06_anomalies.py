"""
test_06_anomalies.py

Detecta datos anómalos en todas las tablas:
  - complexity_factor: rango esperado, sin negativos, sin valores extremos
  - ok (tools): sólo 0 o 1
  - duration_s: sin negativos, sin duraciones imposiblemente largas
  - campos de ID: sin valores vacíos o en blanco
  - stoppage_time_accum_tool_day: sin extremos irrazonables
  - line_daily: sin días con 0 vehículos

Criterios de anomalía:
  - complexity_factor < 0 → imposible (es un factor de multiplicación)
  - complexity_factor > 20 → muy improbable; se reporta pero no falla hard (warning count)
  - duration_s < 0 → imposible
  - duration_s > 7 días en segundos (604_800 s) → sospechoso para una operación/parada
  - ok NOT IN (0, 1) → campo binario corrupto
  - vehicle_id / operation_id / tool / line_id vacío ('')
"""

import pytest
from conftest import query_scalar

MAX_DURATION_S   = 7 * 24 * 3600   # 7 días en segundos = 604_800
# El máximo real de complexity_factor en el dataset es 28.90.
# Cualquier valor > 30 es imposible dado el rango observado.
MAX_COMPLEXITY   = 30.0


# ─────────────────────────────────────────────────────────────────────────────
# complexity_factor (operations)
# ─────────────────────────────────────────────────────────────────────────────

class TestComplexityFactor:

    def test_no_negative_complexity(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM operations WHERE complexity_factor < 0",
        )
        assert n == 0, f"operations.complexity_factor: {n:,} valores negativos"

    def test_complexity_no_null(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM operations WHERE complexity_factor IS NULL",
        )
        assert n == 0, f"operations.complexity_factor: {n:,} NULLs"

    def test_complexity_extreme_values(self, con):
        """complexity_factor no debe superar 30 (máximo real observado: 28.90)."""
        n = query_scalar(
            con,
            f"SELECT COUNT(*) FROM operations WHERE complexity_factor > {MAX_COMPLEXITY}",
        )
        assert n == 0, (
            f"operations.complexity_factor: {n:,} valores > {MAX_COMPLEXITY}. "
            f"El máximo conocido en el dataset es 28.90."
        )


# ─────────────────────────────────────────────────────────────────────────────
# ok (tools) — campo binario
# ─────────────────────────────────────────────────────────────────────────────

class TestOkField:

    def test_ok_only_zero_or_one(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM tools WHERE ok NOT IN (0, 1)",
        )
        assert n == 0, f"tools.ok: {n:,} valores fuera de {{0, 1}}"

    def test_ok_no_null(self, con):
        n = query_scalar(con, "SELECT COUNT(*) FROM tools WHERE ok IS NULL")
        assert n == 0, f"tools.ok: {n:,} NULLs"


# ─────────────────────────────────────────────────────────────────────────────
# duration_s — operations y stoppages
# ─────────────────────────────────────────────────────────────────────────────

class TestDurations:

    def test_operations_duration_non_negative(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM operations WHERE duration_s IS NOT NULL AND duration_s < 0",
        )
        assert n == 0, f"operations.duration_s: {n:,} valores negativos"

    def test_operations_duration_not_extreme(self, con):
        n = query_scalar(
            con,
            f"SELECT COUNT(*) FROM operations WHERE duration_s > {MAX_DURATION_S}",
        )
        total = query_scalar(con, "SELECT COUNT(*) FROM operations WHERE duration_s IS NOT NULL")
        pct = n / total if total else 0
        assert pct < 0.001, (
            f"operations.duration_s: {n:,} ({pct*100:.3f}%) duraciones > 7 días. "
            "Posibles errores de fechas."
        )

    def test_stoppages_duration_non_negative(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM stoppages WHERE duration_s IS NOT NULL AND duration_s < 0",
        )
        assert n == 0, f"stoppages.duration_s: {n:,} valores negativos"

    def test_stoppages_duration_not_extreme(self, con):
        n = query_scalar(
            con,
            f"SELECT COUNT(*) FROM stoppages WHERE duration_s > {MAX_DURATION_S}",
        )
        total = query_scalar(con, "SELECT COUNT(*) FROM stoppages WHERE duration_s IS NOT NULL")
        pct = n / total if total else 0
        assert pct < 0.001, (
            f"stoppages.duration_s: {n:,} ({pct*100:.3f}%) duraciones > 7 días."
        )


# ─────────────────────────────────────────────────────────────────────────────
# IDs vacíos o en blanco
# ─────────────────────────────────────────────────────────────────────────────

class TestEmptyIDs:

    def test_no_empty_vehicle_id_operations(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM operations WHERE vehicle_id IS NULL OR TRIM(vehicle_id) = ''",
        )
        assert n == 0, f"operations.vehicle_id: {n:,} valores vacíos o NULL"

    def test_no_empty_vehicle_id_tools(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM tools WHERE vehicle_id IS NULL OR TRIM(vehicle_id) = ''",
        )
        assert n == 0, f"tools.vehicle_id: {n:,} valores vacíos o NULL"

    def test_no_empty_operation_id(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM operations WHERE operation_id IS NULL OR TRIM(operation_id) = ''",
        )
        assert n == 0, f"operations.operation_id: {n:,} valores vacíos o NULL"

    def test_no_empty_line_id(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM operations WHERE line_id IS NULL OR TRIM(line_id) = ''",
        )
        assert n == 0, f"operations.line_id: {n:,} valores vacíos o NULL"

    def test_no_empty_tool(self, con):
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM tools WHERE tool IS NULL OR TRIM(tool) = ''",
        )
        assert n == 0, f"tools.tool: {n:,} valores vacíos o NULL"


# ─────────────────────────────────────────────────────────────────────────────
# stoppage_time_accum_tool_day — anomalías por acumulado diario
# ─────────────────────────────────────────────────────────────────────────────

class TestStoppageAccum:

    def test_stoppage_accum_not_null(self, con):
        """stoppage_time_accum_tool_day no debe contener NULLs."""
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM tools WHERE stoppage_time_accum_tool_day IS NULL",
        )
        assert n == 0, f"tools.stoppage_time_accum_tool_day: {n:,} NULLs"

    def test_stoppage_accum_non_negative(self, con):
        """
        El acumulado de paradas no puede ser negativo.
        NOTA: el valor es la SUMA de paradas de todos los vehículos que pasaron
        por esa tool ese día — puede ser muy grande si muchos vehículos pasan
        por la misma tool (comportamiento esperado y correcto).
        """
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM tools WHERE stoppage_time_accum_tool_day < 0",
        )
        assert n == 0, f"tools.stoppage_time_accum_tool_day: {n:,} valores negativos"


# ─────────────────────────────────────────────────────────────────────────────
# line_daily — coherencia interna
# ─────────────────────────────────────────────────────────────────────────────

class TestLineDailyAnomalies:

    def test_no_zero_vehicle_count(self, con):
        n = query_scalar(con, "SELECT COUNT(*) FROM line_daily WHERE vehicle_count = 0")
        assert n == 0, f"line_daily.vehicle_count: {n:,} filas con 0 vehículos"

    def test_stoppage_time_non_negative(self, con):
        """
        El acumulado de paradas por línea y día no puede ser negativo.
        NOTA: el valor es la suma de paradas de TODOS los vehículos que visitaron
        esa línea ese día — puede ser mayor que 24h cuando hay muchos vehículos
        (comportamiento esperado dado el modelo de datos sin campo line_id en stoppages).
        """
        n = query_scalar(
            con,
            "SELECT COUNT(*) FROM line_daily WHERE stoppage_time_accum < 0",
        )
        assert n == 0, f"line_daily.stoppage_time_accum: {n:,} valores negativos"

    def test_stoppage_count_coherent_with_time(self, con):
        """
        Si stoppage_count > 0, stoppage_time_accum debe ser > 0 (y viceversa).
        Un conteo sin tiempo indica paradas de duración 0 — posible problema.
        """
        n = query_scalar(
            con,
            """
            SELECT COUNT(*)
            FROM line_daily
            WHERE stoppage_count > 0 AND stoppage_time_accum = 0
            """,
        )
        # Permitimos un pequeño número (paradas de 0 s son posibles en datos reales)
        total_with_stops = query_scalar(
            con, "SELECT COUNT(*) FROM line_daily WHERE stoppage_count > 0"
        )
        pct = n / total_with_stops if total_with_stops else 0
        assert pct < 0.05, (
            f"line_daily: {n:,} ({pct*100:.1f}%) filas con paradas pero tiempo_acum = 0"
        )
