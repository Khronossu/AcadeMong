# AcadeMong — Full Deployment Guide

> **Where do commands run?**
> Every command runs on **your local machine in PowerShell** unless a step says "inside SSH session".
> No AWS web console needed — everything is CLI-driven.
>
> **Domain:** `purinboonpetch.com` on Cloudflare. Same idea as your Minecraft server — you just add DNS records in Cloudflare dashboard. No Route 53.

---

## Part 0 — Install tools (one-time)

Open PowerShell and verify:

```powershell
aws --version        # need: aws-cli/2.x.x
terraform --version  # need: Terraform v1.6+
docker --version     # need: Docker 24+
node --version       # need: v18+
```

Install anything missing:
- **AWS CLI v2**: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
- **Terraform**: https://developer.hashicorp.com/terraform/install → Windows AMD64 → unzip → add to PATH
- **Docker Desktop**: https://www.docker.com/products/docker-desktop/

---

## Part 1 — Connect AWS CLI to your account

```powershell
aws configure
```

Four prompts:
```
AWS Access Key ID:     → from AWS Console → IAM → Users → your user → Security credentials → Create access key
AWS Secret Access Key: → same page
Default region:        ap-southeast-1
Default output format: json
```

Verify it works:
```powershell
aws sts get-caller-identity
# Prints your account ID — if you see an error, your key is wrong
```

---

## Part 2 — Create an EC2 key pair

This is how you SSH into the GPU instance later — same as any SSH key.

```powershell
# Create the key pair and save the .pem file
aws ec2 create-key-pair `
  --key-name academong-key `
  --query 'KeyMaterial' `
  --output text `
  --region ap-southeast-1 | Out-File -Encoding ASCII "$env:USERPROFILE\.ssh\academong-key.pem"
```

---

## Part 3 — Bootstrap the Terraform state bucket (run once)

Terraform needs an S3 bucket to store its state file. Run this once before anything else.

```powershell
cd C:\dev\AcadeMong\infra\bootstrap
terraform init
terraform apply
# Type "yes" when prompted
```

Output will look like:
```
state_bucket = "academong-tf-state-a1b2c3d4"
lock_table   = "academong-tf-lock"
```

**Open `C:\dev\AcadeMong\infra\main.tf`** and fill in those two values:

```hcl
backend "s3" {
  bucket         = "academong-tf-state-a1b2c3d4"   ← paste here
  key            = "academong/terraform.tfstate"
  region         = "ap-southeast-1"
  dynamodb_table = "academong-tf-lock"               ← paste here
  encrypt        = true
}
```

---

## Part 4 — Fill in your deployment variables

```powershell
cd C:\dev\AcadeMong\infra
Copy-Item terraform.tfvars.example terraform.tfvars
```

Open `terraform.tfvars` and fill in:

```hcl
domain_name      = "purinboonpetch.com"
app_subdomain    = "app"                     # → app.purinboonpetch.com for the API
gpu_key_name     = "academong-key"           # the key pair you created in Part 2
ssh_allowed_cidr = "YOUR_IP/32"             # run: (Invoke-WebRequest ifconfig.me/ip -UseBasicParsing).Content.Trim()
gpu_instance_type = "g4dn.xlarge"           # T4 16GB ~$0.53/hr, fits all models

# Firebase — copy the FIREBASE_CREDENTIALS_JSON value from your .env file (the whole JSON string)
firebase_credentials_json = "{\"type\":\"service_account\",...}"
```

---

## Part 5 — Deploy the infrastructure

```powershell
cd C:\dev\AcadeMong\infra
terraform init
terraform plan    # preview all ~35 resources — nothing is created yet
```

Read the plan output, then:

```powershell
terraform apply
# Type "yes"
```

**Terraform will pause partway through** — this is expected and intentional. It's waiting for ACM certificates to be validated via DNS. The terminal will show something like:

```
aws_acm_certificate_validation.alb: Still creating... [1m0s elapsed]
aws_acm_certificate_validation.alb: Still creating... [1m30s elapsed]
```

**Do not cancel.** While it's waiting, do Part 6 below.

---

## Part 6 — Add DNS validation records in Cloudflare (while Terraform is waiting)

Open a **second PowerShell window** (keep the first one running terraform apply).

Get the CNAME values Terraform needs you to add:

```powershell
cd C:\dev\AcadeMong\infra
terraform output cloudflare_step1_acm_validation
```

This prints two sets of CNAME records — one for the ALB cert, one for the CloudFront cert. They look like:

```
alb_cert = {
  "app.purinboonpetch.com" = {
    name  = "_abc123def456"
    type  = "CNAME"
    value = "_xyz789.acm-validations.aws"
  }
}
cloudfront_cert = {
  "purinboonpetch.com" = {
    name  = "_ghi789jkl012"
    type  = "CNAME"
    value = "_mno345.acm-validations.aws"
  }
}
```

**Now go to Cloudflare dashboard → purinboonpetch.com → DNS → Records → Add record:**

| Type | Name | Content (Target) | Proxy |
|---|---|---|---|
| CNAME | `_abc123def456` | `_xyz789.acm-validations.aws` | **OFF** (grey cloud) |
| CNAME | `_ghi789jkl012` | `_mno345.acm-validations.aws` | **OFF** (grey cloud) |

> **Proxy must be OFF** (grey cloud). The orange cloud would intercept the traffic — these are validation records, they need to pass through directly. Same rule as your Minecraft server A record.

After adding both CNAMEs, go back to the first PowerShell window and watch Terraform continue. Certificate validation takes **5–15 minutes**. The full apply takes about **10–15 minutes total** after that (RDS is the slowest).

When apply finishes you'll see all the outputs:
```
app_url            = "https://app.purinboonpetch.com"
frontend_url       = "https://purinboonpetch.com"
ecr_repository_url = "123456789.dkr.ecr.ap-southeast-1.amazonaws.com/academong/fastapi"
gpu_public_ip      = "13.229.xx.xx"
frontend_bucket    = "academong-frontend-staging"
```

---

## Part 7 — Add the live DNS records in Cloudflare

Now that AWS resources exist, point your domain at them.

Get the values:
```powershell
cd C:\dev\AcadeMong\infra
terraform output cloudflare_step2_dns_records
```

Output:
```
api = {
  comment = "app.purinboonpetch.com → ALB (FastAPI)"
  name    = "app"
  type    = "CNAME"
  value   = "academong-alb-xxxx.ap-southeast-1.elb.amazonaws.com"
}
frontend = {
  comment = "purinboonpetch.com → CloudFront (React app)"
  name    = "@"
  type    = "CNAME"
  value   = "d1234abcde.cloudfront.net"
}
```

**Go back to Cloudflare → DNS → Add record:**

| Type | Name | Content (Target) | Proxy |
|---|---|---|---|
| CNAME | `app` | `academong-alb-xxxx.ap-southeast-1.elb.amazonaws.com` | **OFF** (grey cloud) |
| CNAME | `@` | `d1234abcde.cloudfront.net` | **OFF** (grey cloud) |

> Both must be **grey cloud (DNS only)**. ALB and CloudFront handle SSL themselves — if Cloudflare proxies on top, you get double-SSL errors.

---

## Part 8 — Wait for GPU models to download

The GPU instance downloads all 4 AI models in the background after boot. SSH in to check:

```powershell
$GPU_IP = terraform -chdir=C:\dev\AcadeMong\infra output -raw gpu_public_ip
ssh -i "$env:USERPROFILE\.ssh\academong-key.pem" ubuntu@$GPU_IP
```

You are now inside the GPU instance. Run:

```bash
# Watch model downloads — takes ~10–15 min total
tail -f /var/log/ollama-pull.log

# All 4 models done when you see these lines:
# pulled scb10x/llama3.1-typhoon2-8b-instruct
# pulled nomic-embed-text
# pulled gemma:8b
# pulled llama-guard3:1b

# Check Ollama is ready
curl http://localhost:11434/api/tags

# Check Qdrant container is running
docker ps
# Should show: qdrant/qdrant  Up X minutes

# Exit back to your local machine
exit
```

---

## Part 9 — Deploy the FastAPI backend

Back on your local machine:

```powershell
cd C:\dev\AcadeMong

# Get the ECR repo URL
$ECR = terraform -chdir=infra output -raw ecr_repository_url

# Log Docker into AWS's container registry
aws ecr get-login-password --region ap-southeast-1 | `
  docker login --username AWS --password-stdin $ECR

# Build the FastAPI image
docker build -t "${ECR}:latest" ./backend

# Push it
docker push "${ECR}:latest"

# Tell ECS to deploy it
aws ecs update-service `
  --cluster academong-cluster `
  --service academong-fastapi `
  --force-new-deployment `
  --region ap-southeast-1
```

Watch the deployment roll out:
```powershell
aws ecs describe-services `
  --cluster academong-cluster `
  --services academong-fastapi `
  --region ap-southeast-1 `
  --query "services[0].{Running:runningCount,Desired:desiredCount,Rollout:deployments[0].rolloutState}"
```

When `Running` equals `Desired` and `Rollout` shows `COMPLETED` — it's live.

---

## Part 10 — Run the database schema

```powershell
# Get the DB endpoint
$RDS_HOST = terraform -chdir=C:\dev\AcadeMong\infra output -raw rds_endpoint

# Get the generated DB password from Secrets Manager
$DB_PASS = aws secretsmanager get-secret-value `
  --secret-id "academong/staging/db-password" `
  --query SecretString --output text --region ap-southeast-1

# Apply the schema (requires psql — install from https://www.postgresql.org/download/windows/)
$env:PGPASSWORD = $DB_PASS
psql -h $RDS_HOST -U admin -d tcas_advisor -f C:\dev\AcadeMong\backend\db\schema.sql
```

---

## Part 11 — Deploy the React frontend

```powershell
cd C:\dev\AcadeMong\frontend
npm install
npm run build

$BUCKET = terraform -chdir=../infra output -raw frontend_bucket

# Upload build to S3
aws s3 sync dist/ "s3://$BUCKET" --delete --region ap-southeast-1

# Clear CloudFront cache so users get the new version immediately
$CF_DIST = aws cloudfront list-distributions `
  --query "DistributionList.Items[?contains(Aliases.Items, 'purinboonpetch.com')].Id" `
  --output text

aws cloudfront create-invalidation `
  --distribution-id $CF_DIST `
  --paths "/*"
```

---

## Part 12 — Load RAG PDFs

The ingestion script runs on the GPU instance because that's where Qdrant and Ollama (for embeddings) live. Your repo needs to be on the GPU first.

**Step A — Copy your PDFs and manifest to the GPU** (run locally):
```powershell
$GPU_IP = terraform -chdir=C:\dev\AcadeMong\infra output -raw gpu_public_ip

# Copy the PDFs
scp -i "$env:USERPROFILE\.ssh\academong-key.pem" `
  C:\dev\AcadeMong\data\pdfs\*.pdf `
  ubuntu@${GPU_IP}:/tmp/pdfs/

# Copy the manifest
scp -i "$env:USERPROFILE\.ssh\academong-key.pem" `
  C:\dev\AcadeMong\data\pdfs\manifest.json `
  ubuntu@${GPU_IP}:/tmp/pdfs/
```

The `manifest.json` tells the ingestion script which PDF belongs to which university/major/round:
```json
[
  {
    "filename": "chula_cs_round3_2567.pdf",
    "university": "Chulalongkorn",
    "major": "Computer Science",
    "round": 3,
    "year": 2567,
    "source_url": "https://..."
  }
]
```

**Step B — Run ingestion on the GPU** (SSH in first):
```bash
ssh -i "$env:USERPROFILE\.ssh\academong-key.pem" ubuntu@<GPU_IP>

# Clone repo (first time only)
git clone https://github.com/Khronossu/AcadeMong.git /opt/academong

# Install Python deps
cd /opt/academong/backend
pip3 install -r requirements.txt

# Set env vars so the script can reach RDS and Qdrant
export POSTGRES_HOST=<RDS_ENDPOINT_FROM_TERRAFORM_OUTPUT>
export POSTGRES_PORT=5432
export POSTGRES_DB=tcas_advisor
export POSTGRES_USER=admin
export POSTGRES_PASSWORD=<DB_PASS_FROM_SECRETS_MANAGER>
export QDRANT_HOST=localhost
export QDRANT_PORT=6333
export OLLAMA_HOST=localhost
export OLLAMA_PORT=11434
export EMBEDDING_MODEL=nomic-embed-text

# Copy PDFs to the expected location
cp -r /tmp/pdfs /opt/academong/data/

# Run ingestion — processes all PDFs in data/pdfs/, skips unchanged ones (hash check)
python -m ingestion.ingest_pdfs --pdf-dir ../data/pdfs
```

Re-running is safe — unchanged PDFs are skipped via document hash. New PDFs are added.

---

## Part 13 — Load career data

```bash
# Still on the GPU (or SSH back in)

# Copy career JSON files to GPU first (locally):
# scp -i ~/.ssh/academong-key.pem data/career/jobthai_raw.json ubuntu@<GPU_IP>:/opt/academong/data/career/
# scp -i ~/.ssh/academong-key.pem data/career/jobtopgun_raw.json ubuntu@<GPU_IP>:/opt/academong/data/career/

# On the GPU:
cd /opt/academong/backend
python -m ingestion.career_data_loader
```

Also idempotent — uses `ON CONFLICT DO UPDATE` in Postgres and Qdrant upserts.

---

## Part 14 — Check everything is running

Run this from your local PowerShell for a full status summary:

```powershell
Write-Host "`n=== FastAPI Health ===" -ForegroundColor Cyan
try {
  (Invoke-WebRequest -Uri "https://app.purinboonpetch.com/health" -UseBasicParsing).Content
} catch { "UNREACHABLE - check ECS logs or Cloudflare DNS" }

Write-Host "`n=== ECS Service ===" -ForegroundColor Cyan
aws ecs describe-services `
  --cluster academong-cluster `
  --services academong-fastapi `
  --region ap-southeast-1 `
  --query "services[0].{Running:runningCount,Desired:desiredCount,Status:status}" `
  --output table

Write-Host "`n=== RDS ===" -ForegroundColor Cyan
aws rds describe-db-instances `
  --db-instance-identifier academong-postgres `
  --region ap-southeast-1 `
  --query "DBInstances[0].{Status:DBInstanceStatus,Host:Endpoint.Address}" `
  --output table

Write-Host "`n=== Redis ===" -ForegroundColor Cyan
aws elasticache describe-cache-clusters `
  --cache-cluster-id academong-redis `
  --region ap-southeast-1 `
  --query "CacheClusters[0].{Status:CacheClusterStatus}" `
  --output table

Write-Host "`n=== GPU Instance ===" -ForegroundColor Cyan
aws ec2 describe-instances `
  --filters "Name=tag:Name,Values=academong-gpu" `
  --region ap-southeast-1 `
  --query "Reservations[0].Instances[0].{State:State.Name,IP:PublicIpAddress,Type:InstanceType}" `
  --output table
```

**Check FastAPI logs (live):**
```powershell
aws logs tail /ecs/academong/fastapi --follow --region ap-southeast-1
```

**Check Qdrant has data** (SSH into GPU):
```bash
# Total points in the RAG collection
curl http://localhost:6333/collections/tcas_documents | python3 -m json.tool

# Total points in the careers collection
curl http://localhost:6333/collections/careers | python3 -m json.tool
```

**Check ECS tasks (if something crashes):**
```powershell
# List recent stopped tasks to see why they failed
aws ecs list-tasks `
  --cluster academong-cluster `
  --desired-status STOPPED `
  --region ap-southeast-1

# Then describe a stopped task to see the stop reason
aws ecs describe-tasks `
  --cluster academong-cluster `
  --tasks <TASK_ARN> `
  --region ap-southeast-1 `
  --query "tasks[0].{StopCode:stopCode,StoppedReason:stoppedReason,Containers:containers[0].reason}"
```

---

## Quick reference — what runs where

| Step | Runs on |
|---|---|
| `aws configure`, `terraform`, `docker build/push`, `aws ecs update-service`, `aws s3 sync` | Your local machine (PowerShell) |
| `tail -f /var/log/ollama-pull.log`, `docker ps`, `python -m ingestion.*` | GPU instance (after SSH) |
| Adding DNS records (validation CNAMEs + A/CNAME records) | Cloudflare dashboard in browser |
| `psql ... schema.sql` | Your local machine (needs psql) OR GPU (has internet to RDS) |

---

## Cost-saving — stop the GPU when not in use

The GPU instance (~$0.53/hr) is the biggest cost. Stop it overnight during development:

```powershell
$ID = aws ec2 describe-instances `
  --filters "Name=tag:Name,Values=academong-gpu" `
  --region ap-southeast-1 `
  --query "Reservations[0].Instances[0].InstanceId" --output text

# Stop (billing pauses for compute, EBS still charges ~$0.10/mo)
aws ec2 stop-instances --instance-ids $ID --region ap-southeast-1

# Start again before working
aws ec2 start-instances --instance-ids $ID --region ap-southeast-1
```

The Elastic IP keeps the same public IP across stop/start, so no Cloudflare DNS changes needed.

---

## Troubleshooting

**`terraform apply` stuck on cert validation for >20 min:**
- Check the CNAME records are in Cloudflare with proxy OFF
- Verify they resolve: `nslookup _abc123def456.purinboonpetch.com 8.8.8.8`

**ECS task keeps restarting:**
```powershell
aws logs tail /ecs/academong/fastapi --follow --region ap-southeast-1
# Usually: missing env var, can't reach RDS, or Firebase credentials invalid
```

**Can't SSH into GPU:**
- Your IP may have changed: `(Invoke-WebRequest ifconfig.me/ip -UseBasicParsing).Content.Trim()`
- Update `ssh_allowed_cidr` in `terraform.tfvars` then `terraform apply`

**`app.purinboonpetch.com` unreachable after DNS records added:**
- DNS propagation takes up to 5 min on Cloudflare
- Verify with: `nslookup app.purinboonpetch.com 1.1.1.1`
- Make sure proxy is OFF (grey cloud) on the CNAME record

**Frontend loads but API calls fail (CORS):**
- The FastAPI backend needs `purinboonpetch.com` added to its CORS origins
- Check `backend/main.py` `allow_origins` list
