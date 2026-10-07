-- indicators.sql
-- Consultas definitivas de los indicadores del laboratorio.
--
-- Fuente: base persistente data/processed/lab8.duckdb
--   trips           tabla materializada y normalizada (2024, 2025 y 2026)
--   trips_enriched  vista con variables derivadas y banderas de calidad
--   trips_valid     vista trips_enriched sin: datetime inválido o duración no positiva,
--                   distancia/tarifa/total negativos, velocidad > 100 mph, duración > 24 h
--
-- Uso:
--   duckdb -readonly data/processed/lab8.duckdb < sql/indicators.sql   (CLI de DuckDB)
--   o, desde Python, lab8_common.cargar_sql('sql/indicators.sql') -> {nombre: sql}
--
-- El comentario /*filtros*/ marca dónde se agregan filtros opcionales sin duplicar
-- la consulta:
--   * notebook, comparación YTD:  AND source_month <= <último mes común>
--   * Metabase:                  [[AND source_year = {{anio}}]] [[AND taxi_type = {{taxi}}]] [[AND source_month = {{mes}}]]
-- Sin reemplazo, el comentario no tiene efecto y la consulta usa todos los datos.
--
-- Códigos de payment_type: diccionario oficial de la TLC
-- (Data Dictionary – Yellow Taxi Trip Records, 18-mar-2025): 0 = Flex Fare trip,
-- 1 = Credit card, 2 = Cash, 3 = No charge, 4 = Dispute, 5 = Unknown, 6 = Voided trip.
-- NULL no tiene código en el diccionario y se reporta como tal.


-- name: cobertura_meses
-- Meses disponibles por tipo y año (base para la comparación YTD).
SELECT taxi_type, source_year,
       MIN(source_month) AS min_month,
       MAX(source_month) AS max_month,
       COUNT(DISTINCT source_month) AS months_available
FROM trips
GROUP BY ALL
ORDER BY ALL;


-- name: ind_a_volumen_mensual
-- Indicador A. Registros por mes de archivo fuente y tipo (todos los registros publicados).
SELECT source_year, source_month, taxi_type,
       make_date(source_year, source_month, 1) AS month_start,
       COUNT(*) AS trip_count
FROM trips_enriched
WHERE TRUE /*filtros*/
GROUP BY ALL
ORDER BY ALL;


-- name: ind_b_distancia
-- Indicador B. Distancia típica (millas) de viajes válidos.
SELECT source_year, taxi_type,
       COUNT(*) AS n_valid,
       AVG(trip_distance) AS avg_distance_mi,
       median(trip_distance) AS median_distance_mi,
       quantile_cont(trip_distance, 0.95) AS p95_distance_mi
FROM trips_valid
WHERE TRUE /*filtros*/
GROUP BY ALL
ORDER BY ALL;


-- name: ind_c_duracion
-- Indicador C. Duración mediana (minutos) de viajes válidos. GROUPING SETS devuelve en una sola
-- consulta el nivel mensual y el anual (filas con source_month NULL = año completo disponible).
SELECT source_year, source_month, taxi_type,
       make_date(source_year, source_month, 1) AS month_start,
       COUNT(*) AS n_valid,
       median(trip_minutes) AS median_minutes,
       quantile_cont(trip_minutes, 0.25) AS p25_minutes,
       quantile_cont(trip_minutes, 0.75) AS p75_minutes
FROM trips_valid
WHERE TRUE /*filtros*/
GROUP BY GROUPING SETS ((source_year, source_month, taxi_type), (source_year, taxi_type))
ORDER BY source_year, taxi_type, source_month NULLS FIRST;


-- name: ind_d_monto_total
-- Indicador D. Monto total por viaje (USD) de viajes válidos (total_amount >= 0 por la regla de validez).
SELECT source_year, taxi_type,
       COUNT(*) AS n_valid,
       AVG(total_amount) AS avg_total_usd,
       median(total_amount) AS median_total_usd,
       AVG(fare_amount) AS avg_fare_usd
FROM trips_valid
WHERE TRUE /*filtros*/
GROUP BY ALL
ORDER BY ALL;


-- name: ind_e_pagos
-- Indicador E. Métodos de pago: cantidad y % dentro de cada tipo/año (todos los registros).
SELECT source_year, taxi_type, payment_type,
       CASE payment_type
            WHEN 0 THEN '0 Flex Fare' WHEN 1 THEN '1 Tarjeta' WHEN 2 THEN '2 Efectivo'
            WHEN 3 THEN '3 Sin cargo' WHEN 4 THEN '4 Disputa' WHEN 5 THEN '5 Desconocido'
            WHEN 6 THEN '6 Anulado' ELSE 'NULL (sin código)' END AS payment_label,
       COUNT(*) AS trip_count,
       100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY source_year, taxi_type) AS pct
FROM trips_enriched
WHERE TRUE /*filtros*/
GROUP BY source_year, taxi_type, payment_type
ORDER BY source_year, taxi_type, payment_type NULLS LAST;


-- name: ind_f_propinas
-- Indicador F. Propinas: solo viajes válidos pagados con tarjeta (la TLC no registra propinas en efectivo)
-- y con fare_amount > 0. tip_percentage = 100 * tip_amount / fare_amount.
SELECT source_year, taxi_type,
       COUNT(*) AS n_card_trips,
       100.0 * AVG((tip_amount > 0)::INTEGER) AS pct_with_tip,
       median(tip_percentage) AS median_tip_pct,
       AVG(tip_percentage) AS mean_tip_pct,
       median(tip_amount) AS median_tip_usd
FROM trips_valid
WHERE payment_type = 1 AND fare_amount > 0 /*filtros*/
GROUP BY ALL
ORDER BY ALL;


-- name: ind_g_demanda_hora_dia
-- Indicador G. Viajes por día de la semana (1 = lunes ... 7 = domingo) y hora de recogida.
-- Se excluyen pickups nulos o fuera del mes del archivo fuente.
SELECT taxi_type, pickup_weekday, pickup_hour,
       COUNT(*) AS trip_count,
       100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY taxi_type) AS pct_of_taxi
FROM trips_enriched
WHERE pickup_datetime IS NOT NULL AND NOT is_pickup_outside_source_month /*filtros*/
GROUP BY taxi_type, pickup_weekday, pickup_hour
ORDER BY ALL;


-- name: ind_h_calidad
-- Indicador H. % de registros con al menos una bandera problemática (todos los registros).
SELECT source_year, taxi_type,
       COUNT(*) AS n_rows,
       COUNT(*) FILTER (WHERE is_invalid_datetime OR is_negative_distance OR is_negative_fare
                           OR is_negative_total OR is_extreme_speed OR is_extreme_duration) AS n_flagged,
       100.0 * COUNT(*) FILTER (WHERE is_invalid_datetime OR is_negative_distance OR is_negative_fare
                                   OR is_negative_total OR is_extreme_speed OR is_extreme_duration)
             / COUNT(*) AS pct_flagged,
       100.0 * COUNT(*) FILTER (WHERE pickup_datetime IS NULL OR dropoff_datetime IS NULL) / COUNT(*) AS pct_null_datetime,
       100.0 * COUNT(*) FILTER (WHERE trip_minutes <= 0) / COUNT(*) AS pct_non_positive_duration,
       100.0 * COUNT(*) FILTER (WHERE is_negative_distance) / COUNT(*) AS pct_negative_distance,
       100.0 * COUNT(*) FILTER (WHERE is_negative_fare) / COUNT(*) AS pct_negative_fare,
       100.0 * COUNT(*) FILTER (WHERE is_negative_total) / COUNT(*) AS pct_negative_total,
       100.0 * COUNT(*) FILTER (WHERE is_extreme_speed) / COUNT(*) AS pct_extreme_speed,
       100.0 * COUNT(*) FILTER (WHERE is_extreme_duration) / COUNT(*) AS pct_extreme_duration
FROM trips_enriched
WHERE TRUE /*filtros*/
GROUP BY ALL
ORDER BY ALL;


-- name: ind_top_pickup
-- Pregunta complementaria: 10 PULocationID con más viajes por tipo y año.
-- Solo IDs: el proyecto no incluye el catálogo de zonas, por lo que no se asignan nombres.
SELECT source_year, taxi_type, pu_location_id, trip_count, pct, rank
FROM (
    SELECT source_year, taxi_type, pu_location_id,
           COUNT(*) AS trip_count,
           100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY source_year, taxi_type) AS pct,
           ROW_NUMBER() OVER (PARTITION BY source_year, taxi_type ORDER BY COUNT(*) DESC) AS rank
    FROM trips_enriched
    WHERE pu_location_id IS NOT NULL /*filtros*/
    GROUP BY source_year, taxi_type, pu_location_id
)
WHERE rank <= 10
ORDER BY source_year, taxi_type, rank;


-- name: ind_distancia_tarifa
-- Pregunta complementaria: relación distancia–tarifa en viajes válidos con distancia y tarifa positivas.
SELECT source_year, taxi_type,
       COUNT(*) AS n,
       corr(trip_distance, fare_amount) AS corr,
       regr_slope(fare_amount, trip_distance) AS slope_usd_per_mile,
       regr_intercept(fare_amount, trip_distance) AS intercept_usd,
       median(fare_amount / trip_distance) AS median_fare_per_mile
FROM trips_valid
WHERE trip_distance > 0 AND fare_amount > 0 /*filtros*/
GROUP BY ALL
ORDER BY ALL;


-- name: evo_volumen_ytd
-- Evolución interanual comparable: viajes de enero hasta el último mes común a todos los
-- tipos y años (se calcula, no se fija).
WITH cobertura AS (
    SELECT MIN(max_month) AS mes_comun
    FROM (SELECT taxi_type, source_year, MAX(source_month) AS max_month FROM trips GROUP BY ALL)
)
SELECT source_year, taxi_type, mes_comun, COUNT(*) AS trips_ytd
FROM trips_enriched, cobertura
WHERE source_month <= mes_comun /*filtros*/
GROUP BY ALL
ORDER BY ALL;
