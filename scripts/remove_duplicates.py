"""
remove_duplicates.py
Elimina duplicados de todas las tablas de ford_hackathon.db.

Por tabla:
  - concerns: duplicados por (vehicle_id, timestamp, point, section, cause, concern)
  - operations: duplicados por (vehicle_id, operation_id)
  - stoppages: duplicados por (vehicle_id, description, code, starttime, endtime)
  - tools: duplicados por (vehicle_id, tool, timestamp, ok)

Mantiene el primer registro (rowid menor) y elimina los posteriores.
"""

import sqlite3
import pandas as pd
from pathlib import Path
from tqdm import tqdm

DB_PATH = Path(__file__).parent.parent / "ford_hackathon.db"

# Define duplicate keys por tabla
DUPLICATE_KEYS = {
    "concerns": ["vehicle_id", "timestamp", "point", "section", "cause", "concern"],
    "operations": ["vehicle_id", "operation_id"],
    "stoppages": ["vehicle_id", "description", "code", "starttime", "endtime"],
    "tools": ["vehicle_id", "tool", "timestamp", "ok"],
    "vehicle_features": ["vehicle_id", "feature"],
}


def connect():
    con = sqlite3.connect(str(DB_PATH))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def remove_duplicates_for_table(con, table, key_cols):
    """
    Elimina duplicados en una tabla manteniendo el primer registro (rowid menor).
    """
    print(f"\n[{table}]")
    
    # Contar duplicados con GROUP BY
    key_list = ", ".join(key_cols)
    query_count = f"""
        SELECT COUNT(*) - COUNT(DISTINCT {key_list}) as duplicates_count
        FROM (
            SELECT {key_list} FROM {table}
        )
    """
    # Mejor: contar grupos con más de 1 registro
    query_count = f"""
        SELECT SUM(cnt - 1) as duplicates_count
        FROM (
            SELECT COUNT(*) as cnt
            FROM {table}
            GROUP BY {key_list}
            HAVING COUNT(*) > 1
        )
    """
    dup_count = pd.read_sql_query(query_count, con).iloc[0, 0]
    if dup_count is None:
        dup_count = 0
    print(f"  Duplicados encontrados: {dup_count}")
    
    if dup_count == 0:
        print(f"  ✓ Sin duplicados")
        return 0
    
    # Identificar rowids a eliminar (mantener el primero de cada grupo)
    # Usar CTE con ROW_NUMBER() para eficiencia (mucho más rápido que correlated subqueries)
    key_list = ", ".join(key_cols)
    query_dup_ids = f"""
        WITH ranked AS (
            SELECT rowid, ROW_NUMBER() OVER (PARTITION BY {key_list} ORDER BY rowid) as rn
            FROM {table}
        )
        SELECT rowid FROM ranked WHERE rn > 1
    """
    
    dup_rowids = pd.read_sql_query(query_dup_ids, con)["rowid"].tolist()
    
    if len(dup_rowids) == 0:
        print(f"  ✓ Sin duplicados para eliminar")
        return 0
    
    # Eliminar con barra de progreso (en lotes)
    batch_size = 10000
    cursor = con.cursor()
    
    with tqdm(total=len(dup_rowids), desc=f"  Eliminando", leave=False, unit="registros") as pbar:
        for i in range(0, len(dup_rowids), batch_size):
            batch = dup_rowids[i:i+batch_size]
            placeholders = ",".join("?" * len(batch))
            cursor.execute(f"DELETE FROM {table} WHERE rowid IN ({placeholders})", batch)
            pbar.update(len(batch))
    
    con.commit()
    
    print(f"  ✓ Eliminados: {len(dup_rowids):,} registros")
    return len(dup_rowids)


def main():
    con = connect()
    
    print("=" * 60)
    print("  ELIMINANDO DUPLICADOS — ford_hackathon.db")
    print("=" * 60)
    
    # Contar registros antes
    print("\n[ANTES]")
    totals_before = {}
    for table in tqdm(DUPLICATE_KEYS.keys(), desc="Contando antes", unit="tabla", leave=False):
        count = pd.read_sql_query(f"SELECT COUNT(*) as n FROM {table}", con).iloc[0, 0]
        totals_before[table] = count
        print(f"  {table:20s}: {count:,} registros")
    
    # Eliminar duplicados por tabla
    print("\n[ELIMINANDO]")
    total_deleted = 0
    for table, key_cols in tqdm(DUPLICATE_KEYS.items(), desc="Procesando tablas", unit="tabla"):
        deleted = remove_duplicates_for_table(con, table, key_cols)
        total_deleted += deleted
    
    # Contar registros después
    print("\n[DESPUÉS]")
    totals_after = {}
    for table in tqdm(DUPLICATE_KEYS.keys(), desc="Contando después", unit="tabla", leave=False):
        count = pd.read_sql_query(f"SELECT COUNT(*) as n FROM {table}", con).iloc[0, 0]
        totals_after[table] = count
        diff = totals_before[table] - count
        pct = (diff / totals_before[table] * 100) if totals_before[table] > 0 else 0
        status = f"  {table:20s}: {count:,} registros"
        if diff > 0:
            status += f"  (-{diff:,}, -{pct:.2f}%)"
        print(status)
    
    con.close()
    
    print("\n" + "=" * 60)
    print(f"  Total eliminados: {total_deleted:,} registros")
    print("=" * 60)
    print("\n✓ Completo!")


if __name__ == "__main__":
    main()
