-- exploration.sql
-- Consultas principales de la exploración directa sobre Parquet (TLC 2026).
-- Ejecutar vía DuckDB; ajustar PROJECT_ROOT / globs según el entorno.

-- ============================================================================
-- Inventario: conteo de registros por tipo y mes (vía vistas normalizadas)
-- ============================================================================

-- Yellow: conteo por mes (ejemplo con glob)
-- SELECT
--     2026 AS source_year,
--     CAST(regexp_extract(filename, '(\d{4})-(\d{2})', 2) AS INTEGER) AS source_month,
--     COUNT(*) AS n_rows
-- FROM read_parquet('data/raw/yellow/2026/*.parquet',
--                   filename = true, union_by_name = true)
-- GROUP BY 1, 2
-- ORDER BY 2;

-- ============================================================================
-- Vista normalizada yellow
-- ============================================================================
-- CREATE OR REPLACE TEMP VIEW yellow_trips AS
-- SELECT
--     'yellow' AS taxi_type,
--     tpep_pickup_datetime AS pickup_datetime,
--     tpep_dropoff_datetime AS dropoff_datetime,
--     passenger_count,
--     trip_distance,
--     PULocationID AS pu_location_id,
--     DOLocationID AS do_location_id,
--     payment_type,
--     fare_amount,
--     tip_amount,
--     tolls_amount,
--     total_amount,
--     filename AS source_file,
--     CAST(regexp_extract(filename, '(\d{4})-(\d{2})', 1) AS INTEGER) AS source_year,
--     CAST(regexp_extract(filename, '(\d{4})-(\d{2})', 2) AS INTEGER) AS source_month
-- FROM read_parquet('data/raw/yellow/2026/*.parquet',
--                   filename = true, union_by_name = true);

-- ============================================================================
-- Vista normalizada green
-- ============================================================================
-- CREATE OR REPLACE TEMP VIEW green_trips AS
-- SELECT
--     'green' AS taxi_type,
--     lpep_pickup_datetime AS pickup_datetime,
--     lpep_dropoff_datetime AS dropoff_datetime,
--     passenger_count,
--     trip_distance,
--     PULocationID AS pu_location_id,
--     DOLocationID AS do_location_id,
--     payment_type,
--     fare_amount,
--     tip_amount,
--     tolls_amount,
--     total_amount,
--     filename AS source_file,
--     CAST(regexp_extract(filename, '(\d{4})-(\d{2})', 1) AS INTEGER) AS source_year,
--     CAST(regexp_extract(filename, '(\d{4})-(\d{2})', 2) AS INTEGER) AS source_month
-- FROM read_parquet('data/raw/green/2026/*.parquet',
--                   filename = true, union_by_name = true);

-- ============================================================================
-- Unión analítica
-- ============================================================================
-- CREATE OR REPLACE TEMP VIEW trips AS
-- SELECT * FROM yellow_trips
-- UNION ALL BY NAME
-- SELECT * FROM green_trips;

-- ============================================================================
-- Conteo total y por tipo
-- ============================================================================
SELECT taxi_type, COUNT(*) AS n_rows
FROM trips
GROUP BY taxi_type
ORDER BY taxi_type;

-- ============================================================================
-- Conteo por mes y tipo
-- ============================================================================
SELECT taxi_type, source_year, source_month, COUNT(*) AS n_rows
FROM trips
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- ============================================================================
-- Esquemas
-- ============================================================================
DESCRIBE SELECT * FROM read_parquet('data/raw/yellow/2026/*.parquet',
                                    filename = true, union_by_name = true)
LIMIT 0;

DESCRIBE SELECT * FROM read_parquet('data/raw/green/2026/*.parquet',
                                    filename = true, union_by_name = true)
LIMIT 0;

DESCRIBE trips;

-- ============================================================================
-- Muestra pequeña (ambos tipos)
-- ============================================================================
(
    SELECT * FROM trips WHERE taxi_type = 'yellow' LIMIT 5
)
UNION ALL BY NAME
(
    SELECT * FROM trips WHERE taxi_type = 'green' LIMIT 5
);

-- ============================================================================
-- Calidad de datos inicial
-- ============================================================================

-- Datetimes nulos
SELECT
    taxi_type,
    COUNT(*) FILTER (WHERE pickup_datetime IS NULL) AS null_pickup,
    COUNT(*) FILTER (WHERE dropoff_datetime IS NULL) AS null_dropoff,
    COUNT(*) AS n_rows
FROM trips
GROUP BY taxi_type;

-- Dropoff <= pickup
SELECT taxi_type, COUNT(*) AS n_invalid_order
FROM trips
WHERE dropoff_datetime IS NOT NULL
  AND pickup_datetime IS NOT NULL
  AND dropoff_datetime <= pickup_datetime
GROUP BY taxi_type;

-- Distancia negativa o cero
SELECT
    taxi_type,
    COUNT(*) FILTER (WHERE trip_distance < 0) AS negative_distance,
    COUNT(*) FILTER (WHERE trip_distance = 0) AS zero_distance
FROM trips
GROUP BY taxi_type;

-- Tarifas / montos negativos
SELECT
    taxi_type,
    COUNT(*) FILTER (WHERE fare_amount < 0) AS negative_fare,
    COUNT(*) FILTER (WHERE total_amount < 0) AS negative_total,
    COUNT(*) FILTER (WHERE passenger_count < 0) AS negative_passengers
FROM trips
GROUP BY taxi_type;

-- Duración excesiva (> 24 h) y velocidad implícita alta (> 100 mph)
-- Umbral 100 mph: regla analítica de detección, no prueba definitiva de invalidez.
SELECT
    taxi_type,
    COUNT(*) FILTER (
        WHERE pickup_datetime IS NOT NULL
          AND dropoff_datetime IS NOT NULL
          AND epoch(dropoff_datetime) - epoch(pickup_datetime) > 24 * 3600
    ) AS duration_over_24h,
    COUNT(*) FILTER (
        WHERE pickup_datetime IS NOT NULL
          AND dropoff_datetime IS NOT NULL
          AND epoch(dropoff_datetime) - epoch(pickup_datetime) > 0
          AND trip_distance >= 0
          AND trip_distance
              / ((epoch(dropoff_datetime) - epoch(pickup_datetime)) / 3600.0)
              > 100
    ) AS speed_over_100_mph
FROM trips
GROUP BY taxi_type;

-- Nulos en variables importantes
SELECT
    taxi_type,
    COUNT(*) FILTER (WHERE passenger_count IS NULL) AS null_passengers,
    COUNT(*) FILTER (WHERE trip_distance IS NULL) AS null_distance,
    COUNT(*) FILTER (WHERE pu_location_id IS NULL) AS null_pu,
    COUNT(*) FILTER (WHERE do_location_id IS NULL) AS null_do,
    COUNT(*) FILTER (WHERE fare_amount IS NULL) AS null_fare,
    COUNT(*) FILTER (WHERE total_amount IS NULL) AS null_total
FROM trips
GROUP BY taxi_type;

-- Percentiles extremos
SELECT
    taxi_type,
    approx_quantile(trip_distance, 0.01) AS dist_p01,
    approx_quantile(trip_distance, 0.50) AS dist_p50,
    approx_quantile(trip_distance, 0.99) AS dist_p99,
    approx_quantile(fare_amount, 0.01) AS fare_p01,
    approx_quantile(fare_amount, 0.50) AS fare_p50,
    approx_quantile(fare_amount, 0.99) AS fare_p99,
    approx_quantile(total_amount, 0.01) AS total_p01,
    approx_quantile(total_amount, 0.50) AS total_p50,
    approx_quantile(total_amount, 0.99) AS total_p99
FROM trips
GROUP BY taxi_type;
