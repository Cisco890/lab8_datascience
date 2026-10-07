#!/usr/bin/env python3
"""Crea data/processed/lab8.duckdb con la tabla `trips` (idempotente)."""
from __future__ import annotations

import argparse
import time

import duckdb

from lab8_common import DATA_RAW, DB_PATH, PROJECT_ROOT, TAXIS, THREADS, YEARS_ALL, select_trips


def materializar(years=YEARS_ALL, db_path=DB_PATH):
    """CREATE OR REPLACE TABLE; cierra la conexión de escritura al terminar (evita bloqueos con Metabase)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    wcon = duckdb.connect(str(db_path))
    try:
        wcon.execute(f"SET threads = {THREADS}")
        t0 = time.perf_counter()
        wcon.execute("CREATE OR REPLACE TABLE trips AS\n" + select_trips(years))
        wcon.execute("CHECKPOINT")
        segundos = time.perf_counter() - t0
        total = wcon.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
        por_anio = wcon.execute("SELECT source_year, COUNT(*) AS n_rows FROM trips GROUP BY 1 ORDER BY 1").fetchdf()
        por_taxi = wcon.execute("SELECT taxi_type, COUNT(*) AS n_rows FROM trips GROUP BY 1 ORDER BY 1").fetchdf()
    finally:
        wcon.close()
    return segundos, total, por_anio, por_taxi


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", type=int, nargs="+", default=list(YEARS_ALL))
    a = ap.parse_args()
    assert "*.duckdb" in (PROJECT_ROOT / ".gitignore").read_text(), "lab8.duckdb debe estar en .gitignore"

    seg, total, por_anio, por_taxi = materializar(a.years)
    size_db = DB_PATH.stat().st_size / 2**20
    size_pq = sum(p.stat().st_size for t in TAXIS for y in a.years for p in (DATA_RAW / t / str(y)).glob("*.parquet")) / 2**20
    print(f"Materialización (métrica separada): {seg:.1f} s | filas: {total:,}")
    print(f"lab8.duckdb: {size_db:.1f} MB | Parquet {a.years}: {size_pq:.1f} MB")
    print("\nPor año:\n" + por_anio.to_string(index=False))
    print("\nPor taxi:\n" + por_taxi.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
