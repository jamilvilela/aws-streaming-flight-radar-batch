"""
Gerador de dados de streaming CDC para DMS.
Estratégia: mantém N voos ativos simultâneos gerando posições
a cada ciclo para atingir 150MB de CDC a cada 5 minutos.
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from ..core.interpolation import generate_positions_for_flight
from .base import BaseGenerator

logger = logging.getLogger("gen.stream")

BYTES_PER_POSITION = 120


class StreamGenerator(BaseGenerator):
    """
    Gera dados contínuos simulando CDC (Change Data Capture).

    Cálculo de volume:
      150MB / 5min = 30MB/min = 0.5MB/s
      0.5MB/s / 120 bytes = ~4.167 posições/segundo
      Com intervalo de 1s entre ciclos → ~4.167 posições/ciclo
      Com 500 voos ativos → ~8 posições/voo/ciclo
    """

    def run(
        self,
        interval_seconds: int = 1,
        target_mb_per_5min: float = 150.0,
        max_active_flights: int = 500,
        delete_probability: float = 0.02,
        update_probability: float = 0.10,
        new_flights_per_cycle: int = 2,
        duration_seconds: int | None = None,
        positions_per_flight_per_cycle: int = 5,
    ) -> None:
        """
        Gera dados de streaming CDC.

        Args:
            interval_seconds: Intervalo entre ciclos (default: 1s)
            target_mb_per_5min: Alvo de volume MB a cada 5 min (default: 150)
            max_active_flights: Máximo de voos ativos simultâneos (default: 500)
            delete_probability: Probabilidade de DELETE por ciclo (default: 0.02)
            update_probability: Probabilidade de UPDATE por ciclo (default: 0.10)
            new_flights_per_cycle: Novos voos INSERT por ciclo (default: 2)
            duration_seconds: Duração total (None = infinito)
            positions_per_flight_per_cycle: Posições por voo ativo por ciclo (default: 5)
        """
        logger.info("=" * 60)
        logger.info(
            "STREAMING CDC — alvo ~%.0fMB/5min, intervalo=%ds, max_ativos=%d",
            target_mb_per_5min, interval_seconds, max_active_flights,
        )
        logger.info("=" * 60)

        self.setup()

        now = datetime.now(timezone.utc)
        end_time = now + timedelta(seconds=duration_seconds) if duration_seconds else (
            now + timedelta(days=365)
        )
        cycle = 0
        total_inserted = 0
        total_updated = 0
        total_deleted = 0
        start_wall = time.perf_counter()
        report_interval = max(1, 300 // interval_seconds)  # report a cada ~5min

        # Garante pool de aeronaves suficiente
        aircraft_needed = max_active_flights + 1000
        if len(self._aircraft_icaos) < aircraft_needed:
            logger.info(
                "Pool de aeronaves insuficiente (%d). Gerando mais %d...",
                len(self._aircraft_icaos), aircraft_needed - len(self._aircraft_icaos),
            )
            from .historical import HistoricalGenerator
            hist = HistoricalGenerator(self.cfg)
            hist.repo = self.repo
            hist._airline_icaos = self._airline_icaos
            hist._aircraft_icaos = self._aircraft_icaos
            hist._airport_map = self._airport_map
            hist._generate_aircraft_pool(aircraft_needed)
            self._aircraft_icaos = self.repo.get_aircraft_icao24s()

        # Pré-carrega alguns voos ativos iniciais para começar rápido
        self._seed_initial_flights(max_active_flights // 2)

        while datetime.now(timezone.utc) < end_time:
            cycle += 1
            cycle_start = time.perf_counter()
            inserted = updated = deleted = 0

            try:
                with self.repo.transaction() as cur:
                    # 1. INSERT: novos voos
                    inserted += self._insert_new_flights(cur, new_flights_per_cycle)

                    # 2. INSERT: posições para voos ativos
                    inserted += self._insert_positions(
                        cur,
                        max_active_flights,
                        positions_per_flight_per_cycle,
                    )

                    # 3. UPDATE: transições de status
                    if random.random() < update_probability:
                        updated += self._update_flight_status(cur)

                    # 4. DELETE: raro
                    if random.random() < delete_probability:
                        deleted += self._delete_old_flight(cur)

            except Exception as e:
                logger.error("Erro no ciclo %d: %s", cycle, e)

            total_inserted += inserted
            total_updated += updated
            total_deleted += deleted

            elapsed = time.perf_counter() - cycle_start
            sleep_time = interval_seconds - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

            # Log periódico
            if cycle % report_interval == 0 or cycle == 1:
                wall_elapsed = time.perf_counter() - start_wall
                rate = total_inserted / wall_elapsed if wall_elapsed > 0 else 0
                mb_per_5min = (rate * BYTES_PER_POSITION * 300) / 1_000_000
                logger.info(
                    "Ciclo %5d | I=%d U=%d D=%d | "
                    "Total: I=%d U=%d D=%d | "
                    "%.0f pos/s | ~%.1f MB/5min | %.1f min decorridos",
                    cycle, inserted, updated, deleted,
                    total_inserted, total_updated, total_deleted,
                    rate, mb_per_5min, wall_elapsed / 60,
                )

        wall_elapsed = time.perf_counter() - start_wall
        logger.info("")
        logger.info("=" * 60)
        logger.info(
            "STREAM ENCERRADO — %d ciclos, "
            "I=%d U=%d D=%d em %.1f min",
            cycle, total_inserted, total_updated, total_deleted,
            wall_elapsed / 60,
        )
        logger.info("=" * 60)

        self.teardown()

    # ── Internals ────────────────────────────────────────────────────────

    def _seed_initial_flights(self, count: int) -> None:
        """Cria voos iniciais já no status 'active'."""
        logger.info("Criando %d voos ativos iniciais...", count)
        with self.repo.transaction() as cur:
            for _ in range(count):
                ref_time = datetime.now(timezone.utc) - timedelta(hours=random.uniform(1, 6))
                row = self._random_flight_row(ref_time)
                row["status"] = "active"
                row["actual_departure"] = row["scheduled_departure"] + timedelta(minutes=random.randint(0, 15))
                self.repo.insert_flight(cur, row)
        logger.info("Voos iniciais criados.")

    def _insert_new_flights(self, cur, count: int) -> int:
        """Faz INSERT de novos voos."""
        inserted = 0
        for _ in range(count):
            row = self._random_flight_row(datetime.now(timezone.utc))
            self.repo.insert_flight(cur, row)
            inserted += 1
        return inserted

    def _insert_positions(
        self, cur, max_flights: int, per_flight: int
    ) -> int:
        """Gera e insere posições para voos ativos."""
        inserted = 0
        active = self.repo.get_active_flights_for_positions(limit=max_flights)
        for f in active:
            dep = f["actual_departure"] or (
                datetime.now(timezone.utc) - timedelta(hours=2)
            )
            arr = f["actual_arrival"] or (dep + timedelta(hours=5))
            orig_data = self._airport_map.get(f["origin_airport"])
            dest_data = self._airport_map.get(f["destination_airport"])
            if not orig_data or not dest_data:
                continue
            if not orig_data.get("lat") or not dest_data.get("lat"):
                continue

            # Gera várias posições futuras (CDC em tempo real)
            base_time = datetime.now(timezone.utc) - timedelta(seconds=per_flight * 2)
            pos_list = generate_positions_for_flight(
                flight_id=f["flight_id"],
                icao24=f["aircraft_icao24"],
                lat1=orig_data["lat"],
                lon1=orig_data["lon"],
                lat2=dest_data["lat"],
                lon2=dest_data["lon"],
                dep_time=dep,
                arr_time=arr,
                interval_seconds=5,
                jitter=0.2,
            )
            # Pega apenas as últimas N posições (mais recentes)
            if pos_list:
                recent = pos_list[-per_flight:]
                inserted += self.repo.insert_positions_batch(cur, recent)

        return inserted

    def _update_flight_status(self, cur) -> int:
        """Transiciona status de voos scheduled→active→landed/diverted."""
        updated = 0
        cur.execute(
            """
            SELECT flight_id, status FROM flights
            WHERE status IN ('scheduled', 'active')
            ORDER BY random() LIMIT %s
            """,
            (random.randint(1, 5),),
        )
        for f_up in cur.fetchall():
            old_status = f_up["status"]
            if old_status == "scheduled":
                new_status = "active"
                actual_dep = datetime.now(timezone.utc) - timedelta(
                    minutes=random.randint(1, 15)
                )
                cur.execute(
                    """
                    UPDATE flights
                    SET status = %s, actual_departure = %s, updated_at = NOW()
                    WHERE flight_id = %s
                    """,
                    (new_status, actual_dep, f_up["flight_id"]),
                )
            elif old_status == "active":
                new_status = random.choice(["landed", "diverted"])
                actual_arr = datetime.now(timezone.utc) - timedelta(
                    minutes=random.randint(1, 10)
                )
                cur.execute(
                    """
                    UPDATE flights
                    SET status = %s, actual_arrival = %s, updated_at = NOW()
                    WHERE flight_id = %s
                    """,
                    (new_status, actual_arr, f_up["flight_id"]),
                )
            else:
                continue
            updated += 1
        return updated

    def _delete_old_flight(self, cur) -> int:
        """Remove voo antigo já finalizado."""
        cur.execute(
            """
            SELECT flight_id FROM flights
            WHERE status IN ('landed', 'cancelled', 'diverted')
              AND created_at < NOW() - INTERVAL '30 minutes'
            ORDER BY random() LIMIT 1
            """
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                "DELETE FROM aircraft_positions WHERE flight_id = %s",
                (row["flight_id"],),
            )
            cur.execute(
                "DELETE FROM flights WHERE flight_id = %s",
                (row["flight_id"],),
            )
            return 1
        return 0

    def _random_flight_row(self, ref_time: datetime) -> dict:
        """Gera um dicionário representando uma linha da tabela flights."""
        icao24 = random.choice(self._aircraft_icaos)
        airline = self._random_airline()
        orig, dest, _, _ = self._random_airport_pair()

        flight_number = self._generate_flight_number(airline)
        # No streaming, todos os voos são "agora" ou futuro próximo
        scheduled_dep = ref_time + timedelta(minutes=random.randint(-30, 60))
        duration_h = random.uniform(1, 14)
        scheduled_arr = scheduled_dep + timedelta(hours=duration_h)

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
