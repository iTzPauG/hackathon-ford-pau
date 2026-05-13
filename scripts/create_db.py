"""
create_db.py
Imports all Hackaton Ford 2026 CSV files into a local SQLite database.

Tables created:
  - concerns      (index, vehicle_id, timestamp, point, section, cause, concern)
  - vehicle_features  (vehicle_id, feature)   -- normalised from features.csv
  - operations    (vehicle_id, operation_id, department_id, line_id, complexity_factor, entered, exited)
  - stoppages     (vehicle_id, description, code, starttime, endtime)
  - tools         (vehicle_id, tool, timestamp, subprocess, ok, concern)
"""

import sqlite3
import csv
import re
import os
import sys

DATA_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "Hackaton Ford 2026")
DB_PATH = os.path.join(os.path.dirname(__file__), "ford_hackathon.db")

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def progress(msg: str):
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# table creation
# ---------------------------------------------------------------------------

DDL = {
    "concerns": """
        CREATE TABLE IF NOT EXISTS concerns (
            id              INTEGER PRIMARY KEY,
            vehicle_id      TEXT,
            timestamp       TEXT,
            point           TEXT,
            section         TEXT,
            cause           TEXT,
            concern         TEXT
        )
    """,
    "vehicle_features": """
        CREATE TABLE IF NOT EXISTS vehicle_features (
            vehicle_id  TEXT NOT NULL,
            feature     TEXT NOT NULL,
            PRIMARY KEY (vehicle_id, feature)
        )
    """,
    "operations": """
        CREATE TABLE IF NOT EXISTS operations (
            vehicle_id          TEXT,
            operation_id        TEXT,
            department_id       TEXT,
            line_id             TEXT,
            complexity_factor   REAL,
            entered             TEXT,
            exited              TEXT
        )
    """,
    "stoppages": """
        CREATE TABLE IF NOT EXISTS stoppages (
            vehicle_id  TEXT,
            description TEXT,
            code        TEXT,
            starttime   TEXT,
            endtime     TEXT
        )
    """,
    "tools": """
        CREATE TABLE IF NOT EXISTS tools (
            vehicle_id  TEXT,
            tool        TEXT,
            timestamp   TEXT,
            subprocess  INTEGER,
            ok          INTEGER,
            concern     TEXT
        )
    """,
}


# ---------------------------------------------------------------------------
# loaders
# ---------------------------------------------------------------------------

BATCH = 50_000


def load_concerns(con: sqlite3.Connection, data_dir: str):
    path = os.path.join(data_dir, "concerns.csv")
    progress(f"Loading concerns from {path} ...")
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append((
                row.get("") or None,       # original index column
                row["vehicle_id"],
                row["timestamp"],
                row["point"],
                row["section"],
                row["cause"],
                row["concern"],
            ))
            if len(rows) >= BATCH:
                con.executemany(
                    "INSERT INTO concerns VALUES (?,?,?,?,?,?,?)", rows
                )
                con.commit()
                rows = []
    if rows:
        con.executemany("INSERT INTO concerns VALUES (?,?,?,?,?,?,?)", rows)
        con.commit()
    progress("  concerns: done")


def parse_feature_list(raw: str) -> list[str]:
    """Parse a Python-style list string: ['A' 'B' 'C'] -> ['A', 'B', 'C']"""
    return re.findall(r"'(FEATURE-[^']+)'", raw)


def load_features(con: sqlite3.Connection, data_dir: str):
    path = os.path.join(data_dir, "features.csv")
    progress(f"Loading vehicle_features from {path} ...")
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            vehicle_id = row["vehicle_id"]
            features = parse_feature_list(row["feature"])
            for feat in features:
                rows.append((vehicle_id, feat))
            if len(rows) >= BATCH:
                con.executemany(
                    "INSERT OR IGNORE INTO vehicle_features VALUES (?,?)", rows
                )
                con.commit()
                rows = []
    if rows:
        con.executemany(
            "INSERT OR IGNORE INTO vehicle_features VALUES (?,?)", rows
        )
        con.commit()
    progress("  vehicle_features: done")


def load_operations(con: sqlite3.Connection, data_dir: str):
    path = os.path.join(data_dir, "operations.csv")
    progress(f"Loading operations from {path} ...")
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cf = row["complexity_factor"]
            rows.append((
                row["vehicle_id"],
                row["operation_id"],
                row["department_id"],
                row["line_id"],
                float(cf) if cf else None,
                row["entered"],
                row["exited"],
            ))
            if len(rows) >= BATCH:
                con.executemany(
                    "INSERT INTO operations VALUES (?,?,?,?,?,?,?)", rows
                )
                con.commit()
                rows = []
    if rows:
        con.executemany("INSERT INTO operations VALUES (?,?,?,?,?,?,?)", rows)
        con.commit()
    progress("  operations: done")


def load_stoppages(con: sqlite3.Connection, data_dir: str):
    path = os.path.join(data_dir, "stoppages.csv")
    progress(f"Loading stoppages from {path} ...")
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append((
                row["vehicle_id"],
                row["description"],
                row["code"] or None,
                row["starttime"],
                row["endtime"],
            ))
            if len(rows) >= BATCH:
                con.executemany(
                    "INSERT INTO stoppages VALUES (?,?,?,?,?)", rows
                )
                con.commit()
                rows = []
    if rows:
        con.executemany("INSERT INTO stoppages VALUES (?,?,?,?,?)", rows)
        con.commit()
    progress("  stoppages: done")


def load_tools(con: sqlite3.Connection, data_dir: str):
    path = os.path.join(data_dir, "tools.csv")
    progress(f"Loading tools from {path} ...")
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ok_val = row["ok"]
            rows.append((
                row["vehicle_id"],
                row["tool"],
                row["timestamp"],
                int(row["subprocess"]) if row["subprocess"] else None,
                1 if ok_val.strip().lower() == "true" else 0 if ok_val.strip().lower() == "false" else None,
                row["concern"] or None,
            ))
            if len(rows) >= BATCH:
                con.executemany(
                    "INSERT INTO tools VALUES (?,?,?,?,?,?)", rows
                )
                con.commit()
                rows = []
    if rows:
        con.executemany("INSERT INTO tools VALUES (?,?,?,?,?,?)", rows)
        con.commit()
    progress("  tools: done")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        progress(f"Removed existing database at {DB_PATH}")

    con = connect(DB_PATH)

    progress("Creating tables...")
    for name, ddl in DDL.items():
        con.execute(ddl)
    con.commit()

    load_concerns(con, DATA_DIR)
    load_features(con, DATA_DIR)
    load_operations(con, DATA_DIR)
    load_stoppages(con, DATA_DIR)
    load_tools(con, DATA_DIR)

    progress("\nRow counts:")
    for table in DDL.keys():
        (n,) = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        progress(f"  {table}: {n:,}")

    con.close()
    progress(f"\nDatabase saved to: {DB_PATH}")


if __name__ == "__main__":
    main()
