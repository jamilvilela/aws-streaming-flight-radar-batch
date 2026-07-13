# =============================================================================
# Core Variables
# =============================================================================

variable "project_name" {
  description = "Nome do projeto"
  type        = string
}

variable "aws_region" {
  description = "Região AWS"
  type        = string
}

variable "environment" {
  description = "Ambiente (dev, staging, production)"
  type        = string
}

variable "tags" {
  description = "Tags comuns para todos os recursos"
  type        = map(string)
  default     = {}
}

# =============================================================================
# VPC Configuration
# =============================================================================

variable "vpc_id" {
  description = "ID explícito da VPC (se null, descobre pelo nome)"
  type        = string
  default     = null
}

variable "vpc_name" {
  description = "Name tag da VPC para descoberta automática"
  type        = string
  default     = null
}

variable "subnet_ids" {
  description = "Lista explícita de subnet IDs (se null, descobre automático)"
  type        = list(string)
  default     = null
}

# =============================================================================
# Database Connection (Aurora PostgreSQL - gerenciado em repo separado)
# =============================================================================

variable "db_host" {
  description = "Endpoint do Aurora PostgreSQL"
  type        = string
}

variable "db_port" {
  description = "Porta do banco"
  type        = string
  default     = "5432"
}

variable "db_name" {
  description = "Nome do banco de dados"
  type        = string
  default     = "flightradar"
}

variable "db_user" {
  description = "Usuário do banco"
  type        = string
}

variable "db_password" {
  description = "Senha do banco"
  type        = string
  sensitive   = true
}

# =============================================================================
# AWS Batch Configuration
# =============================================================================

variable "batch_config" {
  description = "Configuration for AWS Batch compute environment and job definitions"
  type = object({
    enabled                     = optional(bool, false)
    ecr_image_tag               = optional(string, "latest")
    efs_file_system_id          = optional(string, "")
    efs_file_system_arn         = optional(string, "")
    compute_instance_types      = optional(list(string), ["m6i.large", "c6a.large", "m5.large"])
    compute_min_vcpus           = optional(number, 0)
    compute_max_vcpus           = optional(number, 16)
    compute_desired_vcpus       = optional(number, 0)
    compute_spot_bid_percentage = optional(number, 100)

    job_historical_vcpus  = optional(number, 2)
    job_historical_memory = optional(number, 4096)
    job_stream_vcpus      = optional(number, 1)
    job_stream_memory     = optional(number, 2048)
    job_load_ref_vcpus    = optional(number, 1)
    job_load_ref_memory   = optional(number, 1024)

    log_retention_days = optional(number, 30)
  })
  default = {}
}
