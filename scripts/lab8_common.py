"""Configuración compartida: rutas, normalización de esquema, vistas analíticas y consultas del EDA."""
from __future__ import annotations

import os
import re
from pathlib import Path

import duckdb

from download_data import project_root_from

PROJECT_ROOT = project_root_from()
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
SQL_DIR = PROJECT_ROOT / "sql"
DOCS_DIR = PROJECT_ROOT / "docs"
DB_PATH = DATA_PROCESSED / "lab8.duckdb"

TAXIS = ("yellow", "green")
PICKUP_COLS = {"yellow": ("tpep_pickup_datetime", "tpep_dropoff_datetime"),
               "green": ("lpep_pickup_datetime", "lpep_dropoff_datetime")}
SPEED_THRESHOLD_MPH = 100       # regla de dominio (detección, no prueba de invalidez)
DURATION_LIMIT_MIN = 24 * 60    # regla de dominio: viaje > 24 h
THREADS = os.cpu_count() or 1

FLAGS = ["is_invalid_datetime", "is_negative_distance", "is_zero_distance", "is_negative_fare",
         "is_negative_total", "is_extreme_speed", "is_extreme_duration", "is_pickup_outside_source_month"]
# trips_valid excluye estas reglas; la distancia cero NO excluye (se marca y se reporta)
VALID_RULE = ("NOT (is_invalid_datetime OR is_negative_distance OR is_negative_fare OR "
              "is_negative_total OR is_extreme_speed OR is_extreme_duration)")

# Códigos de payment_type según el diccionario de datos oficial de la TLC
# (data_dictionary_trip_records_yellow.pdf / _green.pdf, revisión de 2025).
PAGO = {0: "Flex fare", 1: "Tarjeta", 2: "Efectivo", 3: "Sin cargo", 4: "Disputa", 5: "Desconocido", 6: "Anulado"}
DIAS = {1: "Lun", 2: "Mar", 3: "Mié", 4: "Jue", 5: "Vie", 6: "Sáb", 7: "Dom"}
COLOR = {"yellow": "#e0b400", "green": "#2e8b57"}


def anios_disponibles(taxis=TAXIS) -> tuple[int, ...]:
    """Años con al menos un Parquet en data/raw/<taxi>/<anio>/ (se descubren, no se fijan)."""
    return tuple(sorted({int(d.name) for t in taxis for d in (DATA_RAW / t).glob("[0-9]" * 4)
                         if any(d.glob("*.parquet"))}))


def sql_years(years) -> str:
    return ", ".join(str(int(y)) for y in years)


def years_con_datos(taxi: str, years) -> list[int]:
    return [y for y in years if any((DATA_RAW / taxi / str(y)).glob("*.parquet"))]


def select_normalizado(taxi: str, years) -> str | None:
    """Nombres y tipos explícitos; año/mes extraídos del nombre del archivo fuente."""
    pu, do = PICKUP_COLS[taxi]
    globs = [(DATA_RAW / taxi / str(y) / "*.parquet").as_posix() for y in years_con_datos(taxi, years)]
    if not globs:
        return None
    lista = "[" + ", ".join(f"'{g}'" for g in globs) + "]"
    return rf"""SELECT
    '{taxi}' AS taxi_type,
    CAST({pu} AS TIMESTAMP) AS pickup_datetime,
    CAST({do} AS TIMESTAMP) AS dropoff_datetime,
    TRY_CAST(passenger_count AS INTEGER) AS passenger_count,
    CAST(trip_distance AS DOUBLE) AS trip_distance,
    CAST(PULocationID AS INTEGER) AS pu_location_id,
    CAST(DOLocationID AS INTEGER) AS do_location_id,
    TRY_CAST(payment_type AS INTEGER) AS payment_type,
    CAST(fare_amount AS DOUBLE) AS fare_amount,
    CAST(tip_amount AS DOUBLE) AS tip_amount,
    CAST(tolls_amount AS DOUBLE) AS tolls_amount,
    CAST(total_amount AS DOUBLE) AS total_amount,
    parse_filename(filename) AS source_file,
    CAST(regexp_extract(filename, '_(\d{{4}})-(\d{{2}})\.parquet$', 1) AS INTEGER) AS source_year,
    CAST(regexp_extract(filename, '_(\d{{4}})-(\d{{2}})\.parquet$', 2) AS INTEGER) AS source_month
FROM read_parquet({lista}, filename = true, union_by_name = true)"""


def select_trips(years) -> str:
    partes = [p for p in (select_normalizado(t, years) for t in TAXIS) if p]
    return "\nUNION ALL BY NAME\n".join(partes)


SQL_ENRIQUECIDA = f"""
WITH base AS (
    SELECT *,
        date_diff('second', pickup_datetime, dropoff_datetime) / 60.0 AS trip_minutes,
        hour(pickup_datetime)         AS pickup_hour,
        CAST(pickup_datetime AS DATE) AS pickup_date,
        isodow(pickup_datetime)       AS pickup_weekday          -- 1 = lunes ... 7 = domingo
    FROM trips
), derivadas AS (
    SELECT *,
        -- propina % = 100 * tip_amount / fare_amount, solo tarjeta (payment_type = 1) y fare_amount > 0
        CASE WHEN payment_type = 1 AND fare_amount > 0 AND tip_amount IS NOT NULL
             THEN 100.0 * tip_amount / fare_amount END AS tip_percentage,
        -- velocidad solo con duración > 0 y distancia >= 0
        CASE WHEN trip_minutes > 0 AND trip_distance >= 0
             THEN trip_distance / (trip_minutes / 60.0) END AS avg_speed_mph
    FROM base
)
SELECT *,
    (pickup_datetime IS NULL OR dropoff_datetime IS NULL OR dropoff_datetime <= pickup_datetime) AS is_invalid_datetime,
    coalesce(trip_distance < 0, false) AS is_negative_distance,
    coalesce(trip_distance = 0, false) AS is_zero_distance,
    coalesce(fare_amount < 0, false)   AS is_negative_fare,
    coalesce(total_amount < 0, false)  AS is_negative_total,
    coalesce(avg_speed_mph > {SPEED_THRESHOLD_MPH}, false) AS is_extreme_speed,
    coalesce(trip_minutes > {DURATION_LIMIT_MIN}, false)   AS is_extreme_duration,
    coalesce(year(pickup_datetime) <> source_year OR month(pickup_datetime) <> source_month, false)
        AS is_pickup_outside_source_month
FROM derivadas
"""


def crear_vistas(con, years=None) -> None:
    """trips -> trips_enriched -> trips_valid (los años sin archivos se omiten)."""
    years = years or anios_disponibles()
    con.execute("CREATE OR REPLACE TEMP VIEW trips AS\n" + select_trips(years))
    crear_vistas_derivadas(con, temp=True)


def crear_vistas_derivadas(con, temp=False) -> None:
    """trips_enriched y trips_valid sobre una relación `trips` ya existente (vista o tabla)."""
    kind = "TEMP VIEW" if temp else "VIEW"
    con.execute(f"CREATE OR REPLACE {kind} trips_enriched AS" + SQL_ENRIQUECIDA)
    con.execute(f"CREATE OR REPLACE {kind} trips_valid AS SELECT * FROM trips_enriched WHERE {VALID_RULE}")


def cargar_sql(path) -> dict[str, str]:
    """Lee un archivo .sql con bloques `-- name: <id>` y devuelve {id: sql}."""
    bloques, actual = {}, None
    for linea in Path(path).read_text(encoding="utf-8").splitlines():
        m = re.match(r"--\s*name:\s*(\w+)", linea)
        if m:
            actual = m.group(1); bloques[actual] = []
        elif actual:
            bloques[actual].append(linea)
    return {k: "\n".join(v).strip().rstrip(";") for k, v in bloques.items()}


def nueva_conexion(database=":memory:", read_only=False):
    """Conexión DuckDB con la misma configuración en todo el proyecto (hilos fijos, sin barra de progreso)."""
    con = duckdb.connect(str(database), read_only=read_only)
    con.execute(f"SET threads = {THREADS}")
    try:
        con.execute("SET enable_progress_bar = false")
    except duckdb.Error:      # DuckDB 1.1 en Jupyter sin ipywidgets: la barra ya está inactiva
        pass
    return con


def conectar(years=None):
    """Conexión en memoria con las vistas analíticas creadas."""
    con = nueva_conexion()
    crear_vistas(con, years)
    return con


# ----------------------------------------------------------------------------- consultas del EDA
def sql_resumen(col, src="trips_valid", extra="TRUE"):
    qs = ", ".join(f"approx_quantile({col}, {p}) AS p{str(p)[2:].ljust(2, '0')}"
                   for p in (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 0.999))
    return f"""SELECT taxi_type, '{col}' AS metric, COUNT({col}) AS n, AVG({col}) AS mean, STDDEV_SAMP({col}) AS std,
       MIN({col}) AS min, {qs}, MAX({col}) AS max
FROM {src} WHERE source_year IN ({{years}}) AND {extra} GROUP BY taxi_type ORDER BY taxi_type"""


def sql_hist(col, width, cap):
    return f"""SELECT taxi_type, LEAST(FLOOR({col} / {width}) * {width}, {cap}) AS bin, COUNT(*) AS n
FROM trips_valid WHERE source_year IN ({{years}}) AND {col} >= 0 GROUP BY ALL ORDER BY ALL"""


def sql_top(col):
    return f"""SELECT taxi_type, {col}, COUNT(*) AS n_trips,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY taxi_type), 2) AS pct
FROM trips_enriched WHERE source_year IN ({{years}}) AND {col} IS NOT NULL
GROUP BY taxi_type, {col}
QUALIFY ROW_NUMBER() OVER (PARTITION BY taxi_type ORDER BY COUNT(*) DESC) <= 15
ORDER BY taxi_type, n_trips DESC"""


_flags_sql = ",\n       ".join(f"COUNT(*) FILTER (WHERE {f}) AS {f}" for f in FLAGS)
_en_fecha = "pickup_datetime IS NOT NULL AND NOT is_pickup_outside_source_month"

EDA_QUERIES = {
    "volumen_mensual": """SELECT source_year, source_month, taxi_type, COUNT(*) AS n_trips
FROM trips_enriched WHERE source_year IN ({years}) GROUP BY ALL ORDER BY ALL""",
    "demanda_hora": f"""SELECT taxi_type, pickup_hour, COUNT(*) AS n_trips,
       100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY taxi_type) AS pct_trips
FROM trips_enriched WHERE source_year IN ({{years}}) AND {_en_fecha}
GROUP BY taxi_type, pickup_hour ORDER BY taxi_type, pickup_hour""",
    "demanda_dia_semana": f"""SELECT taxi_type, pickup_weekday, COUNT(*) AS n_trips, COUNT(DISTINCT pickup_date) AS n_days,
       COUNT(*) / COUNT(DISTINCT pickup_date) AS avg_trips_per_day
FROM trips_enriched WHERE source_year IN ({{years}}) AND {_en_fecha} GROUP BY ALL ORDER BY ALL""",
    "resumen_distancia": sql_resumen("trip_distance"),
    "resumen_duracion": sql_resumen("trip_minutes"),
    "resumen_fare": sql_resumen("fare_amount"),
    "resumen_total": sql_resumen("total_amount"),
    "hist_distancia": sql_hist("trip_distance", 1, 20),
    "hist_duracion": sql_hist("trip_minutes", 5, 90),
    "hist_fare": sql_hist("fare_amount", 5, 100),
    "hist_total": sql_hist("total_amount", 5, 100),
    "distancia_vs_fare": """SELECT taxi_type, COUNT(*) AS n, corr(trip_distance, fare_amount) AS corr,
       regr_slope(fare_amount, trip_distance) AS slope_usd_per_mile, regr_intercept(fare_amount, trip_distance) AS intercept_usd
FROM trips_valid WHERE source_year IN ({years}) AND trip_distance > 0 AND fare_amount > 0 GROUP BY taxi_type ORDER BY taxi_type""",
    "pagos": """SELECT taxi_type, payment_type, COUNT(*) AS n_trips,
       100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY taxi_type) AS pct
FROM trips_enriched WHERE source_year IN ({years})
GROUP BY taxi_type, payment_type ORDER BY taxi_type, payment_type""",
    "propinas": """SELECT taxi_type, COUNT(*) AS n_aplicables, 100.0 * AVG((tip_amount > 0)::INT) AS pct_con_propina,
       AVG(tip_amount) AS mean_tip_usd, AVG(tip_percentage) AS mean_tip_pct,
       approx_quantile(tip_percentage, 0.25) AS p25_pct, approx_quantile(tip_percentage, 0.5) AS p50_pct,
       approx_quantile(tip_percentage, 0.75) AS p75_pct, approx_quantile(tip_percentage, 0.95) AS p95_pct,
       approx_quantile(tip_percentage, 0.99) AS p99_pct
FROM trips_valid WHERE source_year IN ({years}) AND payment_type = 1 AND fare_amount > 0 GROUP BY taxi_type ORDER BY taxi_type""",
    "propina_por_pago": """SELECT taxi_type, payment_type, COUNT(*) AS n_trips, 100.0 * AVG((tip_amount > 0)::INT) AS pct_tip_gt0
FROM trips_valid WHERE source_year IN ({years}) GROUP BY ALL ORDER BY ALL""",
    "flags_calidad": f"""SELECT taxi_type, COUNT(*) AS n_rows,
       {_flags_sql},
       COUNT(*) FILTER (WHERE {VALID_RULE}) AS n_valid
FROM trips_enriched WHERE source_year IN ({{years}}) GROUP BY taxi_type ORDER BY taxi_type""",
    "extremos_sin_filtrar": "\nUNION ALL\n".join(
        sql_resumen(c, src="trips_enriched").rsplit(" GROUP BY", 1)[0] + " GROUP BY taxi_type"
        for c in ("trip_distance", "trip_minutes", "fare_amount", "total_amount", "avg_speed_mph")),
    "top_pu": sql_top("pu_location_id"),
    "top_do": sql_top("do_location_id"),
    "comparacion": """SELECT taxi_type, COUNT(*) AS n_valid,
       AVG(trip_distance) AS dist_mean, median(trip_distance) AS dist_median,
       AVG(trip_minutes) AS min_mean, median(trip_minutes) AS min_median,
       AVG(fare_amount) AS fare_mean, median(fare_amount) AS fare_median,
       AVG(total_amount) AS total_mean, median(total_amount) AS total_median,
       100.0 * AVG((payment_type = 1)::INT) AS pct_tarjeta, 100.0 * AVG((payment_type = 2)::INT) AS pct_efectivo
FROM trips_valid WHERE source_year IN ({years}) GROUP BY taxi_type ORDER BY taxi_type""",
    "volumen_valido": "SELECT taxi_type, COUNT(*) AS n_rows, COUNT(*) FILTER (WHERE " + VALID_RULE + """) AS n_valid
FROM trips_enriched WHERE source_year IN ({years}) GROUP BY taxi_type ORDER BY taxi_type""",
}

SQL_MUESTRA = """SELECT trip_distance, fare_amount FROM (
    SELECT trip_distance, fare_amount FROM trips_valid
    WHERE source_year IN ({years}) AND taxi_type = '{taxi}'
      AND trip_distance > 0 AND trip_distance <= 30 AND fare_amount > 0 AND fare_amount <= 150
) USING SAMPLE reservoir(20000 ROWS) REPEATABLE (42)"""   # seed fija; con varios hilos no se garantiza idéntica


def q(con, name: str, years):
    """Ejecuta una consulta del EDA para el conjunto de años dado."""
    return con.execute(EDA_QUERIES[name].format(years=sql_years(years))).fetchdf()


def correr_eda(con, years) -> dict:
    return {n: q(con, n, years) for n in EDA_QUERIES}
