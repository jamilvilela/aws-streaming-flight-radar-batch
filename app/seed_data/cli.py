#!/usr/bin/env python3
"""
CLI principal para o gerador de dados de teste DMS.

Modos de uso:
  # Carregar dados de referência dos CSVs
  python app/seed_data/cli.py load-reference

  # Geração histórica (5 anos, ~5GB)
  python app/seed_data/cli.py historical --years 5 --target-size-gb 5

  # Geração streaming CDC (150MB a cada 5 min)
  python app/seed_data/cli.py stream --interval 1 --target-mb-5min 150

  # Tudo em sequência
  python app/seed_data/cli.py all --years 5 --target-size-gb 5
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Garante que o diretório pai está no path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seed_data.core.config import DBConfig
from seed_data.core.data_loader import load_all_reference_data
from seed_data.generators.historical import HistoricalGenerator
from seed_data.generators.stream import StreamGenerator
from seed_data.core.repository import DatabaseRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cli")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Gera dados de teste no RDS para o pipeline DMS",
    )
    p.add_argument(
        "--host", default=None,
        help="RDS host (env: DB_HOST, default: localhost)",
    )
    p.add_argument("--port", type=int, default=None, help="RDS port (env: DB_PORT)")
    p.add_argument("--db", default=None, help="Database name (env: DB_NAME)")
    p.add_argument("--user", default=None, help="Database user (env: DB_USER)")
    p.add_argument("--password", default=None, help="Database password (env: DB_PASSWORD)")

    sub = p.add_subparsers(dest="mode", required=True, help="Modo de operação")

    # load-reference
    lr = sub.add_parser("load-reference", help="Carrega dados de referência dos CSVs")
    lr.add_argument(
        "--tables", type=str, nargs="*",
        choices=["countries", "aircraft_types", "airports", "airlines", "routes"],
        default=None,
        help="Tabelas a popular (ex: --tables airports airlines). "
             "Omite para carregar todas.",
    )

    # historical
    h = sub.add_parser("historical", help="Gera massa de dados históricos (full load)")
    h.add_argument(
        "--years", type=int, default=5,
        help="Quantidade de anos (default: 5, ignorado se --years-list for usado)",
    )
    h.add_argument(
        "--years-list", type=int, nargs="*", default=None,
        help="Anos específicos (ex: --years-list 2022 2024). Sobrescreve --years.",
    )
    h.add_argument(
        "--target-size-gb", type=float, default=5.0,
        help="Tamanho alvo em GB (default: 5.0)",
    )
    h.add_argument(
        "--flights-per-year", type=int, default=None,
        help="Forçar número de voos por ano (calculado se omitido)",
    )
    h.add_argument(
        "--batch-size", type=int, default=500,
        help="Voos entre commits (default: 500)",
    )

    # stream
    s = sub.add_parser("stream", help="Gera dados contínuos para CDC")
    s.add_argument(
        "--interval", type=int, default=1,
        help="Intervalo entre ciclos em segundos (default: 1)",
    )
    s.add_argument(
        "--target-mb-5min", type=float, default=150.0,
        help="Volume alvo de dados a cada 5 min em MB (default: 150)",
    )
    s.add_argument(
        "--max-active-flights", type=int, default=500,
        help="Máximo de voos ativos simultâneos (default: 500)",
    )
    s.add_argument(
        "--duration", type=int, default=None,
        help="Duração total em segundos (default: infinito)",
    )

    # all
    a = sub.add_parser("all", help="Referência + histórico + stream em sequência")
    a.add_argument("--years", type=int, default=5)
    a.add_argument("--years-list", type=int, nargs="*", default=None)
    a.add_argument("--target-size-gb", type=float, default=5.0)
    a.add_argument("--interval", type=int, default=1)
    a.add_argument("--target-mb-5min", type=float, default=150.0)
    a.add_argument("--duration", type=int, default=None)

    return p


def cmd_load_reference(args: argparse.Namespace, cfg: DBConfig) -> None:
    """Carrega dados de referência dos CSVs para o banco."""
    tables = args.tables  # None = todas, ou lista ex: ["airports", "airlines"]

    logger.info("=" * 60)
    logger.info("CARREGANDO DADOS DE REFERÊNCIA")
    if tables:
        logger.info("Tabelas selecionadas: %s", ", ".join(tables))
    else:
        logger.info("Todas as tabelas")
    logger.info("=" * 60)

    data = load_all_reference_data(cfg)
    repo = DatabaseRepository(cfg)
    repo.connect()

    # Ordem correta: countries → aircraft_types → airports → airlines → routes
    if tables is None or "countries" in tables:
        logger.info("Inserindo %d países...", len(data["countries"]))
        repo.insert_countries([r.model_dump() for r in data["countries"]])

    if tables is None or "aircraft_types" in tables:
        logger.info("Inserindo %d tipos de aeronave...", len(data["aircraft_types"]))
        repo.insert_aircraft_types([r.model_dump() for r in data["aircraft_types"]])

    if tables is None or "airports" in tables:
        logger.info("Inserindo %d aeroportos...", len(data["airports"]))
        repo.insert_airports([r.model_dump() for r in data["airports"]])

    if tables is None or "airlines" in tables:
        logger.info("Inserindo %d companhias...", len(data["airlines"]))
        repo.insert_airlines([r.model_dump() for r in data["airlines"]])

    if tables is None or "routes" in tables:
        logger.info("Inserindo %d rotas...", len(data["routes"]))
        repo.insert_routes([r.model_dump() for r in data["routes"]])

    # Calcula durações das rotas (precisa da função haversine no banco)
    try:
        repo.calculate_route_durations()
    except Exception as e:
        logger.warning(
            "Não foi possível calcular durações das rotas: %s", e
        )

    repo.close()
    logger.info("Carga de referência concluída!")


def cmd_historical(args: argparse.Namespace, cfg: DBConfig) -> None:
    gen = HistoricalGenerator(cfg)
    gen.run(
        years=args.years,
        target_size_gb=args.target_size_gb,
        flights_per_year=args.flights_per_year,
        batch_size=args.batch_size,
        years_list=args.years_list,
    )


def cmd_stream(args: argparse.Namespace, cfg: DBConfig) -> None:
    gen = StreamGenerator(cfg)
    gen.run(
        interval_seconds=args.interval,
        target_mb_per_5min=args.target_mb_5min,
        max_active_flights=args.max_active_flights,
        duration_seconds=args.duration,
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Monta DBConfig a partir de env + CLI (CLI sobrescreve env)
    cfg = DBConfig.from_env_or_args()
    if args.host:
        cfg.host = args.host
    if args.port:
        cfg.port = args.port
    if args.db:
        cfg.dbname = args.db
    if args.user:
        cfg.user = args.user
    if args.password:
        cfg.password = args.password

    if args.mode == "load-reference":
        cmd_load_reference(args, cfg)
    elif args.mode == "historical":
        cmd_historical(args, cfg)
    elif args.mode == "stream":
        cmd_stream(args, cfg)
    elif args.mode == "all":
        logger.info("🔷 MODO ALL: referência → histórico → stream")
        cmd_load_reference(args, cfg)
        logger.info("")
        cmd_historical(args, cfg)
        logger.info("")
        cmd_stream(args, cfg)

    logger.info("Done!")


if __name__ == "__main__":
    main()
