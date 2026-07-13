# =============================================================================
# CloudWatch Log Group - Logs dos jobs Batch
# =============================================================================

resource "aws_cloudwatch_log_group" "batch_logs" {
  count = var.batch_config.enabled ? 1 : 0

  name              = "/aws/batch/${var.project_name}-${var.environment}"
  retention_in_days = var.batch_config.log_retention_days
  tags              = var.tags
}
