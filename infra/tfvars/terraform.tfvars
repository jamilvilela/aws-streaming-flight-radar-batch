aws_region   = "us-east-1"
project_name = "flight-radar-stream"
environment  = "production"
vpc_name     = "default-vpc"

tags = {
  Environment = "production"
  Project     = "flight-radar-stream"
  ManagedBy   = "terraform"
}

# ═════════════════════════════════════════════════════════════════════════════
# Database Connection (Aurora PostgreSQL - gerenciado em repo separado)
# ═════════════════════════════════════════════════════════════════════════════
# Preenchido automaticamente via .env → TF_VAR_db_host, TF_VAR_db_port, etc.
# Valores abaixo são placeholders; sobrescritos pelo setup-env.sh

db_host     = ""
db_port     = "5432"
db_name     = "flightradar"
db_user     = ""
db_password = ""

# ═════════════════════════════════════════════════════════════════════════════
# AWS Batch Configuration
# ═════════════════════════════════════════════════════════════════════════════
batch_config = {
  enabled = true
  ecr_image_tag = "latest"
  efs_file_system_id  = ""
  efs_file_system_arn = ""

  compute_instance_types      = ["m6i.large", "c6a.large", "m5.large"]
  compute_min_vcpus           = 0
  compute_max_vcpus           = 16
  compute_desired_vcpus       = 0
  compute_spot_bid_percentage = 100

  job_historical_vcpus  = 2
  job_historical_memory = 4096
  job_stream_vcpus      = 1
  job_stream_memory     = 2048
  job_load_ref_vcpus    = 1
  job_load_ref_memory   = 1024

  log_retention_days = 30
}

