"""
add_temporal_features.py
Añade columnas de features temporales derivadas de los timestamps en ford_hackathon.db.

Columnas añadidas por tabla (si no existen ya):
  ─ Todas las tablas con timestamp ─────────────────────────────
    ts_year       INTEGER   → año                 (2025)
    ts_month      INTEGER   → mes                 (1-12)
    ts_day        INTEGER   → día del mes         (1-31)
    ts_hour       INTEGER   → hora                (0-23)
    ts_hour_min   REAL      → hora + minutos      (14.5 = 14:30)
    ts_ms         INTEGER   → milisegundos        (0-999)

  ─ Tablas con start/end (operations, stoppages) ───────────────
    duration_s    REAL      → duración en segundos

Tablas y columnas de origen:
  concerns   → timestamp
  tools      → timestamp
  operations → entered  (+ duration_s desde entered→exited)
  stoppages  → starttime (+ duration_s desde starttime→endtime)
"""

import sqlite3
import re
from pathlib import Path
from tqdm import tqdm

DB_PATH = Path(__file__).parent.parent / "ford_hackathon.db"

# (tabla, columna_ts, columna_start, columna_end)
# columna_start/end solo para tablas con duración
TABLES = [
    ("concerns",   "timestamp",  None,        None),
    ("tools",      "timestamp",  None,        None),
    ("operations", "entered",    "entered",   "exited"),
    ("stoppages",  "starttime",  "starttime", "endtime"),
]

TEMPORAL_COLS = [
    ("ts_year",     "INTEGER"),
    ("ts_month",    "INTEGER"),
    ("ts_day",      "INTEGER"),
    ("ts_hour",     "INTEGER"),
    ("ts_hour_min", "REAL"),
    ("ts_ms",       "INTEGER"),
]

DURATION_COL = ("duration_s", "REAL")


def parse_ts(val: str):
    """
    Parsea un timestamp ISO 8601 (2025-06-09T14:16:57.123Z) y devuelve
    (year, month, day, hour, hour_min, ms) o None si no parseable.
    """
    if not val:
        return None
    # Normalizar: reemplazar T/espacio, quitar Z/+00:00/UTC
    s = re.sub(r'[Zz]$', '', str(val).strip())
    s = re.sub(r'\+00:00$', '', s)
    s = re.sub(r'\s+UTC$', '', s)
    s = s.replace('T', ' ')

    # Extraer componentes
    m = re.match(
        r'(\d{4})-(\d{2})-(\d{2})\s(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?', s
    )
    if not m:
        return None

    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hour, minute, second = int(m.group(4)), int(m.group(5)), int(m.group(6))
    frac = m.group(7) or "0"
    ms = int(frac[:3].ljust(3, '0'))  # truncar a milisegundos

    hour_min = round(hour + minute / 60.0, 6)

    return (year, month, day, hour, hour_min, ms)


def duration_seconds(start: str, end: str) -> float | None:
    """Calcula duración en segundos entre dos timestamps ISO 8601."""
    if not start or not end:
        return None

    def to_seconds(val):
        p = parse_ts(val)
        if p is None:
            return None
        year, month, day, hour, _, _ = p
        # Reconstruir desde los componentes originales
        s = re.sub(r'[Zz\+].*$', '', re.sub(r'\s+UTC$', '', str(val).strip()))
        s = s.replace('T', ' ')
        m = re.match(r'(\d{4})-(\d{2})-(\d{2})[\sT](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?', s)
        if not m:
            return None
        Y, M, D = int(m.group(1)), int(m.group(2)), int(m.group(3))
        h, mi, sec = int(m.group(4)), int(m.group(5)), int(m.group(6))
        frac = m.group(7) or "0"
        ms_val = int(frac[:3].ljust(3, '0')) / 1000.0
        # Convertir a segundos desde epoch simplificado con datetime
        from datetime import datetime
        try:
            dt = datetime(Y, M, D, h, mi, sec)
            return dt.timestamp() + ms_val
        except Exception:
            return None

    t1 = to_seconds(start)
    t2 = to_seconds(end)
    if t1 is None or t2 is None:
        return None
    diff = t2 - t1
    return round(diff, 3) if diff >= 0 else None


def ensure_columns(con: sqlite3.Connection, table: str, has_duration: bool):
    """Añade las columnas si no existen ya."""
    existing = {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
    added = []

    for col_name, col_type in TEMPORAL_COLS:
        if col_name not in existing:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
            added.append(col_name)

    if has_duration and DURATION_COL[0] not in existing:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {DURATION_COL[0]} {DURATION_COL[1]}")
        added.append(DURATION_COL[0])

    if added:
        con.commit()
        print(f"  Columnas añadidas: {added}")
    else:
        print(f"  Columnas ya existentes, sobreescribiendo valores...")


def process_table(con: sqlite3.Connection, table: str, ts_col: str,
                  start_col: str | None, end_col: str | None):
    print(f"\n[{table}]")
    ensure_columns(con, table, has_duration=start_col is not None)

    # Leer solo columnas necesarias
    extra_cols = ""
    if start_col and end_col and start_col != ts_col:
        extra_cols = f", {end_col}"
    elif start_col and end_col:
        extra_cols = f", {end_col}"

    rows = con.execute(
        f"SELECT rowid, {ts_col}{extra_cols} FROM {table}"
    ).fetchall()

    updates = []
    for row in rows:
        rowid = row[0]
        ts_val = row[1]
        end_val = row[2] if len(row) > 2 else None

        parsed = parse_ts(ts_val)
        if parsed:
            year, month, day, hour, hour_min, ms = parsed
        else:
            year = month = day = hour = hour_min = ms = None

        dur = None
        if start_col and end_col:
            start_v = ts_val
            end_v = end_val
            dur = duration_seconds(start_v, end_v)

        updates.append((year, month, day, hour, hour_min, ms, dur, rowid))

    # Actualizar en lotes
    batch_size = 10000
    set_clause = "ts_year=?, ts_month=?, ts_day=?, ts_hour=?, ts_hour_min=?, ts_ms=?"
    if start_col:
        set_clause += ", duration_s=?"
        with tqdm(total=len(updates), desc=f"  Actualizando", unit="filas", leave=False) as pbar:
            for i in range(0, len(updates), batch_size):
                batch = updates[i:i + batch_size]
                con.executemany(
                    f"UPDATE {table} SET {set_clause} WHERE rowid=?", batch
                )
                pbar.update(len(batch))
    else:
        # Sin duración: quitar el campo dur del tuple
        updates_no_dur = [(y, mo, d, h, hm, ms, rid) for y, mo, d, h, hm, ms, _, rid in updates]
        with tqdm(total=len(updates_no_dur), desc=f"  Actualizando", unit="filas", leave=False) as pbar:
            for i in range(0, len(updates_no_dur), batch_size):
                batch = updates_no_dur[i:i + batch_size]
                con.executemany(
                    f"UPDATE {table} SET {set_clause} WHERE rowid=?", batch
                )
                pbar.update(len(batch))

    con.commit()
    print(f"  ✓ {len(updates):,} filas procesadas")

    # Verificación rápida
    sample = con.execute(
        f"SELECT {ts_col}, ts_year, ts_month, ts_day, ts_hour, ts_hour_min, ts_ms"
        + (", duration_s" if start_col else "")
        + f" FROM {table} WHERE {ts_col} IS NOT NULL LIMIT 2"
    ).fetchall()
    print(f"  Ejemplos:")
    for r in sample:
        print(f"    {r}")


def main():
    con = sqlite3.connect(str(DB_PATH))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")

    print("=" * 60)
    print("  AÑADIENDO FEATURES TEMPORALES — ford_hackathon.db")
    print("=" * 60)

    for table, ts_col, start_col, end_col in TABLES:
        process_table(con, table, ts_col, start_col, end_col)

    con.close()
    print("\n" + "=" * 60)
    print("  ✓ Completo!")
    print("=" * 60)
    print("\nColumnas añadidas en cada tabla:")
    print("  ts_year, ts_month, ts_day, ts_hour, ts_hour_min, ts_ms")
    print("  duration_s  (solo en operations y stoppages)")


if __name__ == "__main__":
    main()
