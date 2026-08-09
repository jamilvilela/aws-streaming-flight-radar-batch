#!/usr/bin/env python3
"""
Batch Entrypoint Script
Executa diferentes tipos de jobs de carga de dados baseado na variável de ambiente JOB_TYPE.

Tipos de job suportados:
- historical: Gera dados históricos (anos passados)
- stream: Gera streaming CDC contínuo
- load-reference: Carrega dados de referência (CSVs)
- clean: Limpa tabelas de dados gerados
"""

import os
import sys
import subprocess
import logging
import json

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("batch-entrypoint")


def fetch_db_credentials_from_secrets_manager(secret_id: str) -> dict:
    """Busca credenciais do banco no AWS Secrets Manager.
    Aceita o nome ou o ARN do segredo como SecretId."""
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        logger.error("boto3 não instalado. Não é possível buscar segredo do Secrets Manager.")
        return {}

    logger.info(f"Buscando credenciais do banco no Secrets Manager: {secret_id}")
    client = boto3.client("secretsmanager")
    try:
        response = client.get_secret_value(SecretId=secret_id)
        secret_string = response.get("SecretString", "{}")
        secret = json.loads(secret_string)
        logger.info("Credenciais obtidas com sucesso do Secrets Manager")
        return secret
    except ClientError as e:
        logger.error(f"Erro ao buscar segredo no Secrets Manager: {e}")
        return {}


def run_command(cmd: list[str], env: dict | None = None) -> int:
    """Executa comando e retorna código de saída."""
    logger.info(f"Executando: {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env or os.environ)
    return result.returncode


def main():
    # Se DB_SECRET_NAME estiver definido, busca credenciais no Secrets Manager
    db_secret_name = os.getenv("DB_SECRET_NAME")
    if db_secret_name:
        secret = fetch_db_credentials_from_secrets_manager(db_secret_name)
        if secret:
            # Define variáveis de ambiente esperadas pelo seed_data/cli.py
            os.environ["DB_HOST"] = secret.get("host", os.getenv("DB_HOST", ""))
            os.environ["DB_PORT"] = str(secret.get("port", os.getenv("DB_PORT", "5432")))
            os.environ["DB_NAME"] = secret.get("dbname", secret.get("database", os.getenv("DB_NAME", "flightradar")))
            os.environ["DB_USER"] = secret.get("username", secret.get("user", os.getenv("DB_USER", "")))
            os.environ["DB_PASSWORD"] = secret.get("password", os.getenv("DB_PASSWORD", ""))
            logger.info("Variáveis de conexão DB configuradas a partir do Secrets Manager")
        else:
            logger.warning(
                "Secrets Manager falhou. Usando variáveis DB_HOST/DB_USER/DB_PASSWORD "
                "do ambiente (containerOverrides ou .env)."
            )

    # Diagnóstico: exibe qual host será usado para conexão
    db_host = os.getenv("DB_HOST", "localhost")
    logger.info("DB_HOST configurado: %s", db_host)

    job_type = os.getenv("JOB_TYPE", "historical").lower()
    logger.info("Iniciando job tipo: %s", job_type)

    # Caminho relativo ao WORKDIR /app (definido no Dockerfile)
    base_cmd = [
        sys.executable,
        "seed_data/cli.py"
    ]

    # Mapeia tipo de job para comando
    if job_type == "historical":
        years = os.getenv("YEARS", "5")
        target_size_gb = os.getenv("TARGET_SIZE_GB", "5")
        years_list = os.getenv("YEARS_LIST", "")
        cmd = base_cmd + [
            "historical",
            "--years", years,
            "--target-size-gb", target_size_gb
        ]
        if years_list:
            # Aceita formato JSON array "[2025,2026]" ou espaço-separado "2025 2026"
            years_parsed = years_list.strip().strip("[]").replace(",", " ")
            cmd.extend(["--years-list", *years_parsed.split()])

    elif job_type == "stream":
        interval = os.getenv("INTERVAL", "1")
        target_mb = os.getenv("TARGET_MB_5MIN", "150")
        duration = os.getenv("DURATION", "")
        cmd = base_cmd + [
            "stream",
            "--interval", interval,
            "--target-mb-5min", target_mb
        ]
        if duration:
            cmd.extend(["--duration", duration])

    elif job_type == "load-reference":
        tables = os.getenv("TABLES", "")
        cmd = base_cmd + ["load-reference"]
        if tables:
            cmd.extend(["--tables", tables])

    elif job_type == "clean":
        cmd = base_cmd + ["clean"]

    elif job_type == "all":
        years = os.getenv("YEARS", "5")
        target_size_gb = os.getenv("TARGET_SIZE_GB", "5")
        cmd = base_cmd + [
            "all",
            "--years", years,
            "--target-size-gb", target_size_gb
        ]

    else:
        logger.error(f"Tipo de job desconhecido: {job_type}")
        logger.info("Tipos válidos: historical, stream, load-reference, clean, all")
        sys.exit(1)

    # Executa o comando
    exit_code = run_command(cmd)
    if exit_code != 0:
        logger.error(f"Job falhou com código {exit_code}")
        sys.exit(exit_code)

    logger.info("Job concluído com sucesso!")


if __name__ == "__main__":
    main()
