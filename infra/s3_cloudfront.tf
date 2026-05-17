# Frontend is served via Cloudflare Pages (free, no AWS verification needed).
# This file only manages the S3 bucket used as a build artifact store —
# Cloudflare Pages pulls from git directly, so S3 is not needed for hosting.
# Keeping the bucket for future use or if CloudFront is added later.

resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project}-frontend-${var.environment}"
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  versioning_configuration { status = "Enabled" }
}
