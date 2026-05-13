"""
normalize_timestamps.py
Normaliza todos los timestamps de ford_hackathon.db al formato ISO 8601:
    2025-06-09T14:16:57.000Z

Tablas y columnas afectadas:
  - operations : entered, exited   → "2025-06-09 14:16:57.915252+00:00"
  - stoppages  : starttime, endtime → "2025-06-09 16:47:15.000000 UTC"
  - tools      : timestamp          → "2025-06-08 15:25:56+00:00"

concerns.timestamp ya está en el formato correcto → se omite.
"""

import sqlite3
import re
from pathlib import Path
from datetime import datetime, timezone
from tqdm import tqdm

DB_PATH = Path(__file__).parent.parent / "ford_hackathon.db"

# (tabla, [columnas])
TABLES_TO_NORMALIZE = {
    "operations": ["entered", "exited"],
    "stoppages":  ["starttime", "endtime"],
    "tools":      ["timestamp"],
}


def parse_to_utc(value: str) -> str:
    """
    Parsea cualquiera de los tres formatos detectados y devuelve
    la cadena en formato ISO 8601: 2025-06-09T14:16:57.000Z
    """
    if not value or not isinstance(value, str):
        return value

    s = value.strip()

    # Quitar sufijo " UTC" → "2025-06-09 16:47:15.000000"
    s = re.sub(r'\s+UTC$', '', s)

    # Reemplazar espacio separador por T si no hay T ya
    if 'T' not in s:
        s = s.replace(' ', 'T', 1)

    # Normalizar zona horaria:
    #   "+00:00" → "Z"
    s = re.sub(r'\+00:00$', 'Z', s)

    # Si aún no termina en Z, añadirlo (caso sin zona horaria explícita)
    if not s.endswith('Z'):
        s += 'Z'

    # Normalizar microsegundos/milisegundos a exactamente 3 dígitos
    # Detectar ".NNNNNN" o ".NNN" antes de Z
    m = re.match(r'^(.+T\d{2}:\d{2}:\d{2})\.(\d+)Z$', s)
    if m:
        base, frac = m.group(1), m.group(2)
        ms = frac[:3].ljust(3, '0')   # truncar a 3 dígitos
        s = f"{base}.{ms}Z"
    else:
        # Sin fracción de segundo → añadir .000
        m2 = re.match(r'^(.+T\d{2}:\d{2}:\d{2})Z$', s)
        if m2:
            s = f"{m2.group(1)}.000Z"

    return s


def normalize_column(con: sqlite3.Connection, table: str, col: str) -> int:
    """Actualiza en lotes la columna col de table. Devuelve el nº de filas actualizadas."""
    cursor = con.cursor()

    # Leer todos los rowid + valor actuales que no están ya en formato correcto
    rows = cursor.execute(
        f"SELECT rowid, {col} FROM {table} WHERE {col} IS NOT NULL"
    ).fetchall()

    updates = []
    for rowid, val in rows:
        normalized = parse_to_utc(val)
        if normalized != val:
            updates.append((normalized, rowid))

    if not updates:
        print(f"  ✓ {table}.{col}: ya normalizado")
        return 0

    batch_size = 5000
    with tqdm(total=len(updates), desc=f"  {table}.{col}", unit="filas", leave=False) as pbar:
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]
            cursor.executemany(
                f"UPDATE {table} SET {col} = ? WHERE rowid = ?", batch
            )
            pbar.update(len(batch))

    con.commit()
    return len(updates)


def verify(con: sqlite3.Connection, table: str, col: str):
    """Muestra algunos ejemplos post-normalización para validación visual."""
    samples = con.execute(
        f"SELECT DISTINCT {col} FROM {table} LIMIT 4"
    ).fetchall()
    for (v,) in samples:
        print(f"    {v}")


def main():
    con = sqlite3.connect(str(DB_PATH))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")

    print("=" * 60)
    print("  NORMALIZACIÓN DE TIMESTAMPS — ford_hackathon.db")
    print("=" * 60)

    total_updated = 0
    for table, cols in TABLES_TO_NORMALIZE.items():
        print(f"\n[{table}]")
        for col in cols:
            updated = normalize_column(con, table, col)
            if updated:
                print(f"  ✓ {table}.{col}: {updated:,} filas actualizadas")
                print(f"    Ejemplos post-normalización:")
                verify(con, table, col)
            total_updated += updated

    con.close()

    print("\n" + "=" * 60)
    print(f"  Total filas normalizadas: {total_updated:,}")
    print("=" * 60)
    print("\n✓ Completo!")


if __name__ == "__main__":
    main()
