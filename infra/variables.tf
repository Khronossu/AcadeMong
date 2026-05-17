variable "aws_region" {
  description = "AWS region — ap-southeast-1 (Singapore) for low latency from Thailand"
  type        = string
  default     = "ap-southeast-1"
}

variable "environment" {
  description = "staging | prod"
  type        = string
  default     = "staging"
  validation {
    condition     = contains(["staging", "prod"], var.environment)
    error_message = "Must be staging or prod."
  }
}

variable "project" {
  description = "Short project name, used as prefix for all resource names"
  type        = string
  default     = "academong"
}

# ── Networking ────────────────────────────────────────────────────────────────

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "2 public subnets for ALB + EC2 GPU (must span 2 AZs)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "2 private subnets for RDS + ElastiCache"
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24"]
}

# ── Domain & TLS ──────────────────────────────────────────────────────────────

variable "domain_name" {
  description = "Root domain managed by Cloudflare. DNS records are added manually in Cloudflare dashboard."
  type        = string
  default     = "purinboonpetch.com"
}

variable "app_subdomain" {
  description = "Subdomain for the API/app (will be app.<domain_name>)"
  type        = string
  default     = "app"
}

# ── EC2 GPU ───────────────────────────────────────────────────────────────────

variable "gpu_instance_type" {
  description = "g4dn.xlarge = T4 16GB ~$0.53/hr (fits all models). g5.xlarge = A10G 24GB ~$1.01/hr (comfortable headroom)."
  type        = string
  default     = "g4dn.xlarge"
}

variable "gpu_key_name" {
  description = "Name of an existing EC2 key pair for SSH access to the GPU instance"
  type        = string
}

variable "ssh_allowed_cidr" {
  description = "Your IP CIDR allowed for SSH to GPU instance (e.g. 1.2.3.4/32)"
  type        = string
}

variable "gpu_volume_size_gb" {
  description = "Root EBS volume size for GPU instance (Ollama models take ~20GB)"
  type        = number
  default     = 60
}

# ── RDS ───────────────────────────────────────────────────────────────────────

variable "rds_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "rds_allocated_storage" {
  type    = number
  default = 20
}

variable "db_name" {
  type    = string
  default = "tcas_advisor"
}

variable "db_username" {
  type    = string
  default = "admin"
}

# ── ElastiCache ───────────────────────────────────────────────────────────────

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.small"
}

# ── ECS / FastAPI ─────────────────────────────────────────────────────────────

variable "fastapi_cpu" {
  description = "Fargate task CPU units (1024 = 1 vCPU)"
  type        = number
  default     = 1024
}

variable "fastapi_memory" {
  description = "Fargate task memory in MB"
  type        = number
  default     = 2048
}

variable "fastapi_desired_count" {
  type    = number
  default = 1
}

# ── Firebase ──────────────────────────────────────────────────────────────────

variable "firebase_credentials_json" {
  description = "Firebase service account JSON (single-line). Stored in Secrets Manager."
  type        = string
  sensitive   = true
}
