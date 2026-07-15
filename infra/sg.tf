# =============================================================================
# Security Group - AWS Batch Compute Environment
# =============================================================================

resource "aws_security_group" "batch" {
  name        = "${var.project_name}-${var.environment}-batch-sg"
  description = "Security group for AWS Batch compute environment"
  vpc_id      = local.effective_vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "PostgreSQL access"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-batch-sg"
  })
}
