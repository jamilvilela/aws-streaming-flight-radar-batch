"""
Carregamento dos datasets CSV (OpenFlights + OurAirports).
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Iterator

from .config import DBConfig
from .models import (
    AircraftTypeRow,
    AirlineRow,
    AirportRow,
    CountryRow,
    RouteRow,
)

logger = logging.getLogger("data_loader")

# ── Helpers ───────────────────────────────────────────────────────────────────


def _nullify(val: str) -> str | None:
    """Converte string vazia ou '\\N' para None."""
    if val is None:
        return None
    val = val.strip()
    return None if val in ("", "\\N", '""') else val


def _bool_yes(val: str | None) -> bool:
    return val is not None and val.strip().lower() == "yes"


def _bool_Y(val: str | None) -> bool:
    return val is not None and val.strip().upper() == "Y"


def _int_or_none(val: str | None) -> int | None:
    v = _nullify(val)
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _float_or_none(val: str | None) -> float | None:
    v = _nullify(val)
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None


# ── Loaders ───────────────────────────────────────────────────────────────────


def load_countries(path: Path) -> list[CountryRow]:
    """Carrega countries.csv (OurAirports)."""
    rows: list[CountryRow] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(
                CountryRow(
                    id=int(r["id"]),
                    code=r["code"],
                    name=r["name"],
                    continent=_nullify(r.get("continent", "")),
                    wikipedia_link=_nullify(r.get("wikipedia_link", "")),
                )
            )
    logger.info("Países carregados: %d", len(rows))
    return rows


def load_aircraft_types(path: Path) -> list[AircraftTypeRow]:
    """
    Carrega airplanes.csv (OpenFlights).
    Arquivo SEM header: colunas = name, iata_code, icao_code
    """
    rows: list[AircraftTypeRow] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for r in reader:
            if len(r) < 3:
                continue
            rows.append(
                AircraftTypeRow(
                    name=r[0].strip(),
                    iata_code=_nullify(r[1]) if len(r) > 1 else None,
                    icao_code=_nullify(r[2]) if len(r) > 2 else None,
                )
            )
    logger.info("Tipos de aeronave carregados: %d", len(rows))
    return rows


def load_airports(path: Path) -> list[AirportRow]:
    """Carrega airports.csv (OurAirports)."""
    rows: list[AirportRow] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(
                AirportRow(
                    id=int(r["id"]),
                    ident=_nullify(r.get("ident", "")),
                    type=_nullify(r.get("type", "")),
                    name=r["name"],
                    latitude_deg=_float_or_none(r.get("latitude_deg", "")),
                    longitude_deg=_float_or_none(r.get("longitude_deg", "")),
                    elevation_ft=_int_or_none(r.get("elevation_ft", "")),
                    continent=_nullify(r.get("continent", "")),
                    iso_country=_nullify(r.get("iso_country", "")),
                    iso_region=_nullify(r.get("iso_region", "")),
                    municipality=_nullify(r.get("municipality", "")),
                    scheduled_service=_bool_yes(r.get("scheduled_service", "")),
                    icao_code=_nullify(r.get("icao_code", "")),
                    iata_code=_nullify(r.get("iata_code", "")),
                    gps_code=_nullify(r.get("gps_code", "")),
                    local_code=_nullify(r.get("local_code", "")),
                )
            )
    logger.info(
        "Aeroportos carregados: %d (scheduled=%d, com ICAO=%d)",
        len(rows),
        sum(1 for a in rows if a.scheduled_service),
        sum(1 for a in rows if a.icao_code),
    )
    return rows


def load_airlines(path: Path) -> list[AirlineRow]:
    """Carrega airlines.csv (OpenFlights)."""
    rows: list[AirlineRow] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for r in reader:
            if len(r) < 8:
                continue
            rows.append(
                AirlineRow(
                    id=_int_or_none(r[0]) or 0,
                    name=r[1] if len(r) > 1 else "",
                    alias=_nullify(r[2]) if len(r) > 2 else None,
                    iata_code=_nullify(r[3]) if len(r) > 3 else None,
                    icao_code=_nullify(r[4]) if len(r) > 4 else None,
                    callsign=_nullify(r[5]) if len(r) > 5 else None,
                    country=_nullify(r[6]) if len(r) > 6 else None,
                    is_active=_bool_Y(r[7]) if len(r) > 7 else False,
                )
            )
    logger.info(
        "Companhias carregadas: %d (ativas=%d, com ICAO=%d)",
        len(rows),
        sum(1 for a in rows if a.is_active),
        sum(1 for a in rows if a.icao_code),
    )
    return rows


def load_routes(path: Path) -> list[RouteRow]:
    """Carrega routes.csv (OpenFlights). Sem header."""
    rows: list[RouteRow] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for r in reader:
            if len(r) < 9:
                continue
            rows.append(
                RouteRow(
                    airline_iata=_nullify(r[0]),
                    airline_id=_int_or_none(r[1]),
                    src_airport=_nullify(r[2]),
                    src_airport_id=_int_or_none(r[3]),
                    dst_airport=_nullify(r[4]),
                    dst_airport_id=_int_or_none(r[5]),
                    codeshare=_nullify(r[6]),
                    stops=_int_or_none(r[7]) or 0,
                    equipment=_nullify(r[8]),
                )
            )
    logger.info("Rotas carregadas: %d", len(rows))
    return rows


# ── Loader agrupado ──────────────────────────────────────────────────────────


def load_all_reference_data(
    cfg: DBConfig,
) -> dict[str, list[Any]]:
    """Carrega todos os CSVs de uma vez."""
    paths = cfg.csv_paths
    return {
        "countries": load_countries(paths["countries"]),
        "aircraft_types": load_aircraft_types(paths["airplanes"]),
        "airports": load_airports(paths["airports"]),
        "airlines": load_airlines(paths["airlines"]),
        "routes": load_routes(paths["routes"]),
    }
