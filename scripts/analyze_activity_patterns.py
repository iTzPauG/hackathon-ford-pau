"""
analyze_activity_patterns.py
Analiza las franjas de actividad productiva por hora y minuto.
Detecta arranques, paradas y caídas de actividad.
Output: profile_report/activity_patterns.png + resumen en stdout
"""

import sqlite3
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "ford_hackathon.db"
OUT_DIR = Path(__file__).parent / "profile_report"
os.makedirs(OUT_DIR, exist_ok=True)

# Umbral para considerar actividad "alta" (% del pico)
ACTIVE_THRESHOLD = 0.15   # > 15% del máximo = activo
LOW_THRESHOLD    = 0.05   # < 5% del máximo = inactivo


def load_hourly(con, table, col):
    return pd.read_sql_query(f"""
        SELECT ts_hour as hour, COUNT(*) as n
        FROM {table}
        WHERE ts_hour IS NOT NULL
        GROUP BY ts_hour ORDER BY ts_hour
    """, con)


def load_by_minute(con, table, col, hours):
    hour_list = ",".join(str(h) for h in hours)
    return pd.read_sql_query(f"""
        SELECT CAST(strftime('%H', {col}) AS INTEGER) as hour,
               CAST(strftime('%M', {col}) AS INTEGER) as minute,
               strftime('%H:%M', {col}) as hm,
               COUNT(*) as n
        FROM {table}
        WHERE ts_hour IN ({hour_list})
        GROUP BY hm ORDER BY hm
    """, con)


def detect_transitions(hourly_df, threshold_active, threshold_low):
    """Detecta franjas de actividad y paradas."""
    max_n = hourly_df["n"].max()
    hourly_df = hourly_df.copy()
    hourly_df["pct"] = hourly_df["n"] / max_n
    hourly_df["state"] = hourly_df["pct"].apply(
        lambda x: "active" if x > threshold_active else ("low" if x > threshold_low else "inactive")
    )
    return hourly_df


def print_activity_summary(df, table_name):
    print(f"\n{'='*60}")
    print(f"  ACTIVIDAD — {table_name}")
    print(f"{'='*60}")
    print(f"\n  {'HORA':<8} {'EVENTOS':>10}  {'% PICO':>8}  {'ESTADO'}")
    print(f"  {'-'*45}")
    for _, row in df.iterrows():
        estado = {"active": "▓▓ ACTIVO", "low": "░░ BAJO  ", "inactive": "   PARADO"}.get(row["state"], "")
        bar = "█" * int(row["pct"] * 30)
        print(f"  {int(row['hour']):02d}h    {int(row['n']):>10,}  {row['pct']*100:>7.1f}%  {estado}")
    
    # Resumen de franjas
    print(f"\n  FRANJAS DETECTADAS:")
    prev_state = None
    start_hour = None
    for _, row in df.iterrows():
        if row["state"] != prev_state:
            if prev_state is not None and start_hour is not None:
                end_h = int(row["hour"])
                label = {"active": "🟢 ACTIVO ", "low": "🟡 BAJO   ", "inactive": "🔴 PARADO "}.get(prev_state, "")
                print(f"    {label}: {int(start_hour):02d}:00 → {end_h:02d}:00")
            start_hour = row["hour"]
            prev_state = row["state"]
    # Último tramo
    if prev_state and start_hour is not None:
        label = {"active": "🟢 ACTIVO ", "low": "🟡 BAJO   ", "inactive": "🔴 PARADO "}.get(prev_state, "")
        print(f"    {label}: {int(start_hour):02d}:00 → 23:59")


def plot_activity(hourly_ops, hourly_tools, minute_ops_start, minute_ops_end, minute_ops_noon):
    fig = plt.figure(figsize=(18, 14))
    gs = fig.add_gridspec(3, 2, hspace=0.45, wspace=0.3)

    colors = {"active": "#2ecc71", "low": "#f39c12", "inactive": "#e74c3c"}

    # ── Panel 1: Actividad por hora - operations ──────────────────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    max_ops = hourly_ops["n"].max()
    bar_colors = [colors[s] for s in hourly_ops["state"]]
    bars = ax1.bar(hourly_ops["hour"], hourly_ops["n"], color=bar_colors, edgecolor="white", linewidth=0.5)
    ax1.axhline(y=max_ops * ACTIVE_THRESHOLD, color="orange", linestyle="--", linewidth=1, label=f"Umbral activo ({ACTIVE_THRESHOLD*100:.0f}%)")
    ax1.axhline(y=max_ops * LOW_THRESHOLD, color="red", linestyle="--", linewidth=1, label=f"Umbral inactivo ({LOW_THRESHOLD*100:.0f}%)")
    ax1.set_title("Operations — Actividad por hora", fontsize=11)
    ax1.set_xlabel("Hora del día")
    ax1.set_ylabel("Nº operaciones")
    ax1.set_xticks(range(24))
    ax1.legend(fontsize=8)

    # ── Panel 2: Actividad por hora - tools ───────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    max_tools = hourly_tools["n"].max()
    bar_colors_t = [colors[s] for s in hourly_tools["state"]]
    ax2.bar(hourly_tools["hour"], hourly_tools["n"], color=bar_colors_t, edgecolor="white", linewidth=0.5)
    ax2.axhline(y=max_tools * ACTIVE_THRESHOLD, color="orange", linestyle="--", linewidth=1)
    ax2.axhline(y=max_tools * LOW_THRESHOLD, color="red", linestyle="--", linewidth=1)
    ax2.set_title("Tools — Actividad por hora", fontsize=11)
    ax2.set_xlabel("Hora del día")
    ax2.set_ylabel("Nº eventos")
    ax2.set_xticks(range(24))

    # ── Panel 3: Arranque (minuto a minuto, 03h-07h) ──────────────────────────
    ax3 = fig.add_subplot(gs[1, :])
    if not minute_ops_start.empty:
        x = range(len(minute_ops_start))
        ax3.fill_between(x, minute_ops_start["n"], alpha=0.6, color="#3498db")
        ax3.plot(x, minute_ops_start["n"], color="#2980b9", linewidth=1)
        
        # Marcas de hora en punto
        hour_ticks = minute_ops_start[minute_ops_start["minute"] == 0]
        for _, row in hour_ticks.iterrows():
            idx = minute_ops_start[minute_ops_start["hm"] == row["hm"]].index
            if len(idx) > 0:
                pos = minute_ops_start.index.get_loc(idx[0])
                ax3.axvline(x=pos, color="red", linestyle="--", alpha=0.7, linewidth=1.5)
                ax3.text(pos + 0.5, ax3.get_ylim()[1] * 0.9, row["hm"], fontsize=9, color="red")
        
        # Etiquetas eje X cada 10 minutos
        tick_positions = [i for i, hm in enumerate(minute_ops_start["hm"]) if hm.endswith(("00", "10", "20", "30", "40", "50"))]
        tick_labels = [minute_ops_start["hm"].iloc[i] for i in tick_positions]
        ax3.set_xticks(tick_positions)
        ax3.set_xticklabels(tick_labels, rotation=45, fontsize=7)
        ax3.set_title("Operations — Arranque y parada por minuto (03h-07h y 19h-21h)", fontsize=11)
        ax3.set_ylabel("Nº operaciones")

    # ── Panel 4: Mediodía (minuto a minuto, 12h-15h) ──────────────────────────
    ax4 = fig.add_subplot(gs[2, :])
    if not minute_ops_noon.empty:
        x = range(len(minute_ops_noon))
        ax4.fill_between(x, minute_ops_noon["n"], alpha=0.6, color="#9b59b6")
        ax4.plot(x, minute_ops_noon["n"], color="#8e44ad", linewidth=1)
        
        hour_ticks = minute_ops_noon[minute_ops_noon["minute"] == 0]
        for _, row in hour_ticks.iterrows():
            idx = minute_ops_noon[minute_ops_noon["hm"] == row["hm"]].index
            if len(idx) > 0:
                pos = minute_ops_noon.index.get_loc(idx[0])
                ax4.axvline(x=pos, color="red", linestyle="--", alpha=0.7, linewidth=1.5)
                ax4.text(pos + 0.5, ax4.get_ylim()[1] * 0.9, row["hm"], fontsize=9, color="red")
        
        tick_positions = [i for i, hm in enumerate(minute_ops_noon["hm"]) if hm.endswith(("00", "10", "20", "30", "40", "50"))]
        tick_labels = [minute_ops_noon["hm"].iloc[i] for i in tick_positions]
        ax4.set_xticks(tick_positions)
        ax4.set_xticklabels(tick_labels, rotation=45, fontsize=7)
        ax4.set_title("Operations — Franja mediodía/tarde por minuto (12h-16h)", fontsize=11)
        ax4.set_ylabel("Nº operaciones")

    # Leyenda global
    legend_patches = [
        mpatches.Patch(color="#2ecc71", label="Activo"),
        mpatches.Patch(color="#f39c12", label="Actividad baja"),
        mpatches.Patch(color="#e74c3c", label="Inactivo / parado"),
    ]
    fig.legend(handles=legend_patches, loc="upper right", fontsize=9)
    fig.suptitle("Análisis de franjas de actividad — ford_hackathon.db", fontsize=14, y=1.01)

    out_path = OUT_DIR / "activity_patterns.png"
    plt.savefig(out_path, bbox_inches="tight", dpi=130)
    plt.close()
    print(f"\n  → Gráfico guardado en: {out_path}")


def main():
    con = sqlite3.connect(str(DB_PATH))

    print("Cargando datos...")

    # Datos por hora
    hourly_ops   = load_hourly(con, "operations", "entered")
    hourly_tools = load_hourly(con, "tools", "timestamp")

    # Detectar estados
    hourly_ops   = detect_transitions(hourly_ops, ACTIVE_THRESHOLD, LOW_THRESHOLD)
    hourly_tools = detect_transitions(hourly_tools, ACTIVE_THRESHOLD, LOW_THRESHOLD)

    # Datos por minuto en zonas de transición
    minute_ops_start = load_by_minute(con, "operations", "entered", [3, 4, 5, 6, 7])
    minute_ops_end   = load_by_minute(con, "operations", "entered", [19, 20, 21])
    minute_ops_noon  = load_by_minute(con, "operations", "entered", [12, 13, 14, 15])

    # Combinar arranque + parada en un solo df para el panel
    minute_ops_transitions = pd.concat([minute_ops_start, minute_ops_end]).reset_index(drop=True)

    con.close()

    # Resúmenes en stdout
    print_activity_summary(hourly_ops, "operations.entered")
    print_activity_summary(hourly_tools, "tools.timestamp")

    # Análisis detallado de arranque
    print(f"\n{'='*60}")
    print("  ARRANQUE PRECISO — operations (minuto a minuto)")
    print(f"{'='*60}")
    max_start = minute_ops_start["n"].max()
    prev_state = None
    for _, row in minute_ops_start.iterrows():
        pct = row["n"] / max_start
        state = "activo" if pct > ACTIVE_THRESHOLD else "bajo"
        if state != prev_state:
            print(f"\n  → Cambio a [{state.upper()}] en {row['hm']}  ({int(row['n']):,} eventos, {pct*100:.1f}%)")
            prev_state = state

    print(f"\n{'='*60}")
    print("  PARADA PRECISA — operations (minuto a minuto)")
    print(f"{'='*60}")
    max_end = minute_ops_end["n"].max()
    prev_state = None
    for _, row in minute_ops_end.iterrows():
        pct = row["n"] / max_end
        state = "activo" if pct > ACTIVE_THRESHOLD else ("bajo" if pct > LOW_THRESHOLD else "inactivo")
        if state != prev_state:
            print(f"\n  → Cambio a [{state.upper()}] en {row['hm']}  ({int(row['n']):,} eventos, {pct*100:.1f}%)")
            prev_state = state

    # Generar gráfico
    plot_activity(hourly_ops, hourly_tools, minute_ops_transitions, minute_ops_end, minute_ops_noon)


if __name__ == "__main__":
    main()
