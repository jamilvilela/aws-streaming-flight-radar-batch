# =============================================================================
# Rede para acesso ao Secrets Manager
#
# A causa dos erros dos jobs era timeout de conexão para o Secrets Manager.
# Detalhe importante: a VPC JÁ possui um VPC interface endpoint para o
# Secrets Manager (vpce-...), pertencente a outro módulo/repo (DMS serverless),
# com private DNS ativo. Por isso NÃO é possível (nem necessário) criar outro
# endpoint com private DNS aqui - o domínio secretsmanager.<region>.amazonaws.com
# já é roteado para o endpoint existente.
#
# O problema real: o SG desse endpoint existente só liberava 443 para o SG do
# DMS - o SG do Batch era bloqueado. Aqui reutilizamos o endpoint existente e
# adicionamos uma regra de ingresso liberando o SG do Batch.
# =============================================================================

# -------------------------------------------------------------------------------
# Descoberta do VPC interface endpoint do Secrets Manager já existente
# -------------------------------------------------------------------------------
data "aws_vpc_endpoint" "secretsmanager" {
  count = var.batch_config.enabled && local.secrets_enabled ? 1 : 0

  filter {
    name   = "service-name"
    values = ["com.amazonaws.${var.aws_region}.secretsmanager"]
  }
  filter {
    name   = "vpc-id"
    values = [local.effective_vpc_id]
  }
  filter {
    name   = "vpc-endpoint-state"
    values = ["available"]
  }
}

# -------------------------------------------------------------------------------
# Libera o SG do Batch no SG do endpoint existente (porta 443 / HTTPS)
# NOTA: o SG do endpoint é compartilhado com o repo do DMS; regra adicionada de
# forma cirúrgica (aws_vpc_security_group_ingress_rule), sem tomar posse do SG.
# -------------------------------------------------------------------------------
resource "aws_vpc_security_group_ingress_rule" "secrets_endpoint_batch" {
  count                        = var.batch_config.enabled && local.secrets_enabled ? 1 : 0
  security_group_id            = one(data.aws_vpc_endpoint.secretsmanager[0].security_group_ids)
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  referenced_security_group_id = aws_security_group.batch.id
  description                  = "Allow HTTPS from AWS Batch to Secrets Manager VPC endpoint"
}