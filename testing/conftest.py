"""
conftest.py — Fixtures compartidas para todos los tests.

Conexión a la base de datos SQLite y utilidades comunes.
"""

import sqlite3
from pathlib import Path

import pytest

DB_PATH = Path(__file__).parent.parent / "ford_hackathon.db"

# Número de filas a muestrear en validaciones pesadas (None = todas)
SAMPLE_SIZE = 50_000


@pytest.fixture(scope="session")
def con():
    """Conexión SQLite compartida durante toda la sesión de tests."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def query_scalar(conn: sqlite3.Connection, sql: str, params=()) -> int | float | None:
    """Ejecuta una consulta y devuelve el primer valor de la primera fila."""
    return conn.execute(sql, params).fetchone()[0]
