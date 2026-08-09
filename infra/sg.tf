# =============================================================================
# Security Group - AWS Batch Compute Environment
# =============================================================================

resource "aws_security_group" "batch" {
  name        = "${var.project_name}-${var.environment}-batch-sg"
  description = "Security group for AWS Batch compute environment"
  vpc_id      = local.effective_vpc_id

  # Sem ingress 5432 aberto para 0.0.0.0/0: o acesso ao Aurora é controlado
  # pelo SG do banco (repo separado), que libera apenas o CIDR da VPC ou
  # referências SG→SG. O Batch só precisa de egress para alcançar o banco.

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
