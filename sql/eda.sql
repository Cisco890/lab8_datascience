-- Consultas principales del EDA y comparación yellow/green (años 2024, 2025, 2026). Editar `source_year IN (...)` para otros años.

-- Vistas analíticas: trips (normalizada), trips_enriched (derivadas), trips_valid (reglas de calidad)
CREATE OR REPLACE TEMP VIEW trips AS
SELECT
    'yellow' AS taxi_type,
    CAST(tpep_pickup_datetime AS TIMESTAMP) AS pickup_datetime,
    CAST(tpep_dropoff_datetime AS TIMESTAMP) AS dropoff_datetime,
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
    CAST(regexp_extract(filename, '_(\d{4})-(\d{2})\.parquet$', 1) AS INTEGER) AS source_year,
    CAST(regexp_extract(filename, '_(\d{4})-(\d{2})\.parquet$', 2) AS INTEGER) AS source_month
FROM read_parquet(['data/raw/yellow/2024/*.parquet', 'data/raw/yellow/2025/*.parquet', 'data/raw/yellow/2026/*.parquet'], filename = true, union_by_name = true)
UNION ALL BY NAME
SELECT
    'green' AS taxi_type,
    CAST(lpep_pickup_datetime AS TIMESTAMP) AS pickup_datetime,
    CAST(lpep_dropoff_datetime AS TIMESTAMP) AS dropoff_datetime,
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
    CAST(regexp_extract(filename, '_(\d{4})-(\d{2})\.parquet$', 1) AS INTEGER) AS source_year,
    CAST(regexp_extract(filename, '_(\d{4})-(\d{2})\.parquet$', 2) AS INTEGER) AS source_month
FROM read_parquet(['data/raw/green/2024/*.parquet', 'data/raw/green/2025/*.parquet', 'data/raw/green/2026/*.parquet'], filename = true, union_by_name = true);

CREATE OR REPLACE TEMP VIEW trips_enriched AS
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
    coalesce(avg_speed_mph > 100, false) AS is_extreme_speed,
    coalesce(trip_minutes > 1440, false)   AS is_extreme_duration,
    coalesce(year(pickup_datetime) <> source_year OR month(pickup_datetime) <> source_month, false)
        AS is_pickup_outside_source_month
FROM derivadas
;

-- trips_valid excluye: fechas inválidas, distancia/tarifa/total negativos, velocidad > 100 mph, duración > 24 h.
-- La distancia cero NO se excluye (se marca con is_zero_distance).
CREATE OR REPLACE TEMP VIEW trips_valid AS SELECT * FROM trips_enriched WHERE NOT (is_invalid_datetime OR is_negative_distance OR is_negative_fare OR is_negative_total OR is_extreme_speed OR is_extreme_duration);

-- volumen_mensual
SELECT source_year, source_month, taxi_type, COUNT(*) AS n_trips
FROM trips_enriched WHERE source_year IN (2024, 2025, 2026) GROUP BY ALL ORDER BY ALL;

-- demanda_hora
SELECT taxi_type, pickup_hour, COUNT(*) AS n_trips,
       100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY taxi_type) AS pct_trips
FROM trips_enriched WHERE source_year IN (2024, 2025, 2026) AND pickup_datetime IS NOT NULL AND NOT is_pickup_outside_source_month
GROUP BY taxi_type, pickup_hour ORDER BY taxi_type, pickup_hour;

-- demanda_dia_semana
SELECT taxi_type, pickup_weekday, COUNT(*) AS n_trips, COUNT(DISTINCT pickup_date) AS n_days,
       COUNT(*) / COUNT(DISTINCT pickup_date) AS avg_trips_per_day
FROM trips_enriched WHERE source_year IN (2024, 2025, 2026) AND pickup_datetime IS NOT NULL AND NOT is_pickup_outside_source_month GROUP BY ALL ORDER BY ALL;

-- resumen_distancia
SELECT taxi_type, 'trip_distance' AS metric, COUNT(trip_distance) AS n, AVG(trip_distance) AS mean, STDDEV_SAMP(trip_distance) AS std,
       MIN(trip_distance) AS min, approx_quantile(trip_distance, 0.01) AS p01, approx_quantile(trip_distance, 0.05) AS p05, approx_quantile(trip_distance, 0.25) AS p25, approx_quantile(trip_distance, 0.5) AS p50, approx_quantile(trip_distance, 0.75) AS p75, approx_quantile(trip_distance, 0.95) AS p95, approx_quantile(trip_distance, 0.99) AS p99, approx_quantile(trip_distance, 0.999) AS p999, MAX(trip_distance) AS max
FROM trips_valid WHERE source_year IN (2024, 2025, 2026) AND TRUE GROUP BY taxi_type ORDER BY taxi_type;

-- resumen_duracion
SELECT taxi_type, 'trip_minutes' AS metric, COUNT(trip_minutes) AS n, AVG(trip_minutes) AS mean, STDDEV_SAMP(trip_minutes) AS std,
       MIN(trip_minutes) AS min, approx_quantile(trip_minutes, 0.01) AS p01, approx_quantile(trip_minutes, 0.05) AS p05, approx_quantile(trip_minutes, 0.25) AS p25, approx_quantile(trip_minutes, 0.5) AS p50, approx_quantile(trip_minutes, 0.75) AS p75, approx_quantile(trip_minutes, 0.95) AS p95, approx_quantile(trip_minutes, 0.99) AS p99, approx_quantile(trip_minutes, 0.999) AS p999, MAX(trip_minutes) AS max
FROM trips_valid WHERE source_year IN (2024, 2025, 2026) AND TRUE GROUP BY taxi_type ORDER BY taxi_type;

-- resumen_fare
SELECT taxi_type, 'fare_amount' AS metric, COUNT(fare_amount) AS n, AVG(fare_amount) AS mean, STDDEV_SAMP(fare_amount) AS std,
       MIN(fare_amount) AS min, approx_quantile(fare_amount, 0.01) AS p01, approx_quantile(fare_amount, 0.05) AS p05, approx_quantile(fare_amount, 0.25) AS p25, approx_quantile(fare_amount, 0.5) AS p50, approx_quantile(fare_amount, 0.75) AS p75, approx_quantile(fare_amount, 0.95) AS p95, approx_quantile(fare_amount, 0.99) AS p99, approx_quantile(fare_amount, 0.999) AS p999, MAX(fare_amount) AS max
FROM trips_valid WHERE source_year IN (2024, 2025, 2026) AND TRUE GROUP BY taxi_type ORDER BY taxi_type;

-- resumen_total
SELECT taxi_type, 'total_amount' AS metric, COUNT(total_amount) AS n, AVG(total_amount) AS mean, STDDEV_SAMP(total_amount) AS std,
       MIN(total_amount) AS min, approx_quantile(total_amount, 0.01) AS p01, approx_quantile(total_amount, 0.05) AS p05, approx_quantile(total_amount, 0.25) AS p25, approx_quantile(total_amount, 0.5) AS p50, approx_quantile(total_amount, 0.75) AS p75, approx_quantile(total_amount, 0.95) AS p95, approx_quantile(total_amount, 0.99) AS p99, approx_quantile(total_amount, 0.999) AS p999, MAX(total_amount) AS max
FROM trips_valid WHERE source_year IN (2024, 2025, 2026) AND TRUE GROUP BY taxi_type ORDER BY taxi_type;

-- hist_distancia
SELECT taxi_type, LEAST(FLOOR(trip_distance / 1) * 1, 20) AS bin, COUNT(*) AS n
FROM trips_valid WHERE source_year IN (2024, 2025, 2026) AND trip_distance >= 0 GROUP BY ALL ORDER BY ALL;

-- hist_duracion
SELECT taxi_type, LEAST(FLOOR(trip_minutes / 5) * 5, 90) AS bin, COUNT(*) AS n
FROM trips_valid WHERE source_year IN (2024, 2025, 2026) AND trip_minutes >= 0 GROUP BY ALL ORDER BY ALL;

-- hist_fare
SELECT taxi_type, LEAST(FLOOR(fare_amount / 5) * 5, 100) AS bin, COUNT(*) AS n
FROM trips_valid WHERE source_year IN (2024, 2025, 2026) AND fare_amount >= 0 GROUP BY ALL ORDER BY ALL;

-- hist_total
SELECT taxi_type, LEAST(FLOOR(total_amount / 5) * 5, 100) AS bin, COUNT(*) AS n
FROM trips_valid WHERE source_year IN (2024, 2025, 2026) AND total_amount >= 0 GROUP BY ALL ORDER BY ALL;

-- distancia_vs_fare
SELECT taxi_type, COUNT(*) AS n, corr(trip_distance, fare_amount) AS corr,
       regr_slope(fare_amount, trip_distance) AS slope_usd_per_mile, regr_intercept(fare_amount, trip_distance) AS intercept_usd
FROM trips_valid WHERE source_year IN (2024, 2025, 2026) AND trip_distance > 0 AND fare_amount > 0 GROUP BY taxi_type ORDER BY taxi_type;

-- pagos
SELECT taxi_type, payment_type, COUNT(*) AS n_trips,
       100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY taxi_type) AS pct
FROM trips_enriched WHERE source_year IN (2024, 2025, 2026)
GROUP BY taxi_type, payment_type ORDER BY taxi_type, payment_type;

-- propinas
SELECT taxi_type, COUNT(*) AS n_aplicables, 100.0 * AVG((tip_amount > 0)::INT) AS pct_con_propina,
       AVG(tip_amount) AS mean_tip_usd, AVG(tip_percentage) AS mean_tip_pct,
       approx_quantile(tip_percentage, 0.25) AS p25_pct, approx_quantile(tip_percentage, 0.5) AS p50_pct,
       approx_quantile(tip_percentage, 0.75) AS p75_pct, approx_quantile(tip_percentage, 0.95) AS p95_pct,
       approx_quantile(tip_percentage, 0.99) AS p99_pct
FROM trips_valid WHERE source_year IN (2024, 2025, 2026) AND payment_type = 1 AND fare_amount > 0 GROUP BY taxi_type ORDER BY taxi_type;

-- propina_por_pago
SELECT taxi_type, payment_type, COUNT(*) AS n_trips, 100.0 * AVG((tip_amount > 0)::INT) AS pct_tip_gt0
FROM trips_valid WHERE source_year IN (2024, 2025, 2026) GROUP BY ALL ORDER BY ALL;

-- flags_calidad
SELECT taxi_type, COUNT(*) AS n_rows,
       COUNT(*) FILTER (WHERE is_invalid_datetime) AS is_invalid_datetime,
       COUNT(*) FILTER (WHERE is_negative_distance) AS is_negative_distance,
       COUNT(*) FILTER (WHERE is_zero_distance) AS is_zero_distance,
       COUNT(*) FILTER (WHERE is_negative_fare) AS is_negative_fare,
       COUNT(*) FILTER (WHERE is_negative_total) AS is_negative_total,
       COUNT(*) FILTER (WHERE is_extreme_speed) AS is_extreme_speed,
       COUNT(*) FILTER (WHERE is_extreme_duration) AS is_extreme_duration,
       COUNT(*) FILTER (WHERE is_pickup_outside_source_month) AS is_pickup_outside_source_month,
       COUNT(*) FILTER (WHERE NOT (is_invalid_datetime OR is_negative_distance OR is_negative_fare OR is_negative_total OR is_extreme_speed OR is_extreme_duration)) AS n_valid
FROM trips_enriched WHERE source_year IN (2024, 2025, 2026) GROUP BY taxi_type ORDER BY taxi_type;

-- extremos_sin_filtrar
SELECT taxi_type, 'trip_distance' AS metric, COUNT(trip_distance) AS n, AVG(trip_distance) AS mean, STDDEV_SAMP(trip_distance) AS std,
       MIN(trip_distance) AS min, approx_quantile(trip_distance, 0.01) AS p01, approx_quantile(trip_distance, 0.05) AS p05, approx_quantile(trip_distance, 0.25) AS p25, approx_quantile(trip_distance, 0.5) AS p50, approx_quantile(trip_distance, 0.75) AS p75, approx_quantile(trip_distance, 0.95) AS p95, approx_quantile(trip_distance, 0.99) AS p99, approx_quantile(trip_distance, 0.999) AS p999, MAX(trip_distance) AS max
FROM trips_enriched WHERE source_year IN (2024, 2025, 2026) AND TRUE GROUP BY taxi_type
UNION ALL
SELECT taxi_type, 'trip_minutes' AS metric, COUNT(trip_minutes) AS n, AVG(trip_minutes) AS mean, STDDEV_SAMP(trip_minutes) AS std,
       MIN(trip_minutes) AS min, approx_quantile(trip_minutes, 0.01) AS p01, approx_quantile(trip_minutes, 0.05) AS p05, approx_quantile(trip_minutes, 0.25) AS p25, approx_quantile(trip_minutes, 0.5) AS p50, approx_quantile(trip_minutes, 0.75) AS p75, approx_quantile(trip_minutes, 0.95) AS p95, approx_quantile(trip_minutes, 0.99) AS p99, approx_quantile(trip_minutes, 0.999) AS p999, MAX(trip_minutes) AS max
FROM trips_enriched WHERE source_year IN (2024, 2025, 2026) AND TRUE GROUP BY taxi_type
UNION ALL
SELECT taxi_type, 'fare_amount' AS metric, COUNT(fare_amount) AS n, AVG(fare_amount) AS mean, STDDEV_SAMP(fare_amount) AS std,
       MIN(fare_amount) AS min, approx_quantile(fare_amount, 0.01) AS p01, approx_quantile(fare_amount, 0.05) AS p05, approx_quantile(fare_amount, 0.25) AS p25, approx_quantile(fare_amount, 0.5) AS p50, approx_quantile(fare_amount, 0.75) AS p75, approx_quantile(fare_amount, 0.95) AS p95, approx_quantile(fare_amount, 0.99) AS p99, approx_quantile(fare_amount, 0.999) AS p999, MAX(fare_amount) AS max
FROM trips_enriched WHERE source_year IN (2024, 2025, 2026) AND TRUE GROUP BY taxi_type
UNION ALL
SELECT taxi_type, 'total_amount' AS metric, COUNT(total_amount) AS n, AVG(total_amount) AS mean, STDDEV_SAMP(total_amount) AS std,
       MIN(total_amount) AS min, approx_quantile(total_amount, 0.01) AS p01, approx_quantile(total_amount, 0.05) AS p05, approx_quantile(total_amount, 0.25) AS p25, approx_quantile(total_amount, 0.5) AS p50, approx_quantile(total_amount, 0.75) AS p75, approx_quantile(total_amount, 0.95) AS p95, approx_quantile(total_amount, 0.99) AS p99, approx_quantile(total_amount, 0.999) AS p999, MAX(total_amount) AS max
FROM trips_enriched WHERE source_year IN (2024, 2025, 2026) AND TRUE GROUP BY taxi_type
UNION ALL
SELECT taxi_type, 'avg_speed_mph' AS metric, COUNT(avg_speed_mph) AS n, AVG(avg_speed_mph) AS mean, STDDEV_SAMP(avg_speed_mph) AS std,
       MIN(avg_speed_mph) AS min, approx_quantile(avg_speed_mph, 0.01) AS p01, approx_quantile(avg_speed_mph, 0.05) AS p05, approx_quantile(avg_speed_mph, 0.25) AS p25, approx_quantile(avg_speed_mph, 0.5) AS p50, approx_quantile(avg_speed_mph, 0.75) AS p75, approx_quantile(avg_speed_mph, 0.95) AS p95, approx_quantile(avg_speed_mph, 0.99) AS p99, approx_quantile(avg_speed_mph, 0.999) AS p999, MAX(avg_speed_mph) AS max
FROM trips_enriched WHERE source_year IN (2024, 2025, 2026) AND TRUE GROUP BY taxi_type;

-- top_pu
SELECT taxi_type, pu_location_id, COUNT(*) AS n_trips,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY taxi_type), 2) AS pct
FROM trips_enriched WHERE source_year IN (2024, 2025, 2026) AND pu_location_id IS NOT NULL
GROUP BY taxi_type, pu_location_id
QUALIFY ROW_NUMBER() OVER (PARTITION BY taxi_type ORDER BY COUNT(*) DESC) <= 15
ORDER BY taxi_type, n_trips DESC;

-- top_do
SELECT taxi_type, do_location_id, COUNT(*) AS n_trips,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY taxi_type), 2) AS pct
FROM trips_enriched WHERE source_year IN (2024, 2025, 2026) AND do_location_id IS NOT NULL
GROUP BY taxi_type, do_location_id
QUALIFY ROW_NUMBER() OVER (PARTITION BY taxi_type ORDER BY COUNT(*) DESC) <= 15
ORDER BY taxi_type, n_trips DESC;

-- comparacion
SELECT taxi_type, COUNT(*) AS n_valid,
       AVG(trip_distance) AS dist_mean, median(trip_distance) AS dist_median,
       AVG(trip_minutes) AS min_mean, median(trip_minutes) AS min_median,
       AVG(fare_amount) AS fare_mean, median(fare_amount) AS fare_median,
       AVG(total_amount) AS total_mean, median(total_amount) AS total_median,
       100.0 * AVG((payment_type = 1)::INT) AS pct_tarjeta, 100.0 * AVG((payment_type = 2)::INT) AS pct_efectivo
FROM trips_valid WHERE source_year IN (2024, 2025, 2026) GROUP BY taxi_type ORDER BY taxi_type;

-- volumen_valido
SELECT taxi_type, COUNT(*) AS n_rows, COUNT(*) FILTER (WHERE NOT (is_invalid_datetime OR is_negative_distance OR is_negative_fare OR is_negative_total OR is_extreme_speed OR is_extreme_duration)) AS n_valid
FROM trips_enriched WHERE source_year IN (2024, 2025, 2026) GROUP BY taxi_type ORDER BY taxi_type;

-- muestra controlada distancia vs tarifa (yellow; repetir con 'green')
SELECT trip_distance, fare_amount FROM (
    SELECT trip_distance, fare_amount FROM trips_valid
    WHERE source_year IN (2024, 2025, 2026) AND taxi_type = 'yellow'
      AND trip_distance > 0 AND trip_distance <= 30 AND fare_amount > 0 AND fare_amount <= 150
) USING SAMPLE reservoir(20000 ROWS) REPEATABLE (42);
