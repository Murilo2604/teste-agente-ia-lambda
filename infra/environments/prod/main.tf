# ================================================================================
# GCB AI Agent - Prod Environment
# ================================================================================
# This is the root module that orchestrates all infrastructure for production.
# ================================================================================

terraform {
  required_version = ">= 1.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ------------------- Provider Configuration -------------------
provider "aws" {
  region = var.aws_region

  # Use AWS profile or environment variables for credentials
  # Do NOT hardcode access keys here
  
  default_tags {
    tags = {
      Environment = var.environment
      ManagedBy   = "Terraform"
      Project     = "GCB-AI-Agent"
    }
  }
}

# ------------------- Data Sources -------------------
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "aws_s3_bucket" "existing" {
  bucket = var.s3_bucket_name
}

# ===============================================================================
# MODULES - Order matters for dependencies
# ===============================================================================

# ------------------- 1. ECR Module (independent) -------------------
module "ecr" {
  source = "../../modules/ecr"

  name_prefix = var.name_prefix
  environment = var.environment
  image_tag   = var.image_tag
}

# ------------------- 2. SQS Module (independent) -------------------
module "sqs" {
  source = "../../modules/sqs"

  name_prefix                = var.name_prefix
  environment                = var.environment
  delay_seconds              = var.sqs_delay_seconds
  visibility_timeout_seconds = var.sqs_visibility_timeout_seconds
  max_receive_count          = var.sqs_max_receive_count
}

# ------------------- 3. IAM Module (depends on SQS, S3) -------------------
module "iam" {
  source = "../../modules/iam"

  name_prefix   = var.name_prefix
  environment   = var.environment
  sqs_queue_arn = module.sqs.queue_arn
  s3_bucket_arn = data.aws_s3_bucket.existing.arn

  depends_on = [module.sqs]
}

# ------------------- 4. Lambda Module (depends on all above) -------------------
module "lambda" {
  source = "../../modules/lambda"

  name_prefix     = var.name_prefix
  environment     = var.environment
  lambda_role_arn = module.iam.lambda_execution_role_arn
  ecr_image_uri   = module.ecr.image_uri
  sqs_queue_arn   = module.sqs.queue_arn
  sqs_queue_url   = module.sqs.queue_url
  s3_bucket_name  = var.s3_bucket_name
  s3_endpoint     = var.s3_endpoint
  openai_api_key  = var.openai_api_key
  timeout         = var.lambda_timeout
  memory_size     = var.lambda_memory_size

  depends_on = [module.iam, module.ecr, module.sqs]
}
