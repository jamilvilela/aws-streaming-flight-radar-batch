# =============================================================================
# IAM Roles, Policies e Instance Profiles
# =============================================================================

# -------------------------------------------------------------------------------
# Service Role para Batch
# -------------------------------------------------------------------------------
resource "aws_iam_role" "batch_service_role" {
  count = var.batch_config.enabled ? 1 : 0

  name = "${var.project_name}-${var.environment}-batch-service-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "batch.amazonaws.com" }
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "batch_service_role_policy" {
  count = var.batch_config.enabled ? 1 : 0

  role       = aws_iam_role.batch_service_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBatchServiceRole"
}

# Política adicional para o Batch service role (ECS permissions)
# Necessário para criar/gerenciar o cluster ECS do compute environment
resource "aws_iam_role_policy" "batch_service_ecs" {
  count = var.batch_config.enabled ? 1 : 0

  name = "${var.project_name}-${var.environment}-batch-service-ecs-policy"
  role = aws_iam_role.batch_service_role[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:DescribeClusters",
          "ecs:CreateCluster",
          "ecs:DeleteCluster",
          "ecs:ListClusters",
          "ecs:RegisterContainerInstance",
          "ecs:DeregisterContainerInstance",
          "ecs:DiscoverPollEndpoint",
          "ecs:Poll",
          "ecs:StartTask",
          "ecs:StopTask",
          "ecs:DescribeTasks",
          "ecs:ListTasks",
          "ecs:RunTask",
          "ecs:DescribeContainerInstances",
          "ecs:ListContainerInstances"
        ]
        Resource = "*"
      }
    ]
  })
}

# -------------------------------------------------------------------------------
# Spot Fleet Role
# -------------------------------------------------------------------------------
resource "aws_iam_role" "batch_spot_fleet_role" {
  count = var.batch_config.enabled && var.batch_config.compute_spot_bid_percentage > 0 ? 1 : 0

  name = "${var.project_name}-${var.environment}-batch-spot-fleet-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "spotfleet.amazonaws.com" }
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "batch_spot_fleet_role_policy" {
  count = var.batch_config.enabled && var.batch_config.compute_spot_bid_percentage > 0 ? 1 : 0

  role       = aws_iam_role.batch_spot_fleet_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2SpotFleetTaggingRole"
}

# -------------------------------------------------------------------------------
# Instance Profile para EC2
# -------------------------------------------------------------------------------
resource "aws_iam_role" "batch_instance_role" {
  count = var.batch_config.enabled ? 1 : 0

  name = "${var.project_name}-${var.environment}-batch-instance-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
  tags = var.tags
}

resource "aws_iam_instance_profile" "batch_instance_profile" {
  count = var.batch_config.enabled ? 1 : 0

  name = "${var.project_name}-${var.environment}-batch-instance-profile"
  role = aws_iam_role.batch_instance_role[0].name
}

resource "aws_iam_role_policy_attachment" "batch_instance_ecs" {
  count = var.batch_config.enabled ? 1 : 0

  role       = aws_iam_role.batch_instance_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_role_policy_attachment" "batch_instance_efs" {
  count = var.batch_config.enabled ? 1 : 0

  role       = aws_iam_role.batch_instance_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonElasticFileSystemClientFullAccess"
}

resource "aws_iam_role_policy_attachment" "batch_instance_logs" {
  count = var.batch_config.enabled ? 1 : 0

  role       = aws_iam_role.batch_instance_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"
}

resource "aws_iam_role_policy_attachment" "batch_instance_secrets" {
  count = var.batch_config.enabled ? 1 : 0

  role       = aws_iam_role.batch_instance_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/SecretsManagerReadWrite"
}

# -------------------------------------------------------------------------------
# Job Role (permissões do job em execução)
# -------------------------------------------------------------------------------
resource "aws_iam_role" "batch_job_role" {
  count = var.batch_config.enabled ? 1 : 0

  name = "${var.project_name}-${var.environment}-batch-job-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy" "batch_job_policy" {
  count = var.batch_config.enabled ? 1 : 0

  name = "${var.project_name}-${var.environment}-batch-job-policy"
  role = aws_iam_role.batch_job_role[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Effect = "Allow"
          Action = [
            "logs:CreateLogStream",
            "logs:PutLogEvents",
            "logs:DescribeLogGroups",
            "logs:DescribeLogStreams"
          ]
          Resource = "${aws_cloudwatch_log_group.batch_logs[0].arn}:*"
        },
        {
          Effect = "Allow"
          Action = [
            "secretsmanager:GetSecretValue",
            "secretsmanager:DescribeSecret"
          ]
          Resource = "*"
        },
        {
          Effect = "Allow"
          Action = [
            "rds-db:connect"
          ]
          Resource = "*"
        }
      ],
      # Só inclui permissões EFS se o ARN foi informado
      var.batch_config.efs_file_system_arn != "" ? [
        {
          Effect = "Allow"
          Action = [
            "elasticfilesystem:ClientMount",
            "elasticfilesystem:ClientWrite",
            "elasticfilesystem:ClientRootAccess"
          ]
          Resource = var.batch_config.efs_file_system_arn
        }
      ] : []
    )
  })
}

# -------------------------------------------------------------------------------
# Execution Role (para pull da imagem ECR)
# -------------------------------------------------------------------------------
resource "aws_iam_role" "batch_execution_role" {
  count = var.batch_config.enabled ? 1 : 0

  name = "${var.project_name}-${var.environment}-batch-execution-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "batch_execution_role_policy" {
  count = var.batch_config.enabled ? 1 : 0

  role       = aws_iam_role.batch_execution_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}
