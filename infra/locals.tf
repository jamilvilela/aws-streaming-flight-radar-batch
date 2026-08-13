locals {
  # ── VPC ID: usa o valor explícito ou descobre via data source ──
  effective_vpc_id = var.vpc_id != null ? var.vpc_id : try(data.aws_vpc.selected[0].id, null)

  # ── Subnet IDs: usa a lista explícita ou descobre via data source ──
  effective_subnet_ids = var.subnet_ids != null ? var.subnet_ids : try(data.aws_subnets.selected[0].ids, [])

  # ── Secrets Manager: criação/gerenciamento do segredo do banco ──
  secrets_enabled = var.db_secret_name != ""
  secret_arn      = local.secrets_enabled ? aws_secretsmanager_secret.create[0].arn : null

  # Detecta se já existe um segredo com o mesmo nome (para decisão de import)
  secret_exists = local.secrets_enabled ? try(length(data.aws_secretsmanager_secrets.by_name[0].arns), 0) > 0 : false
}
