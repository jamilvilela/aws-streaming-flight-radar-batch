# =============================================================================
# AWS Secrets Manager - Segredo de credenciais do banco (Aurora PostgreSQL)
#
# O segredo é criado a partir dos valores do .env (DB_HOST/DB_PORT/DB_NAME/
# DB_USER/DB_PASSWORD) e injetado no Batch via DB_SECRET_NAME.
#
# Se já existir um segredo com o MESMO nome, ele NÃO é recriado: o setup-env.sh
# executa `terraform import` para adotá-lo e o valor existente é reaproveitado.
# =============================================================================

# -------------------------------------------------------------------------------
# Probe de existência (não gerencia nada; usado pelo setup-env.sh e outputs)
# -------------------------------------------------------------------------------
data "aws_secretsmanager_secrets" "by_name" {
  count = local.secrets_enabled ? 1 : 0

  filter {
    name   = "name"
    values = [var.db_secret_name]
  }
}

# -------------------------------------------------------------------------------
# Segredo em si
# -------------------------------------------------------------------------------
resource "aws_secretsmanager_secret" "create" {
  count = local.secrets_enabled ? 1 : 0

  name = var.db_secret_name
  tags = var.tags
}

# -------------------------------------------------------------------------------
# Valor do segredo (JSON consumido por entrypoint.py e setup-env.sh)
# -------------------------------------------------------------------------------
resource "aws_secretsmanager_secret_version" "create" {
  count     = local.secrets_enabled ? 1 : 0
  secret_id = aws_secretsmanager_secret.create[0].id

  secret_string = jsonencode({
    host     = var.db_host
    port     = var.db_port
    dbname   = var.db_name
    username = var.db_user
    password = var.db_password
  })
}

# -------------------------------------------------------------------------------
# Resource policy do segredo - libera leitura para as roles do Batch
# (já existe permissão via IAM role policy; isto adiciona defesa em profundidade)
# -------------------------------------------------------------------------------
resource "aws_secretsmanager_secret_policy" "batch_read" {
  count = local.secrets_enabled && var.batch_config.enabled ? 1 : 0

  secret_arn = local.secret_arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowBatchRolesRead"
        Effect = "Allow"
        Principal = {
          AWS = [
            aws_iam_role.batch_job_role[0].arn,
            aws_iam_role.batch_instance_role[0].arn,
          ]
        }
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret",
        ]
        Resource = local.secret_arn
      },
    ]
  })
}