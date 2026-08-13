# ============================================================================
# AWS Batch outputs
# ============================================================================

output "batch_compute_environment_name" {
  description = "Nome do Compute Environment"
  value       = try(aws_batch_compute_environment.this[0].name, null)
}

output "batch_compute_environment_arn" {
  description = "ARN do Compute Environment"
  value       = try(aws_batch_compute_environment.this[0].arn, null)
}

output "batch_job_queue_name" {
  description = "Nome da Job Queue"
  value       = try(aws_batch_job_queue.this[0].name, null)
}

output "batch_job_queue_arn" {
  description = "ARN da Job Queue"
  value       = try(aws_batch_job_queue.this[0].arn, null)
}

output "batch_job_definition_historical_name" {
  description = "Nome da Job Definition para carga histórica"
  value       = try(aws_batch_job_definition.historical[0].name, null)
}

output "batch_job_definition_stream_name" {
  description = "Nome da Job Definition para streaming CDC"
  value       = try(aws_batch_job_definition.stream[0].name, null)
}

output "batch_job_definition_load_reference_name" {
  description = "Nome da Job Definition para load-reference"
  value       = try(aws_batch_job_definition.load_reference[0].name, null)
}

output "batch_job_role_arn" {
  description = "ARN da IAM Role para jobs"
  value       = try(aws_iam_role.batch_job_role[0].arn, null)
}

output "batch_execution_role_arn" {
  description = "ARN da IAM Execution Role"
  value       = try(aws_iam_role.batch_execution_role[0].arn, null)
}

output "batch_log_group_name" {
  description = "Nome do CloudWatch Log Group"
  value       = try(aws_cloudwatch_log_group.batch_logs[0].name, null)
}

# ============================================================================
# ECR outputs
# ============================================================================

output "ecr_repository_url" {
  description = "URL do repositório ECR para push da imagem Docker"
  value       = aws_ecr_repository.this.repository_url
}

output "ecr_repository_name" {
  description = "Nome do repositório ECR"
  value       = aws_ecr_repository.this.name
}

# ============================================================================
# Security Group outputs
# ============================================================================

output "batch_security_group_id" {
  description = "ID do Security Group do Batch"
  value       = aws_security_group.batch.id
}

# ============================================================================
# Secrets Manager outputs
# ============================================================================

output "db_secret_name" {
  description = "Nome do segredo no Secrets Manager (credenciais do banco)"
  value       = local.secrets_enabled ? var.db_secret_name : null
}

output "db_secret_arn" {
  description = "ARN do segredo no Secrets Manager"
  value       = local.secret_arn
}

output "secretsmanager_vpc_endpoint_id" {
  description = "ID do VPC interface endpoint do Secrets Manager (existente/reutilizado)"
  value       = try(data.aws_vpc_endpoint.secretsmanager[0].id, null)
}

output "secretsmanager_vpc_endpoint_sg_id" {
  description = "ID do Security Group do VPC endpoint do Secrets Manager"
  value       = try(one(data.aws_vpc_endpoint.secretsmanager[0].security_group_ids), null)
}

output "secretsmanager_vpc_endpoint_dns" {
  description = "DNS names do VPC endpoint do Secrets Manager"
  value       = try([for d in data.aws_vpc_endpoint.secretsmanager[0].dns_entry : d.dns_name], [])
}


