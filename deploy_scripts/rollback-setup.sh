#!/bin/bash
# rollback-setup.sh - DESTRÓI os recursos do AWS Batch + ECR
# Usage: ./rollback-setup.sh
#
# Fluxo:
#   1. terraform destroy (remove Batch, ECR, Security Groups)

set -a

export AWS_PAGER=""  # disable AWS CLI pager

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

# =============================================================================
# STEP 1: Load environment variables from .env
# =============================================================================
if [ -f .env ]; then
    echo -e "${BOLD}📂 Carregando variáveis de .env...${NC}"
    source .env
    echo -e "${GREEN}✅ Variáveis carregadas com sucesso!${NC}"

    # Export DB connection vars for Terraform
    if [ -n "$DB_HOST" ]; then
      export TF_VAR_db_host="$DB_HOST"
      export TF_VAR_db_port="${DB_PORT:-5432}"
      export TF_VAR_db_name="${DB_NAME:-flightradar}"
      export TF_VAR_db_user="$DB_USER"
      export TF_VAR_db_password="$DB_PASSWORD"
    fi
fi

# =============================================================================
# STEP 2: Navigate to infra directory
# =============================================================================
if [ ! -d "infra" ]; then
    echo -e "${RED}❌ Diretório infra/ não encontrado!${NC}"
    echo "   Execute este script da raiz do projeto"
    exit 1
fi

cd infra || exit 1
echo -e "${BOLD}📁 Mudado para diretório: $(pwd)${NC}"

set +a

PROJECT_NAME="${PROJECT_NAME:-flight-radar-stream}"
REGION="${AWS_REGION:-us-east-1}"

# =============================================================================
# STEP 3: Terraform destroy (Batch + ECR + Security Groups)
# =============================================================================
echo ""
echo -e "${YELLOW}${BOLD}⚠️  STEP 3 — DESTRUINDO todos os recursos via Terraform${NC}"
echo "   Projeto: $PROJECT_NAME | Ambiente: production"
echo "   Recursos: ECR Repository, AWS Batch, Security Groups, IAM Roles"
echo ""

echo -e "${RED}🔥 Destruindo recursos...${NC}"
terraform destroy -var-file="tfvars/terraform.tfvars" -auto-approve

DESTROY_EXIT=$?

if [ $DESTROY_EXIT -ne 0 ]; then
    echo -e "${RED}❌ terraform destroy falhou (código $DESTROY_EXIT).${NC}"
    echo "   Reveja os erros acima e execute manualmente se necessário."
    exit 1
fi

# =============================================================================
# STEP 4: Summary
# =============================================================================
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo -e "  ${GREEN}${BOLD}✅ Rollback concluído!${NC}"
echo ""
echo "  📌 Todos os recursos foram DESTRUÍDOS via Terraform."
echo "  📌 AWS Batch, ECR Repository e Security Groups deletados."
echo ""
echo "  ▶️  Para recriar o ambiente do zero, rode:"
echo "     ./setup-env.sh"
echo ""
echo "═══════════════════════════════════════════════════════════════"
exit 0
