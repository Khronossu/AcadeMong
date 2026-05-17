# AcadeMong — Terraform Infrastructure

Deploys the full AWS stack: VPC → EC2 GPU (Ollama + Qdrant) → RDS Postgres → ElastiCache Redis → ECS Fargate (FastAPI) → ALB → S3/CloudFront (React) → ACM + Route 53.

## Prerequisites

- Terraform >= 1.6 (`brew install terraform` or [releases page](https://releases.hashicorp.com/terraform/))
- AWS CLI v2 configured (`aws configure` — region: `ap-southeast-1`)
- An EC2 key pair already created in your AWS account
- A Route 53 hosted zone for your domain

---

## First-time setup

### Step 1 — Create S3 backend (run once)

```bash
cd infra/bootstrap
terraform init
terraform apply
# Note the state_bucket and lock_table outputs
```

### Step 2 — Configure the backend

Edit `infra/main.tf` and fill in the `backend "s3"` block with the values from Step 1.

### Step 3 — Create your tfvars

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — fill in domain, key pair, SSH IP, Firebase JSON
```

### Step 4 — Deploy

```bash
cd infra
terraform init
terraform plan   # review what will be created
terraform apply  # takes ~10 min (RDS + ACM cert validation are slowest)
```

---

## After first deploy

### Build and push the FastAPI image

```bash
# Get ECR URL from Terraform output
ECR=$(terraform output -raw ecr_repository_url)
REGION=$(terraform output -raw aws_region 2>/dev/null || echo "ap-southeast-1")

aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR
docker build -t $ECR:latest ./backend
docker push $ECR:latest

# Force ECS to pick up the new image
aws ecs update-service \
  --cluster academong-cluster \
  --service academong-fastapi \
  --force-new-deployment \
  --region $REGION
```

### Deploy the React frontend

```bash
BUCKET=$(terraform output -raw frontend_bucket)
CF_ID=$(terraform output -raw cloudfront_domain)

cd frontend
npm run build
aws s3 sync dist/ s3://$BUCKET --delete
aws cloudfront create-invalidation --distribution-id $CF_ID --paths "/*"
```

### SSH into the GPU instance

```bash
GPU_IP=$(terraform output -raw gpu_public_ip)
ssh -i ~/.ssh/your-key.pem ubuntu@$GPU_IP

# Check model pull progress
tail -f /var/log/ollama-pull.log

# Check Qdrant container
docker ps
```

### Run DB migrations

```bash
GPU_IP=$(terraform output -raw gpu_public_ip)  # or any host with psql
RDS=$(terraform output -raw rds_endpoint)      # will prompt for password

psql -h $RDS -U admin -d tcas_advisor -f backend/db/schema.sql
```

---

## Cost estimate (ap-southeast-1, running 24/7)

| Resource | Type | $/hr | $/mo |
|---|---|---|---|
| EC2 GPU | g4dn.xlarge | ~$0.53 | ~$385 |
| RDS | db.t4g.medium | ~$0.068 | ~$49 |
| ElastiCache | cache.t4g.small | ~$0.034 | ~$25 |
| ECS Fargate | 1 vCPU / 2GB | ~$0.05 | ~$36 |
| ALB | per LCU | ~$0.016 | ~$12 |
| NAT Gateway | per GB | ~$0.045 | ~$5+ |
| **Total** | | | **~$515/mo** |

> Stop the GPU instance overnight to cut ~60% of the bill during dev:
> `aws ec2 stop-instances --instance-ids $(terraform output -raw gpu_instance_id 2>/dev/null)`

---

## Tear down

```bash
cd infra
terraform destroy   # destroys everything except the S3 state bucket (has prevent_destroy)
```
