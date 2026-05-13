# AcadeMong — AWS Deployment Guide

> Assumes you have AWS credits covering all costs.
> Architecture: EC2 GPU (Ollama) + ECS Fargate (FastAPI) + RDS (PostgreSQL) + ElastiCache (Redis) + ECS/EC2 (Qdrant) + S3/CloudFront (React) + ALB + ACM

---

## Overview

```
Internet
  │
  ├── CloudFront ──► S3 (React build)
  │
  └── ALB (HTTPS 443) ──► ECS Fargate (FastAPI :8000)
                               │
                 ┌─────────────┼─────────────────────┐
                 │             │                      │
           RDS Postgres   ElastiCache Redis    EC2 (Qdrant :6333)
                                                      │
                                              EC2 GPU (Ollama :11434)
```

All services run inside one VPC. Only ALB and CloudFront are internet-facing.

---

## Prerequisites

- AWS account with credits
- AWS CLI v2 installed and configured (`aws configure`)
- Docker + Docker Compose installed locally
- Firebase project with service account key
- Domain name (optional but recommended — ALB gives a DNS name if not)
- GitHub repo with the AcadeMong codebase

---

## Step 1 — AWS Account Bootstrap

### 1.1 Install & Configure AWS CLI

```bash
# Install AWS CLI v2 (if not already)
# https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html

aws configure
# AWS Access Key ID: <your key>
# AWS Secret Access Key: <your secret>
# Default region: ap-southeast-1   ← Singapore, lowest latency from Thailand
# Default output format: json
```

### 1.2 Create an IAM User for Deployments (if using root account now, do this)

```bash
aws iam create-user --user-name academong-deploy
aws iam attach-user-policy \
  --user-name academong-deploy \
  --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
# For production: scope down permissions. For demo: AdministratorAccess is fine.
```

---

## Step 2 — Networking (VPC)

You can use the **default VPC** for a demo. For a clean setup:

```bash
# Create VPC
VPC_ID=$(aws ec2 create-vpc --cidr-block 10.0.0.0/16 \
  --query 'Vpc.VpcId' --output text)
aws ec2 modify-vpc-attribute --vpc-id $VPC_ID --enable-dns-hostnames
aws ec2 create-tags --resources $VPC_ID --tags Key=Name,Value=academong-vpc

# Internet Gateway
IGW_ID=$(aws ec2 create-internet-gateway --query 'InternetGateway.InternetGatewayId' --output text)
aws ec2 attach-internet-gateway --internet-gateway-id $IGW_ID --vpc-id $VPC_ID

# Public subnets (2 AZs — required for ALB)
SUBNET_A=$(aws ec2 create-subnet --vpc-id $VPC_ID \
  --cidr-block 10.0.1.0/24 --availability-zone ap-southeast-1a \
  --query 'Subnet.SubnetId' --output text)
SUBNET_B=$(aws ec2 create-subnet --vpc-id $VPC_ID \
  --cidr-block 10.0.2.0/24 --availability-zone ap-southeast-1b \
  --query 'Subnet.SubnetId' --output text)

# Route table → IGW
RT_ID=$(aws ec2 create-route-table --vpc-id $VPC_ID \
  --query 'RouteTable.RouteTableId' --output text)
aws ec2 create-route --route-table-id $RT_ID \
  --destination-cidr-block 0.0.0.0/0 --gateway-id $IGW_ID
aws ec2 associate-route-table --route-table-id $RT_ID --subnet-id $SUBNET_A
aws ec2 associate-route-table --route-table-id $RT_ID --subnet-id $SUBNET_B
```

> **Shortcut for demo**: Use the default VPC's existing subnets. Run `aws ec2 describe-subnets` to find them.

---

## Step 3 — Security Groups

Create one security group per service:

```bash
# ALB — internet-facing
SG_ALB=$(aws ec2 create-security-group \
  --group-name academong-alb-sg \
  --description "ALB inbound 80/443" \
  --vpc-id $VPC_ID \
  --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id $SG_ALB \
  --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $SG_ALB \
  --protocol tcp --port 443 --cidr 0.0.0.0/0

# FastAPI (ECS) — only from ALB
SG_APP=$(aws ec2 create-security-group \
  --group-name academong-app-sg \
  --description "FastAPI ECS tasks" \
  --vpc-id $VPC_ID \
  --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id $SG_APP \
  --protocol tcp --port 8000 --source-group $SG_ALB

# RDS — only from app
SG_RDS=$(aws ec2 create-security-group \
  --group-name academong-rds-sg \
  --description "Postgres RDS" \
  --vpc-id $VPC_ID \
  --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id $SG_RDS \
  --protocol tcp --port 5432 --source-group $SG_APP

# Redis — only from app
SG_REDIS=$(aws ec2 create-security-group \
  --group-name academong-redis-sg \
  --description "ElastiCache Redis" \
  --vpc-id $VPC_ID \
  --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id $SG_REDIS \
  --protocol tcp --port 6379 --source-group $SG_APP

# GPU/Qdrant EC2 — only from app + SSH from your IP
SG_GPU=$(aws ec2 create-security-group \
  --group-name academong-gpu-sg \
  --description "GPU EC2 for Ollama + Qdrant" \
  --vpc-id $VPC_ID \
  --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id $SG_GPU \
  --protocol tcp --port 11434 --source-group $SG_APP  # Ollama
aws ec2 authorize-security-group-ingress --group-id $SG_GPU \
  --protocol tcp --port 6333 --source-group $SG_APP   # Qdrant
aws ec2 authorize-security-group-ingress --group-id $SG_GPU \
  --protocol tcp --port 22 --cidr <YOUR_IP>/32         # SSH — replace with your IP
```

---

## Step 4 — EC2 GPU Instance (Ollama + Qdrant)

This single EC2 instance runs both Ollama and Qdrant. Recommended: `g4dn.xlarge` (T4 16GB, ~$0.53/hr) or `g5.xlarge` (A10G 24GB, ~$1.01/hr).

### 4.1 Launch Instance

```bash
# Find Deep Learning AMI (CUDA pre-installed) — Ubuntu 22.04
AMI_ID=$(aws ec2 describe-images \
  --owners amazon \
  --filters "Name=name,Values=Deep Learning OSS Nvidia Driver AMI GPU PyTorch * (Ubuntu 22.04)*" \
  --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
  --output text \
  --region ap-southeast-1)

echo "Using AMI: $AMI_ID"

# Create key pair
aws ec2 create-key-pair --key-name academong-key \
  --query 'KeyMaterial' --output text > academong-key.pem
chmod 400 academong-key.pem

# Launch instance
INSTANCE_ID=$(aws ec2 run-instances \
  --image-id $AMI_ID \
  --instance-type g4dn.xlarge \
  --key-name academong-key \
  --security-group-ids $SG_GPU \
  --subnet-id $SUBNET_A \
  --associate-public-ip-address \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":100,"VolumeType":"gp3"}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=academong-gpu}]' \
  --query 'Instances[0].InstanceId' --output text)

echo "Instance: $INSTANCE_ID"

# Wait for it to be running
aws ec2 wait instance-running --instance-ids $INSTANCE_ID

# Get public IP
GPU_PUBLIC_IP=$(aws ec2 describe-instances \
  --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)

GPU_PRIVATE_IP=$(aws ec2 describe-instances \
  --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].PrivateIpAddress' \
  --output text)

echo "Public IP: $GPU_PUBLIC_IP"
echo "Private IP: $GPU_PRIVATE_IP"
```

### 4.2 Install Ollama + Pull Models

```bash
ssh -i academong-key.pem ubuntu@$GPU_PUBLIC_IP

# --- On the EC2 instance ---

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable ollama
sudo systemctl start ollama

# Pull all required models (takes 10–20 min depending on connection)
ollama pull scb10x/llama3.1-typhoon2-8b-instruct
ollama pull nomic-embed-text
ollama pull llama-guard3:1b
ollama pull gemma:8b      # fallback model

# Verify
ollama list

# Make Ollama listen on all interfaces (not just localhost)
# Edit the systemd service
sudo systemctl edit ollama --force
# Add:
# [Service]
# Environment="OLLAMA_HOST=0.0.0.0"
sudo systemctl daemon-reload
sudo systemctl restart ollama

# Test
curl http://localhost:11434/api/tags
```

### 4.3 Install Qdrant

```bash
# --- Still on the EC2 instance ---

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu
newgrp docker

# Run Qdrant
docker run -d \
  --name qdrant \
  --restart unless-stopped \
  -p 6333:6333 \
  -v /home/ubuntu/qdrant_storage:/qdrant/storage \
  qdrant/qdrant

# Verify
curl http://localhost:6333/collections
```

---

## Step 5 — RDS PostgreSQL

```bash
# Subnet group (needs 2 AZs)
aws rds create-db-subnet-group \
  --db-subnet-group-name academong-subnet-group \
  --db-subnet-group-description "AcadeMong RDS subnets" \
  --subnet-ids $SUBNET_A $SUBNET_B

# Create RDS instance (db.t3.medium — 2 vCPU, 4GB RAM)
aws rds create-db-instance \
  --db-instance-identifier academong-postgres \
  --db-instance-class db.t3.medium \
  --engine postgres \
  --engine-version 16 \
  --master-username admin \
  --master-user-password "StrongPassword123!" \
  --db-name tcas_advisor \
  --allocated-storage 20 \
  --storage-type gp3 \
  --vpc-security-group-ids $SG_RDS \
  --db-subnet-group-name academong-subnet-group \
  --no-publicly-accessible \
  --backup-retention-period 1 \
  --tags Key=Name,Value=academong-postgres

# Wait for it to be available (~5–10 min)
aws rds wait db-instance-available \
  --db-instance-identifier academong-postgres

# Get endpoint
RDS_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier academong-postgres \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)

echo "RDS endpoint: $RDS_ENDPOINT"
```

### Run Schema Migration

```bash
# From your local machine — tunnel through the GPU instance or use a bastion
# Simplest: temporarily allow your IP to SG_RDS for migration, then revoke

aws ec2 authorize-security-group-ingress --group-id $SG_RDS \
  --protocol tcp --port 5432 --cidr <YOUR_IP>/32

psql -h $RDS_ENDPOINT -U admin -d tcas_advisor \
  -f backend/db/schema.sql

# Revoke after migration
aws ec2 revoke-security-group-ingress --group-id $SG_RDS \
  --protocol tcp --port 5432 --cidr <YOUR_IP>/32
```

---

## Step 6 — ElastiCache Redis

```bash
# Subnet group
aws elasticache create-cache-subnet-group \
  --cache-subnet-group-name academong-redis-subnet \
  --cache-subnet-group-description "AcadeMong Redis" \
  --subnet-ids $SUBNET_A $SUBNET_B

# Create Redis cluster (cache.t3.micro — free-tier eligible, fine for demo)
aws elasticache create-cache-cluster \
  --cache-cluster-id academong-redis \
  --cache-node-type cache.t3.micro \
  --engine redis \
  --engine-version 7.0 \
  --num-cache-nodes 1 \
  --cache-subnet-group-name academong-redis-subnet \
  --security-group-ids $SG_REDIS \
  --tags Key=Name,Value=academong-redis

# Wait
aws elasticache wait cache-cluster-available \
  --cache-cluster-id academong-redis

# Get endpoint
REDIS_ENDPOINT=$(aws elasticache describe-cache-clusters \
  --cache-cluster-id academong-redis \
  --show-cache-node-info \
  --query 'CacheClusters[0].CacheNodes[0].Endpoint.Address' \
  --output text)

echo "Redis endpoint: $REDIS_ENDPOINT"
```

---

## Step 7 — Secrets Manager

Store all sensitive values here — never put them in environment variables directly in ECS task definitions.

```bash
# Firebase credentials (minified JSON — copy from your Firebase console)
FIREBASE_JSON=$(cat path/to/firebase-service-account.json | python3 -m json.tool --compact)

aws secretsmanager create-secret \
  --name academong/firebase-credentials \
  --secret-string "$FIREBASE_JSON" \
  --region ap-southeast-1

# DB password
aws secretsmanager create-secret \
  --name academong/db-password \
  --secret-string "StrongPassword123!" \
  --region ap-southeast-1

# All app secrets bundled (easier to manage)
aws secretsmanager create-secret \
  --name academong/app-secrets \
  --secret-string '{
    "POSTGRES_PASSWORD": "StrongPassword123!",
    "FIREBASE_CREDENTIALS_JSON": "'"$FIREBASE_JSON"'"
  }' \
  --region ap-southeast-1
```

---

## Step 8 — ECR (Container Registry)

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=ap-southeast-1

# Create repositories
aws ecr create-repository --repository-name academong/backend --region $REGION
aws ecr create-repository --repository-name academong/frontend --region $REGION

# Log in
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin \
  $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

# Build and push backend
docker build -t academong/backend ./backend
docker tag academong/backend:latest \
  $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/academong/backend:latest
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/academong/backend:latest

# Build and push frontend
docker build -t academong/frontend ./frontend
docker tag academong/frontend:latest \
  $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/academong/frontend:latest
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/academong/frontend:latest
```

---

## Step 9 — ALB + ACM Certificate

### 9.1 Request SSL Certificate

```bash
# Request cert (must own the domain — if no domain, skip TLS and use HTTP for demo)
CERT_ARN=$(aws acm request-certificate \
  --domain-name yourdomain.com \
  --validation-method DNS \
  --query 'CertificateArn' --output text \
  --region ap-southeast-1)

# Follow DNS validation — add the CNAME record to your DNS provider
# Check status until Issued:
aws acm describe-certificate --certificate-arn $CERT_ARN \
  --query 'Certificate.Status' --output text
```

> **No domain?** Skip ACM and use HTTP only on the ALB. Fine for a demo.

### 9.2 Create ALB

```bash
# Create ALB
ALB_ARN=$(aws elbv2 create-load-balancer \
  --name academong-alb \
  --subnets $SUBNET_A $SUBNET_B \
  --security-groups $SG_ALB \
  --scheme internet-facing \
  --type application \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text)

ALB_DNS=$(aws elbv2 describe-load-balancers \
  --load-balancer-arns $ALB_ARN \
  --query 'LoadBalancers[0].DNSName' --output text)

echo "ALB DNS: $ALB_DNS"

# Create target group for FastAPI
TG_ARN=$(aws elbv2 create-target-group \
  --name academong-fastapi-tg \
  --protocol HTTP \
  --port 8000 \
  --vpc-id $VPC_ID \
  --target-type ip \
  --health-check-path /health \
  --health-check-interval-seconds 30 \
  --query 'TargetGroups[0].TargetGroupArn' --output text)

# HTTP listener (redirect to HTTPS, or use directly if no cert)
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTP --port 80 \
  --default-actions Type=redirect,RedirectConfig='{Protocol=HTTPS,Port=443,StatusCode=HTTP_301}'

# HTTPS listener (skip if no cert)
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTPS --port 443 \
  --certificates CertificateArn=$CERT_ARN \
  --default-actions Type=forward,TargetGroupArn=$TG_ARN
```

---

## Step 10 — ECS Fargate (FastAPI)

### 10.1 Create ECS Cluster

```bash
aws ecs create-cluster --cluster-name academong --region $REGION
```

### 10.2 IAM Roles

```bash
# Execution role — allows ECS to pull ECR images and read Secrets Manager
cat > ecs-execution-trust.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role \
  --role-name academong-ecs-execution-role \
  --assume-role-policy-document file://ecs-execution-trust.json

aws iam attach-role-policy \
  --role-name academong-ecs-execution-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Allow reading Secrets Manager
aws iam attach-role-policy \
  --role-name academong-ecs-execution-role \
  --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite
```

### 10.3 Task Definition

Create `ecs-task-definition.json`:

```json
{
  "family": "academong-backend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::<ACCOUNT_ID>:role/academong-ecs-execution-role",
  "containerDefinitions": [
    {
      "name": "backend",
      "image": "<ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/academong/backend:latest",
      "portMappings": [
        {"containerPort": 8000, "protocol": "tcp"}
      ],
      "environment": [
        {"name": "POSTGRES_HOST", "value": "<RDS_ENDPOINT>"},
        {"name": "POSTGRES_PORT", "value": "5432"},
        {"name": "POSTGRES_DB", "value": "tcas_advisor"},
        {"name": "POSTGRES_USER", "value": "admin"},
        {"name": "REDIS_HOST", "value": "<REDIS_ENDPOINT>"},
        {"name": "REDIS_PORT", "value": "6379"},
        {"name": "QDRANT_HOST", "value": "<GPU_PRIVATE_IP>"},
        {"name": "QDRANT_PORT", "value": "6333"},
        {"name": "OLLAMA_HOST", "value": "<GPU_PRIVATE_IP>"},
        {"name": "OLLAMA_PORT", "value": "11434"},
        {"name": "PRIMARY_MODEL", "value": "scb10x/llama3.1-typhoon2-8b-instruct"},
        {"name": "EMBEDDING_MODEL", "value": "nomic-embed-text"},
        {"name": "FALLBACK_MODEL", "value": "gemma:8b"},
        {"name": "SAFETY_MODEL", "value": "llama-guard3:1b"},
        {"name": "TOP_K_RETRIEVAL", "value": "5"},
        {"name": "RERANKER_TOP_K", "value": "3"},
        {"name": "CHAT_RATE_LIMIT_PER_HOUR", "value": "60"},
        {"name": "INGESTION_RATE_LIMIT_PER_HOUR", "value": "10"}
      ],
      "secrets": [
        {
          "name": "POSTGRES_PASSWORD",
          "valueFrom": "arn:aws:secretsmanager:ap-southeast-1:<ACCOUNT_ID>:secret:academong/db-password"
        },
        {
          "name": "FIREBASE_CREDENTIALS_JSON",
          "valueFrom": "arn:aws:secretsmanager:ap-southeast-1:<ACCOUNT_ID>:secret:academong/firebase-credentials"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/academong-backend",
          "awslogs-region": "ap-southeast-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3
      }
    }
  ]
}
```

Replace `<ACCOUNT_ID>`, `<RDS_ENDPOINT>`, `<REDIS_ENDPOINT>`, `<GPU_PRIVATE_IP>` with actual values.

```bash
# Create CloudWatch log group
aws logs create-log-group \
  --log-group-name /ecs/academong-backend \
  --region $REGION

# Register task definition
aws ecs register-task-definition \
  --cli-input-json file://ecs-task-definition.json \
  --region $REGION
```

### 10.4 Create ECS Service

```bash
aws ecs create-service \
  --cluster academong \
  --service-name academong-backend \
  --task-definition academong-backend \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[$SUBNET_A,$SUBNET_B],
    securityGroups=[$SG_APP],
    assignPublicIp=ENABLED
  }" \
  --load-balancers "targetGroupArn=$TG_ARN,containerName=backend,containerPort=8000" \
  --region $REGION
```

---

## Step 11 — Frontend (S3 + CloudFront)

```bash
# Build React app
cd frontend
# Set the API URL to your ALB DNS (or domain)
echo "VITE_API_URL=https://$ALB_DNS" > .env.production
npm run build
cd ..

# Create S3 bucket
BUCKET_NAME=academong-frontend-$(date +%s)
aws s3 mb s3://$BUCKET_NAME --region $REGION

# Enable static website hosting
aws s3 website s3://$BUCKET_NAME \
  --index-document index.html \
  --error-document index.html

# Upload build
aws s3 sync frontend/dist/ s3://$BUCKET_NAME --delete

# Make public (for demo — use CloudFront OAC for production hardening)
aws s3api put-bucket-policy --bucket $BUCKET_NAME --policy '{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "PublicReadGetObject",
    "Effect": "Allow",
    "Principal": "*",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::'"$BUCKET_NAME"'/*"
  }]
}'

# Create CloudFront distribution
CF_ID=$(aws cloudfront create-distribution \
  --origin-domain-name $BUCKET_NAME.s3-website-$REGION.amazonaws.com \
  --default-root-object index.html \
  --query 'Distribution.Id' --output text)

CF_DOMAIN=$(aws cloudfront get-distribution \
  --id $CF_ID \
  --query 'Distribution.DomainName' --output text)

echo "Frontend URL: https://$CF_DOMAIN"
```

---

## Step 12 — Ingest TCAS Data & PDFs

After all services are up, run ingestion from your local machine pointing at the production endpoints.

```bash
# Set env vars pointing to production
export POSTGRES_HOST=$RDS_ENDPOINT
export POSTGRES_PASSWORD="StrongPassword123!"
export QDRANT_HOST=$GPU_PUBLIC_IP  # use public IP for one-time ingestion
export QDRANT_PORT=6333
export OLLAMA_HOST=$GPU_PUBLIC_IP
export OLLAMA_PORT=11434

# TCAS CSV ingestion
.venv\Scripts\python.exe -m backend.ingestion.tcas_csv_ingestion \
  --csv-dir data/tcas_csvs/

# PDF ingestion (mคอ.2 + announcements)
.venv\Scripts\python.exe -m backend.ingestion.pdf_parser \
  --pdf-dir data/pdfs/

# Career data
.venv\Scripts\python.exe -m backend.ingestion.career_data_loader \
  --data-dir data/career/
```

---

## Step 13 — DNS (Optional but Recommended)

If you have a domain:

```bash
# Add CNAME in your DNS provider:
# api.yourdomain.com  →  $ALB_DNS
# www.yourdomain.com  →  $CF_DOMAIN (or ALIAS record)

# If using Cloudflare:
# 1. Add CNAME: api → $ALB_DNS (proxied = orange cloud ON)
# 2. SSL/TLS mode: Full (strict)
# 3. Add CNAME: www → $CF_DOMAIN (proxied = ON)
```

Update `CORS_ORIGINS` in `backend/main.py` to include your domain.

---

## Step 14 — Verify Everything Works

```bash
# 1. Health check
curl https://$ALB_DNS/health
# Expected: {"status": "ok"}

# 2. Auth test
# Open frontend → sign in with Google → check browser network tab for 200 on /api/auth/login

# 3. Chat test
# Send a TCAS query through the UI
# Check ECS logs:
aws logs tail /ecs/academong-backend --follow --region $REGION

# 4. Check GPU instance is responding
curl http://$GPU_PRIVATE_IP:11434/api/tags

# 5. Check Qdrant
curl http://$GPU_PRIVATE_IP:6333/collections
```

---

## Step 15 — Update Frontend API URL

If your frontend was built with the wrong API URL:

```bash
cd frontend
echo "VITE_API_URL=https://api.yourdomain.com" > .env.production
npm run build
aws s3 sync dist/ s3://$BUCKET_NAME --delete
aws cloudfront create-invalidation --distribution-id $CF_ID --paths "/*"
```

---

## Redeploy After Code Changes

```bash
# 1. Build + push new image
docker build -t academong/backend ./backend
docker tag academong/backend:latest \
  $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/academong/backend:latest
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/academong/backend:latest

# 2. Force ECS to pull new image
aws ecs update-service \
  --cluster academong \
  --service academong-backend \
  --force-new-deployment \
  --region $REGION

# 3. Watch rollout
aws ecs wait services-stable \
  --cluster academong \
  --services academong-backend \
  --region $REGION
```

---

## Cost Estimate (Demo — 2 days with credits)

| Service | Instance | 2-day cost |
|---|---|---|
| EC2 GPU (Ollama + Qdrant) | g4dn.xlarge | ~$25 |
| EC2 GPU (Ollama + Qdrant) | g5.xlarge | ~$48 |
| ECS Fargate (FastAPI) | 1 vCPU / 2GB | ~$2 |
| RDS PostgreSQL | db.t3.medium | ~$3 |
| ElastiCache Redis | cache.t3.micro | ~$0.30 |
| ALB | — | ~$0.50 |
| S3 + CloudFront | — | ~$0.10 |
| **Total (g4dn)** | | **~$31** |
| **Total (g5)** | | **~$54** |

With AWS credits: **$0 out of pocket**.

> **Tip**: Stop the EC2 GPU instance when not demoing — you only pay for running time. The ECS Fargate tasks, RDS, and ElastiCache can stay running (very cheap). Restart the GPU instance 5 min before the demo to let Ollama load models into VRAM.

---

## Teardown (After Demo)

```bash
# Stop GPU instance (keeps EBS, stops billing for compute)
aws ec2 stop-instances --instance-ids $INSTANCE_ID

# Or fully terminate everything:
aws ecs update-service --cluster academong --service academong-backend --desired-count 0
aws ecs delete-service --cluster academong --service academong-backend
aws rds delete-db-instance --db-instance-identifier academong-postgres --skip-final-snapshot
aws elasticache delete-cache-cluster --cache-cluster-id academong-redis
aws ec2 terminate-instances --instance-ids $INSTANCE_ID
aws s3 rb s3://$BUCKET_NAME --force
```

---

## Quick Reference — All Values to Note Down

After completing the steps above, keep these handy:

```
VPC_ID            = vpc-xxxxxxxxxxxxxxxxx
SUBNET_A          = subnet-xxxxxxxxxxxxxxxxx
SUBNET_B          = subnet-xxxxxxxxxxxxxxxxx
SG_ALB            = sg-xxxxxxxxxxxxxxxxx
SG_APP            = sg-xxxxxxxxxxxxxxxxx
SG_RDS            = sg-xxxxxxxxxxxxxxxxx
SG_REDIS          = sg-xxxxxxxxxxxxxxxxx
SG_GPU            = sg-xxxxxxxxxxxxxxxxx

GPU_INSTANCE_ID   = i-xxxxxxxxxxxxxxxxx
GPU_PUBLIC_IP     = xx.xx.xx.xx
GPU_PRIVATE_IP    = 10.0.x.x

RDS_ENDPOINT      = academong-postgres.xxxxxxxx.ap-southeast-1.rds.amazonaws.com
REDIS_ENDPOINT    = academong-redis.xxxxxx.0001.apse1.cache.amazonaws.com

ALB_ARN           = arn:aws:elasticloadbalancing:...
ALB_DNS           = academong-alb-xxxxxxxx.ap-southeast-1.elb.amazonaws.com
TG_ARN            = arn:aws:elasticloadbalancing:...

BUCKET_NAME       = academong-frontend-xxxxxxxxxx
CF_ID             = XXXXXXXXXXXXXX
CF_DOMAIN         = xxxxxxxxxxxx.cloudfront.net

ECR_BACKEND       = <ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/academong/backend
ECR_FRONTEND      = <ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/academong/frontend
```
