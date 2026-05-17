# Bootstrap — run once before the main infra
# Creates the S3 bucket + DynamoDB table used as the Terraform remote backend.
#
# Usage:
#   cd infra/bootstrap
#   terraform init
#   terraform apply
#
# After apply, note the outputs and paste them into infra/main.tf backend block.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.6"
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  default = "ap-southeast-1"
}

variable "project" {
  default = "academong"
}

resource "aws_s3_bucket" "tf_state" {
  bucket = "${var.project}-tf-state-${random_id.suffix.hex}"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket                  = aws_s3_bucket.tf_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "tf_lock" {
  name         = "${var.project}-tf-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}

resource "random_id" "suffix" {
  byte_length = 4
}

output "state_bucket" {
  value = aws_s3_bucket.tf_state.bucket
}

output "lock_table" {
  value = aws_dynamodb_table.tf_lock.name
}

output "backend_config" {
  value = <<-EOT
    # Paste this into infra/main.tf backend "s3" block:
    bucket         = "${aws_s3_bucket.tf_state.bucket}"
    key            = "academong/terraform.tfstate"
    region         = "${var.aws_region}"
    dynamodb_table = "${aws_dynamodb_table.tf_lock.name}"
    encrypt        = true
  EOT
}
