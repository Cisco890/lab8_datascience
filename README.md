# Laboratorio 8 — DuckDB y TLC Trip Records

Análisis reproducible de taxis amarillos y verdes de NYC (2026) con DuckDB,
consulta directa sobre Parquet, JupyterLab y Metabase.

## Requisitos

- Docker y Docker Compose

## Levantar el ambiente

Desde la raíz del proyecto:

```bash
docker compose up --build -d
```

Servicios:

| Servicio  | URL local                 | Puerto | Uso                          |
|-----------|---------------------------|--------|------------------------------|
| JupyterLab| http://localhost:8888     | 8888   | Notebooks y análisis         |
| Metabase  | http://localhost:3000     | 3000   | Tableros (configuración posterior) |

Carpetas montadas en el contenedor de análisis (`/workspace`):

- `data/`
- `notebooks/`
- `scripts/`
- `sql/`
- `docs/`
- `docker-compose.yml`, `Dockerfile` y `README.md` (lectura; ayudan a localizar la raíz)

Para detener:

```bash
docker compose down
```

## Descarga de datos 2026

El script descarga únicamente `yellow` y `green` del año 2026, consulta qué
meses están publicados en la TLC y omite archivos locales válidos.

Dentro del contenedor de análisis:

```bash
docker compose exec analysis python scripts/download_data.py
```

O desde el host (con las dependencias de `requirements.txt` instaladas):

```bash
python scripts/download_data.py
```

Archivos resultantes:

```text
data/raw/yellow/2026/yellow_tripdata_2026-MM.parquet
data/raw/green/2026/green_tripdata_2026-MM.parquet
```

## Verificar completitud

“Completo” significa que todos los meses **publicados** por la TLC están
presentes localmente y no están vacíos. No se exigen 12 meses.

```bash
docker compose exec analysis python scripts/download_data.py --verify
```

## Ejecutar el notebook

1. Abre http://localhost:8888
2. Abre `notebooks/lab8_duckdb.ipynb`
3. Ejecuta todas las celdas de arriba hacia abajo (`Run All`)

El notebook configura rutas buscando `docker-compose.yml`, por lo que funciona
tanto dentro del contenedor como en un entorno local si el cwd está en el
proyecto.

## Estructura

```text
data/raw/          Parquet originales de la TLC
data/processed/    Artefactos generados / DuckDB materializado
notebooks/         Análisis reproducible
scripts/           Automatización (descarga)
sql/               Consultas SQL documentadas
docs/              Evidencia auxiliar
```
