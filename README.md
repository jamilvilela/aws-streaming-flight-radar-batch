# aws-streaming-flight-radar-batch

**AWS Batch** — Infraestrutura de jobs de carga de dados para dados de voos com schema `flight_radar`.

## Serviços

| Serviço | Descrição |
|---------|-----------|
| **AWS Batch** | Jobs de carga de dados: `historical`, `stream`, `load-reference` |
| **ECR** | Repositório de imagem Docker para os jobs Batch |

## Estrutura

```
infra/                     # Terraform
├── main.tf                # Recursos AWS Batch + ECR + Security Groups
├── variables.tf           # Variáveis de entrada (DB host, Batch config)
├── outputs.tf             # Outputs do stack
├── providers.tf           # Provider AWS
├── data.tf                # Data sources (VPC, subnets)
├── locals.tf              # Locals
└── tfvars/
    └── terraform.tfvars   # Valores das variáveis

app/
├── entrypoint.py          # Entrypoint dos jobs Batch
├── seed_data/             # Geradores de dados (historical, stream, load-reference)
├── data/                  # Dados de referência (CSVs)
└── sql/                   # Schema SQL

docker/
└── Dockerfile.batch       # Dockerfile para a imagem do Batch

app/
├── entrypoint.py          # Entrypoint dos jobs Batch
├── seed_data/             # Geradores de dados (historical, stream, load-reference)
├── data/                  # Dados de referência (CSVs)
└── sql/                   # Schema SQL

setup-env.sh               # Deploy automatizado (Terraform + Docker build/push)
rollback-setup.sh          # Destrói recursos (Terraform destroy)
```

## Pré-requisitos

- AWS CLI configurado (credentials ou SSO)
- Docker instalado
- Terraform >= 1.1.0
- Acesso ao banco Aurora PostgreSQL (gerenciado em repo separado)

## Deploy rápido

```bash
# 1. Configure .env com os dados de conexão do Aurora
cp .env.example .env
# Edite .env com DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

# 2. Deploy (Terraform + Docker build/push)
./setup-env.sh
```

## Destruir recursos

```bash
./rollback-setup.sh
```
