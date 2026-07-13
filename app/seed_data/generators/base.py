"""
Classe base abstrata para geradores (Strategy Pattern).
"""

from __future__ import annotations

import logging
import random
from abc import ABC, abstractmethod
from typing import Any

from ..core.config import DBConfig
from ..core.repository import DatabaseRepository

logger = logging.getLogger("generator")


class BaseGenerator(ABC):
    """Base para todos os geradores de dados de teste."""

    def __init__(self, cfg: DBConfig):
        self.cfg = cfg
        self.repo = DatabaseRepository(cfg)
        self._airline_icaos: list[str] = []
        self._aircraft_icaos: list[str] = []
        self._airport_map: dict[str, dict[str, Any]] = {}

    # ── Lifecycle ────────────────────────────────────────────────────────

    def setup(self) -> None:
        """Conecta ao banco e carrega dados de referência."""
        self.repo.connect()
        self._airline_icaos = self.repo.get_active_airline_icaos()
        self._aircraft_icaos = self.repo.get_aircraft_icao24s()
        self._airport_map = self.repo.get_icao_airport_map()
        logger.info(
            "Setup: %d airlines, %d aircraft, %d airports",
            len(self._airline_icaos),
            len(self._aircraft_icaos),
            len(self._airport_map),
        )

    def teardown(self) -> None:
        self.repo.close()

    # ── Helpers ──────────────────────────────────────────────────────────

    def _random_airline(self) -> str:
        return random.choice(self._airline_icaos)

    def _random_aircraft(self) -> str:
        return random.choice(self._aircraft_icaos)

    def _random_airport_pair(
        self,
    ) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
        """Retorna (icao_orig, icao_dest, dict_orig, dict_dest)."""
        icaos = list(self._airport_map.keys())
        orig = random.choice(icaos)
        dest = random.choice([i for i in icaos if i != orig])
        return (orig, dest, self._airport_map[orig], self._airport_map[dest])

    def _generate_flight_number(self, airline_icao: str) -> str:
        number = random.randint(100, 9999)
        return f"{airline_icao}{number}"

    @abstractmethod
    def run(self) -> None:
        """Executa a geração de dados."""
        ...
