#!/usr/bin/env python3
"""Genera sql/eda.sql y sql/benchmark.sql desde las mismas definiciones que usan los scripts."""
from __future__ import annotations

from benchmark import BENCH_QUERIES, SOURCES, sql_fuente
from lab8_common import (DATA_RAW, EDA_QUERIES, SPEED_THRESHOLD_MPH, SQL_DIR, SQL_ENRIQUECIDA, SQL_MUESTRA,
                         VALID_RULE, YEARS_ALL, select_trips, sql_years)


def rel(sql: str) -> str:
    return sql.replace(DATA_RAW.as_posix() + "/", "data/raw/")


def main() -> int:
    SQL_DIR.mkdir(parents=True, exist_ok=True)
    partes = ["-- Ejecutar desde la raíz del proyecto. Generado por scripts/generate_sql.py\n",
              "-- Cada consulta aparece sobre Parquet directo y sobre la tabla `trips` de data/processed/lab8.duckdb.\n"
              "-- Para la versión tabla: ATTACH 'data/processed/lab8.duckdb' AS lab8 (READ_ONLY); USE lab8;\n"]
    for qn, body in BENCH_QUERIES.items():
        for s in SOURCES:
            partes.append(f"-- {qn} | fuente: {s} | escenario: 2024+2026\n{rel(sql_fuente(s, list(YEARS_ALL), body))};\n")
    (SQL_DIR / "benchmark.sql").write_text("\n".join(partes), encoding="utf-8")

    vistas = ("-- Vistas analíticas: trips (normalizada), trips_enriched (derivadas), trips_valid (reglas de calidad)\n"
              f"CREATE OR REPLACE TEMP VIEW trips AS\n{rel(select_trips(list(YEARS_ALL)))};\n\n"
              f"CREATE OR REPLACE TEMP VIEW trips_enriched AS{SQL_ENRIQUECIDA};\n\n"
              f"-- trips_valid excluye: fechas inválidas, distancia/tarifa/total negativos, velocidad > {SPEED_THRESHOLD_MPH} mph, duración > 24 h.\n"
              "-- La distancia cero NO se excluye (se marca con is_zero_distance).\n"
              f"CREATE OR REPLACE TEMP VIEW trips_valid AS SELECT * FROM trips_enriched WHERE {VALID_RULE};\n")
    eda = ["-- Consultas principales del EDA y comparación yellow/green (años 2024, 2026). Editar `source_year IN (...)` para otros años.\n", vistas]
    for n, sql in EDA_QUERIES.items():
        eda.append(f"-- {n}\n{sql.format(years=sql_years(YEARS_ALL))};\n")
    eda.append("-- muestra controlada distancia vs tarifa (yellow; repetir con 'green')\n"
               + SQL_MUESTRA.format(years=sql_years(YEARS_ALL), taxi="yellow") + ";\n")
    (SQL_DIR / "eda.sql").write_text("\n".join(eda), encoding="utf-8")
    print("Escritos:", SQL_DIR / "eda.sql", SQL_DIR / "benchmark.sql")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
