#!/usr/bin/env python3
"""
Script para limpar tabelas de dados gerados (flights, aircraft_positions, aircraft)
Mantém as tabelas de referência (countries, aircraft_types, airports, airlines, routes)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seed_data.core.config import DBConfig
from seed_data.core.repository import DatabaseRepository

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("clean_generated_data")


def main():
    cfg = DBConfig.from_env_or_args()
    repo = DatabaseRepository(cfg)
    repo.connect()

    try:
        with repo.transaction() as cur:
            # Ordem importante: filhos antes dos pais (FK)
            logger.info("Limpando aircraft_positions...")
            cur.execute("TRUNCATE TABLE flight_radar.aircraft_positions RESTART IDENTITY CASCADE;")

            logger.info("Limpando flights...")
            cur.execute("TRUNCATE TABLE flight_radar.flights RESTART IDENTITY CASCADE;")

            logger.info("Limpando aircraft...")
            cur.execute("TRUNCATE TABLE flight_radar.aircraft RESTART IDENTITY CASCADE;")

            logger.info("✅ Tabelas de dados gerados limpas com sucesso!")
            logger.info("Tabelas de referência preservadas: countries, aircraft_types, airports, airlines, routes")

    except Exception as e:
        logger.error(f"Erro ao limpar: {e}")
        raise
    finally:
        repo.close()


if __name__ == "__main__":
    main()