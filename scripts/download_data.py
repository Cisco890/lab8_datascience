#!/usr/bin/env python3
"""Descarga taxis amarillos y verdes de la TLC (NYC) en formato Parquet.

Por defecto trabaja con yellow y green de los años 2024 y 2026 (se puede elegir
otro conjunto con ``--years``). Consulta qué meses están publicados mediante
HEAD, descarga por streaming a un temporal ``.part`` y renombra al finalizar.
Omite archivos locales válidos, por lo que es incremental.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import requests

BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"
DEFAULT_TAXI_TYPES = ("yellow", "green")
DEFAULT_YEARS = (2024, 2026)
DEFAULT_TIMEOUT = 60
DEFAULT_RETRIES = 3
DEFAULT_RETRY_WAIT = 2.0
USER_AGENT = "lab8-datascience-download/1.0"


def construir_nombre(tipo: str, anio: int, mes: int) -> str:
    return f"{tipo}_tripdata_{anio}-{mes:02d}.parquet"


def construir_url(tipo: str, anio: int, mes: int) -> str:
    return f"{BASE_URL}/{construir_nombre(tipo, anio, mes)}"


def ruta_destino(
    tipo: str, anio: int, mes: int, root: Path | None = None
) -> Path:
    """data/raw/<tipo>/<anio>/<archivo>.parquet"""
    root = root or project_root_from()
    return root / "data" / "raw" / tipo / str(anio) / construir_nombre(tipo, anio, mes)


@dataclass
class MonthStatus:
    """Estado de un mes para un tipo de taxi."""

    taxi_type: str
    year: int
    month: int
    published: bool = False
    local_exists: bool = False
    local_size: int = 0
    downloaded: bool = False
    skipped_existing: bool = False
    failed: bool = False
    error: str | None = None
    remote_size: int | None = None

    @property
    def filename(self) -> str:
        return construir_nombre(self.taxi_type, self.year, self.month)

    @property
    def url(self) -> str:
        return construir_url(self.taxi_type, self.year, self.month)


@dataclass
class DownloadSummary:
    """Resumen agregado de una corrida de descarga o verificación."""

    statuses: list[MonthStatus] = field(default_factory=list)

    def by_flag(self, attr: str) -> list[MonthStatus]:
        return [s for s in self.statuses if getattr(s, attr)]

    def print_report(self) -> None:
        downloaded = self.by_flag("downloaded")
        skipped = self.by_flag("skipped_existing")
        failed = self.by_flag("failed")
        published = self.by_flag("published")
        unpublished = [s for s in self.statuses if not s.published]

        print("\n=== Resumen de descarga / verificación ===")
        print(f"Meses publicados en TLC: {len(published)}")
        print(f"Descargados ahora:        {len(downloaded)}")
        print(f"Ya existían:              {len(skipped)}")
        print(f"Aún no publicados:        {len(unpublished)}")
        print(f"Fallidos:                 {len(failed)}")

        if downloaded:
            print("\nDescargados:")
            for s in downloaded:
                print(f"  + {s.filename}")
        if skipped:
            print("\nOmitidos (ya existían):")
            for s in skipped:
                print(f"  = {s.filename} ({s.local_size:,} bytes)")
        if unpublished:
            print("\nNo publicados todavía:")
            for s in unpublished:
                print(f"  - {s.taxi_type} {s.year}-{s.month:02d}")
        if failed:
            print("\nFallidos:")
            for s in failed:
                print(f"  ! {s.filename}: {s.error}")


def project_root_from(start: Path | None = None) -> Path:
    """Localiza la raíz del proyecto buscando ``docker-compose.yml``.

    También acepta un directorio que ya contenga la estructura del laboratorio
    (data/, notebooks/, scripts/) por si se ejecuta en un montaje parcial.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "docker-compose.yml").is_file():
            return candidate
        markers = (
            (candidate / "data").is_dir()
            and (candidate / "notebooks").is_dir()
            and (candidate / "scripts" / "download_data.py").is_file()
        )
        if markers:
            return candidate
    raise FileNotFoundError(
        "No se encontró la raíz del proyecto (docker-compose.yml o estructura lab)."
    )


def local_path(root: Path, taxi_type: str, year: int, filename: str) -> Path:
    """Compatibilidad: ruta a partir del nombre de archivo."""
    return root / "data" / "raw" / taxi_type / str(year) / filename


def is_valid_local(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def head_published(
    session: requests.Session,
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[bool, int | None]:
    """Devuelve (publicado, content_length) según respuesta HEAD."""
    try:
        response = session.head(url, timeout=timeout, allow_redirects=True)
        if response.status_code == 200:
            length = response.headers.get("Content-Length")
            return True, int(length) if length is not None else None
        return False, None
    except requests.RequestException:
        return False, None


def discover_published_months(
    session: requests.Session,
    taxi_types: Iterable[str],
    year: int,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[MonthStatus]:
    """Consulta los 12 meses posibles y marca cuáles están publicados."""
    statuses: list[MonthStatus] = []
    for taxi_type in taxi_types:
        for month in range(1, 13):
            status = MonthStatus(taxi_type=taxi_type, year=year, month=month)
            published, remote_size = head_published(session, status.url, timeout)
            status.published = published
            status.remote_size = remote_size
            statuses.append(status)
    return statuses


def download_file(
    session: requests.Session,
    url: str,
    destination: Path,
    retries: int = DEFAULT_RETRIES,
    timeout: int = DEFAULT_TIMEOUT,
    retry_wait: float = DEFAULT_RETRY_WAIT,
) -> int:
    """Descarga ``url`` a ``destination`` vía temporal ``.part``.

    Returns:
        Tamaño final en bytes.

    Raises:
        RuntimeError: si agota reintentos o el archivo queda vacío.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(destination.suffix + ".part")

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            if temp_path.exists():
                temp_path.unlink()

            with session.get(url, stream=True, timeout=timeout) as response:
                response.raise_for_status()
                with temp_path.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            handle.write(chunk)

            size = temp_path.stat().st_size
            if size <= 0:
                temp_path.unlink(missing_ok=True)
                raise RuntimeError("archivo descargado vacío")

            temp_path.replace(destination)
            return size
        except (requests.RequestException, OSError, RuntimeError) as exc:
            last_error = exc
            temp_path.unlink(missing_ok=True)
            if attempt < retries:
                time.sleep(retry_wait * attempt)
                continue
            raise RuntimeError(
                f"falló descarga de {url} tras {retries} intentos: {exc}"
            ) from last_error

    raise RuntimeError(f"falló descarga de {url}: {last_error}")


def _nueva_sesion() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def verificar(
    tipo: str,
    anio: int,
    root: Path | None = None,
    session: requests.Session | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[MonthStatus]:
    """Compara meses publicados en la TLC con archivos locales no vacíos
    para un tipo de taxi y un año."""
    root = root or project_root_from()
    own_session = session is None
    session = session or _nueva_sesion()
    try:
        statuses = discover_published_months(session, [tipo], anio, timeout)
        for status in statuses:
            path = ruta_destino(tipo, anio, status.month, root)
            status.local_exists = is_valid_local(path)
            status.local_size = path.stat().st_size if path.exists() else 0
        return statuses
    finally:
        if own_session:
            session.close()


def descargar(
    tipo: str,
    anio: int,
    root: Path | None = None,
    session: requests.Session | None = None,
    retries: int = DEFAULT_RETRIES,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[MonthStatus]:
    """Descarga los meses publicados que falten para un tipo y año.

    Nunca toca otros años y nunca vuelve a descargar un archivo local válido.
    """
    root = root or project_root_from()
    own_session = session is None
    session = session or _nueva_sesion()
    try:
        statuses = discover_published_months(session, [tipo], anio, timeout)
        for status in statuses:
            path = ruta_destino(tipo, anio, status.month, root)
            if is_valid_local(path):
                status.local_exists = True
                status.local_size = path.stat().st_size
                if status.published:
                    status.skipped_existing = True
                continue
            if not status.published:
                continue

            logging.info("Descargando %s", status.filename)
            try:
                size = download_file(
                    session, status.url, path, retries=retries, timeout=timeout
                )
                status.downloaded = True
                status.local_exists = True
                status.local_size = size
                print(f"OK  {status.filename} ({size:,} bytes)")
            except RuntimeError as exc:
                status.failed = True
                status.error = str(exc)
                logging.error("%s", exc)
                print(f"ERR {status.filename}: {exc}")
        return statuses
    finally:
        if own_session:
            session.close()


def verify_completeness(
    root: Path,
    taxi_types: Iterable[str],
    year: int,
    session: requests.Session | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> DownloadSummary:
    """Compatibilidad con el notebook: verifica varios tipos para un año."""
    statuses: list[MonthStatus] = []
    for tipo in taxi_types:
        statuses += verificar(tipo, year, root, session, timeout)
    return DownloadSummary(statuses=statuses)


def print_verification(summary: DownloadSummary) -> bool:
    """Imprime la verificación por (tipo, año).

    Returns:
        True si todos los meses publicados están presentes localmente.
    """
    published = summary.by_flag("published")
    missing = [s for s in published if not s.local_exists]
    unexpected = [s for s in summary.statuses if s.local_exists and not s.published]

    print("\n=== Verificación de completitud ===")
    print(
        "Completo = todos los meses publicados por la TLC están "
        "locales y con tamaño > 0 (no se exigen 12 meses)."
    )
    print(f"Publicados:              {len(published)}")
    print(f"Locales válidos:         {sum(1 for s in published if s.local_exists)}")
    print(f"Ausentes:                {len(missing)}")
    print(f"Locales no publicados:   {len(unexpected)}")

    groups: dict[tuple[str, int], list[MonthStatus]] = {}
    for status in published:
        groups.setdefault((status.taxi_type, status.year), []).append(status)

    for (tipo, anio), items in sorted(groups.items()):
        months = sorted(s.month for s in items if s.local_exists)
        print(
            f"  {tipo} {anio}: {len(months)}/{len(items)} publicados | "
            f"meses locales={months}"
        )

    if missing:
        print("\nMeses publicados ausentes localmente:")
        for status in missing:
            print(f"  - {status.filename}")
    if unexpected:
        print("\nArchivos locales sin publicación remota:")
        for status in unexpected:
            print(f"  ? {status.filename}")

    complete = len(missing) == 0
    print(f"\nResultado: {'COMPLETO' if complete else 'INCOMPLETO'}")
    return complete


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Descarga y verifica trip records Parquet de TLC (yellow/green)."
    )
    parser.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=list(DEFAULT_YEARS),
        help=f"Años a procesar (default: {' '.join(map(str, DEFAULT_YEARS))})",
    )
    parser.add_argument(
        "--taxi",
        "--taxi-types",
        dest="taxi",
        nargs="+",
        default=list(DEFAULT_TAXI_TYPES),
        choices=list(DEFAULT_TAXI_TYPES),
        help="Tipos de taxi a procesar (default: yellow green)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Solo verificar completitud sin descargar",
    )
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    try:
        root = project_root_from()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    years = sorted(set(args.years))
    taxis = list(dict.fromkeys(args.taxi))
    (root / "data" / "raw").mkdir(parents=True, exist_ok=True)

    statuses: list[MonthStatus] = []
    session = _nueva_sesion()
    try:
        for anio in years:
            for tipo in taxis:
                if args.verify:
                    statuses += verificar(tipo, anio, root, session, args.timeout)
                else:
                    statuses += descargar(
                        tipo, anio, root, session, args.retries, args.timeout
                    )
    finally:
        session.close()

    summary = DownloadSummary(statuses=statuses)
    if not args.verify:
        summary.print_report()
    complete = print_verification(summary)

    if summary.by_flag("failed"):
        return 1
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
