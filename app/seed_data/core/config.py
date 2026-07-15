"""
Configuração — carregamento de .env e parâmetros de conexão.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse

from dotenv import load_dotenv

# Carrega .env da raiz do projeto
_env_path = Path(__file__).resolve().parents[3] / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)


@dataclass
class DBConfig:
    """Configuração de conexão com o banco PostgreSQL."""

    host: str = "localhost"
    port: int = 5432
    dbname: str = "flightradar"
    user: str = "dbadmin"
    password: str = ""

    # Caminhos dos datasets
    data_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[3] / "app" / "data"
    )

    DEFAULT_HOST: ClassVar[str] = "localhost"
    DEFAULT_PORT: ClassVar[int] = 5432
    DEFAULT_DB: ClassVar[str] = "flightradar"
    DEFAULT_USER: ClassVar[str] = "dbadmin"

    @classmethod
    def from_env_or_args(cls) -> "DBConfig":
        raw_host = os.environ.get("DB_HOST", "")

        # Se DB_HOST for uma URI (postgresql://user@host:port/dbname), faz o parse
        if raw_host.startswith("postgresql://") or raw_host.startswith("postgres://"):
            parsed = urlparse(raw_host)
            host = parsed.hostname or cls.DEFAULT_HOST
            port = parsed.port or int(os.environ.get("DB_PORT", str(cls.DEFAULT_PORT)))
            dbname = parsed.path.lstrip("/") or os.environ.get("DB_NAME", cls.DEFAULT_DB)
            user = parsed.username or os.environ.get("DB_USER", cls.DEFAULT_USER)
            password = parsed.password or os.environ.get("DB_PASSWORD", "")
        else:
            host = raw_host or cls.DEFAULT_HOST
            port = int(os.environ.get("DB_PORT", str(cls.DEFAULT_PORT)))
            dbname = os.environ.get("DB_NAME", cls.DEFAULT_DB)
            user = os.environ.get("DB_USER", cls.DEFAULT_USER)
            password = os.environ.get("DB_PASSWORD", "")

        return cls(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
        )

    @property
    def dsn(self) -> str:
        return (
            f"host={self.host} port={self.port} "
            f"dbname={self.dbname} user={self.user} password={self.password}"
        )

    @property
    def csv_paths(self) -> dict[str, Path]:
        """Retorna os caminhos absolutos de cada CSV."""
        d = self.data_dir
        return {
            "airports": d / "airports.csv",
            "airlines": d / "airlines.csv",
            "airplanes": d / "airplanes.csv",
            "routes": d / "routes.csv",
            "countries": d / "countries.csv",
        }
