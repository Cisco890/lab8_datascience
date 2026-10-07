# Laboratorio 8 — DuckDB y TLC Trip Records

Análisis reproducible de los viajes de taxis amarillos (`yellow`) y verdes (`green`) de NYC
publicados por la TLC para 2024, 2025 y 2026, con DuckDB sobre Parquet, una tabla materializada,
un benchmark Parquet vs tabla, indicadores y un tablero en Metabase.

Flujo completo:

```text
Docker Compose → descarga incremental → Parquet en data/raw → consultas DuckDB directas → EDA
→ tabla materializada (lab8.duckdb) → benchmark → indicadores → Metabase → discusión y conclusiones
```

## Requisitos

- Docker y Docker Compose.
- Espacio en disco: unos 2.5 GB para los Parquet de 2024–2026, alrededor de 2.5 GB para
  `data/processed/lab8.duckdb` y unos 2 GB para las imágenes.
- Conexión a internet para descargar los datos y construir las imágenes.

## Levantar el ambiente

```bash
docker compose up --build -d
```

| Servicio   | URL                   | Puerto | Uso                                     |
|------------|-----------------------|--------|-----------------------------------------|
| `analysis` | http://localhost:8888 | 8888   | JupyterLab, Python, DuckDB              |
| `metabase` | http://localhost:3000 | 3000   | Tablero (driver DuckDB de MotherDuck)   |

`analysis` monta `data/`, `notebooks/`, `scripts/`, `sql/` y `docs/` en `/workspace`.
`metabase` monta `data/` en **solo lectura** en `/workspace/data`. La imagen de Metabase
(`metabase.Dockerfile`) usa una base Debian porque el driver DuckDB necesita glibc.

Para detener: `docker compose down` (los datos de Metabase quedan en el volumen `metabase_data`).

## Descargar datos

El script consulta en la TLC qué meses están publicados (petición `HEAD` por mes), descarga solo
los que faltan y nunca vuelve a descargar un archivo local válido. Por defecto procesa 2024, 2025 y
2026 para yellow y green.

```bash
docker compose exec analysis python scripts/download_data.py                       # 2024 2025 2026, yellow y green
docker compose exec analysis python scripts/download_data.py --years 2024 2025 2026  # equivalente explícito
docker compose exec analysis python scripts/download_data.py --years 2025 --taxi green
```

Verificar sin descargar (por tipo y año, comparando lo publicado con lo local):

```bash
docker compose exec analysis python scripts/download_data.py --verify --years 2024 2025 2026
```

Estructura resultante: `data/raw/<tipo>/<anio>/<tipo>_tripdata_<anio>-<mes>.parquet`.
"Completo" significa que todos los meses publicados están presentes; 2026 solo tiene los meses que la
TLC ya publicó.

## Ejecutar el análisis

1. Abrir http://localhost:8888 y luego `notebooks/lab8_duckdb.ipynb`.
2. Ejecutar todas las celdas **de arriba hacia abajo** (*Run All*). Tarda unos 10–15 minutos.

O sin abrir JupyterLab:

```bash
docker compose exec analysis jupyter nbconvert --to notebook --execute --inplace notebooks/lab8_duckdb.ipynb
```

El notebook descarga lo que falte (no-op si los Parquet ya existen), hace la exploración y el EDA
sobre Parquet, incorpora 2024 y 2025, materializa la base, corre el benchmark, calcula los indicadores
y la evolución interanual, y al final cierra todas las conexiones DuckDB.

Las consultas también se pueden correr por separado con los scripts:

```bash
docker compose exec analysis python scripts/run_eda.py --years 2026
docker compose exec analysis python scripts/validate_years.py
```

## Materializar DuckDB

La sección *19. Materialización en DuckDB* del notebook crea `data/processed/lab8.duckdb` con la
tabla `trips` (columnas normalizadas + `source_file`, `source_year`, `source_month`) y las vistas
`trips_enriched` (variables derivadas y banderas) y `trips_valid` (reglas de validez). La sección 22 la
reconstruye con los tres años. Desde la terminal:

```bash
docker compose exec analysis python scripts/materialize.py            # todos los años descargados
docker compose exec analysis python scripts/materialize.py --years 2024 2026
```

El proceso es idempotente (`CREATE OR REPLACE`) y cierra la conexión de escritura al terminar. Antes
de volver a materializar con Metabase en uso, detén Metabase (`docker compose stop metabase`) para
que no mantenga el archivo abierto.

## Reproducir el benchmark

Sección *Benchmark: Parquet vs tabla materializada* del notebook (y su continuación en la sección
22 para el escenario 2024+2025+2026). Desde la terminal, con la base ya materializada:

```bash
docker compose exec analysis python scripts/benchmark.py --repeats 5
```

Cada combinación consulta × fuente × escenario verifica primero que ambas fuentes den el mismo
resultado, hace 1 calentamiento y 5 mediciones con `time.perf_counter()` después de `fetchall()`.
El resumen (mediana, media, desviación, mínimo y máximo) se guarda en `docs/benchmark_results.csv`.
Las consultas están en `sql/benchmark.sql`.

## Generar los resultados principales

- **Indicadores:** sección *Indicadores y preguntas de análisis* del notebook. Las consultas
  definitivas están en `sql/indicators.sql` (bloques `-- name:`); el notebook las lee con
  `lab8_common.cargar_sql`. Con el CLI de DuckDB instalado en el host también se pueden ejecutar
  directo: `duckdb -readonly data/processed/lab8.duckdb < sql/indicators.sql`.
- **SQL del EDA y del benchmark:** `sql/eda.sql` y `sql/benchmark.sql` se generan con
  `python scripts/generate_sql.py` desde las mismas definiciones que usa el notebook.
- **Metabase:**
  1. Termina la ejecución del notebook (cierra las conexiones a `lab8.duckdb`).
  2. Abre http://localhost:3000. Si es la primera vez, el script del paso 3 crea el usuario
     administrador con las credenciales que le pases.
  3. Crea la conexión y el tablero:

     ```bash
     docker compose exec -e MB_EMAIL=<correo> -e MB_PASSWORD=<contraseña> analysis \
         python scripts/metabase_dashboard.py --url http://metabase:3000
     ```

     Conexión manual equivalente: *Admin → Databases → Add database → DuckDB*, archivo
     `/workspace/data/processed/lab8.duckdb` y la opción *Establish a read-only connection*.
  4. Abre el tablero **"Laboratorio 8 — Taxis NYC 2024–2026"** y usa los filtros año, tipo de taxi y mes.

  Detalles del tablero y cómo se tomó la captura: `docs/dashboard/README.md`.

## Estructura

```text
data/raw/          Parquet originales de la TLC, data/raw/<tipo>/<anio>/ (no versionados)
data/processed/    lab8.duckdb: tabla trips y vistas analíticas (no versionado)
notebooks/         lab8_duckdb.ipynb: análisis completo y documentado
scripts/           download_data.py (descarga/verificación por año), lab8_common.py (vistas y consultas),
                   materialize.py, benchmark.py, run_eda.py, validate_years.py, eda_plots.py,
                   generate_sql.py, metabase_dashboard.py
sql/               exploration.sql, eda.sql, benchmark.sql, indicators.sql
docs/              benchmark_results.csv y evidencia del tablero (docs/dashboard/)
```
