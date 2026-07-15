-- =============================================================================
-- Flight Radar RDS PostgreSQL — Schema Inicial
-- Laboratório de migração DMS com dados dos datasets OpenFlights + OurAirports
--
-- Fontes dos dados de referência (app/data/):
--   airports.csv       → OurAirports (~85k aeroportos, ~10k com ICAO)
--   airlines.csv       → OpenFlights (~6k companhias, ~1.2k ativas)
--   airplanes.csv      → OpenFlights (~245 tipos de aeronave)
--   routes.csv         → OpenFlights (~67k rotas entre ~3.4k aeroportos)
--   countries.csv      → OurAirports (250 países)
--
-- Geração dinâmica (app/seed_data/):
--   aircraft            → gerado combinando aircraft_types + registrations
--   flights             → voos gerados a partir de routes + aircraft
--   aircraft_positions  → posições interpoladas (PARTITIONED por mês)
--
-- Volumes alvo:
--   Histórico:  5 anos, ~5GB (via python cli.py historical --years 5 --target-size-gb 5)
--   Streaming:  150MB a cada 5 min (via python cli.py stream --interval 1 --target-mb-5min 150)
--
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS flight_radar;
SET search_path TO flight_radar;

-- =============================================================================
-- Funções auxiliares
-- =============================================================================

-- Haversine: distância em km entre dois pontos na superfície da Terra
CREATE OR REPLACE FUNCTION flight_radar.haversine_km(
    lat1 NUMERIC, lon1 NUMERIC,
    lat2 NUMERIC, lon2 NUMERIC
) RETURNS NUMERIC
    LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE
AS $$
DECLARE
    dlat NUMERIC := RADIANS(lat2 - lat1);
    dlon NUMERIC := RADIANS(lon2 - lon1);
    a    NUMERIC := SIN(dlat / 2)^2 + COS(RADIANS(lat1)) * COS(RADIANS(lat2)) * SIN(dlon / 2)^2;
    c    NUMERIC := 2 * ASIN(SQRT(a));
BEGIN
    RETURN 6371.0 * c;  -- raio médio da Terra em km
END;
$$;

-- #############################################################################
-- TABELAS DE REFERÊNCIA (carregadas dos CSVs)
-- #############################################################################

-- -------------------------------------------------------------------------------
-- Países
-- Fonte: countries.csv (OurAirports)
-- -------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flight_radar.countries (
    id          INTEGER PRIMARY KEY,
    code        CHAR(2) NOT NULL UNIQUE,
    name        VARCHAR(200) NOT NULL,
    continent   CHAR(2),
    wikipedia_link TEXT
);

-- -------------------------------------------------------------------------------
-- Tipos de aeronave / modelos (catálogo)
-- Fonte: airplanes.csv (OpenFlights) — nome + IATA code + ICAO code
-- Usado como lookup para as aeronaves individuais (aircraft table)
-- -------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flight_radar.aircraft_types (
    icao_code   VARCHAR(4) PRIMARY KEY,              -- ex: B738, A320, E190
    iata_code   VARCHAR(3),                          -- ex: 738, 320, 190
    name        VARCHAR(200) NOT NULL,                -- ex: "Boeing 737-800"
    manufacturer VARCHAR(100) GENERATED ALWAYS AS (
        CASE
            WHEN name ILIKE 'Boeing%' THEN 'Boeing'
            WHEN name ILIKE 'Airbus%' THEN 'Airbus'
            WHEN name ILIKE 'Embraer%' OR name ILIKE '%Embraer%' THEN 'Embraer'
            WHEN name ILIKE 'Bombardier%' THEN 'Bombardier'
            WHEN name ILIKE 'ATR%' OR name ILIKE 'Aerospatiale%' THEN 'ATR/Aerospatiale'
            WHEN name ILIKE 'Cessna%' THEN 'Cessna'
            WHEN name ILIKE 'Antonov%' THEN 'Antonov'
            WHEN name ILIKE 'Ilyushin%' THEN 'Ilyushin'
            WHEN name ILIKE 'Tupolev%' THEN 'Tupolev'
            WHEN name ILIKE 'McDonnell%' OR name ILIKE 'Douglas%' OR name ILIKE 'MD-%' THEN 'McDonnell Douglas'
            WHEN name ILIKE 'Lockheed%' THEN 'Lockheed'
            WHEN name ILIKE 'British Aerospace%' OR name ILIKE 'BAe%' THEN 'British Aerospace'
            WHEN name ILIKE 'Dassault%' THEN 'Dassault'
            WHEN name ILIKE 'Gulfstream%' THEN 'Gulfstream'
            WHEN name ILIKE 'Learjet%' THEN 'Learjet'
            WHEN name ILIKE 'Pilatus%' THEN 'Pilatus'
            WHEN name ILIKE 'Diamond%' THEN 'Diamond'
            WHEN name ILIKE 'Piper%' THEN 'Piper'
            WHEN name ILIKE 'Beechcraft%' OR name ILIKE 'Raytheon%' THEN 'Beechcraft/Raytheon'
            WHEN name ILIKE 'Fokker%' THEN 'Fokker'
            WHEN name ILIKE 'de Havilland%' OR name ILIKE 'DHC%' THEN 'De Havilland Canada'
            WHEN name ILIKE 'Saab%' THEN 'Saab'
            WHEN name ILIKE 'CASA%' OR name ILIKE 'CN-%' THEN 'CASA'
            WHEN name ILIKE 'Britten-Norman%' THEN 'Britten-Norman'
            WHEN name ILIKE 'Let%' THEN 'Let'
            WHEN name ILIKE 'PAC%' THEN 'PAC'
            WHEN name ILIKE 'Viking%' THEN 'Viking Air'
            WHEN name ILIKE 'COMAC%' THEN 'COMAC'
            WHEN name ILIKE 'Mitsubishi%' THEN 'Mitsubishi'
            WHEN name ILIKE 'Sukhoi%' THEN 'Sukhoi'
            WHEN name ILIKE 'Yakovlev%' THEN 'Yakovlev'
            ELSE 'Other'
        END
    ) STORED
);

-- -------------------------------------------------------------------------------
-- Aeroportos
-- Fonte: airports.csv (OurAirports) — ~85k registros, ~10k com ICAO, ~4k com IATA+scheduled
-- -------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flight_radar.airports (
    id              INTEGER PRIMARY KEY,
    ident           VARCHAR(20),
    type            VARCHAR(50),                     -- large_airport, medium_airport, small_airport, heliport...
    name            VARCHAR(300) NOT NULL,
    latitude_deg    DECIMAL(10,7),
    longitude_deg   DECIMAL(10,7),
    elevation_ft    INTEGER,
    continent       CHAR(2),
    iso_country     CHAR(2) REFERENCES flight_radar.countries(code),
    iso_region      VARCHAR(10),
    municipality    VARCHAR(200),
    scheduled_service BOOLEAN NOT NULL DEFAULT FALSE,
    icao_code       VARCHAR(4) UNIQUE,
    iata_code       VARCHAR(3),
    gps_code        VARCHAR(4),
    local_code      VARCHAR(10),
    home_link       TEXT,
    wikipedia_link  TEXT
);

CREATE INDEX IF NOT EXISTS idx_airports_icao     ON flight_radar.airports(icao_code);
CREATE INDEX IF NOT EXISTS idx_airports_iata     ON flight_radar.airports(iata_code);
CREATE INDEX IF NOT EXISTS idx_airports_country  ON flight_radar.airports(iso_country);
CREATE INDEX IF NOT EXISTS idx_airports_type     ON flight_radar.airports(type);
CREATE INDEX IF NOT EXISTS idx_airports_scheduled ON flight_radar.airports(scheduled_service)
    WHERE scheduled_service = TRUE;

-- -------------------------------------------------------------------------------
-- Companhias aéreas
-- Fonte: airlines.csv (OpenFlights) — ~6k registros, ~1.2k ativas
-- -------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flight_radar.airlines (
    id          INTEGER PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    alias       VARCHAR(100),
    iata_code   VARCHAR(2),
    icao_code   VARCHAR(3) UNIQUE,
    callsign    VARCHAR(50),
    country     VARCHAR(100),
    is_active   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_airlines_icao   ON flight_radar.airlines(icao_code);
CREATE INDEX IF NOT EXISTS idx_airlines_active ON flight_radar.airlines(is_active)
    WHERE is_active = TRUE;

-- -------------------------------------------------------------------------------
-- Rotas entre aeroportos
-- Fonte: routes.csv (OpenFlights) — ~67k rotas
-- -------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flight_radar.routes (
    id              BIGSERIAL PRIMARY KEY,
    airline_iata    VARCHAR(2),                      -- código IATA da companhia
    airline_id      INTEGER REFERENCES flight_radar.airlines(id),
    src_airport     VARCHAR(4),                      -- IATA code do aeroporto origem
    src_airport_id  INTEGER REFERENCES flight_radar.airports(id),
    dst_airport     VARCHAR(4),                      -- IATA code do aeroporto destino
    dst_airport_id  INTEGER REFERENCES flight_radar.airports(id),
    codeshare       VARCHAR(1),
    stops           INTEGER NOT NULL DEFAULT 0,
    equipment       VARCHAR(200),                    -- códigos ICAO dos tipos de aeronave
    duration_minutes INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique index natural: mesma companhia + mesma origem/destino + mesmas escalas = mesma rota
-- COALESCE trata NULLs corretamente (PostgreSQL trata NULLs como diferentes em unique index)
CREATE UNIQUE INDEX IF NOT EXISTS uq_routes_natural
    ON flight_radar.routes(COALESCE(airline_id,0), COALESCE(src_airport_id,0), COALESCE(dst_airport_id,0), stops);

CREATE INDEX IF NOT EXISTS idx_routes_src     ON flight_radar.routes(src_airport_id);
CREATE INDEX IF NOT EXISTS idx_routes_dst     ON flight_radar.routes(dst_airport_id);
CREATE INDEX IF NOT EXISTS idx_routes_airline ON flight_radar.routes(airline_id);

-- #############################################################################
-- TABELAS GERADAS DINAMICAMENTE
-- #############################################################################

-- -------------------------------------------------------------------------------
-- Aeronaves individuais (com registros ICAO24 fictícios)
-- Gerado combinando aircraft_types + prefixos de país + números seriais
-- -------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flight_radar.aircraft (
    icao24          VARCHAR(6) PRIMARY KEY,          -- endereço ICAO hex (ex: a0f1b2)
    registration    VARCHAR(20) NOT NULL,            -- matrícula (ex: N12345, D-ABYT)
    aircraft_type   VARCHAR(4) NOT NULL REFERENCES flight_radar.aircraft_types(icao_code),
    serial_number   VARCHAR(30),
    operator_icao   VARCHAR(3) REFERENCES flight_radar.airlines(icao_code),
    operator_name   VARCHAR(200),
    year_built      SMALLINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aircraft_type     ON flight_radar.aircraft(aircraft_type);
CREATE INDEX IF NOT EXISTS idx_aircraft_operator ON flight_radar.aircraft(operator_icao);

-- -------------------------------------------------------------------------------
-- Voos (tabela fato — instâncias de voo)
-- Gerado dinamicamente combinando routes + aircraft + schedules
-- -------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flight_radar.flights (
    flight_id           BIGSERIAL PRIMARY KEY,
    flight_number       VARCHAR(10) NOT NULL,
    airline_icao        VARCHAR(3) REFERENCES flight_radar.airlines(icao_code),
    aircraft_icao24     VARCHAR(6) REFERENCES flight_radar.aircraft(icao24),
    origin_airport      VARCHAR(4) REFERENCES flight_radar.airports(icao_code),
    destination_airport VARCHAR(4) REFERENCES flight_radar.airports(icao_code),
    scheduled_departure TIMESTAMPTZ,
    scheduled_arrival   TIMESTAMPTZ,
    actual_departure    TIMESTAMPTZ,
    actual_arrival      TIMESTAMPTZ,
    status              VARCHAR(20) NOT NULL DEFAULT 'scheduled',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_flight_status CHECK (
        status IN ('scheduled','active','landed','cancelled','diverted')
    )
);

-- Unique index natural para permitir ON CONFLICT (idempotência)
-- flight_number + airline + aircraft + scheduled_departure identifica um voo único
CREATE UNIQUE INDEX IF NOT EXISTS uq_flights_natural
    ON flight_radar.flights(flight_number, airline_icao, aircraft_icao24, scheduled_departure);

CREATE INDEX IF NOT EXISTS idx_flights_status        ON flight_radar.flights(status);
CREATE INDEX IF NOT EXISTS idx_flights_aircraft      ON flight_radar.flights(aircraft_icao24);
CREATE INDEX IF NOT EXISTS idx_flights_airline       ON flight_radar.flights(airline_icao);
CREATE INDEX IF NOT EXISTS idx_flights_origin        ON flight_radar.flights(origin_airport);
CREATE INDEX IF NOT EXISTS idx_flights_destination   ON flight_radar.flights(destination_airport);
CREATE INDEX IF NOT EXISTS idx_flights_sched_dep     ON flight_radar.flights(scheduled_departure);
CREATE INDEX IF NOT EXISTS idx_flights_sched_arr     ON flight_radar.flights(scheduled_arrival);

-- -------------------------------------------------------------------------------
-- Posições de aeronave (tabela fato de altíssimo volume — PARTICIONADA)
-- Cada linha = uma reportação de posição ADS-B
-- Volume alvo: 5GB históricos + 150MB/5min em streaming CDC
-- Estratégia: PARTITION BY RANGE (recorded_at) para manutenção eficiente
-- -------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flight_radar.aircraft_positions (
    position_id     BIGSERIAL,
    aircraft_icao24 VARCHAR(6) NOT NULL REFERENCES flight_radar.aircraft(icao24),
    flight_id       BIGINT REFERENCES flight_radar.flights(flight_id),
    latitude        DECIMAL(10,7),
    longitude       DECIMAL(10,7),
    altitude_ft     INTEGER,
    velocity_kts    DECIMAL(7,2),
    heading         DECIMAL(5,2),
    vertical_rate_fpm DECIMAL(7,2),
    on_ground       BOOLEAN NOT NULL DEFAULT FALSE,
    recorded_at     TIMESTAMPTZ NOT NULL,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (position_id, recorded_at)
) PARTITION BY RANGE (recorded_at);

-- Unique index para evitar duplicação de posições no mesmo instante
CREATE UNIQUE INDEX IF NOT EXISTS uq_aircraft_positions_instant
    ON flight_radar.aircraft_positions(flight_id, recorded_at);

-- =============================================================================
-- Criação das partições mensais para aircraft_positions
-- Gera partições para 5 anos (2022-2026) + janela futura de 1 ano
-- =============================================================================
DO $$
DECLARE
    start_date  DATE := '2022-01-01';
    end_date    DATE := '2028-01-01';
    part_date   DATE;
    part_name   TEXT;
BEGIN
    part_date := start_date;
    WHILE part_date < end_date LOOP
        part_name := 'aircraft_positions_'
                     || TO_CHAR(part_date, 'YYYY_MM');
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS flight_radar.%I PARTITION OF flight_radar.aircraft_positions
             FOR VALUES FROM (%L) TO (%L)',
            part_name,
            part_date,
            part_date + INTERVAL '1 month'
        );
        -- Cria índice local na partição
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON flight_radar.%I (aircraft_icao24, recorded_at)',
            'idx_' || part_name || '_aircraft_rec',
            part_name
        );
        part_date := part_date + INTERVAL '1 month';
    END LOOP;
END;
$$;

-- Índices na tabela particionada (aplica a todas as partições via PostgreSQL 17)
CREATE INDEX IF NOT EXISTS idx_positions_aircraft   ON flight_radar.aircraft_positions(aircraft_icao24);
CREATE INDEX IF NOT EXISTS idx_positions_recorded   ON flight_radar.aircraft_positions(recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_positions_flight     ON flight_radar.aircraft_positions(flight_id);

-- =============================================================================
-- VIEW AUXILIAR: visão consolidada de voo + posição mais recente
-- =============================================================================
CREATE OR REPLACE VIEW flight_radar.v_latest_positions AS
SELECT DISTINCT ON (ap.aircraft_icao24)
    ap.aircraft_icao24,
    ap.flight_id,
    ap.latitude,
    ap.longitude,
    ap.altitude_ft,
    ap.velocity_kts,
    ap.heading,
    ap.vertical_rate_fpm,
    ap.on_ground,
    ap.recorded_at,
    f.flight_number,
    f.airline_icao,
    f.origin_airport,
    f.destination_airport,
    f.status
FROM flight_radar.aircraft_positions ap
JOIN flight_radar.flights f ON f.flight_id = ap.flight_id
WHERE ap.recorded_at > NOW() - INTERVAL '2 hours'
ORDER BY ap.aircraft_icao24, ap.recorded_at DESC;

-- =============================================================================
-- FUNÇÃO: Estatísticas rápidas de volume de dados
-- =============================================================================
CREATE OR REPLACE FUNCTION flight_radar.fn_data_volume_stats()
RETURNS TABLE (
    table_name      TEXT,
    row_count       BIGINT,
    total_size_mb   NUMERIC,
    partition_count INTEGER
) LANGUAGE plpgsql AS $$
DECLARE
    pos_partitions INTEGER;
BEGIN
    SELECT COUNT(*) INTO pos_partitions
    FROM pg_class
    WHERE relname LIKE 'aircraft_positions_%'
      AND relkind = 'r';

    RETURN QUERY
    SELECT
        relname::TEXT,
        n_live_tup::BIGINT,
        ROUND(pg_total_relation_size(relid) / 1048576.0, 2),
        CASE
            WHEN relname = 'aircraft_positions'
            THEN pos_partitions
            ELSE 0
        END
    FROM pg_stat_user_tables
    WHERE schemaname = 'flight_radar'
    ORDER BY n_live_tup DESC;
END;
$$;

-- =============================================================================
-- CONFIGURAÇÃO DMS — Logical Replication com pglogical
-- =============================================================================

-- Extensão pglogical
CREATE EXTENSION IF NOT EXISTS pglogical;

-- Garante que o dbadmin tenha privilégio rds_replication
GRANT rds_replication TO dbadmin;

--
-- Parâmetros WAL e replicação lógica são configurados via
-- cluster parameter group no Terraform do repositório de Aurora:
--
--   rds.logical_replication          = 1        (habilita wal_level = logical)
--   max_replication_slots            = 20
--   max_wal_senders                  = 20
--   max_logical_replication_workers  = 12
--   max_worker_processes             = 30
--   wal_buffers                      = 65536   (64MB em blocos de 8KB)
--
-- Após alterar o parameter group, é necessário REBOOT do cluster.
-- Use AWS Console ou CLI:
--   aws rds reboot-db-cluster --db-cluster-identifier <cluster_id>
--
-- Comandos ALTER SYSTEM não funcionam no RDS (exigem superuser).
--

-- =============================================================================
-- NOTAS DE USO:
-- =============================================================================
-- 1. Carga dos dados de referência:
--    python app/seed_data/cli.py load-reference
--
-- 2. Geração de dados históricos (5 anos, ~5GB):
--    python app/seed_data/cli.py historical --years 5 --target-size-gb 5
--
-- 3. Geração de streaming CDC (150MB/5min):
--    python app/seed_data/cli.py stream --interval 1 --target-mb-5min 150
--
-- 4. Monitoramento de volume:
--    SELECT * FROM flight_radar.fn_data_volume_stats();
--
-- 5. Consulta de posições mais recentes:
--    SELECT * FROM flight_radar.v_latest_positions LIMIT 50;
-- ============================================================================="