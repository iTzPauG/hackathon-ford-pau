"""
gx_profile.py
Genera un reporte Data Docs de Great Expectations para cada tabla de ford_hackathon.db.
Salida: scripts/gx_profile/  (abre gx_profile/uncommitted/data_docs/local_site/index.html)
"""

import os
import sqlite3
import pandas as pd
import great_expectations as gx
from great_expectations.core.expectation_suite import ExpectationSuite
from great_expectations.core.validation_definition import ValidationDefinition
from great_expectations.checkpoint import Checkpoint

DB_PATH  = os.path.join(os.path.dirname(__file__), "..", "ford_hackathon.db")
GX_DIR   = os.path.join(os.path.dirname(__file__), "gx_profile")
TABLES   = ["concerns", "operations", "stoppages", "tools", "vehicle_features"]


def load(table: str) -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as con:
        return pd.read_sql_query(f"SELECT * FROM {table}", con)


def add_expectations(suite: ExpectationSuite, df: pd.DataFrame):
    """Añade expectativas automáticas según tipo de columna."""
    import great_expectations.expectations as gxe

    for col in df.columns:
        series = df[col].dropna()

        # columna no vacía
        suite.add_expectation(gxe.ExpectColumnToExist(column=col))

        null_pct = df[col].isna().mean()
        if null_pct == 0:
            suite.add_expectation(gxe.ExpectColumnValuesToNotBeNull(column=col))

        # numérica
        if pd.api.types.is_numeric_dtype(df[col]) and len(series) > 0:
            suite.add_expectation(gxe.ExpectColumnValuesToBeBetween(
                column=col,
                min_value=float(series.min()),
                max_value=float(series.max()),
            ))
            suite.add_expectation(gxe.ExpectColumnMeanToBeBetween(
                column=col,
                min_value=float(series.mean() * 0.5),
                max_value=float(series.mean() * 1.5),
            ))

        # categórica de baja cardinalidad
        elif pd.api.types.is_object_dtype(df[col]):
            n_unique = df[col].nunique()
            if n_unique <= 50:
                suite.add_expectation(gxe.ExpectColumnValuesToBeInSet(
                    column=col,
                    value_set=list(series.unique()),
                ))
            suite.add_expectation(gxe.ExpectColumnValueLengthsToBeBetween(
                column=col,
                min_value=1,
            ))


def main():
    os.makedirs(GX_DIR, exist_ok=True)
    context = gx.get_context(mode="file", project_root_dir=GX_DIR)

    # Fuente de datos pandas reutilizable
    try:
        ds = context.data_sources.add_pandas(name="sqlite_pandas")
    except Exception:
        ds = context.data_sources.get("sqlite_pandas")

    validation_defs = []

    for table in TABLES:
        print(f"[{table}] cargando…")
        df = load(table)
        print(f"  {len(df):,} filas × {len(df.columns)} columnas")

        # Asset + batch
        try:
            asset = ds.add_dataframe_asset(name=table)
        except Exception:
            asset = ds.get_asset(table)

        try:
            batch_def = asset.add_batch_definition_whole_dataframe(f"{table}_batch")
        except Exception:
            batch_def = asset.get_batch_definition(f"{table}_batch")

        # Suite de expectativas
        suite_name = f"suite_{table}"
        try:
            context.suites.delete(suite_name)
        except Exception:
            pass
        suite = context.suites.add(ExpectationSuite(name=suite_name))
        add_expectations(suite, df)
        print(f"  {len(suite.expectations)} expectativas generadas")

        # Definición de validación
        vd_name = f"vd_{table}"
        try:
            context.validation_definitions.delete(vd_name)
        except Exception:
            pass
        vd = context.validation_definitions.add(
            ValidationDefinition(name=vd_name, data=batch_def, suite=suite)
        )
        validation_defs.append((vd, df))

    # Checkpoint único con todas las tablas
    cp_name = "ford_checkpoint"
    try:
        context.checkpoints.delete(cp_name)
    except Exception:
        pass
    checkpoint = context.checkpoints.add(
        Checkpoint(name=cp_name, validation_definitions=[vd for vd, _ in validation_defs])
    )

    print("\nEjecutando validaciones…")
    # Pasamos los dataframes como batch_parameters por validación
    batch_params = {
        vd.name: {"dataframe": df}
        for vd, df in validation_defs
    }
    result = checkpoint.run(batch_parameters=batch_params)

    # Data Docs
    context.build_data_docs()
    docs_path = os.path.join(
        GX_DIR, "uncommitted", "data_docs", "local_site", "index.html"
    )
    print(f"\nData Docs generados → {docs_path}")
    os.system(f"open '{docs_path}'")


if __name__ == "__main__":
    main()
