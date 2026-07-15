#!/bin/bash
# setup-env.sh - Deploy AWS Batch infrastructure, build & push Docker image,
#                then verify every resource.
#
# Usage:   ./setup-env.sh
# Aliases: ./setup-env.sh --skip-apply   # init/validate/plan only
#          ./setup-env.sh --skip-docker  # skip docker build & push
#          ./setup-env.sh --no-verify    # skip post-deploy checks
#
# Exit codes:
#   0  success
#   1  prerequisites missing (env, tfvars, credentials)
#   2  terraform step failed
#   3  post-deploy verification found missing resources
#   4  docker build/push failed

set -a  # export everything we `source`

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ---------------------------------------------------------------------------
# CLI flags
# ---------------------------------------------------------------------------
SKIP_APPLY=0
SKIP_DOCKER=0
NO_VERIFY=0
for arg in "$@"; do
  case "$arg" in
    --skip-apply) SKIP_APPLY=1 ;;
    --skip-docker) SKIP_DOCKER=1 ;;
    --no-verify)  NO_VERIFY=1 ;;
    -h|--help)
      sed -n '2,15p' "$0"
      exit 0
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
section() { echo -e "\n${BOLD}${BLUE}== $* ==${NC}"; }
ok()      { echo -e "  ${GREEN}✅ $*${NC}"; }
warn()    { echo -e "  ${YELLOW}⚠️  $*${NC}"; }
fail()    { echo -e "  ${RED}❌ $*${NC}"; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { fail "Comando obrigatório ausente: $1"; exit 1; }
}

# Fetch DB credentials from AWS Secrets Manager
# Usage: fetch_db_credentials_from_secrets_manager <secret_name_or_arn>
fetch_db_credentials_from_secrets_manager() {
  local secret_id="$1"
  section "Obtendo credenciais do Secrets Manager: $secret_id"

  require_cmd aws
  require_cmd jq

  local secret_json
  if ! secret_json=$(aws secretsmanager get-secret-value --secret-id "$secret_id" --query 'SecretString' --output text 2>/dev/null); then
    warn "Falha ao obter segredo '$secret_id' do Secrets Manager; usando os valores do .env como fallback"
    return 1
  fi

  if [ -z "$secret_json" ] || [ "$secret_json" = "null" ]; then
    warn "Segredo '$secret_id' vazio ou indisponível; usando os valores do .env como fallback"
    return 1
  fi

  # Parse JSON and export as TF_VAR_*
  export TF_VAR_db_host=$(echo "$secret_json" | jq -r '.host // .DB_HOST // .db_host // empty')
  export TF_VAR_db_port=$(echo "$secret_json" | jq -r '.port // .DB_PORT // .db_port // "5432"')
  export TF_VAR_db_name=$(echo "$secret_json" | jq -r '.dbname // .DB_NAME // .db_name // "flightradar"')
  export TF_VAR_db_user=$(echo "$secret_json" | jq -r '.username // .DB_USER // .db_user // empty')
  export TF_VAR_db_password=$(echo "$secret_json" | jq -r '.password // .DB_PASSWORD // .db_password // empty')

  # Validate required fields
  if [ -z "$TF_VAR_db_host" ] || [ -z "$TF_VAR_db_user" ] || [ -z "$TF_VAR_db_password" ]; then
    warn "Segredo '$secret_id' não contém campos obrigatórios (host, username, password); usando os valores do .env como fallback"
    return 1
  fi

  ok "Credenciais obtidas do Secrets Manager"
  echo "   DB_HOST: $TF_VAR_db_host"
  echo "   DB_PORT: $TF_VAR_db_port"
  echo "   DB_NAME: $TF_VAR_db_name"
  echo "   DB_USER: $TF_VAR_db_user"
  echo "   DB_PASSWORD: ********"
  return 0
}

# ---------------------------------------------------------------------------
# STEP 1: Load .env
# ---------------------------------------------------------------------------
section "STEP 1 — Carregando .env"

if [ ! -f .env ]; then
  fail "Arquivo .env não encontrado na raiz do projeto."
  echo "   Copie .env.example para .env e preencha com seus valores"
  echo "   cp .env.example .env"
  exit 1
fi
source .env
ok "Variáveis de .env carregadas"

# Export DB connection vars for Terraform (sobrescrevem tfvars)
if [ -n "$AWS_REGION" ]; then
  export TF_VAR_aws_region="$AWS_REGION"
fi

# Se DB_SECRET_NAME estiver definido, tenta buscar credenciais do Secrets Manager
# e usa o .env como fallback se o segredo não estiver disponível.
if [ -n "$DB_SECRET_NAME" ]; then
  if fetch_db_credentials_from_secrets_manager "$DB_SECRET_NAME"; then
    :
  elif [ -n "$DB_HOST" ]; then
    export TF_VAR_db_host="$DB_HOST"
    export TF_VAR_db_port="${DB_PORT:-5432}"
    export TF_VAR_db_name="${DB_NAME:-flightradar}"
    export TF_VAR_db_user="$DB_USER"
    export TF_VAR_db_password="$DB_PASSWORD"
    ok "Credenciais de banco carregadas do .env (fallback após falha do Secrets Manager)"
  else
    warn "Nenhuma credencial de banco encontrada (DB_HOST ou DB_SECRET_NAME)"
    echo "   Defina DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD no .env"
    echo "   OU defina DB_SECRET_NAME para buscar do Secrets Manager"
  fi
elif [ -n "$DB_HOST" ]; then
  export TF_VAR_db_host="$DB_HOST"
  export TF_VAR_db_port="${DB_PORT:-5432}"
  export TF_VAR_db_name="${DB_NAME:-flightradar}"
  export TF_VAR_db_user="$DB_USER"
  export TF_VAR_db_password="$DB_PASSWORD"
  ok "Credenciais de banco carregadas do .env"
else
  warn "Nenhuma credencial de banco encontrada (DB_HOST ou DB_SECRET_NAME)"
  echo "   Defina DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD no .env"
  echo "   OU defina DB_SECRET_NAME para buscar do Secrets Manager"
fi

# ---------------------------------------------------------------------------
# STEP 2: AWS credentials sanity check (warn only, do not block)
# ---------------------------------------------------------------------------
section "STEP 2 — Verificando credenciais AWS"

CREDENTIALS_FOUND=0

# Check 1: environment variables
if [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
  CREDENTIALS_FOUND=1
  ok "Credenciais AWS via environment variables"
fi

# Check 2: aws configure (default profile)
if [ "$CREDENTIALS_FOUND" -eq 0 ] && [ -f "$HOME/.aws/credentials" ]; then
  if grep -q "aws_access_key_id" "$HOME/.aws/credentials" 2>/dev/null; then
    CREDENTIALS_FOUND=1
    ok "Credenciais AWS via aws configure (default profile)"
  fi
fi

# Check 3: try sts get-caller-identity (covers SSO, instance profile, etc.)
if [ "$CREDENTIALS_FOUND" -eq 0 ]; then
  if aws sts get-caller-identity &>/dev/null; then
    CREDENTIALS_FOUND=1
    ok "Credenciais AWS ativas (SSO / instance profile / environment)"
  fi
fi

if [ "$CREDENTIALS_FOUND" -eq 0 ]; then
  warn "Nenhuma credencial AWS encontrada."
  echo "   Configure com 'aws configure', exporte AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY,"
  echo "   ou use uma role/SSO via 'aws sso login'."
  echo "   Continuando (pode falhar no terraform apply se não houver credenciais)."
fi

# ---------------------------------------------------------------------------
# STEP 3: Move into infra/
# ---------------------------------------------------------------------------
section "STEP 3 — Acessando diretório infra/"

if [ ! -d "infra" ]; then
  fail "Diretório infra/ não encontrado. Execute este script da raiz do projeto."
  exit 1
fi
cd infra || exit 1
ok "Diretório atual: $(pwd)"

set +a  # done auto-exporting

TFVARS_FILE="tfvars/terraform.tfvars"
if [ ! -f "$TFVARS_FILE" ]; then
  fail "Arquivo de variáveis '$TFVARS_FILE' não encontrado."
  echo "   Crie a partir do template: cp tfvars/terraform.tfvars.example tfvars/terraform.tfvars"
  exit 1
fi

# ---------------------------------------------------------------------------
# STEP 4-7: Terraform init/validate/plan/apply
# ---------------------------------------------------------------------------
section "STEP 4 — terraform init"
terraform init
[ $? -ne 0 ] && { fail "terraform init falhou"; exit 2; }
ok "init concluído"

section "STEP 5 — terraform validate"
terraform validate
[ $? -ne 0 ] && { fail "terraform validate falhou"; exit 2; }
ok "validate concluído"

section "STEP 6 — terraform plan"
terraform plan -var-file="$TFVARS_FILE" -out=tfplan
[ $? -ne 0 ] && { fail "terraform plan falhou"; exit 2; }
ok "plan concluido (salvo em tfplan)"

if [ "$SKIP_APPLY" -eq 1 ]; then
  warn "--skip-apply informado; apply nao sera executado."
else
  section "STEP 7 — terraform apply"
  terraform apply -var-file="$TFVARS_FILE" -auto-approve tfplan
  [ $? -ne 0 ] && { fail "terraform apply falhou"; exit 2; }
  ok "apply concluido"
  rm -f tfplan
fi

# ---------------------------------------------------------------------------
# STEP 8: Terraform outputs
# ---------------------------------------------------------------------------
section "STEP 8 — Outputs do Terraform"

require_cmd terraform

print_output() {
  local name="$1"
  local value
  if value="$(terraform output -raw "$name" 2>/dev/null)" && [ -n "$value" ]; then
    echo -e "  ${BOLD}${name}${NC} = ${value}"
    return
  fi
  warn "Output '${name}' ausente"
}

echo -e "  ${BLUE}-- ECR --${NC}"
print_output ecr_repository_url
print_output ecr_repository_name
echo -e "  ${BLUE}-- Batch --${NC}"
print_output batch_compute_environment_name
print_output batch_job_queue_name
print_output batch_job_definition_historical_name
print_output batch_job_definition_stream_name
print_output batch_job_definition_load_reference_name

# ---------------------------------------------------------------------------
# STEP 9: Build & Push Docker image to ECR
# ---------------------------------------------------------------------------
if [ "$SKIP_APPLY" -eq 1 ] || [ "$SKIP_DOCKER" -eq 1 ]; then
  warn "Build/ push Docker ignorado."
else
  section "STEP 9 — Build & Push Docker image"

  if ! command -v docker >/dev/null 2>&1; then
    warn "Docker CLI não encontrado; pulando build/push. Instale o Docker para publicar a imagem."
  elif ! docker info >/dev/null 2>&1; then
    warn "Docker daemon indisponível; pulando build/push. Inicie o daemon do Docker para publicar a imagem."
  else
    ECR_REPO_URL=$(terraform output -raw ecr_repository_url 2>/dev/null)
    ECR_REPO_NAME=$(terraform output -raw ecr_repository_name 2>/dev/null)

    if [ -z "$ECR_REPO_URL" ]; then
      fail "URL do ECR não encontrada no terraform output"
      exit 4
    fi

    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
    REGION="${AWS_REGION:-us-east-1}"

    # Login no ECR
    ok "Fazendo login no ECR..."
    aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
    [ $? -ne 0 ] && { fail "Login no ECR falhou"; exit 4; }

    IMAGE_TAG="${BATCH_IMAGE_TAG:-latest}"
    IMAGE_URI="${ECR_REPO_URL}:${IMAGE_TAG}"

    # Build da imagem
    ok "Build da imagem Docker..."
    cd ..
    docker build -f docker/Dockerfile.batch -t "$ECR_REPO_NAME:$IMAGE_TAG" .
    [ $? -ne 0 ] && { fail "Build da imagem falhou"; exit 4; }

    # Tag para o ECR
    docker tag "$ECR_REPO_NAME:$IMAGE_TAG" "$IMAGE_URI"

    # Push para o ECR
    ok "Push da imagem para o ECR..."
    docker push "$IMAGE_URI"
    [ $? -ne 0 ] && { fail "Push da imagem falhou"; exit 4; }

    ok "Imagem enviada: ${GREEN}${IMAGE_URI}${NC}"
    cd infra || exit 1
  fi
fi

# ---------------------------------------------------------------------------
# STEP 10: Post-deploy verification
# ---------------------------------------------------------------------------
if [ "$NO_VERIFY" -eq 1 ]; then
  warn "--no-verify informado; pulando checagens pós-deploy."
  exit 0
fi

section "STEP 10 — Verificação pós-deployment"

require_cmd aws
require_cmd jq

REGION="${AWS_REGION:-us-east-1}"
PROJECT_NAME="${TF_VAR_project_name:-$(grep -E '^project_name' "$TFVARS_FILE" | head -1 | cut -d= -f2 | tr -d ' \"')}"
PROJECT_NAME="${PROJECT_NAME//$'\r'}"
if [ -z "$PROJECT_NAME" ]; then
  fail "Não foi possível determinar project_name; defina TF_VAR_project_name ou edite o tfvars"
  exit 3
fi
ok "Projeto detectado: $PROJECT_NAME (region: $REGION)"

# Verify ECR repository
section "10.1 — ECR Repository"
ECR_CHECK=$(aws ecr describe-repositories --repository-names "$PROJECT_NAME-production" --region "$REGION" --query 'repositories[0].repositoryUri' --output text 2>/dev/null)
if [ -n "$ECR_CHECK" ] && [ "$ECR_CHECK" != "None" ]; then
  ok "Repositório ECR: $ECR_CHECK"
else
  fail "Repositório ECR '$PROJECT_NAME-production' não encontrado"
  MISSING=1
fi

# Verify Batch compute environment
section "10.2 — AWS Batch"
CE_NAME=$(aws batch describe-compute-environments --compute-environments "${PROJECT_NAME}-production-batch-env" --region "$REGION" --query 'computeEnvironments[0].computeEnvironmentName' --output text 2>/dev/null || echo "")
if [ -n "$CE_NAME" ] && [ "$CE_NAME" != "None" ]; then
  CE_STATUS=$(aws batch describe-compute-environments --compute-environments "$CE_NAME" --region "$REGION" --query 'computeEnvironments[0].status' --output text 2>/dev/null)
  ok "Compute Environment '$CE_NAME' (status: $CE_STATUS)"
else
  fail "Batch Compute Environment não encontrado"
  MISSING=1
fi

# ---------------------------------------------------------------------------
# STEP 11: Final summary
# ---------------------------------------------------------------------------
section "STEP 11 — Resumo final"

ECR_URL=$(terraform output -raw ecr_repository_url 2>/dev/null || echo "<missing>")

echo ""
echo -e "${BOLD}📦 Imagem Docker:${NC}"
echo -e "  ${BOLD}ECR Repo${NC} = ${GREEN}${ECR_URL}${NC}"
echo ""
echo -e "${BOLD}⚙️  AWS Batch:${NC}"
print_output batch_compute_environment_name
print_output batch_job_queue_name
print_output batch_job_definition_historical_name
print_output batch_job_definition_stream_name
print_output batch_job_definition_load_reference_name
echo ""

if [ "${MISSING:-0}" = "1" ]; then
  fail "Verificação pós-deployment encontrou recursos faltando (ver acima)."
  exit 3
fi

echo -e "${GREEN}${BOLD}🎉 Deployment concluído e verificado com sucesso!${NC}"
exit 0
