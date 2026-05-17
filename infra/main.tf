terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  required_version = ">= 1.6"

  # Fill in bucket/dynamodb_table from bootstrap outputs before running:
  #   cd infra/bootstrap && terraform apply
  backend "s3" {
    bucket         = "academong-tf-state-284725bb"
    key            = "academong/terraform.tfstate"
    region         = "ap-southeast-1"
    dynamodb_table = "academong-tf-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "academong"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
