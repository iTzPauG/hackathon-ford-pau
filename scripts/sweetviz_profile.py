"""
sweetviz_profile.py
Genera reportes HTML interactivos con Sweetviz para cada tabla de ford_hackathon.db.
Salida: profile_report/sweetviz_<tabla>.html
"""

import os
import sqlite3
import pandas as pd
import sweetviz as sv

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "ford_hackathon.db")
OUT_DIR = os.path.join(os.path.dirname(__file__), "profile_report")
os.makedirs(OUT_DIR, exist_ok=True)

TABLES = ["concerns", "operations", "stoppages", "tools", "vehicle_features"]


def load(table: str) -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as con:
        return pd.read_sql_query(f"SELECT * FROM {table}", con)


def main():
    for table in TABLES:
        print(f"[{table}] cargando datos...")
        df = load(table)
        print(f"  {len(df):,} filas × {len(df.columns)} columnas")

        report = sv.analyze(df, pairwise_analysis="off")
        out_path = os.path.join(OUT_DIR, f"sweetviz_{table}.html")
        report.show_html(out_path, open_browser=False)
        print(f"  → {out_path}")

    print("\nListo. Abre los HTML en profile_report/")


if __name__ == "__main__":
    main()
