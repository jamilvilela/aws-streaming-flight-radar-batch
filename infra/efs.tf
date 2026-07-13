# =============================================================================
# EFS Access Point (opcional, para armazenamento compartilhado)
# =============================================================================

resource "aws_efs_access_point" "batch" {
  count = var.batch_config.enabled && var.batch_config.efs_file_system_id != "" ? 1 : 0

  file_system_id = var.batch_config.efs_file_system_id
  posix_user {
    gid = 1000
    uid = 1000
  }
  root_directory {
    path = "/batch"
    creation_info {
      owner_gid   = 1000
      owner_uid   = 1000
      permissions = "0755"
    }
  }
  tags = var.tags
}
