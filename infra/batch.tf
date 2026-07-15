# =============================================================================
# AWS Batch - Compute Environment, Queue e Job Definitions
# =============================================================================

variable "db_secret_arn" {
  description = "ARN do segredo no Secrets Manager com credenciais do banco (opcional)"
  type        = string
  default     = ""
}

# -------------------------------------------------------------------------------
# Compute Environment (Ambiente de computação gerenciado)
# -------------------------------------------------------------------------------
resource "aws_batch_compute_environment" "this" {
  count = var.batch_config.enabled ? 1 : 0

  name         = "${var.project_name}-${var.environment}-batch-env"
  type         = "MANAGED"
  state        = "ENABLED"
  service_role = aws_iam_role.batch_service_role[0].arn

  depends_on = [
    aws_iam_role_policy_attachment.batch_service_role_policy,
    aws_iam_role_policy.batch_service_ecs,
    time_sleep.batch_service_role_propagation
  ]

  compute_resources {
    type                = "EC2"
    instance_role       = aws_iam_instance_profile.batch_instance_profile[0].arn
    instance_type       = toset(var.batch_config.compute_instance_types)
    min_vcpus           = var.batch_config.compute_min_vcpus
    max_vcpus           = var.batch_config.compute_max_vcpus
    desired_vcpus       = var.batch_config.compute_desired_vcpus
    subnets             = local.effective_subnet_ids
    security_group_ids  = [aws_security_group.batch.id]
    allocation_strategy = "BEST_FIT_PROGRESSIVE"
    bid_percentage      = var.batch_config.compute_spot_bid_percentage
    spot_iam_fleet_role = var.batch_config.compute_spot_bid_percentage > 0 ? aws_iam_role.batch_spot_fleet_role[0].arn : null
    tags                = merge(var.tags, { Name = "${var.project_name}-${var.environment}-batch-compute" })
  }
}

# -------------------------------------------------------------------------------
# Job Queue (Fila de jobs)
# -------------------------------------------------------------------------------
resource "aws_batch_job_queue" "this" {
  count = var.batch_config.enabled ? 1 : 0

  name     = "${var.project_name}-${var.environment}-job-queue"
  state    = "ENABLED"
  priority = 1
  compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.this[0].arn
  }
  tags = var.tags
}

# -------------------------------------------------------------------------------
# Job Definition - Historical Generator (Carga histórica)
# -------------------------------------------------------------------------------
resource "aws_batch_job_definition" "historical" {
  count = var.batch_config.enabled ? 1 : 0

  name                  = "${var.project_name}-${var.environment}-historical"
  type                  = "container"
  platform_capabilities = ["EC2"]
  container_properties = jsonencode({
    image            = "${aws_ecr_repository.this.repository_url}:${var.batch_config.ecr_image_tag}"
    vcpus            = var.batch_config.job_historical_vcpus
    memory           = var.batch_config.job_historical_memory
    command          = ["python", "seed_data/cli.py", "historical"]
    jobRoleArn       = aws_iam_role.batch_job_role[0].arn
    executionRoleArn = aws_iam_role.batch_execution_role[0].arn
    environment = [
      { name = "DB_HOST", value = var.db_host },
      { name = "DB_PORT", value = var.db_port },
      { name = "DB_NAME", value = var.db_name },
      { name = "DB_USER", value = var.db_user },
      { name = "DB_PASSWORD", value = var.db_password },
      { name = "AWS_DEFAULT_REGION", value = var.aws_region },
      { name = "PYTHONUNBUFFERED", value = "1" }
    ]
    mountPoints = var.batch_config.efs_file_system_id != "" ? [
      { sourceVolume = "efs", containerPath = "/efs", readOnly = false }
    ] : []
    volumes = var.batch_config.efs_file_system_id != "" ? [
      { name = "efs", efsVolumeConfiguration = { fileSystemId = var.batch_config.efs_file_system_id, rootDirectory = "/batch", transitEncryption = "ENABLED" } }
    ] : []
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.batch_logs[0].name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "historical"
      }
    }
  })
  tags = var.tags
}

# -------------------------------------------------------------------------------
# Job Definition - Stream Generator (CDC streaming)
# -------------------------------------------------------------------------------
resource "aws_batch_job_definition" "stream" {
  count = var.batch_config.enabled ? 1 : 0

  name                  = "${var.project_name}-${var.environment}-stream"
  type                  = "container"
  platform_capabilities = ["EC2"]
  container_properties = jsonencode({
    image            = "${aws_ecr_repository.this.repository_url}:${var.batch_config.ecr_image_tag}"
    vcpus            = var.batch_config.job_stream_vcpus
    memory           = var.batch_config.job_stream_memory
    command          = ["python", "seed_data/cli.py", "stream"]
    jobRoleArn       = aws_iam_role.batch_job_role[0].arn
    executionRoleArn = aws_iam_role.batch_execution_role[0].arn
    environment = [
      { name = "DB_HOST", value = var.db_host },
      { name = "DB_PORT", value = var.db_port },
      { name = "DB_NAME", value = var.db_name },
      { name = "DB_USER", value = var.db_user },
      { name = "DB_PASSWORD", value = var.db_password },
      { name = "AWS_DEFAULT_REGION", value = var.aws_region },
      { name = "PYTHONUNBUFFERED", value = "1" }
    ]
    mountPoints = var.batch_config.efs_file_system_id != "" ? [
      { sourceVolume = "efs", containerPath = "/efs", readOnly = false }
    ] : []
    volumes = var.batch_config.efs_file_system_id != "" ? [
      { name = "efs", efsVolumeConfiguration = { fileSystemId = var.batch_config.efs_file_system_id, rootDirectory = "/batch", transitEncryption = "ENABLED" } }
    ] : []
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.batch_logs[0].name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "stream"
      }
    }
  })
  tags = var.tags
}

# -------------------------------------------------------------------------------
# Job Definition - Load Reference (Dados de referência)
# -------------------------------------------------------------------------------
resource "aws_batch_job_definition" "load_reference" {
  count = var.batch_config.enabled ? 1 : 0

  name                  = "${var.project_name}-${var.environment}-load-reference"
  type                  = "container"
  platform_capabilities = ["EC2"]
  container_properties = jsonencode({
    image            = "${aws_ecr_repository.this.repository_url}:${var.batch_config.ecr_image_tag}"
    vcpus            = var.batch_config.job_load_ref_vcpus
    memory           = var.batch_config.job_load_ref_memory
    command          = ["python", "seed_data/cli.py", "load-reference"]
    jobRoleArn       = aws_iam_role.batch_job_role[0].arn
    executionRoleArn = aws_iam_role.batch_execution_role[0].arn
    environment = [
      { name = "DB_HOST", value = var.db_host },
      { name = "DB_PORT", value = var.db_port },
      { name = "DB_NAME", value = var.db_name },
      { name = "DB_USER", value = var.db_user },
      { name = "DB_PASSWORD", value = var.db_password },
      { name = "AWS_DEFAULT_REGION", value = var.aws_region },
      { name = "PYTHONUNBUFFERED", value = "1" }
    ]
    mountPoints = var.batch_config.efs_file_system_id != "" ? [
      { sourceVolume = "efs", containerPath = "/efs", readOnly = false }
    ] : []
    volumes = var.batch_config.efs_file_system_id != "" ? [
      { name = "efs", efsVolumeConfiguration = { fileSystemId = var.batch_config.efs_file_system_id, rootDirectory = "/batch", transitEncryption = "ENABLED" } }
    ] : []
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.batch_logs[0].name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "load-reference"
      }
    }
  })
  tags = var.tags
}
