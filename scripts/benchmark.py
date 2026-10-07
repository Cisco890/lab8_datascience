#!/usr/bin/env python3
"""Benchmark: Parquet directo vs tabla `trips` de lab8.duckdb (consultas equivalentes).

Requiere haber ejecutado antes scripts/materialize.py.
Escribe docs/benchmark_results.csv (solo el resumen).
"""
from __future__ import annotations

import argparse
import time

import duckdb
import pandas as pd

from lab8_common import DB_PATH, DOCS_DIR, THREADS, YEARS_ALL, select_trips, sql_years, years_con_datos

SOURCES = ("parquet", "duckdb_table")
SCOPES = {"2024": [2024], "2026": [2026], "2024+2026": [2024, 2026]}      # 2026 es parcial

# Cuerpos equivalentes: ambas fuentes exponen la misma relación `scope`
BENCH_QUERIES = {
    "q1_conteo_taxi_anio": "SELECT taxi_type, source_year, COUNT(*) AS n_trips FROM scope GROUP BY ALL ORDER BY ALL",
    "q2_mensual": """SELECT source_year, source_month, COUNT(*) AS n_trips, SUM(total_amount) AS sum_total
FROM scope GROUP BY ALL ORDER BY ALL""",
    "q3_taxi_media_mediana": """SELECT taxi_type, COUNT(*) AS n_trips, AVG(trip_distance) AS avg_distance, median(fare_amount) AS median_fare
FROM scope GROUP BY ALL ORDER BY ALL""",
    "q4_pago_filtrado": """SELECT payment_type, COUNT(*) AS n_trips, AVG(tip_amount) AS avg_tip, AVG(total_amount) AS avg_total
FROM scope WHERE month(pickup_datetime) BETWEEN 3 AND 6 AND trip_distance > 0 AND total_amount > 0
GROUP BY ALL ORDER BY ALL""",
    "q5_hora_taxi": """SELECT taxi_type, hour(pickup_datetime) AS pickup_hour, COUNT(*) AS n_trips, AVG(trip_distance) AS avg_distance
FROM scope WHERE pickup_datetime IS NOT NULL GROUP BY ALL ORDER BY ALL""",
}


def sql_fuente(source: str, years, body: str) -> str:
    if source == "parquet":      # lectura directa: solo los archivos de los años del escenario
        return f"WITH scope AS (\n{select_trips(years)}\n)\n{body}"
    return f"WITH scope AS (SELECT * FROM trips WHERE source_year IN ({sql_years(years)}))\n{body}"


def benchmark(conns, query_name, body, scope_name, years, repeats):
    sqls = {s: sql_fuente(s, years, body) for s in SOURCES}
    a, b = (conns[s].execute(sqls[s]).fetchdf() for s in SOURCES)           # equivalencia (no cronometrada)
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9)
    for s in SOURCES:                                                        # calentamiento no registrado
        conns[s].execute(sqls[s]).fetchall()
    filas = []
    for run in range(1, repeats + 1):
        for s in (SOURCES if run % 2 else SOURCES[::-1]):                    # alterna el orden entre fuentes
            t0 = time.perf_counter()
            n = len(conns[s].execute(sqls[s]).fetchall())                    # fetchall fuerza la materialización
            filas.append(dict(query_name=query_name, source=s, data_scope=scope_name, run=run,
                              elapsed_ms=(time.perf_counter() - t0) * 1000, result_rows=n))
    return filas


def correr(repeats=5):
    con_pq = duckdb.connect(); con_pq.execute(f"SET threads = {THREADS}")
    con_tb = duckdb.connect(str(DB_PATH), read_only=True); con_tb.execute(f"SET threads = {THREADS}")
    conns = {"parquet": con_pq, "duckdb_table": con_tb}
    print(f"threads = {THREADS} (ambas conexiones) | {repeats} repeticiones + 1 calentamiento")
    filas = []
    try:
        for scope_name, years in SCOPES.items():
            if any(len(years_con_datos(t, years)) != len(years) for t in ("yellow", "green")):
                print("Escenario omitido (faltan datos):", scope_name); continue
            for qn, body in BENCH_QUERIES.items():
                print(f"  {scope_name:10s} {qn}")
                filas += benchmark(conns, qn, body, scope_name, years, repeats)
    finally:
        con_pq.close(); con_tb.close()
    runs = pd.DataFrame(filas)
    summary = (runs.groupby(["query_name", "source", "data_scope"])["elapsed_ms"]
               .agg(runs="count", median_ms="median", mean_ms="mean", std_ms="std", min_ms="min", max_ms="max")
               .round(2).reset_index())
    return runs, summary


def plot_resumen(summary):
    import matplotlib.pyplot as plt
    orden = [s for s in SCOPES if s in summary.data_scope.unique()]
    fig, axs = plt.subplots(1, len(orden), figsize=(5.2 * len(orden), 4.2), sharey=True, squeeze=False)
    for ax, sc in zip(axs[0], orden):
        d = summary[summary.data_scope == sc].pivot(index="query_name", columns="source", values="median_ms")
        d.plot.barh(ax=ax, color={"parquet": "#4c72b0", "duckdb_table": "#dd8452"})
        ax.set(title=f"Escenario {sc}", xlabel="Mediana (ms)", ylabel=""); ax.grid(axis="x", alpha=.3)
    axs[0][0].invert_yaxis(); plt.tight_layout()
    return fig


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeats", type=int, default=5, help="mediciones por combinación (mínimo recomendado: 5)")
    ap.add_argument("--plot", action="store_true")
    a = ap.parse_args()
    if not DB_PATH.exists():
        print("Falta data/processed/lab8.duckdb: ejecuta primero scripts/materialize.py"); return 1

    runs, summary = correr(a.repeats)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(DOCS_DIR / "benchmark_results.csv", index=False)         # solo el resumen
    pd.set_option("display.width", 200, "display.max_columns", 30)
    print("\n" + summary.to_string(index=False))
    pv = summary.pivot_table(index=["data_scope", "query_name"], columns="source", values="median_ms")
    pv["parquet / tabla"] = (pv["parquet"] / pv["duckdb_table"]).round(2)    # > 1: tabla más rápida; < 1: Parquet
    print("\nMedianas (ms) y razón parquet/tabla:\n" + pv.to_string())
    print(f"\nGuardado: {DOCS_DIR / 'benchmark_results.csv'}")
    if a.plot:
        import matplotlib.pyplot as plt
        plot_resumen(summary); plt.show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
