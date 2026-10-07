#!/usr/bin/env python3
"""Ejecuta el EDA para los años indicados e imprime las tablas principales.

    python scripts/run_eda.py --years 2026
    python scripts/run_eda.py --years 2024 2026 --plots     # muestra las gráficas
"""
from __future__ import annotations

import argparse

import pandas as pd

from lab8_common import anios_disponibles, conectar, correr_eda, q


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", type=int, nargs="+", default=None, help="por defecto: todos los años descargados")
    ap.add_argument("--plots", action="store_true", help="mostrar las gráficas (requiere entorno gráfico)")
    args = ap.parse_args()
    args.years = list(args.years or anios_disponibles())

    con = conectar(args.years)
    res = correr_eda(con, args.years)
    pd.set_option("display.width", 200, "display.max_columns", 30)
    for name in ("volumen_mensual", "volumen_valido", "flags_calidad", "comparacion", "pagos", "propinas"):
        print(f"\n== {name} ==\n{res[name].round(2).to_string(index=False)}")

    # No regresión: agregar años no cambia los resultados de un año ya analizado
    if len(args.years) > 1:
        base = args.years[-1]
        solo, todos = q(con, "volumen_mensual", [base]), res["volumen_mensual"]
        chk = solo.merge(todos[todos.source_year == base], on=["source_year", "source_month", "taxi_type"], suffixes=("_solo", "_todos"))
        assert len(chk) == len(solo) and (chk.n_trips_solo == chk.n_trips_todos).all(), "el EDA cambió al agregar años"
        print(f"\nNo regresión OK: {base} idéntico solo y junto con {args.years[:-1]}")

    if args.plots:
        import matplotlib.pyplot as plt
        from eda_plots import plot_eda
        plot_eda(con, res, args.years)
        plt.show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
