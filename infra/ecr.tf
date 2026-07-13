# =============================================================================
# ECR Repository - armazenamento da imagem Docker do Batch
# =============================================================================

resource "aws_ecr_repository" "this" {
  name         = "${var.project_name}-${var.environment}"
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Expire old images"
      selection = {
        tagStatus     = "any"
        countType     = "imageCountMoreThan"
        countNumber   = 10
      }
      action = { type = "expire" }
    }]
  })
}
