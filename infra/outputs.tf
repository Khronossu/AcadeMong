# ── Cloudflare DNS records to add manually ────────────────────────────────────

output "cloudflare_step1_acm_validation" {
  description = "Add this CNAME in Cloudflare DURING terraform apply (cert validation). Proxy = OFF."
  value = {
    for dvo in aws_acm_certificate.alb.domain_validation_options :
    dvo.domain_name => {
      type  = "CNAME"
      name  = trimsuffix(dvo.resource_record_name, ".${var.domain_name}.")
      value = trimsuffix(dvo.resource_record_value, ".")
    }
  }
}

output "cloudflare_step2_api_dns" {
  description = "Add this CNAME in Cloudflare AFTER apply finishes. Proxy = OFF."
  value = {
    type    = "CNAME"
    name    = var.app_subdomain
    value   = aws_lb.main.dns_name
    comment = "app.purinboonpetch.com → ALB (FastAPI)"
  }
}

output "app_url" {
  description = "API base URL"
  value       = "https://${local.app_fqdn}"
}

output "frontend_url" {
  description = "React frontend — deploy via Cloudflare Pages"
  value       = "https://${var.domain_name} (Cloudflare Pages)"
}

output "alb_dns" {
  description = "ALB DNS name (for Cloudflare CNAME target)"
  value       = aws_lb.main.dns_name
}

output "ecr_repository_url" {
  description = "Push Docker images here before deploying"
  value       = aws_ecr_repository.fastapi.repository_url
}

output "gpu_public_ip" {
  description = "SSH target for the GPU instance"
  value       = aws_eip.gpu.public_ip
}

output "rds_endpoint" {
  description = "PostgreSQL host"
  value       = aws_db_instance.postgres.address
  sensitive   = true
}

output "redis_endpoint" {
  description = "ElastiCache Redis host"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
  sensitive   = true
}

output "frontend_bucket" {
  value = aws_s3_bucket.frontend.bucket
}

output "db_secret_arn" {
  value = aws_secretsmanager_secret.db_password.arn
}

output "firebase_secret_arn" {
  value = aws_secretsmanager_secret.firebase_credentials.arn
}
