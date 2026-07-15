"""
Repository Pattern — isolamento de operações no banco PostgreSQL.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional

import psycopg2
import psycopg2.extras
import psycopg2.sql as sql
from .config import DBConfig
from .models import PositionRow

logger = logging.getLogger("repository")


def _normalize_icao(value: str | None) -> str | None:
    """Converte 'N/A', '\\N', strings vazias ou None em None (NULL)."""
    if not value or value in ("N/A", "\\N"):
        return None
    return value


class DatabaseRepository:
    """Camada de acesso a dados. Isola todo SQL do resto da aplicação."""

    def __init__(self, cfg: DBConfig):
        self.cfg = cfg
        self.conn: Optional[psycopg2.extensions.connection] = None

    # ── Conexão ──────────────────────────────────────────────────────────

    def connect(self) -> None:
        logger.info(
            "Conectando ao RDS: %s:%s/%s ...",
            self.cfg.host, self.cfg.port, self.cfg.dbname,
        )
        self.conn = psycopg2.connect(self.cfg.dsn)
        self.conn.autocommit = True
        with self.conn.cursor() as cur:
            cur.execute("SET search_path TO flight_radar;")
        logger.info("Conectado!")

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    @contextmanager
    def transaction(self) -> Iterator[psycopg2.extras.RealDictCursor]:
        """Context manager para transação com commit/rollback."""
        if self.conn is None:
            raise RuntimeError("Repositório não conectado. Chame .connect() primeiro.")
        conn = self.conn
        old_autocommit = conn.autocommit
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SET search_path TO flight_radar;")
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.autocommit = old_autocommit
            cur.close()

    def cursor(self) -> psycopg2.extras.RealDictCursor:
        """Cria cursor autocommit."""
        if self.conn is None:
            raise RuntimeError("Repositório não conectado.")
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SET search_path TO flight_radar;")
        return cur

    # ── Referências ──────────────────────────────────────────────────────

    def insert_countries(self, rows: list[dict]) -> int:
        with self.transaction() as cur:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO countries (id, code, name, continent, wikipedia_link) "
                "VALUES %s ON CONFLICT (id) DO NOTHING",
                [(
                    r["id"], r["code"], r["name"],
                    r.get("continent"), r.get("wikipedia_link"),
                ) for r in rows],
                template="(%s, %s, %s, %s::varchar, %s::text)",
            )
        return len(rows)

    def insert_aircraft_types(self, rows: list[dict]) -> int:
        with self.transaction() as cur:
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO aircraft_types (icao_code, iata_code, name) "
                "VALUES %s ON CONFLICT (icao_code) DO NOTHING",
                [(
                    r.get("icao_code"), r.get("iata_code"), r["name"],
                ) for r in rows if r.get("icao_code")],
                template="(%s, %s, %s)",
            )
        return len(rows)

    def insert_airports(self, rows: list[dict]) -> int:
        with self.transaction() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO airports
                    (id, ident, type, name, latitude_deg, longitude_deg,
                     elevation_ft, continent, iso_country, iso_region,
                     municipality, scheduled_service,
                     icao_code, iata_code, gps_code, local_code)
                VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    scheduled_service = EXCLUDED.scheduled_service
                """,
                [(
                    r["id"], r.get("ident"), r.get("type"), r["name"],
                    r.get("latitude_deg"), r.get("longitude_deg"),
                    r.get("elevation_ft"), r.get("continent"),
                    r.get("iso_country"), r.get("iso_region"),
                    r.get("municipality"), r.get("scheduled_service", False),
                    r.get("icao_code"), r.get("iata_code"),
                    r.get("gps_code"), r.get("local_code"),
                ) for r in rows],
                template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            )
        return len(rows)

    def insert_airlines(self, rows: list[dict]) -> int:
        with self.transaction() as cur:
            # Deduplica ICAO codes no batch: mantém o primeiro, os demais viram NULL
            seen_icao: set[str] = set()
            cleaned: list[tuple] = []
            for r in rows:
                icao = _normalize_icao(r.get("icao_code"))
                # ICAO code tem limite de 3 chars na coluna
                if icao and len(str(icao)) > 3:
                    icao = None
                if icao is not None and icao in seen_icao:
                    icao = None  # duplicata → NULL para não violar UNIQUE
                else:
                    seen_icao.add(icao) if icao else None
                # IATA code tem limite de 2 chars na coluna
                iata = r.get("iata_code")
                if iata and len(str(iata)) > 2:
                    iata = None
                cleaned.append((
                    r["id"], r["name"], r.get("alias"),
                    iata, icao,
                    r.get("callsign"), r.get("country"),
                    r.get("is_active", False),
                ))

            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO airlines
                    (id, name, alias, iata_code, icao_code, callsign, country, is_active)
                VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    is_active = EXCLUDED.is_active
                """,
                cleaned,
                template="(%s, %s, %s, %s, %s, %s, %s, %s)",
            )
        return len(rows)

    def _get_valid_airport_ids(self) -> set[int]:
        """Retorna conjunto de IDs de aeroportos existentes no banco."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT id FROM flight_radar.airports")
            return {row[0] for row in cur.fetchall()}

    def _get_valid_airline_ids(self) -> set[int]:
        """Retorna conjunto de IDs de companhias existentes no banco."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT id FROM flight_radar.airlines")
            return {row[0] for row in cur.fetchall()}

    def insert_routes(self, rows: list[dict]) -> int:
        # Carrega IDs válidos para validar FKs (dados do CSV podem conter
        # referências a aeroportos/companhias que não existem)
        valid_airports = self._get_valid_airport_ids()
        valid_airlines = self._get_valid_airline_ids()

        valid_rows = [
            r for r in rows
            if r.get("src_airport_id") in valid_airports
            and r.get("dst_airport_id") in valid_airports
            and (r.get("airline_id") is None or r.get("airline_id") in valid_airlines)
        ]
        skipped = len(rows) - len(valid_rows)
        if skipped:
            logger.warning(
                "Rotas ignoradas por FK inválida: %d de %d (%.1f%%)",
                skipped, len(rows),
                100.0 * skipped / len(rows),
            )

        if not valid_rows:
            return 0

        with self.transaction() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO routes
                    (airline_iata, airline_id, src_airport, src_airport_id,
                     dst_airport, dst_airport_id, codeshare, stops, equipment)
                VALUES %s
                ON CONFLICT (COALESCE(airline_id,0), COALESCE(src_airport_id,0), COALESCE(dst_airport_id,0), stops) DO NOTHING
                """,
                [(
                    # airline_iata VARCHAR(2) — valores >2 chars viram NULL
                    r.get("airline_iata") if len(str(r.get("airline_iata", ""))) <= 2 else None,
                    r.get("airline_id"),
                    r.get("src_airport"), r.get("src_airport_id"),
                    r.get("dst_airport"), r.get("dst_airport_id"),
                    r.get("codeshare"), r.get("stops", 0),
                    r.get("equipment"),
                ) for r in valid_rows],
                template="(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            )
        return len(valid_rows)

    # ── Dados gerados ────────────────────────────────────────────────────

    def insert_aircraft_batch(self, rows: list[dict]) -> int:
        with self.transaction() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO aircraft
                    (icao24, registration, aircraft_type, serial_number,
                     operator_icao, operator_name, year_built)
                VALUES %s
                ON CONFLICT (icao24) DO NOTHING
                """,
                [(
                    r["icao24"], r["registration"], r["aircraft_type"],
                    r.get("serial_number"), r.get("operator_icao"),
                    r.get("operator_name"), r.get("year_built"),
                ) for r in rows],
                template="(%s, %s, %s, %s, %s, %s, %s::smallint)",
            )
        return len(rows)

    def insert_flight(self, cur: psycopg2.extras.RealDictCursor, row: dict) -> int:
        cur.execute(
            """
            INSERT INTO flights
                (flight_number, airline_icao, aircraft_icao24,
                 origin_airport, destination_airport,
                 scheduled_departure, scheduled_arrival,
                 actual_departure, actual_arrival, status)
            VALUES (%(flight_number)s, %(airline_icao)s, %(aircraft_icao24)s,
                    %(origin_airport)s, %(destination_airport)s,
                    %(scheduled_departure)s, %(scheduled_arrival)s,
                    %(actual_departure)s, %(actual_arrival)s, %(status)s)
            ON CONFLICT (flight_number, airline_icao, aircraft_icao24, scheduled_departure)
            DO UPDATE SET flight_number = EXCLUDED.flight_number
            RETURNING flight_id
            """,
            row,
        )
        return cur.fetchone()["flight_id"]

    def get_max_flight_id(self) -> int:
        """Retorna o maior flight_id atual (0 se tabela vazia)."""
        with self.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(flight_id), 0) AS max_id FROM flights")
            return cur.fetchone()["max_id"]

    def get_latest_flight_date(self, year: int) -> datetime | None:
        """
        Retorna a data mais recente (scheduled_departure) de voos no ano informado.
        Retorna None se não houver voos no ano.
        """
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT MAX(scheduled_departure) AS latest
                FROM flights
                WHERE EXTRACT(YEAR FROM scheduled_departure) = %s
                """,
                (year,),
            )
            row = cur.fetchone()
            return row["latest"] if row and row["latest"] else None

    def insert_flights_batch(
        self, rows: list[dict], cur=None
    ) -> int:
        """
        Insert de voos via execute_values (batch com ON CONFLICT).
        Muito mais rápido que INSERT individual.
        """
        if not rows:
            return 0

        if cur is not None:
            self._do_insert_flights_batch(cur, rows)
        else:
            with self.transaction() as cur:
                self._do_insert_flights_batch(cur, rows)
        return len(rows)

    def _do_insert_flights_batch(
        self, cur, rows: list[dict]
    ) -> None:
        """Executa o batch INSERT de voos (helper para evitar duplicação de código)."""
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO flights
                (flight_id, flight_number, airline_icao, aircraft_icao24,
                 origin_airport, destination_airport,
                 scheduled_departure, scheduled_arrival,
                 actual_departure, actual_arrival, status)
            VALUES %s
            ON CONFLICT (flight_number, airline_icao, aircraft_icao24, scheduled_departure)
            DO UPDATE SET flight_id = EXCLUDED.flight_id
            """,
            [(  r["flight_id"],
                r["flight_number"], r["airline_icao"], r["aircraft_icao24"],
                r["origin_airport"], r["destination_airport"],
                r["scheduled_departure"], r["scheduled_arrival"],
                r["actual_departure"], r["actual_arrival"],
                r["status"],
            ) for r in rows],
            template="(%s, %s, %s, %s, %s, %s, %s::timestamptz, %s::timestamptz, %s::timestamptz, %s::timestamptz, %s)",
            page_size=1000,
        )
        # Sincroniza a sequence com o maior flight_id inserido
        max_id = max(r["flight_id"] for r in rows)
        cur.execute("SELECT setval('flights_flight_id_seq', %s)", (max_id,))

    def insert_positions_batch(
        self, cur: psycopg2.extras.RealDictCursor, positions: list[PositionRow]
    ) -> int:
        if not positions:
            return 0
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO aircraft_positions
                (aircraft_icao24, flight_id, latitude, longitude,
                 altitude_ft, velocity_kts, heading, vertical_rate_fpm,
                 on_ground, recorded_at)
            VALUES %s
            ON CONFLICT (flight_id, recorded_at) DO NOTHING
            """,
            [(
                p.aircraft_icao24, p.flight_id,
                p.latitude, p.longitude,
                p.altitude_ft, p.velocity_kts,
                p.heading, p.vertical_rate_fpm,
                p.on_ground, p.recorded_at,
            ) for p in positions],
            template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::timestamptz)",
            page_size=1000,
        )
        return len(positions)

    def ensure_partitions_for_year(self, year: int) -> None:
        """Cria as partições mensais necessárias para o ano + mês anterior/seguinte."""
        # Voos podem ser agendados até 24h antes de year_start e 24h depois
        # de year_end, então criamos Dez/ano-1 e Jan/ano+1 também
        months_to_create = []
        # Dez do ano anterior
        months_to_create.append((year - 1, 12))
        # Todos os meses do ano
        for m in range(1, 13):
            months_to_create.append((year, m))
        # Jan do ano seguinte
        months_to_create.append((year + 1, 1))

        for y, month in months_to_create:
            month_start = datetime(y, month, 1, tzinfo=None)
            if month == 12:
                next_month = datetime(y + 1, 1, 1, tzinfo=None)
            else:
                next_month = datetime(y, month + 1, 1, tzinfo=None)

            part_name = f"aircraft_positions_{y:04d}_{month:02d}"

            with self.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM pg_class WHERE relname = %s AND relkind = 'r'",
                    (part_name,)
                )
                if cur.fetchone():
                    continue

                cur.execute(
                    sql.SQL("CREATE TABLE IF NOT EXISTS flight_radar.{} "
                            "PARTITION OF flight_radar.aircraft_positions "
                            "FOR VALUES FROM ({}) TO ({})")
                    .format(
                        sql.Identifier(part_name),
                        sql.Literal(month_start),
                        sql.Literal(next_month),
                    )
                )
                cur.execute(
                    sql.SQL("CREATE INDEX IF NOT EXISTS {} ON flight_radar.{} (aircraft_icao24, recorded_at)")
                    .format(
                        sql.Identifier(f"idx_{part_name}_aircraft_rec"),
                        sql.Identifier(part_name),
                    )
                )
                logger.info("Partição criada: %s", part_name)

    def insert_positions_copy(
        self, positions: list[PositionRow], cur=None
    ) -> int:
        """
        Insert usando COPY (mais rápido que INSERT para grandes volumes).
        Usa StringIO para construir o buffer em memória.

        Args:
            positions: Lista de PositionRow a inserir.
            cur: Cursor opcional. Se fornecido, reusa a transação existente.
                 Se None, abre uma nova transação.
        """
        import io

        if not positions:
            return 0

        buf = io.StringIO()
        for p in positions:
            buf.write(
                f"{p.aircraft_icao24}\t{p.flight_id}\t{p.latitude}\t{p.longitude}\t"
                f"{p.altitude_ft}\t{p.velocity_kts}\t{p.heading}\t{p.vertical_rate_fpm}\t"
                f"{'t' if p.on_ground else 'f'}\t{p.recorded_at.isoformat()}\n"
            )
        buf.seek(0)

        if cur is not None:
            # Reusa cursor existente (já dentro de uma transação)
            cur.copy_from(
                buf,
                "aircraft_positions",
                columns=(
                    "aircraft_icao24", "flight_id", "latitude", "longitude",
                    "altitude_ft", "velocity_kts", "heading", "vertical_rate_fpm",
                    "on_ground", "recorded_at",
                ),
            )
        else:
            with self.transaction() as cur:
                cur.copy_from(
                    buf,
                    "aircraft_positions",
                    columns=(
                        "aircraft_icao24", "flight_id", "latitude", "longitude",
                        "altitude_ft", "velocity_kts", "heading", "vertical_rate_fpm",
                        "on_ground", "recorded_at",
                    ),
                )
        return len(positions)

    # ── Queries auxiliares ───────────────────────────────────────────────

    def get_icao_airport_map(self) -> dict[str, dict[str, Any]]:
        """Retorna mapa {icao_code: {lat, lon, iata_code}}."""
        with self.cursor() as cur:
            cur.execute(
                "SELECT icao_code, latitude_deg, longitude_deg, iata_code "
                "FROM airports WHERE icao_code IS NOT NULL"
            )
            return {
                r["icao_code"]: {
                    "lat": float(r["latitude_deg"]) if r["latitude_deg"] is not None else None,
                    "lon": float(r["longitude_deg"]) if r["longitude_deg"] is not None else None,
                    "iata_code": r["iata_code"],
                }
                for r in cur.fetchall()
            }

    def get_active_airline_icaos(self) -> list[str]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT icao_code FROM airlines WHERE is_active = TRUE AND icao_code IS NOT NULL"
            )
            return [r["icao_code"] for r in cur.fetchall()]

    def get_aircraft_icao24s(self) -> list[str]:
        with self.cursor() as cur:
            cur.execute("SELECT icao24 FROM aircraft")
            return [r["icao24"] for r in cur.fetchall()]

    def get_aircraft_type_codes(self) -> list[str]:
        """Retorna códigos ICAO válidos da tabela aircraft_types."""
        with self.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT icao_code FROM flight_radar.aircraft_types "
                "WHERE icao_code IS NOT NULL ORDER BY icao_code"
            )
            return [r["icao_code"] for r in cur.fetchall()]

    def get_active_flights_for_positions(
        self, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Retorna voos ativos/scheduled que precisam de posições."""
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT flight_id, aircraft_icao24, origin_airport, destination_airport,
                       actual_departure, actual_arrival, status
                FROM flights
                WHERE status IN ('active', 'scheduled')
                  AND actual_departure IS NOT NULL
                ORDER BY random()
                LIMIT %s
                """,
                (limit,),
            )
            return cur.fetchall()

    def get_route_count(self) -> int:
        with self.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM routes")
            return cur.fetchone()["cnt"]

    def calculate_route_durations(self) -> None:
        """Calcula duration_minutes para rotas baseado nas coordenadas."""
        with self.transaction() as cur:
            cur.execute(
                """
                UPDATE routes r
                SET duration_minutes = (
                    SELECT ROUND(
                        (
                            haversine_km(a1.latitude_deg, a1.longitude_deg,
                                         a2.latitude_deg, a2.longitude_deg)
                            * 0.539957 / 450.0 + 0.5
                        ) * 60
                    )::INTEGER
                    FROM airports a1, airports a2
                    WHERE a1.id = r.src_airport_id
                      AND a2.id = r.dst_airport_id
                )
                WHERE duration_minutes IS NULL
                """
            )
