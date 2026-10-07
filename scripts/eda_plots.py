"""Visualizaciones del EDA (Matplotlib) a partir de DataFrames pequeños agregados con SQL."""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from lab8_common import COLOR, DIAS, FLAGS, PAGO, SQL_MUESTRA, TAXIS, sql_years


def plot_volumen_mensual(df, titulo="Viajes por mes y tipo de taxi"):
    df = df.assign(mes=df.source_year.astype(str) + "-" + df.source_month.astype(str).str.zfill(2))
    fig, axs = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    for ax, taxi in zip(axs, TAXIS):
        d = df[df.taxi_type == taxi]
        ax.bar(d.mes, d.n_trips, color=COLOR[taxi]); ax.set_ylabel(f"Viajes ({taxi})")
        ax.ticklabel_format(axis="y", style="plain"); ax.grid(axis="y", alpha=.3)
    axs[0].set_title(titulo); axs[1].set_xlabel("Mes del archivo fuente (eje categórico: meses sin datos no aparecen)")
    plt.xticks(rotation=60); plt.tight_layout()
    return fig


def plot_demanda_hora(h):
    fig, ax = plt.subplots(figsize=(10, 4))
    for i, taxi in enumerate(TAXIS):
        d = h[h.taxi_type == taxi]
        ax.bar(d.pickup_hour + (i - .5) * .4, d.pct_trips, width=.4, color=COLOR[taxi], label=taxi)
    ax.set(xlabel="Hora de recogida", ylabel="% de viajes del tipo", title="Distribución horaria de la demanda (% dentro de cada tipo)")
    ax.set_xticks(range(24)); ax.legend(); ax.grid(axis="y", alpha=.3); plt.tight_layout()
    return fig


def plot_demanda_dia(w):
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.8))
    for ax, taxi in zip(axs, TAXIS):
        d = w[w.taxi_type == taxi]
        ax.bar(d.pickup_weekday.map(DIAS), d.avg_trips_per_day, color=COLOR[taxi])
        ax.set(title=f"{taxi}: viajes promedio por día", ylabel="Viajes / día"); ax.grid(axis="y", alpha=.3)
    plt.tight_layout()
    return fig


def _box(ax, df, titulo, ylabel):
    stats = [dict(label=r.taxi_type, med=r.p50, q1=r.p25, q3=r.p75, whislo=r.p01, whishi=r.p99, fliers=[]) for r in df.itertuples()]
    bp = ax.bxp(stats, showfliers=False, patch_artist=True)
    for patch, r in zip(bp["boxes"], df.itertuples()):
        patch.set_facecolor(COLOR[r.taxi_type])
    ax.set(title=titulo, ylabel=ylabel); ax.grid(axis="y", alpha=.3)


def plot_distancia_duracion(res):
    fig, axs = plt.subplots(1, 2, figsize=(10, 4))
    _box(axs[0], res["resumen_distancia"], "Distancia (caja p25–p75, bigotes p1–p99)", "Millas")
    _box(axs[1], res["resumen_duracion"], "Duración (caja p25–p75, bigotes p1–p99)", "Minutos")
    plt.tight_layout()
    return fig


def plot_hist(df, titulo, xlabel, cap, width):
    fig, ax = plt.subplots(figsize=(10, 3.8))
    for i, taxi in enumerate(TAXIS):
        d = df[df.taxi_type == taxi]
        ax.bar(d.bin + (i - .5) * width * .4 + width * .2, 100 * d.n / d.n.sum(), width=width * .4, color=COLOR[taxi], label=taxi)
    ax.set(title=titulo, xlabel=f"{xlabel} (último intervalo agrupa valores ≥ {cap}; solo para legibilidad)", ylabel="% de viajes válidos")
    ax.legend(); ax.grid(axis="y", alpha=.3); plt.tight_layout()
    return fig


def plot_distancia_vs_fare(con, res, years):
    fig, axs = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    reg = res["distancia_vs_fare"].set_index("taxi_type")
    for ax, taxi in zip(axs, TAXIS):
        m = con.execute(SQL_MUESTRA.format(years=sql_years(years), taxi=taxi)).fetchdf()
        ax.hexbin(m.trip_distance, m.fare_amount, gridsize=40, bins="log", cmap="viridis", mincnt=1)
        xs = np.array([0, 30]); r = reg.loc[taxi]
        ax.plot(xs, r.intercept_usd + r.slope_usd_per_mile * xs, "r--", lw=1,
                label=f"fare = {r.intercept_usd:.2f} + {r.slope_usd_per_mile:.2f}·millas (r = {r['corr']:.2f})")
        ax.set(title=f"{taxi}: distancia vs fare_amount (muestra; dist ≤ 30 mi, fare ≤ 150)", xlabel="Millas"); ax.legend(fontsize=7)
    axs[0].set_ylabel("fare_amount (USD)"); plt.tight_layout()
    return fig


def plot_comparacion(cmp_df):
    cmp_ = cmp_df.set_index("taxi_type")
    metricas = [("dist_median", "Distancia mediana (mi)"), ("min_median", "Duración mediana (min)"),
                ("fare_median", "fare_amount mediano (USD)"), ("total_median", "total_amount mediano (USD)")]
    fig, axs = plt.subplots(1, 4, figsize=(12, 3.5))
    for ax, (c, t) in zip(axs, metricas):
        ax.bar(cmp_.index, cmp_[c], color=[COLOR[i] for i in cmp_.index]); ax.set_title(t, fontsize=9); ax.grid(axis="y", alpha=.3)
    plt.tight_layout()
    return fig


def plot_pagos(pagos):
    p = pagos.assign(metodo=lambda d: d.payment_type.map(PAGO).fillna("NULL/otro"))
    piv = p.pivot_table(index="metodo", columns="taxi_type", values="pct", fill_value=0)
    ax = piv.plot.bar(color=[COLOR[c] for c in piv.columns], figsize=(9, 3.8), rot=0)
    ax.set(title="Forma de pago (% dentro de cada tipo)", xlabel="", ylabel="% de viajes"); ax.grid(axis="y", alpha=.3)
    plt.tight_layout()
    return ax.figure


def plot_propinas(pr):
    fig, ax = plt.subplots(figsize=(6, 3.8))
    stats = [dict(label=r.taxi_type, med=r.p50_pct, q1=r.p25_pct, q3=r.p75_pct, whislo=0, whishi=r.p95_pct, fliers=[]) for r in pr.itertuples()]
    bp = ax.bxp(stats, showfliers=False, patch_artist=True)
    for patch, r in zip(bp["boxes"], pr.itertuples()):
        patch.set_facecolor(COLOR[r.taxi_type])
    ax.set(title="Propina como % de fare_amount (tarjeta; bigote sup. = p95)", ylabel="% de fare_amount")
    ax.grid(axis="y", alpha=.3); plt.tight_layout()
    return fig


def plot_eda(con, res, years) -> dict:
    """Devuelve todas las figuras del EDA (no llama plt.show)."""
    return {
        "volumen_mensual": plot_volumen_mensual(res["volumen_mensual"]),
        "demanda_hora": plot_demanda_hora(res["demanda_hora"]),
        "demanda_dia": plot_demanda_dia(res["demanda_dia_semana"]),
        "distancia_duracion": plot_distancia_duracion(res),
        "hist_distancia": plot_hist(res["hist_distancia"], "Distribución de distancia", "Millas", 20, 1),
        "hist_duracion": plot_hist(res["hist_duracion"], "Distribución de duración", "Minutos", 90, 5),
        "distancia_vs_fare": plot_distancia_vs_fare(con, res, years),
        "comparacion": plot_comparacion(res["comparacion"]),
        "pagos": plot_pagos(res["pagos"]),
        "propinas": plot_propinas(res["propinas"]),
        "hist_fare": plot_hist(res["hist_fare"], "Distribución de fare_amount (viajes válidos)", "USD", 100, 5),
        "hist_total": plot_hist(res["hist_total"], "Distribución de total_amount (viajes válidos)", "USD", 100, 5),
    }
