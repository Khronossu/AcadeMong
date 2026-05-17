# DNS is managed by Cloudflare. No Route 53 resources.
# One ACM cert for the ALB only (ap-southeast-1).
# Frontend is on Cloudflare Pages — no CloudFront cert needed.

locals {
  app_fqdn = "${var.app_subdomain}.${var.domain_name}"
}

resource "aws_acm_certificate" "alb" {
  domain_name       = local.app_fqdn
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# Waits for ACM to detect the validation CNAME you added in Cloudflare.
resource "aws_acm_certificate_validation" "alb" {
  certificate_arn = aws_acm_certificate.alb.arn
}
