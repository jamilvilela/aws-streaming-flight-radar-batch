#!/usr/bin/env python3
"""
Entry point principal para geração de dados de teste DMS.

Comandos disponíveis via 'python -m seed_data.cli':
  load-reference   → Carrega dados de referência dos CSVs
  historical       → Gera dados históricos (5 anos, ~5GB)
  stream           → Gera streaming CDC (150MB/5min)
  all              → Tudo em sequência

Exemplo:
  python -m seed_data.cli load-reference
  python -m seed_data.cli historical --years 5 --target-size-gb 5
  python -m seed_data.cli stream --interval 1 --target-mb-5min 150

Execução direta:
  python app/seed_data/main.py load-reference
  python app/seed_data/main.py historical --years 5 --target-size-gb 5
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from seed_data.cli import main

if __name__ == "__main__":
    main()
