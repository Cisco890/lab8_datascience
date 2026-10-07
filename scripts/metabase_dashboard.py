#!/usr/bin/env python3
"""Crea (o recrea) en Metabase el tablero del laboratorio sobre data/processed/lab8.duckdb.

Las tarjetas son preguntas SQL nativas construidas con los bloques de sql/indicators.sql: el
marcador /*filtros*/ se reemplaza por cláusulas opcionales de Metabase, de modo que los filtros
globales año / tipo de taxi / mes funcionan en todas las tarjetas sin duplicar SQL.

Uso (con Metabase levantado y la escritura desde Python terminada):

    docker compose exec -e MB_EMAIL=... -e MB_PASSWORD=... analysis \
        python scripts/metabase_dashboard.py --url http://metabase:3000

Si Metabase todavía no tiene usuario administrador, el script completa la configuración inicial
con MB_EMAIL / MB_PASSWORD. Es idempotente: borra el tablero y las tarjetas anteriores con el
mismo prefijo antes de crearlos otra vez.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid

import requests

from lab8_common import SQL_DIR, cargar_sql

DB_NAME = "lab8 DuckDB"
DB_FILE = "/workspace/data/processed/lab8.duckdb"       # ruta dentro del contenedor de Metabase
DASHBOARD = "Laboratorio 8 — Taxis NYC 2024–2026"
PREFIJO = "L8 · "

TAGS = {
    "anio": {"name": "anio", "display-name": "Año", "type": "number"},
    "taxi": {"name": "taxi", "display-name": "Tipo de taxi", "type": "text"},
    "mes": {"name": "mes", "display-name": "Mes", "type": "number"},
}
FILTROS_MB = "[[AND source_year = {{anio}}]] [[AND taxi_type = {{taxi}}]] [[AND source_month = {{mes}}]]"
PARAMS = [
    {"id": "p_anio", "name": "Año", "slug": "anio", "type": "number/=", "sectionId": "number"},
    {"id": "p_taxi", "name": "Tipo de taxi", "slug": "taxi", "type": "string/=", "sectionId": "string",
     "values_source_type": "static-list", "values_source_config": {"values": ["yellow", "green"]}},
    {"id": "p_mes", "name": "Mes", "slug": "mes", "type": "number/=", "sectionId": "number"},
]
GRUPO = "taxi_type || ' ' || CAST(source_year AS VARCHAR) AS grupo"
DIA = ("CASE pickup_weekday WHEN 1 THEN '1 Lun' WHEN 2 THEN '2 Mar' WHEN 3 THEN '3 Mié' WHEN 4 THEN '4 Jue' "
       "WHEN 5 THEN '5 Vie' WHEN 6 THEN '6 Sáb' ELSE '7 Dom' END AS dia")


def tarjetas(ind: dict[str, str]) -> list[dict]:
    """Definición de cada tarjeta: bloque base de indicators.sql + proyección para la gráfica."""
    def envolver(bloque, select, extra=""):
        base = ind[bloque].replace("/*filtros*/", FILTROS_MB)
        return f"SELECT {select}\nFROM (\n{base}\n) AS t\n{extra}".strip()

    def barras(metrics, dims=("grupo",), **kw):
        return {"graph.dimensions": list(dims), "graph.metrics": list(metrics), "graph.x_axis.scale": "ordinal",
                "graph.show_values": True, **kw}

    return [
        dict(name="Viajes por mes", display="line", pos=(0, 2, 12, 6),
             sql=envolver("ind_a_volumen_mensual", "month_start, taxi_type, trip_count"),
             viz={"graph.dimensions": ["month_start", "taxi_type"], "graph.metrics": ["trip_count"],
                  "graph.y_axis.scale": "log", "graph.y_axis.title_text": "Viajes (escala log)"}),
        dict(name="Duración mediana", display="line", pos=(12, 2, 12, 6),
             sql=envolver("ind_c_duracion", "month_start, taxi_type, median_minutes", "WHERE source_month IS NOT NULL"),
             viz={"graph.dimensions": ["month_start", "taxi_type"], "graph.metrics": ["median_minutes"],
                  "graph.y_axis.title_text": "Minutos"}),
        dict(name="Distancia mediana", display="bar", pos=(0, 8, 8, 6),
             sql=envolver("ind_b_distancia", f"{GRUPO}, median_distance_mi, avg_distance_mi"),
             viz=barras(["median_distance_mi", "avg_distance_mi"])),
        dict(name="Monto total promedio", display="bar", pos=(8, 8, 8, 6),
             sql=envolver("ind_d_monto_total", f"{GRUPO}, avg_total_usd, median_total_usd"),
             viz=barras(["avg_total_usd", "median_total_usd"])),
        dict(name="Propina típica", display="bar", pos=(16, 8, 8, 6),
             sql=envolver("ind_f_propinas", f"{GRUPO}, median_tip_pct, pct_with_tip"),
             viz=barras(["median_tip_pct", "pct_with_tip"])),
        dict(name="Distribución de formas de pago", display="bar", pos=(0, 14, 12, 7),
             sql=envolver("ind_e_pagos", f"{GRUPO}, payment_label, pct"),
             viz=barras(["pct"], dims=("grupo", "payment_label"), **{"stackable.stack_type": "stacked",
                                                                    "graph.show_values": False})),
        dict(name="Demanda por hora y día", display="line", pos=(12, 14, 12, 7),
             sql=envolver("ind_g_demanda_hora_dia", f"pickup_hour, {DIA}, SUM(trip_count) AS trip_count",
                          "GROUP BY ALL ORDER BY ALL"),
             viz={"graph.dimensions": ["pickup_hour", "dia"], "graph.metrics": ["trip_count"],
                  "graph.x_axis.title_text": "Hora de recogida"}),
        dict(name="Registros con banderas de calidad", display="bar", pos=(0, 21, 12, 6),
             sql=envolver("ind_h_calidad", f"{GRUPO}, pct_flagged"),
             viz=barras(["pct_flagged"])),
        dict(name="Evolución interanual YTD comparable", display="bar", pos=(12, 21, 12, 6),
             sql=envolver("evo_volumen_ytd", "CAST(source_year AS VARCHAR) AS anio_ytd, taxi_type, trips_ytd"),
             viz=barras(["trips_ytd"], dims=("anio_ytd", "taxi_type"), **{"graph.y_axis.scale": "log"})),
    ]


class Metabase:
    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self.s = requests.Session()

    def call(self, method, path, **kw):
        r = self.s.request(method, f"{self.url}/api{path}", timeout=300, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
        return r.json() if r.content else None

    def login(self, email, password):
        props = self.call("GET", "/session/properties")
        if not props.get("has-user-setup"):
            print("Configuración inicial de Metabase (usuario administrador)")
            r = self.call("POST", "/setup", json={
                "token": props["setup-token"],
                "user": {"first_name": "Lab", "last_name": "8", "email": email, "password": password,
                         "site_name": "Laboratorio 8"},
                "prefs": {"site_name": "Laboratorio 8", "site_locale": "es", "allow_tracking": False}})
        else:
            r = self.call("POST", "/session", json={"username": email, "password": password})
        self.s.headers["X-Metabase-Session"] = r["id"]

    def database(self):
        detalles = {"database_file": DB_FILE, "read_only": True, "old_implicit_casting": True}
        dbs = self.call("GET", "/database")
        dbs = dbs.get("data", dbs) if isinstance(dbs, dict) else dbs
        db = next((d for d in dbs if d["name"] == DB_NAME), None)
        if db is None:
            db = self.call("POST", "/database", json={"engine": "duckdb", "name": DB_NAME, "details": detalles})
            print(f"Base creada: {DB_NAME} (id {db['id']}, solo lectura)")
        else:
            self.call("PUT", f"/database/{db['id']}", json={"details": detalles})
        self.call("POST", f"/database/{db['id']}/sync_schema")
        return db["id"]

    def limpiar(self):
        for d in self.call("GET", "/dashboard/"):
            if d["name"] == DASHBOARD:
                self.call("PUT", f"/dashboard/{d['id']}", json={"archived": True})
                self.call("DELETE", f"/dashboard/{d['id']}")
        for c in self.call("GET", "/card", params={"f": "all"}):
            if c["name"].startswith(PREFIJO):
                self.call("PUT", f"/card/{c['id']}", json={"archived": True})
                self.call("DELETE", f"/card/{c['id']}")

    def crear(self, db_id, ind):
        dashcards, cards = [], []
        texto = ("**Taxis amarillos y verdes de NYC (TLC), 2024–2026.** Fuente: `lab8.duckdb`, tabla `trips` y vistas "
                 "`trips_enriched` / `trips_valid`. 2026 llega hasta el último mes publicado, por eso los totales "
                 "anuales de 2026 no son comparables con 2024–2025; la tarjeta YTD usa los mismos meses en los tres "
                 "años. Filtros vacíos = todos los datos.")
        dashcards.append({"id": -1, "card_id": None, "row": 0, "col": 0, "size_x": 24, "size_y": 2,
                          "parameter_mappings": [],
                          "visualization_settings": {"virtual_card": {"name": None, "display": "text", "archived": False,
                                                                      "visualization_settings": {}, "dataset_query": {}},
                                                     "text": texto}})
        for i, t in enumerate(tarjetas(ind), start=2):
            tags = {k: {**v, "id": str(uuid.uuid4())} for k, v in TAGS.items()}
            card = self.call("POST", "/card", json={
                "name": PREFIJO + t["name"], "type": "question", "display": t["display"],
                "visualization_settings": t["viz"], "collection_id": None,
                "dataset_query": {"type": "native", "database": db_id,
                                  "native": {"query": t["sql"], "template-tags": tags}}})
            cards.append(card)
            col, row, sx, sy = t["pos"]
            dashcards.append({"id": -i, "card_id": card["id"], "row": row, "col": col, "size_x": sx, "size_y": sy,
                              "visualization_settings": {"card.title": t["name"]},
                              "parameter_mappings": [{"parameter_id": p["id"], "card_id": card["id"],
                                                      "target": ["variable", ["template-tag", p["slug"]]]}
                                                     for p in PARAMS]})
        dash = self.call("POST", "/dashboard", json={
            "name": DASHBOARD, "collection_id": None,
            "description": "Indicadores A–H y evolución YTD sobre data/processed/lab8.duckdb (sql/indicators.sql)."})
        self.call("PUT", f"/dashboard/{dash['id']}", json={"parameters": PARAMS, "dashcards": dashcards,
                                                         "width": "full"})
        return dash["id"], cards

    def public_link(self, dash_id, crear=True):
        if crear:
            self.call("PUT", "/setting/enable-public-sharing", json={"value": True})
            return self.call("POST", f"/dashboard/{dash_id}/public_link")["uuid"]
        self.call("DELETE", f"/dashboard/{dash_id}/public_link")
        self.call("PUT", "/setting/enable-public-sharing", json={"value": False})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.environ.get("MB_URL", "http://localhost:3000"))
    ap.add_argument("--public-link", action="store_true",
                    help="habilita un enlace público temporal (solo para capturar la imagen del tablero)")
    ap.add_argument("--revoke-public-link", action="store_true", help="revoca el enlace público y termina")
    a = ap.parse_args()
    email, password = os.environ.get("MB_EMAIL"), os.environ.get("MB_PASSWORD")
    if not email or not password:
        print("Define MB_EMAIL y MB_PASSWORD (usuario administrador de Metabase).", file=sys.stderr)
        return 1

    mb = Metabase(a.url)
    mb.login(email, password)
    if a.revoke_public_link:
        dash = next(d for d in mb.call("GET", "/dashboard/") if d["name"] == DASHBOARD)
        mb.public_link(dash["id"], crear=False)
        print("Enlace público revocado")
        return 0

    db_id = mb.database()
    mb.limpiar()
    dash_id, cards = mb.crear(db_id, cargar_sql(SQL_DIR / "indicators.sql"))
    for c in cards:                                   # cada tarjeta debe ejecutarse sin error
        r = mb.call("POST", f"/card/{c['id']}/query")
        estado = r.get("status")
        filas = len(r.get("data", {}).get("rows", []))
        print(f"  {c['name']:45s} {estado:10s} {filas:4d} filas")
        if estado != "completed":
            print("    error:", r.get("error"))
    print(f"Tablero: {a.url}/dashboard/{dash_id}")
    if a.public_link:
        print(f"Enlace público: {a.url}/public/dashboard/{mb.public_link(dash_id)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
