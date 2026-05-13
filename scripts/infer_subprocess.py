"""
infer_subprocess.py
Infiere los subprocess faltantes basándose en cambios de timestamp.

Para los 134 tools que siempre tienen subprocess NULL, calcula el subprocess
como un contador incremental cada vez que cambia el timestamp dentro de (vehicle_id, tool).
Actualiza la columna subprocess con estos valores inferidos.

Uso: python3 infer_subprocess.py
"""

import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "ford_hackathon.db"


def connect():
    con = sqlite3.connect(str(DB_PATH))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def main():
    con = connect()
    
    # [1] Identificar tools con subprocess NULL o MIXTO
    print("[1] Identificando tools con subprocess NULL y MIXTO...")
    df_tools = pd.read_sql_query("""
        SELECT tool, COUNT(*) as total,
               SUM(CASE WHEN subprocess IS NULL THEN 1 ELSE 0 END) as null_count
        FROM tools
        GROUP BY tool
    """, con)
    
    always_null = df_tools[df_tools["null_count"] == df_tools["total"]]["tool"].tolist()
    mixed = df_tools[(df_tools["null_count"] > 0) & (df_tools["null_count"] < df_tools["total"])]["tool"].tolist()
    
    print(f"    {len(always_null)} tools con 100% subprocess NULL")
    print(f"    {len(mixed)} tools con MEZCLA NULL+valor\n")
    
    tools_to_infer = always_null + mixed
    
    # [2] Crear tabla temporal con subprocess_inferred
    print("[2] Calculando subprocess por cambios de timestamp...")
    
    all_updates = []
    for tool_id in tools_to_infer:
        # Cargar datos para este tool
        df_tool = pd.read_sql_query(f"""
            SELECT rowid as row_id, vehicle_id, timestamp, tool, subprocess
            FROM tools
            WHERE tool = '{tool_id}'
            ORDER BY vehicle_id, timestamp
        """, con)
        
        if len(df_tool) == 0:
            continue
        
        # Calcular subprocess_inferred: incrementa cuando cambia el timestamp dentro de cada VIN
        df_tool["subprocess_inferred"] = df_tool.groupby("vehicle_id")["timestamp"].transform(
            lambda x: (x != x.shift()).cumsum()
        )
        
        # Para tools mixtos: solo actualizar los que son NULL
        if tool_id in mixed:
            df_tool = df_tool[df_tool["subprocess"].isna()]
        
        all_updates.extend(list(zip(df_tool["subprocess_inferred"].astype(int), df_tool["row_id"])))
    
    print(f"    {len(all_updates):,} registros calculados")
    
    # [3] Actualizar la tabla tools
    print("\n[3] Actualizando tabla tools...")
    cursor = con.cursor()
    
    # Crear columna si no existe
    try:
        cursor.execute("ALTER TABLE tools ADD COLUMN subprocess_inferred INTEGER")
        con.commit()
        print("    Columna subprocess_inferred creada")
    except:
        print("    Columna subprocess_inferred ya existe")
    
    # Actualizar registros
    cursor.executemany(
        "UPDATE tools SET subprocess_inferred = ? WHERE rowid = ?",
        all_updates
    )
    con.commit()
    print(f"    {cursor.rowcount:,} registros actualizados\n")
    
    # [4] Validación
    print("[4] Validación final...")
    stats = pd.read_sql_query("""
        SELECT 
            COUNT(*) as total_rows,
            COUNT(CASE WHEN subprocess IS NOT NULL THEN 1 END) as with_original_sp,
            COUNT(CASE WHEN subprocess_inferred IS NOT NULL THEN 1 END) as with_inferred_sp,
            COUNT(DISTINCT CASE WHEN subprocess_inferred IS NOT NULL THEN tool END) as tools_inferred
        FROM tools
    """, con)
    print(stats.to_string(index=False))
    print(f"\n  Tools 100% NULL tratados: {len(always_null)}")
    print(f"  Tools MIXTOS tratados:    {len(mixed)}")
    print(f"  TOTAL tools con inferencia: {len(tools_to_infer)}")
    
    # [5] Sample de resultados
    print("\n[5] Muestra de registros procesados:")
    sample = pd.read_sql_query("""
        SELECT vehicle_id, tool, timestamp, subprocess, subprocess_inferred
        FROM tools
        WHERE subprocess_inferred IS NOT NULL
        ORDER BY RANDOM()
        LIMIT 15
    """, con)
    print(sample.to_string(index=False))
    
    con.close()
    print("\n✓ Completo!")


if __name__ == "__main__":
    main()
