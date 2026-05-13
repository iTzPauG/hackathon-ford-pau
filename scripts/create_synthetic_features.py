"""
create_synthetic_features.py

Genera features sintéticas/derivadas para ML y añade la tabla line_daily.

Cambios en tabla OPERATIONS (columnas nuevas):
  - avg_complexity_vehicle   : media de complexity_factor del vehículo (histórico total)
  - total_complexity_vehicle : suma  de complexity_factor del vehículo (histórico total)
  - shift                    : 'mañana' (6-14h) | 'tarde' (14-22h) | 'noche' (22-6h)
  - day_of_week              : 0=lunes … 6=domingo (de 'entered')
  - position_in_day_line     : nº de vehículos distintos que pasaron por esa línea ese día
                               ANTES que este vehículo (0 = el primero del día)

Cambios en tabla TOOLS (columnas nuevas):
  - avg_complexity_vehicle      : ídem (procedente de operations)
  - total_complexity_vehicle    : ídem
  - shift                       : 'mañana' | 'tarde' | 'noche' (de 'timestamp')
  - day_of_week                 : 0=lunes … 6=domingo
  - position_in_day_tool        : nº de vehículos distintos en esa tool ese día antes
                                  que este vehículo (0 = el primero del día)
  - stoppage_time_accum_tool_day: suma de duration_s de paradas de vehículos que
                                  pasaron por esa tool ese día (segundos)

Nueva tabla LINE_DAILY:
  - line_id
  - date                      : 'YYYY-MM-DD'
  - vehicle_count             : vehículos distintos en esa línea ese día
  - stoppage_count            : nº de registros de stoppage de esos vehículos ese día
  - stoppage_time_accum       : suma duration_s de esas paradas (segundos)
  - avg_complexity_historical : complejidad media histórica (todos los días) de esa línea
  - accumulated_complexity_day: suma complexity_factor de esa línea ese día

NOTA: Las paradas no tienen campo line_id/tool directamente. Se asignan a la línea/tool
por pertenencia del vehículo: si un vehículo usó esa línea/tool ese día y tuvo paradas
ese día, se cuentan. Es una aproximación razonable para análisis operativo.

Uso:
    python3 scripts/create_synthetic_features.py
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
import time

DB_PATH = Path(__file__).parent.parent / "ford_hackathon.db"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def shift_from_hour(series: pd.Series) -> pd.Series:
    """Vectorizado: asigna turno a partir de la hora."""
    h = series.fillna(-1).astype(int)
    conditions = [(h >= 6) & (h < 14), (h >= 14) & (h < 22)]
    return np.select(conditions, ["mañana", "tarde"], default="noche")


def add_columns_if_missing(con: sqlite3.Connection, table: str, columns: dict):
    """ALTER TABLE ADD COLUMN sólo si la columna no existe. Idempotente."""
    existing = {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
    for col, dtype in columns.items():
        if col not in existing:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {dtype}")
            print(f"    + columna '{col}' añadida a {table}")
        else:
            print(f"    ~ columna '{col}' ya existía en {table}, se sobreescribirá")
    con.commit()


def bulk_update_via_temp(con: sqlite3.Connection, table: str,
                          df_update: pd.DataFrame, key_col: str = "rowid"):
    """
    Actualiza múltiples columnas de 'table' usando una tabla temporal.

    df_update debe contener key_col (rowid de la tabla destino) + las columnas a actualizar.
    Usa índice sobre _key para acelerar la UPDATE correlacionada.
    """
    value_cols = [c for c in df_update.columns if c != key_col]
    tmp_name = f"_tmp_{table}"

    # Renombramos key_col → _key para no colisionar con el rowid implícito de SQLite
    df_tmp = df_update.rename(columns={key_col: "_key"})

    print(f"    Escribiendo tabla temporal ({len(df_tmp):,} filas)…")
    t0 = time.time()
    df_tmp.to_sql(tmp_name, con, if_exists="replace", index=False)
    con.execute(f"CREATE INDEX idx_{tmp_name}_key ON {tmp_name} (_key)")

    sets = ",\n           ".join(
        f"{c} = (SELECT {c} FROM {tmp_name} t WHERE t._key = {table}.rowid)"
        for c in value_cols
    )
    print(f"    Ejecutando UPDATE…")
    con.execute(f"UPDATE {table} SET {sets}")
    con.execute(f"DROP TABLE IF EXISTS {tmp_name}")
    con.commit()
    print(f"    ✓ UPDATE completado en {time.time()-t0:.1f}s")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Operations
# ─────────────────────────────────────────────────────────────────────────────

def compute_operations_features(con: sqlite3.Connection):
    print("\n[1/3] OPERATIONS ─────────────────────────────────────────")

    add_columns_if_missing(con, "operations", {
        "avg_complexity_vehicle":   "REAL",
        "total_complexity_vehicle": "REAL",
        "shift":                    "TEXT",
        "day_of_week":              "INTEGER",
        "position_in_day_line":     "INTEGER",
    })

    print("  Cargando operations…")
    df = pd.read_sql_query(
        "SELECT rowid, vehicle_id, line_id, complexity_factor, entered, ts_hour "
        "FROM operations",
        con,
    )
    print(f"  {len(df):,} filas cargadas")

    # ── Fecha ────────────────────────────────────────────────────────────────
    df["date"] = df["entered"].str[:10]

    # ── avg / total complexity por vehículo ──────────────────────────────────
    print("  Calculando complejidad por vehículo…")
    veh_cx = (
        df.groupby("vehicle_id")["complexity_factor"]
        .agg(avg_complexity_vehicle="mean", total_complexity_vehicle="sum")
        .reset_index()
    )
    df = df.merge(veh_cx, on="vehicle_id", how="left")

    # ── Turno ────────────────────────────────────────────────────────────────
    df["shift"] = shift_from_hour(df["ts_hour"])

    # ── Día de la semana (0=lunes … 6=domingo) ───────────────────────────────
    df["day_of_week"] = pd.to_datetime(df["date"], errors="coerce").dt.dayofweek.astype("Int64")

    # ── Posición dentro del día por línea ────────────────────────────────────
    # Primera entrada del vehículo en esa línea ese día
    print("  Calculando position_in_day_line…")
    first_entry = (
        df.groupby(["vehicle_id", "line_id", "date"])["entered"]
        .min()
        .reset_index()
        .rename(columns={"entered": "_first_ts"})
    )
    first_entry["position_in_day_line"] = (
        first_entry.groupby(["line_id", "date"])["_first_ts"]
        .rank(method="dense")
        .astype(int) - 1          # 0 = primer vehículo del día en esa línea
    )
    df = df.merge(
        first_entry[["vehicle_id", "line_id", "date", "position_in_day_line"]],
        on=["vehicle_id", "line_id", "date"],
        how="left",
    )

    # ── Escribir de vuelta ───────────────────────────────────────────────────
    update_cols = ["rowid", "avg_complexity_vehicle", "total_complexity_vehicle",
                   "shift", "day_of_week", "position_in_day_line"]
    bulk_update_via_temp(con, "operations", df[update_cols].copy())


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tools
# ─────────────────────────────────────────────────────────────────────────────

def compute_tools_features(con: sqlite3.Connection):
    print("\n[2/3] TOOLS ──────────────────────────────────────────────")

    add_columns_if_missing(con, "tools", {
        "avg_complexity_vehicle":       "REAL",
        "total_complexity_vehicle":     "REAL",
        "shift":                        "TEXT",
        "day_of_week":                  "INTEGER",
        "position_in_day_tool":         "INTEGER",
        "stoppage_time_accum_tool_day": "REAL",
    })

    print("  Cargando tools…")
    df = pd.read_sql_query(
        "SELECT rowid, vehicle_id, tool, timestamp, ts_hour FROM tools",
        con,
    )
    print(f"  {len(df):,} filas cargadas")

    df["date"] = df["timestamp"].str[:10]

    # ── avg / total complexity por vehículo (desde operations) ───────────────
    print("  Cargando complejidad por vehículo desde operations…")
    veh_cx = pd.read_sql_query(
        "SELECT vehicle_id, "
        "AVG(complexity_factor) AS avg_complexity_vehicle, "
        "SUM(complexity_factor) AS total_complexity_vehicle "
        "FROM operations GROUP BY vehicle_id",
        con,
    )
    df = df.merge(veh_cx, on="vehicle_id", how="left")

    # ── Turno ────────────────────────────────────────────────────────────────
    df["shift"] = shift_from_hour(df["ts_hour"])

    # ── Día de la semana ─────────────────────────────────────────────────────
    df["day_of_week"] = pd.to_datetime(df["date"], errors="coerce").dt.dayofweek.astype("Int64")

    # ── Posición dentro del día por tool ─────────────────────────────────────
    print("  Calculando position_in_day_tool…")
    first_entry = (
        df.groupby(["vehicle_id", "tool", "date"])["timestamp"]
        .min()
        .reset_index()
        .rename(columns={"timestamp": "_first_ts"})
    )
    first_entry["position_in_day_tool"] = (
        first_entry.groupby(["tool", "date"])["_first_ts"]
        .rank(method="dense")
        .astype(int) - 1
    )
    df = df.merge(
        first_entry[["vehicle_id", "tool", "date", "position_in_day_tool"]],
        on=["vehicle_id", "tool", "date"],
        how="left",
    )

    # ── Tiempo de parada acumulado por tool y día ────────────────────────────
    # Lógica: vehículos que pasaron por esa tool ese día → sus stoppages de ese día
    print("  Calculando stoppage_time_accum_tool_day…")
    df_stop = pd.read_sql_query(
        "SELECT vehicle_id, starttime, duration_s FROM stoppages WHERE duration_s IS NOT NULL",
        con,
    )
    df_stop["date"] = df_stop["starttime"].str[:10]

    veh_tool_date = df[["vehicle_id", "tool", "date"]].drop_duplicates()
    stop_merged = veh_tool_date.merge(
        df_stop[["vehicle_id", "date", "duration_s"]],
        on=["vehicle_id", "date"],
        how="inner",
    )
    stop_tool_day = (
        stop_merged.groupby(["tool", "date"])["duration_s"]
        .sum()
        .reset_index()
        .rename(columns={"duration_s": "stoppage_time_accum_tool_day"})
    )
    df = df.merge(stop_tool_day, on=["tool", "date"], how="left")
    df["stoppage_time_accum_tool_day"] = df["stoppage_time_accum_tool_day"].fillna(0.0)

    # ── Escribir de vuelta ───────────────────────────────────────────────────
    update_cols = [
        "rowid", "avg_complexity_vehicle", "total_complexity_vehicle",
        "shift", "day_of_week", "position_in_day_tool", "stoppage_time_accum_tool_day",
    ]
    bulk_update_via_temp(con, "tools", df[update_cols].copy())


# ─────────────────────────────────────────────────────────────────────────────
# 3. Tabla line_daily
# ─────────────────────────────────────────────────────────────────────────────

def create_line_daily(con: sqlite3.Connection):
    print("\n[3/3] LINE_DAILY ─────────────────────────────────────────")

    print("  Cargando operations…")
    df_ops = pd.read_sql_query(
        "SELECT vehicle_id, line_id, complexity_factor, entered FROM operations",
        con,
    )
    df_ops["date"] = df_ops["entered"].str[:10]

    print("  Cargando stoppages…")
    df_stop = pd.read_sql_query(
        "SELECT vehicle_id, starttime, duration_s FROM stoppages WHERE duration_s IS NOT NULL",
        con,
    )
    df_stop["date"] = df_stop["starttime"].str[:10]

    # ── Agregados base por (line_id, date) ───────────────────────────────────
    print("  Calculando agregados por línea y día…")
    line_day = (
        df_ops.groupby(["line_id", "date"])
        .agg(
            vehicle_count=("vehicle_id", "nunique"),
            accumulated_complexity_day=("complexity_factor", "sum"),
        )
        .reset_index()
    )

    # ── Complejidad media histórica por línea (todos los tiempos) ─────────────
    hist_cx = (
        df_ops.groupby("line_id")["complexity_factor"]
        .mean()
        .reset_index()
        .rename(columns={"complexity_factor": "avg_complexity_historical"})
    )
    line_day = line_day.merge(hist_cx, on="line_id", how="left")

    # ── Stoppages atribuidas a línea por pertenencia de vehículo ese día ──────
    veh_line_date = df_ops[["vehicle_id", "line_id", "date"]].drop_duplicates()
    stop_merged = veh_line_date.merge(
        df_stop[["vehicle_id", "date", "duration_s"]],
        on=["vehicle_id", "date"],
        how="inner",
    )
    stop_line_day = (
        stop_merged.groupby(["line_id", "date"])
        .agg(
            stoppage_count=("duration_s", "count"),
            stoppage_time_accum=("duration_s", "sum"),
        )
        .reset_index()
    )
    line_day = line_day.merge(stop_line_day, on=["line_id", "date"], how="left")
    line_day["stoppage_count"]   = line_day["stoppage_count"].fillna(0).astype(int)
    line_day["stoppage_time_accum"] = line_day["stoppage_time_accum"].fillna(0.0)

    # ── Ordenar columnas de forma lógica ─────────────────────────────────────
    line_day = line_day[[
        "line_id", "date",
        "vehicle_count",
        "stoppage_count", "stoppage_time_accum",
        "avg_complexity_historical",
        "accumulated_complexity_day",
    ]]

    # ── Guardar en DB ─────────────────────────────────────────────────────────
    con.execute("DROP TABLE IF EXISTS line_daily")
    line_day.to_sql("line_daily", con, if_exists="replace", index=False)
    con.execute("CREATE INDEX idx_line_daily ON line_daily (line_id, date)")
    con.commit()

    print(f"  ✓ line_daily creada: {len(line_day):,} filas, "
          f"{line_day['line_id'].nunique()} líneas distintas, "
          f"{line_day['date'].nunique()} días distintos")
    print()
    print(line_day.describe(include="all").to_string())


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    t_start = time.time()
    print(f"Conectando a {DB_PATH} …")
    con = sqlite3.connect(str(DB_PATH), timeout=600)

    compute_operations_features(con)
    compute_tools_features(con)
    create_line_daily(con)

    con.close()
    elapsed = time.time() - t_start
    print(f"\n✓ Script completado en {elapsed/60:.1f} min")


if __name__ == "__main__":
    main()
