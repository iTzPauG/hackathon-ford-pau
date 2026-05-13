"""
profile_db.py
Deep profiling of ford_hackathon.db — nulls, duplicates, time formats, ID types, distributions.
Outputs: profile_report/  (PNG charts + summary printed to stdout)
"""

import sqlite3
import re
import os
import warnings
from collections import defaultdict

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns

warnings.filterwarnings("ignore")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "ford_hackathon.db")
OUT_DIR = os.path.join(os.path.dirname(__file__), "profile_report")
os.makedirs(OUT_DIR, exist_ok=True)

sns.set_theme(style="darkgrid", palette="muted")
PALETTE = sns.color_palette("muted")

# ── helpers ──────────────────────────────────────────────────────────────────

def con():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def q(sql, params=()):
    with con() as c:
        return pd.read_sql_query(sql, c, params=params)

def save(fig, name):
    path = os.path.join(OUT_DIR, name)
    fig.savefig(path, bbox_inches="tight", dpi=130)
    plt.close(fig)
    print(f"  saved → {name}")

TABLES = {
    "concerns":         ["id","vehicle_id","timestamp","point","section","cause","concern"],
    "vehicle_features": ["vehicle_id","feature"],
    "operations":       ["vehicle_id","operation_id","department_id","line_id","complexity_factor","entered","exited"],
    "stoppages":        ["vehicle_id","description","code","starttime","endtime"],
    "tools":            ["vehicle_id","tool","timestamp","subprocess","ok","concern"],
}

TIME_COLS = {
    "concerns":   ["timestamp"],
    "operations": ["entered","exited"],
    "stoppages":  ["starttime","endtime"],
    "tools":      ["timestamp"],
}

# ── 1. Row counts ─────────────────────────────────────────────────────────────

def plot_row_counts():
    print("\n[1] Row counts")
    counts = {}
    for t in TABLES:
        n = q(f"SELECT COUNT(*) AS n FROM {t}").iloc[0]["n"]
        counts[t] = n
        print(f"  {t}: {n:,}")

    fig, ax = plt.subplots(figsize=(9, 4))
    bars = ax.barh(list(counts.keys()), list(counts.values()), color=PALETTE[:len(counts)])
    ax.bar_label(bars, labels=[f"{v:,}" for v in counts.values()], padding=4, fontsize=9)
    ax.set_xlabel("Row count")
    ax.set_title("Row counts per table")
    ax.invert_yaxis()
    save(fig, "01_row_counts.png")
    return counts

# ── 2. Null / missing values ──────────────────────────────────────────────────

def plot_nulls():
    print("\n[2] Null / empty values")
    null_pct = {}
    for table, cols in TABLES.items():
        total = q(f"SELECT COUNT(*) AS n FROM {table}").iloc[0]["n"]
        pct = {}
        for col in cols:
            n = q(f"SELECT COUNT(*) AS n FROM {table} WHERE {col} IS NULL OR TRIM(CAST({col} AS TEXT))=''").iloc[0]["n"]
            pct[col] = round(100 * n / total, 2) if total else 0
        null_pct[table] = pct
        print(f"  {table}: { {k:v for k,v in pct.items() if v>0} or 'no nulls'}")

    fig, axes = plt.subplots(1, len(TABLES), figsize=(18, 5), sharey=False)
    for ax, (table, pct) in zip(axes, null_pct.items()):
        cols = list(pct.keys())
        vals = list(pct.values())
        colors = ["#e74c3c" if v > 0 else "#2ecc71" for v in vals]
        ax.barh(cols, vals, color=colors)
        ax.set_xlim(0, max(max(null_pct[t].values() or [0]) for t in null_pct) + 5)
        ax.set_title(table, fontsize=10)
        ax.set_xlabel("% null/empty")
        ax.invert_yaxis()
    fig.suptitle("Null / empty values (%) per column", fontsize=13, y=1.02)
    plt.tight_layout()
    save(fig, "02_nulls.png")
    return null_pct

# ── 3. Duplicate analysis ─────────────────────────────────────────────────────

def plot_duplicates():
    print("\n[3] Duplicate rows")
    dup_info = {}

    pk_keys = {
        "concerns":         ["vehicle_id","timestamp","point","cause","concern"],
        "vehicle_features": ["vehicle_id","feature"],
        "operations":       ["vehicle_id","operation_id"],
        "stoppages":        ["vehicle_id","starttime","endtime","description"],
        "tools":            ["vehicle_id","tool","timestamp","subprocess"],
    }

    for table, keys in pk_keys.items():
        key_str = ", ".join(keys)
        total = q(f"SELECT COUNT(*) AS n FROM {table}").iloc[0]["n"]
        dups = q(f"""
            SELECT COUNT(*) AS n FROM (
                SELECT {key_str}, COUNT(*) AS c FROM {table}
                GROUP BY {key_str} HAVING c > 1
            )
        """).iloc[0]["n"]
        dup_rows = q(f"""
            SELECT SUM(c-1) AS n FROM (
                SELECT {key_str}, COUNT(*) AS c FROM {table}
                GROUP BY {key_str} HAVING c > 1
            )
        """).iloc[0]["n"] or 0
        pct = round(100 * dup_rows / total, 2) if total else 0
        dup_info[table] = {"dup_groups": int(dups), "dup_rows": int(dup_rows), "pct": pct}
        print(f"  {table}: {dups} duplicate groups, {dup_rows} extra rows ({pct}%)")

    labels = list(dup_info.keys())
    pcts = [dup_info[t]["pct"] for t in labels]

    fig, ax = plt.subplots(figsize=(9, 4))
    bars = ax.barh(labels, pcts, color=["#e74c3c" if p > 0 else "#2ecc71" for p in pcts])
    ax.bar_label(bars, labels=[f"{p}%" for p in pcts], padding=4, fontsize=9)
    ax.set_xlabel("% duplicate rows")
    ax.set_title("Duplicate rows (%) per table")
    ax.invert_yaxis()
    save(fig, "03_duplicates.png")
    return dup_info

# ── 4. Timestamp format & timezone audit ─────────────────────────────────────

UTC_PATTERNS = {
    "ISO8601+UTC(Z)":  re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"),
    "ISO8601+offset":  re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?[+-]\d{2}:?\d{2}$"),
    "space+UTC label": re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)? UTC$"),
    "space+offset":    re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?[+-]\d{2}:?\d{2}$"),
    "naive datetime":  re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?$"),
    "date only":       re.compile(r"^\d{4}-\d{2}-\d{2}$"),
}

def classify_ts(val):
    if not val:
        return "null/empty"
    for name, pat in UTC_PATTERNS.items():
        if pat.match(str(val).strip()):
            return name
    return "unknown format"

def plot_timestamps():
    print("\n[4] Timestamp format & timezone audit")
    all_results = {}
    for table, cols in TIME_COLS.items():
        for col in cols:
            sample = q(f"SELECT {col} FROM {table} WHERE {col} IS NOT NULL LIMIT 50000")
            counts = defaultdict(int)
            for v in sample[col]:
                counts[classify_ts(v)] += 1
            all_results[f"{table}.{col}"] = dict(counts)
            print(f"  {table}.{col}: {dict(counts)}")

    n = len(all_results)
    cols_n = 3
    rows_n = (n + cols_n - 1) // cols_n
    fig, axes = plt.subplots(rows_n, cols_n, figsize=(16, rows_n * 3.5))
    axes_flat = axes.flatten() if n > 1 else [axes]

    for ax, (label, counts) in zip(axes_flat, all_results.items()):
        cats = list(counts.keys())
        vals = list(counts.values())
        colors = sns.color_palette("Set2", len(cats))
        wedges, texts, autotexts = ax.pie(vals, labels=None, autopct="%1.1f%%",
                                           colors=colors, startangle=90,
                                           pctdistance=0.75)
        ax.legend(wedges, cats, loc="lower center", bbox_to_anchor=(0.5, -0.35),
                  fontsize=7, ncol=1)
        ax.set_title(label, fontsize=9)

    for ax in axes_flat[n:]:
        ax.set_visible(False)

    fig.suptitle("Timestamp format distribution per column", fontsize=13)
    plt.tight_layout()
    save(fig, "04_timestamp_formats.png")
    return all_results

# ── 5. ID type analysis ───────────────────────────────────────────────────────

ID_PATTERNS = {
    "UUID":       re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I),
    "VIN-hex":    re.compile(r"^VIN-[0-9a-f]{7}$", re.I),
    "FEATURE-hex":re.compile(r"^FEATURE-[0-9a-f]{7}$", re.I),
    "POINT-hex":  re.compile(r"^POINT-[0-9a-f]{7}$", re.I),
    "SECTION-hex":re.compile(r"^SECTION-[0-9a-f]{7}$", re.I),
    "CAUSE-hex":  re.compile(r"^CAUSE-[0-9a-f]{7}$", re.I),
    "CONCERN-hex":re.compile(r"^CONCERN-[0-9a-f]{7}$", re.I),
    "STOPPAGE-hex":re.compile(r"^STOPPAGE-[0-9a-f]{7}$", re.I),
    "numeric str":re.compile(r"^\d+$"),
}

ID_COLS = {
    "concerns":         ["vehicle_id","point","section","cause","concern"],
    "vehicle_features": ["vehicle_id","feature"],
    "operations":       ["vehicle_id","operation_id","department_id","line_id"],
    "stoppages":        ["vehicle_id"],
    "tools":            ["vehicle_id","tool"],
}

def classify_id(val):
    if not val:
        return "null/empty"
    for name, pat in ID_PATTERNS.items():
        if pat.match(str(val).strip()):
            return name
    return "other"

def plot_id_types():
    print("\n[5] ID format analysis")
    id_results = {}
    for table, cols in ID_COLS.items():
        for col in cols:
            sample = q(f"SELECT DISTINCT {col} FROM {table} LIMIT 5000")
            counts = defaultdict(int)
            for v in sample[col]:
                counts[classify_id(v)] += 1
            id_results[f"{table}.{col}"] = dict(counts)
            print(f"  {table}.{col}: {dict(counts)}")

    n = len(id_results)
    cols_n = 3
    rows_n = (n + cols_n - 1) // cols_n
    fig, axes = plt.subplots(rows_n, cols_n, figsize=(16, rows_n * 3))
    axes_flat = axes.flatten() if n > 1 else [axes]

    for ax, (label, counts) in zip(axes_flat, id_results.items()):
        cats = list(counts.keys())
        vals = list(counts.values())
        colors = sns.color_palette("tab10", len(cats))
        ax.bar(cats, vals, color=colors)
        ax.set_title(label, fontsize=9)
        ax.set_xticklabels(cats, rotation=30, ha="right", fontsize=8)
        ax.set_ylabel("distinct count")

    for ax in axes_flat[n:]:
        ax.set_visible(False)

    fig.suptitle("ID format types per column (distinct sample)", fontsize=13)
    plt.tight_layout()
    save(fig, "05_id_types.png")
    return id_results

# ── 6. Cardinality (unique values) ───────────────────────────────────────────

def plot_cardinality():
    print("\n[6] Cardinality (distinct values)")
    card = {}
    for table, cols in TABLES.items():
        row = {}
        for col in cols:
            n = q(f"SELECT COUNT(DISTINCT {col}) AS n FROM {table}").iloc[0]["n"]
            row[col] = n
        card[table] = row
        print(f"  {table}: { {k:v for k,v in row.items()} }")

    fig, axes = plt.subplots(1, len(TABLES), figsize=(20, 5))
    for ax, (table, row) in zip(axes, card.items()):
        ax.barh(list(row.keys()), list(row.values()), color=PALETTE[:len(row)])
        ax.set_title(table, fontsize=10)
        ax.set_xlabel("distinct values")
        ax.invert_yaxis()
        for i, v in enumerate(row.values()):
            ax.text(v, i, f" {v:,}", va="center", fontsize=7)
    fig.suptitle("Cardinality per column", fontsize=13)
    plt.tight_layout()
    save(fig, "06_cardinality.png")
    return card

# ── 7. Numeric distributions ─────────────────────────────────────────────────

def plot_numeric():
    print("\n[7] Numeric distributions")

    # complexity_factor
    cf = q("SELECT complexity_factor FROM operations WHERE complexity_factor IS NOT NULL")
    print(f"  operations.complexity_factor: min={cf['complexity_factor'].min():.2f} "
          f"max={cf['complexity_factor'].max():.2f} mean={cf['complexity_factor'].mean():.2f}")

    # tools: subprocess, ok
    sub = q("SELECT subprocess, COUNT(*) AS n FROM tools GROUP BY subprocess ORDER BY subprocess")
    ok  = q("SELECT ok, COUNT(*) AS n FROM tools GROUP BY ok")

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    # complexity_factor histogram
    axes[0].hist(cf["complexity_factor"], bins=50, color=PALETTE[0], edgecolor="white")
    axes[0].set_title("operations.complexity_factor distribution")
    axes[0].set_xlabel("complexity_factor")
    axes[0].set_ylabel("count")

    # subprocess bar
    axes[1].bar(sub["subprocess"].fillna("(null)").astype(str), sub["n"], color=PALETTE[1])
    axes[1].set_title("tools.subprocess values")
    axes[1].set_xlabel("subprocess")
    axes[1].set_ylabel("count")

    # ok pie
    ok_labels = {0: "False", 1: "True", None: "null"}
    labels = [ok_labels.get(v, str(v)) for v in ok["ok"]]
    colors = ["#e74c3c" if l == "False" else "#2ecc71" if l == "True" else "#95a5a6" for l in labels]
    axes[2].pie(ok["n"], labels=labels, autopct="%1.1f%%", colors=colors, startangle=90)
    axes[2].set_title("tools.ok distribution")

    plt.tight_layout()
    save(fig, "07_numeric_distributions.png")

# ── 8. Temporal range & activity heatmap ─────────────────────────────────────

def plot_temporal():
    print("\n[8] Temporal range & daily activity")

    ops = q("""
        SELECT DATE(entered) AS day, COUNT(*) AS n
        FROM operations
        WHERE entered IS NOT NULL
        GROUP BY day ORDER BY day
    """)
    ops["day"] = pd.to_datetime(ops["day"], errors="coerce")
    ops = ops.dropna(subset=["day"])
    print(f"  operations date range: {ops['day'].min().date()} → {ops['day'].max().date()}")

    tools_ts = q("""
        SELECT DATE(timestamp) AS day, COUNT(*) AS n
        FROM tools
        WHERE timestamp IS NOT NULL
        GROUP BY day ORDER BY day
    """)
    tools_ts["day"] = pd.to_datetime(tools_ts["day"], errors="coerce")
    tools_ts = tools_ts.dropna(subset=["day"])

    fig, axes = plt.subplots(2, 1, figsize=(14, 7))

    axes[0].plot(ops["day"], ops["n"], color=PALETTE[0], linewidth=1.2)
    axes[0].fill_between(ops["day"], ops["n"], alpha=0.25, color=PALETTE[0])
    axes[0].set_title("Daily operations volume")
    axes[0].set_ylabel("operations / day")

    axes[1].plot(tools_ts["day"], tools_ts["n"], color=PALETTE[2], linewidth=1.2)
    axes[1].fill_between(tools_ts["day"], tools_ts["n"], alpha=0.25, color=PALETTE[2])
    axes[1].set_title("Daily tool events volume")
    axes[1].set_ylabel("tool events / day")

    plt.tight_layout()
    save(fig, "08_temporal_activity.png")

# ── 9. Operation duration & stoppage duration ─────────────────────────────────

def plot_durations():
    print("\n[9] Duration analysis")

    ops_dur = q("""
        SELECT
            (JULIANDAY(exited) - JULIANDAY(entered)) * 86400 AS duration_s
        FROM operations
        WHERE entered IS NOT NULL AND exited IS NOT NULL
          AND JULIANDAY(exited) >= JULIANDAY(entered)
        LIMIT 500000
    """)
    ops_dur = ops_dur[ops_dur["duration_s"] < 3600]  # cap at 1 hour for readability

    stop_dur = q("""
        SELECT
            (JULIANDAY(endtime) - JULIANDAY(starttime)) * 86400 AS duration_s
        FROM stoppages
        WHERE starttime IS NOT NULL AND endtime IS NOT NULL
          AND JULIANDAY(endtime) >= JULIANDAY(starttime)
    """)
    stop_dur = stop_dur[stop_dur["duration_s"] < 3600]

    print(f"  operations duration (s): mean={ops_dur['duration_s'].mean():.1f} "
          f"median={ops_dur['duration_s'].median():.1f} max={ops_dur['duration_s'].max():.1f}")
    print(f"  stoppages duration (s): mean={stop_dur['duration_s'].mean():.1f} "
          f"median={stop_dur['duration_s'].median():.1f} max={stop_dur['duration_s'].max():.1f}")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    axes[0].hist(ops_dur["duration_s"], bins=80, color=PALETTE[0], edgecolor="white")
    axes[0].set_title("Operation duration (s) — capped at 3600s")
    axes[0].set_xlabel("seconds")
    axes[0].set_ylabel("count")

    axes[1].hist(stop_dur["duration_s"], bins=60, color=PALETTE[3], edgecolor="white")
    axes[1].set_title("Stoppage duration (s) — capped at 3600s")
    axes[1].set_xlabel("seconds")
    axes[1].set_ylabel("count")

    plt.tight_layout()
    save(fig, "09_durations.png")

# ── 10. Top-N categorical values ─────────────────────────────────────────────

def plot_top_categoricals():
    print("\n[10] Top categorical values")

    queries = {
        "top 20 stop codes":        ("stoppages",   "code",          20),
        "top 20 concerns":          ("concerns",    "concern",        20),
        "top 20 concern causes":    ("concerns",    "cause",          20),
        "top 20 features":          ("vehicle_features", "feature",   20),
        "top 20 departments":       ("operations",  "department_id",  20),
        "top 20 lines":             ("operations",  "line_id",        20),
    }

    fig, axes = plt.subplots(2, 3, figsize=(20, 12))
    axes_flat = axes.flatten()

    for ax, (title, (table, col, n)) in zip(axes_flat, queries.items()):
        df = q(f"""
            SELECT {col} AS val, COUNT(*) AS n
            FROM {table}
            WHERE {col} IS NOT NULL AND TRIM(CAST({col} AS TEXT)) != ''
            GROUP BY {col} ORDER BY n DESC LIMIT {n}
        """)
        ax.barh(df["val"].astype(str), df["n"], color=PALETTE[0])
        ax.invert_yaxis()
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("count")
        ax.tick_params(axis="y", labelsize=7)
        print(f"  {title}: top={df.iloc[0]['val']} ({df.iloc[0]['n']:,})")

    plt.tight_layout()
    save(fig, "10_top_categoricals.png")

# ── 11. Cross-table vehicle coverage ─────────────────────────────────────────

def plot_vehicle_coverage():
    print("\n[11] Vehicle coverage across tables")

    sets = {}
    for table in TABLES:
        vids = set(q(f"SELECT DISTINCT vehicle_id FROM {table}")["vehicle_id"].tolist())
        sets[table] = vids
        print(f"  {table}: {len(vids):,} unique vehicles")

    # Venn-style bar: vehicles present in each table
    labels = list(sets.keys())
    counts = [len(v) for v in sets.values()]

    fig, ax = plt.subplots(figsize=(9, 4))
    bars = ax.bar(labels, counts, color=PALETTE[:len(labels)])
    ax.bar_label(bars, labels=[f"{c:,}" for c in counts], padding=4, fontsize=9)
    ax.set_title("Unique vehicle_id count per table")
    ax.set_ylabel("distinct vehicles")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    save(fig, "11_vehicle_coverage.png")

    # overlap matrix (pairwise intersection size)
    tnames = list(sets.keys())
    matrix = pd.DataFrame(index=tnames, columns=tnames, dtype=int)
    for a in tnames:
        for b in tnames:
            matrix.loc[a, b] = len(sets[a] & sets[b])

    fig2, ax2 = plt.subplots(figsize=(8, 6))
    sns.heatmap(matrix.astype(int), annot=True, fmt=",", cmap="YlOrRd", ax=ax2,
                linewidths=0.5, annot_kws={"size": 9})
    ax2.set_title("Pairwise vehicle_id intersection across tables")
    plt.tight_layout()
    save(fig2, "12_vehicle_intersection.png")

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  FORD HACKATHON — deep data profile")
    print("=" * 60)

    row_counts   = plot_row_counts()
    null_pct     = plot_nulls()
    dup_info     = plot_duplicates()
    ts_formats   = plot_timestamps()
    id_types     = plot_id_types()
    cardinality  = plot_cardinality()
    plot_numeric()
    plot_temporal()
    plot_durations()
    plot_top_categoricals()
    plot_vehicle_coverage()

    print("\n" + "=" * 60)
    print(f"  All charts saved to: {OUT_DIR}/")
    print("=" * 60)

if __name__ == "__main__":
    main()
