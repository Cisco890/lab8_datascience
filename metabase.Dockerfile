# Metabase + driver DuckDB (MotherDuck). El driver necesita glibc, por eso se usa
# una base Debian/Ubuntu en lugar de la imagen oficial de Metabase (Alpine).
FROM eclipse-temurin:21-jre-jammy

ARG METABASE_VERSION=0.63.17
ARG DUCKDB_DRIVER_VERSION=1.5.5.0

ENV MB_PLUGINS_DIR=/home/metabase/plugins/

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r metabase && useradd -r -g metabase metabase \
    && mkdir -p /home/metabase/plugins /metabase-data \
    && curl -fsSL -o /home/metabase/metabase.jar \
        "https://downloads.metabase.com/v${METABASE_VERSION}/metabase.jar" \
    && curl -fsSL -o /home/metabase/plugins/duckdb.metabase-driver.jar \
        "https://github.com/motherduckdb/metabase_duckdb_driver/releases/download/${DUCKDB_DRIVER_VERSION}/duckdb.metabase-driver.jar" \
    && chown -R metabase:metabase /home/metabase /metabase-data

WORKDIR /home/metabase
USER metabase
EXPOSE 3000

CMD ["java", "-jar", "/home/metabase/metabase.jar"]
