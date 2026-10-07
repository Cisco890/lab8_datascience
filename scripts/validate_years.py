#!/usr/bin/env python3
"""Tabla de validación por tipo y año con UNA sola consulta DuckDB sobre todos los años."""
from __future__ import annotations

import argparse

import pandas as pd

from lab8_common import DATA_RAW, TAXIS, YEARS_ALL, conectar


def tabla_validacion(con, years=YEARS_ALL) -> pd.DataFrame:
    val = con.execute("""SELECT taxi_type, source_year, COUNT(DISTINCT source_file) AS available_files,
       COUNT(*) AS record_count, MIN(source_month) AS first_month, MAX(source_month) AS last_month
FROM trips GROUP BY ALL ORDER BY ALL""").fetchdf()
    sizes = pd.DataFrame([{"taxi_type": t, "source_year": y,
                           "size_mb": round(sum(p.stat().st_size for p in (DATA_RAW / t / str(y)).glob("*.parquet")) / 2**20, 2)}
                          for t in TAXIS for y in years])
    return val.merge(sizes, on=["taxi_type", "source_year"], how="right")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, nargs="+", default=list(YEARS_ALL))
    a = ap.parse_args()
    v = tabla_validacion(conectar(a.years), a.years)
    print(v.to_string(index=False))
    assert v.record_count.notna().all(), "falta algún tipo/año"
