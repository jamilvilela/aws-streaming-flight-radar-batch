"""
Modelos Pydantic para validação e estruturação dos dados.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FlightStatus(str, Enum):
    scheduled = "scheduled"
    active = "active"
    landed = "landed"
    cancelled = "cancelled"
    diverted = "diverted"


class CountryRow(BaseModel):
    id: int
    code: str = Field(max_length=2)
    name: str
    continent: Optional[str] = None
    wikipedia_link: Optional[str] = None


class AircraftTypeRow(BaseModel):
    name: str
    iata_code: Optional[str] = None
    icao_code: Optional[str] = None


class AirportRow(BaseModel):
    id: int
    ident: Optional[str] = None
    type: Optional[str] = None
    name: str
    latitude_deg: Optional[float] = None
    longitude_deg: Optional[float] = None
    elevation_ft: Optional[int] = None
    continent: Optional[str] = None
    iso_country: Optional[str] = None
    iso_region: Optional[str] = None
    municipality: Optional[str] = None
    scheduled_service: bool = False
    icao_code: Optional[str] = None
    iata_code: Optional[str] = None
    gps_code: Optional[str] = None
    local_code: Optional[str] = None


class AirlineRow(BaseModel):
    id: int
    name: str
    alias: Optional[str] = None
    iata_code: Optional[str] = None
    icao_code: Optional[str] = None
    callsign: Optional[str] = None
    country: Optional[str] = None
    is_active: bool = False


class RouteRow(BaseModel):
    airline_iata: Optional[str] = None
    airline_id: Optional[int] = None
    src_airport: Optional[str] = None
    src_airport_id: Optional[int] = None
    dst_airport: Optional[str] = None
    dst_airport_id: Optional[int] = None
    codeshare: Optional[str] = None
    stops: int = 0
    equipment: Optional[str] = None


class AircraftRow(BaseModel):
    icao24: str = Field(max_length=6)
    registration: str = Field(max_length=20)
    aircraft_type: str = Field(max_length=4)
    serial_number: Optional[str] = None
    operator_icao: Optional[str] = None
    operator_name: Optional[str] = None
    year_built: Optional[int] = None


class FlightRow(BaseModel):
    flight_number: str
    airline_icao: str
    aircraft_icao24: str
    origin_airport: str
    destination_airport: str
    scheduled_departure: Optional[datetime] = None
    scheduled_arrival: Optional[datetime] = None
    actual_departure: Optional[datetime] = None
    actual_arrival: Optional[datetime] = None
    status: FlightStatus = FlightStatus.scheduled


class PositionRow(BaseModel):
    aircraft_icao24: str
    flight_id: int
    latitude: float
    longitude: float
    altitude_ft: int
    velocity_kts: float
    heading: float
    vertical_rate_fpm: float
    on_ground: bool = False
    recorded_at: datetime
