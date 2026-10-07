-- Ejecutar desde la raíz del proyecto. Generado por scripts/generate_sql.py

-- Cada consulta aparece sobre Parquet directo y sobre la tabla `trips` de data/processed/lab8.duckdb.
-- Para la versión tabla: ATTACH 'data/processed/lab8.duckdb' AS lab8 (READ_ONLY); USE lab8;

-- q1_conteo_taxi_anio | fuente: parquet | escenario: 2024+2025+2026
WITH scope AS (
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
FROM read_parquet(['data/raw/green/2024/*.parquet', 'data/raw/green/2025/*.parquet', 'data/raw/green/2026/*.parquet'], filename = true, union_by_name = true)
)
SELECT taxi_type, source_year, COUNT(*) AS n_trips FROM scope GROUP BY ALL ORDER BY ALL;

-- q1_conteo_taxi_anio | fuente: duckdb_table | escenario: 2024+2025+2026
WITH scope AS (SELECT * FROM trips WHERE source_year IN (2024, 2025, 2026))
SELECT taxi_type, source_year, COUNT(*) AS n_trips FROM scope GROUP BY ALL ORDER BY ALL;

-- q2_mensual | fuente: parquet | escenario: 2024+2025+2026
WITH scope AS (
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
FROM read_parquet(['data/raw/green/2024/*.parquet', 'data/raw/green/2025/*.parquet', 'data/raw/green/2026/*.parquet'], filename = true, union_by_name = true)
)
SELECT source_year, source_month, COUNT(*) AS n_trips, SUM(total_amount) AS sum_total
FROM scope GROUP BY ALL ORDER BY ALL;

-- q2_mensual | fuente: duckdb_table | escenario: 2024+2025+2026
WITH scope AS (SELECT * FROM trips WHERE source_year IN (2024, 2025, 2026))
SELECT source_year, source_month, COUNT(*) AS n_trips, SUM(total_amount) AS sum_total
FROM scope GROUP BY ALL ORDER BY ALL;

-- q3_taxi_media_mediana | fuente: parquet | escenario: 2024+2025+2026
WITH scope AS (
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
FROM read_parquet(['data/raw/green/2024/*.parquet', 'data/raw/green/2025/*.parquet', 'data/raw/green/2026/*.parquet'], filename = true, union_by_name = true)
)
SELECT taxi_type, COUNT(*) AS n_trips, AVG(trip_distance) AS avg_distance, median(fare_amount) AS median_fare
FROM scope GROUP BY ALL ORDER BY ALL;

-- q3_taxi_media_mediana | fuente: duckdb_table | escenario: 2024+2025+2026
WITH scope AS (SELECT * FROM trips WHERE source_year IN (2024, 2025, 2026))
SELECT taxi_type, COUNT(*) AS n_trips, AVG(trip_distance) AS avg_distance, median(fare_amount) AS median_fare
FROM scope GROUP BY ALL ORDER BY ALL;

-- q4_pago_filtrado | fuente: parquet | escenario: 2024+2025+2026
WITH scope AS (
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
FROM read_parquet(['data/raw/green/2024/*.parquet', 'data/raw/green/2025/*.parquet', 'data/raw/green/2026/*.parquet'], filename = true, union_by_name = true)
)
SELECT payment_type, COUNT(*) AS n_trips, AVG(tip_amount) AS avg_tip, AVG(total_amount) AS avg_total
FROM scope WHERE month(pickup_datetime) BETWEEN 3 AND 6 AND trip_distance > 0 AND total_amount > 0
GROUP BY ALL ORDER BY ALL;

-- q4_pago_filtrado | fuente: duckdb_table | escenario: 2024+2025+2026
WITH scope AS (SELECT * FROM trips WHERE source_year IN (2024, 2025, 2026))
SELECT payment_type, COUNT(*) AS n_trips, AVG(tip_amount) AS avg_tip, AVG(total_amount) AS avg_total
FROM scope WHERE month(pickup_datetime) BETWEEN 3 AND 6 AND trip_distance > 0 AND total_amount > 0
GROUP BY ALL ORDER BY ALL;

-- q5_hora_taxi | fuente: parquet | escenario: 2024+2025+2026
WITH scope AS (
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
FROM read_parquet(['data/raw/green/2024/*.parquet', 'data/raw/green/2025/*.parquet', 'data/raw/green/2026/*.parquet'], filename = true, union_by_name = true)
)
SELECT taxi_type, hour(pickup_datetime) AS pickup_hour, COUNT(*) AS n_trips, AVG(trip_distance) AS avg_distance
FROM scope WHERE pickup_datetime IS NOT NULL GROUP BY ALL ORDER BY ALL;

-- q5_hora_taxi | fuente: duckdb_table | escenario: 2024+2025+2026
WITH scope AS (SELECT * FROM trips WHERE source_year IN (2024, 2025, 2026))
SELECT taxi_type, hour(pickup_datetime) AS pickup_hour, COUNT(*) AS n_trips, AVG(trip_distance) AS avg_distance
FROM scope WHERE pickup_datetime IS NOT NULL GROUP BY ALL ORDER BY ALL;
