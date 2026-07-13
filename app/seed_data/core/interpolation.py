"""
Interpolação linear de posições entre dois aeroportos.
Funções PURAS (sem dependência de DB) — fáceis de testar.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Iterator

from .models import PositionRow


# ── Cálculo de distância (Haversine) ─────────────────────────────────────────


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em km entre dois pontos geográficos (Haversine)."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def estimate_flight_duration_hours(
    lat1: float, lon1: float, lat2: float, lon2: float, cruise_speed_kts: float = 450
) -> float:
    """Estima duração de voo baseada na distância Haversine."""
    dist_km = haversine_km(lat1, lon1, lat2, lon2)
    dist_nm = dist_km * 0.539957
    return dist_nm / cruise_speed_kts + 0.5  # +0.5h para taxi/decolagem/descida


# ── Interpolação de posição ──────────────────────────────────────────────────


def _interpolate(
    lat1: float, lon1: float, lat2: float, lon2: float, fraction: float
) -> tuple[float, float]:
    """Interpola linearmente entre dois pontos."""
    return (
        lat1 + (lat2 - lat1) * fraction,
        lon1 + (lon2 - lon1) * fraction,
    )


def _compute_flight_phase_altitude_velocity(
    fraction: float,
) -> tuple[int, float, bool]:
    """
    Determina altitude (ft), velocidade (kts) e on_ground
    baseado na fração do voo (0=partida, 1=chegada).
    """
    if fraction < 0.05:
        # Taxi / decolagem
        alt = int(fraction / 0.05 * 1500)
        vel = 10 + fraction / 0.05 * 160
        return (alt, round(vel, 2), True)
    elif fraction < 0.15:
        # Subida inicial
        progress = (fraction - 0.05) / 0.1
        alt = int(1500 + progress * 32000)
        vel = 170 + progress * 280
        return (alt, round(vel, 2), False)
    elif fraction < 0.85:
        # Cruzeiro
        alt = random.randint(33000, 41000)
        vel = random.uniform(420, 510)
        return (alt, round(vel, 2), False)
    elif fraction < 0.95:
        # Descida
        progress = (fraction - 0.85) / 0.1
        alt = int(35000 - progress * 32000)
        vel = 420 - progress * 250
        return (alt, round(vel, 2), False)
    else:
        # Aproximação / taxi
        progress = (fraction - 0.95) / 0.05
        alt = int(3000 - progress * 3000)
        vel = 170 - progress * 160
        on_g = True if fraction > 0.98 else False
        return (max(alt, 0), round(max(vel, 0), 2), on_g)


def generate_positions_for_flight(
    flight_id: int,
    icao24: str,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    dep_time: datetime,
    arr_time: datetime,
    interval_seconds: int = 60,
    jitter: float = 0.3,
) -> list[PositionRow]:
    """
    Gera todas as posições interpoladas para um voo.

    Args:
        flight_id: ID do voo no banco
        icao24: Código ICAO24 da aeronave
        lat1, lon1: Coordenadas do aeroporto de origem
        lat2, lon2: Coordenadas do aeroporto de destino
        dep_time: Partida real (ou scheduled)
        arr_time: Chegada real (ou scheduled)
        interval_seconds: Intervalo entre posições (default: 60s = 1min)
        jitter: Dispersão aleatória máxima em graus (default: 0.3)

    Returns:
        Lista de PositionRow
    """
    if dep_time is None or arr_time is None:
        return []
    if dep_time >= arr_time:
        return []

    # Garante float para evitar erro Decimal * float
    lat1 = float(lat1)
    lon1 = float(lon1)
    lat2 = float(lat2)
    lon2 = float(lon2)

    total_seconds = (arr_time - dep_time).total_seconds()
    steps = max(2, int(total_seconds / interval_seconds))
    positions: list[PositionRow] = []
    now_utc = datetime.now(timezone.utc)

    for i in range(steps):
        fraction = i / (steps - 1)
        lat, lon = _interpolate(lat1, lon1, lat2, lon2, fraction)

        # Jitter para parecer real
        lat += random.uniform(-jitter, jitter)
        lon += random.uniform(-jitter, jitter)

        alt, vel, on_ground = _compute_flight_phase_altitude_velocity(fraction)
        heading = (fraction * 360) % 360
        vertical_rate = random.uniform(-800, 800) if not on_ground else 0.0

        recorded_at = dep_time + timedelta(seconds=int(i * interval_seconds))
        # Não gera posições no futuro
        if recorded_at > now_utc:
            break

        positions.append(
            PositionRow(
                aircraft_icao24=icao24,
                flight_id=flight_id,
                latitude=round(lat, 7),
                longitude=round(lon, 7),
                altitude_ft=alt,
                velocity_kts=round(vel, 2),
                heading=round(heading, 2),
                vertical_rate_fpm=round(vertical_rate, 2),
                on_ground=on_ground,
                recorded_at=recorded_at,
            )
        )

    return positions


def generate_positions_lazy(
    flight_id: int,
    icao24: str,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    dep_time: datetime,
    arr_time: datetime,
    interval_seconds: int = 60,
    jitter: float = 0.3,
) -> Iterator[PositionRow]:
    """
    Versão lazy (gerador) de generate_positions_for_flight.
    Útil para streaming — não aloca tudo em memória.
    """
    if dep_time is None or arr_time is None or dep_time >= arr_time:
        return

    total_seconds = (arr_time - dep_time).total_seconds()
    steps = max(2, int(total_seconds / interval_seconds))
    now_utc = datetime.now(timezone.utc)

    for i in range(steps):
        fraction = i / (steps - 1)
        lat, lon = _interpolate(lat1, lon1, lat2, lon2, fraction)
        lat += random.uniform(-jitter, jitter)
        lon += random.uniform(-jitter, jitter)

        alt, vel, on_ground = _compute_flight_phase_altitude_velocity(fraction)
        heading = (fraction * 360) % 360
        vertical_rate = random.uniform(-800, 800) if not on_ground else 0.0

        recorded_at = dep_time + timedelta(seconds=int(i * interval_seconds))
        if recorded_at > now_utc:
            break

        yield PositionRow(
            aircraft_icao24=icao24,
            flight_id=flight_id,
            latitude=round(lat, 7),
            longitude=round(lon, 7),
            altitude_ft=alt,
            velocity_kts=round(vel, 2),
            heading=round(heading, 2),
            vertical_rate_fpm=round(vertical_rate, 2),
            on_ground=on_ground,
            recorded_at=recorded_at,
        )
