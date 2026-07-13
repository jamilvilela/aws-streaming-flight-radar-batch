"""
Gerador de dados históricos (Full Load para DMS).
Estratégia: gera voos e posições para alcançar ~5GB em 5 anos.
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from ..core.interpolation import generate_positions_for_flight
from ..core.models import FlightStatus
from .base import BaseGenerator

logger = logging.getLogger("gen.historical")

# Estimativa: ~120 bytes por posição no banco
BYTES_PER_POSITION = 120


class HistoricalGenerator(BaseGenerator):
    """
    Gera dados históricos de voos e posições.

    Cálculo de volume:
      5GB = 5.000.000.000 bytes
      ~41.666.667 posições (a 120 bytes cada)
      ~80 posições/voo (médio)
      ~520.000 voos em 5 anos → ~285 voos/dia
    """

    def run(
        self,
        years: int = 5,
        target_size_gb: float = 5.0,
        flights_per_year: int | None = None,
        batch_size: int = 500,
        workers: int = 1,
        years_list: list[int] | None = None,
    ) -> None:
        """
        Gera dados históricos.

        Args:
            years: Número de anos (default: 5, ignorado se years_list for fornecido)
            target_size_gb: Tamanho alvo em GB (default: 5.0)
            flights_per_year: Forçar número de voos/ano (calculado se None)
            batch_size: Voos entre commits (default: 500)
            workers: Workers paralelos (default: 1, futuro)
            years_list: Lista de anos específicos (ex: [2022, 2024]).
                        Quando fornecido, sobrescreve 'years'.
        """
        if years_list:
            years = len(years_list)
            logger.info("=" * 60)
            logger.info(
                "GERAÇÃO HISTÓRICA — anos %s, alvo ~%.1f GB",
                years_list, target_size_gb,
            )
        else:
            logger.info("=" * 60)
            logger.info("GERAÇÃO HISTÓRICA — %d anos, alvo ~%.1f GB", years, target_size_gb)
        logger.info("=" * 60)

        self.setup()

        target_bytes = int(target_size_gb * 1_000_000_000)
        target_positions = target_bytes // BYTES_PER_POSITION

        # Média de posições por voo (considerando vários tamanhos de rota)
        avg_positions_per_flight = 80
        total_flights_needed = target_positions // avg_positions_per_flight
        flights_per_year_calc = total_flights_needed // max(years, 1)

        fpy = flights_per_year or max(100, flights_per_year_calc)
        total_flights = fpy * years
        logger.info(
            "Meta: ~%d posições (%d GB) → %d voos/ano × %d anos = %d voos",
            target_positions, target_size_gb,
            fpy, years, total_flights,
        )

        now = datetime.now(timezone.utc)
        total_flights_created = 0
        total_positions_created = 0
        start_wall = time.perf_counter()

        # Gera aeronaves em lote inicial
        self._generate_aircraft_pool(
            count=max(500, int(fpy * years / 200))
        )

        # Define os anos a processar
        if years_list:
            year_starts = [datetime(y, 1, 1, tzinfo=timezone.utc) for y in years_list]
        else:
            year_starts = [
                now - timedelta(days=365 * (years - i))
                for i in range(years)
            ]

        # Distribui voos pelos anos
        for idx, year_start in enumerate(year_starts):
            year_num = year_start.year
            year_flights = random.randint(
                max(100, fpy - 200),
                fpy + 200,
            )

            logger.info(
                "Ano %d/%d: %d — gerando ~%d voos",
                idx + 1, years, year_num, year_flights,
            )

            flights_created, positions_created = self._generate_year(
                year_start, year_flights,
            )
            total_flights_created += flights_created
            total_positions_created += positions_created

            elapsed = time.perf_counter() - start_wall
            rate = total_positions_created / elapsed if elapsed > 0 else 0
            logger.info(
                "  Ano %d concluído: +%d voos, +%d posições  "
                "(acumulado: %d voos, %d posições, %.0f pos/s, %.1f min decorridos)",
                idx + 1,
                flights_created, positions_created,
                total_flights_created, total_positions_created,
                rate, elapsed / 60,
            )

        elapsed = time.perf_counter() - start_wall
        actual_mb = total_positions_created * BYTES_PER_POSITION / 1_000_000
        logger.info("")
        logger.info("=" * 60)
        logger.info(
            "RESUMO: %d voos, %d posições, ~%.1f MB gerados em %.1f min",
            total_flights_created, total_positions_created,
            actual_mb, elapsed / 60,
        )
        logger.info("=" * 60)

        self.teardown()

    # ── Internals ────────────────────────────────────────────────────────

    def _generate_aircraft_pool(self, count: int) -> None:
        """Gera frota de aeronaves para usar nos voos."""
        logger.info("Gerando pool de %d aeronaves...", count)

        # Busca tipos de aeronave válidos do banco (carregados pelo load-reference)
        aircraft_types = self.repo.get_aircraft_type_codes()
        if not aircraft_types:
            # Fallback: lista genérica caso a tabela esteja vazia
            logger.warning(
                "Tabela aircraft_types vazia — usando lista hardcoded de fallback"
            )
            aircraft_types = [
                "B738", "A320", "A333", "B77W", "B789",
                "E190", "E195", "A359", "B748", "A321",
                "B739", "B763", "A388", "E175", "A332",
            ]
        prefixes = {
            "US": "N", "GB": "G-", "DE": "D-", "FR": "F-",
            "BR": "PT-", "NL": "PH-", "AE": "A6-", "JP": "JA",
            "SG": "9V-", "KR": "HL", "ES": "EC-", "IT": "I-",
            "CA": "C-", "AU": "VH-", "TR": "TC-", "RU": "RA-",
            "BE": "OO-", "CH": "HB-", "SE": "SE-", "NO": "LN-",
        }
        country_list = list(prefixes.keys())

        # Cria operadores a partir das airlines ativas
        operators = self._airline_icaos
        if not operators:
            operators = ["AAL", "UAL", "DAL", "BAW", "AFR", "DLH",
                         "KLM", "SIA", "ANA", "UAE", "QTR", "TAM",
                         "AZU", "GLO", "SWA", "JBU", "RYR", "EZY",
                         "THY", "TAP"]

        batch: list[dict] = []
        used_codes: set[str] = set()

        for i in range(count):
            # Gera ICAO24 hex único
            while True:
                icao24 = "".join(random.choice("abcdef0123456789") for _ in range(6))
                if icao24 not in used_codes:
                    used_codes.add(icao24)
                    break

            country = random.choice(country_list)
            prefix = prefixes[country]
            reg_num = random.randint(1, 99999)
            registration = f"{prefix}{reg_num}"

            ac_type = random.choice(aircraft_types)
            operator = random.choice(operators)
            year_built = random.randint(1995, 2024)
            serial = f"{random.choice('ABCDEFGH')}{random.randint(1000, 99999)}"

            batch.append({
                "icao24": icao24,
                "registration": registration,
                "aircraft_type": ac_type,
                "serial_number": serial,
                "operator_icao": operator,
                "operator_name": None,
                "year_built": year_built,
            })

            if len(batch) >= 100:
                self.repo.insert_aircraft_batch(batch)
                batch = []

        if batch:
            self.repo.insert_aircraft_batch(batch)

        # Recarrega do banco
        self._aircraft_icaos = self.repo.get_aircraft_icao24s()
        logger.info("Pool de aeronaves: %d disponíveis", len(self._aircraft_icaos))

    def _generate_year(
        self, year_start: datetime, num_flights: int
    ) -> tuple[int, int]:
        """Gera um ano de voos — tudo em memória, depois 2 operações de batch."""
        # Cria todas as 12 partições do ano antes de começar
        self.repo.ensure_partitions_for_year(year_start.year)
        logger.info("Partições de %d verificadas/criadas", year_start.year)

        # 1. Consulta o maior flight_id atual para usar contador local
        next_id = self.repo.get_max_flight_id() + 1

        # 2. Verifica se já existem voos neste ano (para execuções incrementais)
        latest_existing = self.repo.get_latest_flight_date(year_start.year)
        if latest_existing:
            # Já há dados neste ano: gera apenas a partir da data mais recente
            year_end = year_start.replace(year=year_start.year + 1)
            available_days = (year_end - latest_existing).days
            if available_days <= 0:
                logger.info(
                    "Ano %d já completo (último voo: %s). Pulando.",
                    year_start.year, latest_existing
                )
                return 0, 0
            logger.info(
                "Ano %d: dados existentes até %s. Gerando %d dias restantes.",
                year_start.year, latest_existing, available_days
            )
            min_ref_time = latest_existing
        else:
            # Ano vazio: pode gerar do início
            min_ref_time = year_start

        # Limita dias para não gerar datas futuras no ano atual
        now = datetime.now(timezone.utc)
        year_end = year_start.replace(year=year_start.year + 1)
        max_ref_time = min(year_end, now)
        if max_ref_time <= min_ref_time:
            logger.info("Ano %d não tem janela válida para geração.", year_start.year)
            return 0, 0

        # 3. Gera TUDO em memória (zero round trips)
        flight_rows: list[dict] = []
        position_buffer: list = []

        for i in range(num_flights):
            # Distribui uniformemente entre min_ref_time e max_ref_time
            total_seconds = (max_ref_time - min_ref_time).total_seconds()
            if total_seconds <= 0:
                break
            offset_seconds = random.uniform(0, total_seconds)
            ref_time = min_ref_time + timedelta(seconds=offset_seconds)

            flight_row = self._random_flight_row(ref_time)
            flight_row["flight_id"] = next_id
            next_id += 1
            flight_rows.append(flight_row)

            # Gera posições para landed/active/scheduled
            if flight_row["status"] in ("landed", "active", "scheduled"):
                dep = flight_row["actual_departure"] or flight_row["scheduled_departure"]
                arr = flight_row["actual_arrival"] or flight_row["scheduled_arrival"]
                if dep and arr:
                    orig_data = self._airport_map.get(flight_row["origin_airport"])
                    dest_data = self._airport_map.get(flight_row["destination_airport"])
                    if orig_data and dest_data and orig_data["lat"] and dest_data["lat"]:
                        interval_min = random.randint(1, 5)
                        pos_list = generate_positions_for_flight(
                            flight_id=flight_row["flight_id"],
                            icao24=flight_row["aircraft_icao24"],
                            lat1=orig_data["lat"],
                            lon1=orig_data["lon"],
                            lat2=dest_data["lat"],
                            lon2=dest_data["lon"],
                            dep_time=dep,
                            arr_time=arr,
                            interval_seconds=interval_min * 60,
                            jitter=0.3,
                        )
                        position_buffer.extend(pos_list)

        # 3. Batch INSERT de voos (1 round trip, com ON CONFLICT)
        self.repo.insert_flights_batch(flight_rows)
        flights_created = len(flight_rows)

        # 4. COPY de posições em chunks (para não estourar memória do lado do DB)
        positions_created = 0
        CHUNK = 10000
        for start in range(0, len(position_buffer), CHUNK):
            chunk = position_buffer[start:start + CHUNK]
            positions_created += self.repo.insert_positions_copy(chunk)
            logger.debug(
                "  Posições: %d/%d (%.1f%%)",
                positions_created, len(position_buffer),
                100.0 * positions_created / len(position_buffer),
            )

        return flights_created, positions_created

    def _random_flight_row(self, ref_time: datetime) -> dict:
        """Gera um dicionário representando uma linha da tabela flights."""
        icao24 = random.choice(self._aircraft_icaos)
        airline = self._random_airline()
        orig, dest, orig_data, dest_data = self._random_airport_pair()

        flight_number = self._generate_flight_number(airline)
        scheduled_dep = ref_time + timedelta(hours=random.uniform(-24, 24))
        scheduled_arr = scheduled_dep + timedelta(hours=random.uniform(1, 14))

        # Status baseado no tempo
        now = datetime.now(timezone.utc)
        if scheduled_arr < now:
            status = random.choices(
                ["landed", "cancelled", "diverted"],
                weights=[0.85, 0.10, 0.05],
            )[0]
        elif scheduled_dep < now < scheduled_arr:
            status = "active"
        else:
            status = "scheduled"

        actual_dep = None
        actual_arr = None
        if status == "active":
            actual_dep = scheduled_dep + timedelta(minutes=random.randint(0, 30))
        elif status == "landed":
            actual_dep = scheduled_dep + timedelta(minutes=random.randint(0, 30))
            actual_arr = scheduled_arr + timedelta(minutes=random.randint(-15, 45))

        return {
            "flight_number": flight_number,
            "airline_icao": airline,
            "aircraft_icao24": icao24,
            "origin_airport": orig,
            "destination_airport": dest,
            "scheduled_departure": scheduled_dep,
            "scheduled_arrival": scheduled_arr,
            "actual_departure": actual_dep,
            "actual_arrival": actual_arr,
            "status": status,
        }
