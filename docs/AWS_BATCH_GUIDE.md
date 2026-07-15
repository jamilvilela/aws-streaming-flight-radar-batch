# AWS Batch - Flight Radar Data Loader

Guia de deploy e execução de jobs de carga de dados via AWS Batch.

---

## 1. Pré-requisitos

### 1.1 Criar repositório ECR
```bash
aws ecr create-repository \
  --repository-name flight-radar-stream/batch \
  --region us-east-1
```

### 1.2 Build e push da imagem Docker
```bash
# Login no ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com

# Build
docker build -f docker/Dockerfile.batch -t flight-radar-stream/batch:latest .

# Tag
docker tag flight-radar-stream/batch:latest \
  123456789012.dkr.ecr.us-east-1.amazonaws.com/flight-radar-stream/batch:latest

# Push
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/flight-radar-stream/batch:latest
```

### 1.3 Criar EFS File System (para armazenamento compartilhado)
```bash
aws efs create-file-system \
  --creation-token flight-radar-batch \
  --performance-mode generalPurpose \
  --throughput-mode bursting \
  --encrypted \
  --tags Key=Name,Value=flight-radar-batch \
  --region us-east-1

# Criar mount targets nas subnets privadas
aws efs create-mount-target \
  --file-system-id fs-xxxxxxxxx \
  --subnet-id subnet-xxxxx \
  --security-groups sg-xxxxx \
  --region us-east-1
```

---

## 2. Deploy via Terraform

### 2.1 Configurar terraform.tfvars
```hcl
batch_config = {
  enabled = true
  ecr_image_tag = "latest"
  efs_file_system_id = "fs-xxxxxxxxx"
  efs_file_system_arn = "arn:aws:elasticfilesystem:us-east-1:123456789012:file-system/fs-xxxxxxxxx"
  
  compute_instance_types = ["t3.medium", "t3.large", "t3.xlarge"]
  compute_min_vcpus = 0
  compute_max_vcpus = 16
  compute_desired_vcpus = 0
  compute_spot_bid_percentage = 100
  
  job_historical_vcpus = 2
  job_historical_memory = 4096
  job_stream_vcpus = 1
  job_stream_memory = 2048
  job_load_ref_vcpus = 1
  job_load_ref_memory = 1024
  
  log_retention_days = 30
}
```

### 2.2 Deploy
```bash
cd infra
terraform init
terraform plan -var-file=tfvars/terraform.tfvars
terraform apply -var-file=tfvars/terraform.tfvars
```

---

## 3. Executar Jobs via AWS CLI

### 3.1 Carga Histórica (7 anos, ~10GB)
```bash
aws batch submit-job \
  --job-name flight-radar-historical-$(date +%Y%m%d-%H%M%S) \
  --job-queue flight-radar-stream-production-job-queue \
  --job-definition flight-radar-stream-production-historical \
  --container-overrides '{
    "environment": [
      {"name": "JOB_TYPE", "value": "historical"},
      {"name": "YEARS", "value": "7"},
      {"name": "TARGET_SIZE_GB", "value": "10"}
    ]
  }' \
  --region us-east-1
```

### 3.2 Carga Histórica para anos específicos
```bash
aws batch submit-job \
  --job-name flight-radar-historical-2020-2022 \
  --job-queue flight-radar-stream-production-job-queue \
  --job-definition flight-radar-stream-production-historical \
  --container-overrides '{
    "environment": [
      {"name": "JOB_TYPE", "value": "historical"},
      {"name": "YEARS_LIST", "value": "[2020,2021,2022]"},
      {"name": "TARGET_SIZE_GB", "value": "3"}
    ]
  }' \
  --region us-east-1
```

### 3.3 Streaming CDC (contínuo, 150MB/5min)
```bash
aws batch submit-job \
  --job-name flight-radar-stream-cdc \
  --job-queue flight-radar-stream-production-job-queue \
  --job-definition flight-radar-stream-production-stream \
  --container-overrides '{
    "environment": [
      {"name": "JOB_TYPE", "value": "stream"},
      {"name": "INTERVAL", "value": "1"},
      {"name": "TARGET_MB_5MIN", "value": "150"},
      {"name": "DURATION", "value": "86400"}
    ]
  }' \
  --region us-east-1
```

### 3.4 Carga de Referência (tabelas de dimensão)
```bash
aws batch submit-job \
  --job-name flight-radar-load-ref \
  --job-queue flight-radar-stream-production-job-queue \
  --job-definition flight-radar-stream-production-load-reference \
  --container-overrides '{
    "environment": [
      {"name": "JOB_TYPE", "value": "load-reference"},
      {"name": "TABLES", "value": "countries,aircraft_types,airports,airlines,routes"}
    ]
  }' \
  --region us-east-1
```

### 3.5 Carga Completa (referência + histórico + stream)
```bash
aws batch submit-job \
  --job-name flight-radar-full-load \
  --job-queue flight-radar-stream-production-job-queue \
  --job-definition flight-radar-stream-production-historical \
  --container-overrides '{
    "environment": [
      {"name": "JOB_TYPE", "value": "all"},
      {"name": "YEARS", "value": "5"},
      {"name": "TARGET_SIZE_GB", "value": "5"}
    ]
  }' \
  --region us-east-1
```

---

## 4. Monitoramento

### 4.1 Listar jobs
```bash
aws batch list-jobs \
  --job-queue flight-radar-stream-production-job-queue \
  --job-status RUNNING \
  --region us-east-1
```

### 4.2 Descrever job
```bash
aws batch describe-jobs \
  --jobs <job-id> \
  --region us-east-1
```

### 4.3 Logs no CloudWatch
```bash
aws logs tail /aws/batch/flight-radar-stream-production --follow --region us-east-1
```

### 4.4 Cancelar job
```bash
aws batch cancel-job \
  --job-id <job-id> \
  --reason "Cancelado pelo usuário" \
  --region us-east-1
```

---

## 5. Pausar/Desativar Compute Environment

### 5.1 Pausar (para economizar custos)
```bash
aws batch update-compute-environment \
  --compute-environment flight-radar-stream-production-batch-env \
  --state DISABLED \
  --region us-east-1
```

### 5.2 Reativar
```bash
aws batch update-compute-environment \
  --compute-environment flight-radar-stream-production-batch-env \
  --state ENABLED \
  --region us-east-1
```

---

## 6. Custos Estimados

| Componente | Configuração | Custo/hora (aprox) |
|------------|--------------|-------------------|
| **Compute (Spot)** | t3.medium (2 vCPU, 4GB) | $0.015/hora |
| **Compute (Spot)** | t3.large (2 vCPU, 8GB) | $0.03/hora |
| **Compute (Spot)** | t3.xlarge (4 vCPU, 16GB) | $0.06/hora |
| **EFS Storage** | 10 GB | $0.30/mês |
| **CloudWatch Logs** | 1 GB ingested | $0.50/mês |
| **Data Transfer** | Dentro da mesma AZ | Grátis |

**Exemplo: Carga histórica 10GB (~4 horas com 4x t3.large)**
- 4 instâncias × 4 horas × $0.03 = **$0.48**

**Streaming CDC contínuo (1x t3.medium 24/7)**
- 1 instância × 720 horas × $0.015 = **$10.80/mês**

---

## 7. Troubleshooting

### Job fica em RUNNABLE
- Verificar se compute environment tem capacidade (max_vcpus)
- Verificar se spot instances estão disponíveis na AZ
- Aumentar `compute_spot_bid_percentage` para 100%

### Job falha com OOM
- Aumentar `memory` na job definition
- Reduzir `vcpus` para ter mais memória por vCPU

### Erro de conexão com banco
- Verificar security group do banco Aurora (repo separado) permite tráfego do SG do Batch
- Verificar se subnets do Batch têm rota para o banco Aurora

### Imagem não encontrada
- Verificar se ECR repository policy permite pull do Batch
- Verificar se execution role tem permissão `ecr:GetDownloadUrlForLayer`, `ecr:BatchGetImage`

---

## 8. Limpeza

```bash
# Terminar jobs rodando
aws batch terminate-job --job-id <id> --reason "Cleanup"

# Deletar job queue
aws batch delete-job-queue --job-queue flight-radar-stream-production-job-queue

# Deletar compute environment
aws batch delete-compute-environment --compute-environment flight-radar-stream-production-batch-env

# Deletar job definitions
aws batch deregister-job-definition --job-definition flight-radar-stream-production-historical
aws batch deregister-job-definition --job-definition flight-radar-stream-production-stream
aws batch deregister-job-definition --job-definition flight-radar-stream-production-load-reference
```