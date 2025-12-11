# ================================================================================
# GCB AI Agent - Dev Environment Variables
# ================================================================================
# All values should be provided via terraform.tfvars or environment variables.
# No hardcoded defaults for sensitive or environment-specific values.
# ================================================================================

# ------------------- AWS Configuration -------------------
variable "aws_region" {
  type        = string
  description = "AWS region for deployment"
  default     = "us-east-1"
}

# ------------------- Environment -------------------
variable "environment" {
  type        = string
  description = "Environment name (dev, staging, prod)"
  default     = "dev"
}

# ------------------- Naming -------------------
variable "name_prefix" {
  type        = string
  description = "Prefix for naming all resources"
  default     = "gcb-ai-agent"
}

# ------------------- ECR / Docker Image -------------------
variable "image_tag" {
  type        = string
  description = "Docker image tag (managed by CI/CD)"
  default     = "latest"
}

# ------------------- S3 Configuration -------------------
variable "s3_bucket_name" {
  type        = string
  description = "Name of the existing S3 bucket for PDFs and results"
  # No default - must be provided
}

variable "s3_endpoint" {
  type        = string
  description = "S3 endpoint URL"
  default     = "https://s3.amazonaws.com"
}

# ------------------- SQS Configuration -------------------
variable "sqs_delay_seconds" {
  type        = number
  description = "Delay in seconds before SQS messages become available"
  default     = 10
}

variable "sqs_visibility_timeout_seconds" {
  type        = number
  description = "SQS visibility timeout (should be >= Lambda timeout)"
  default     = 900
}

variable "sqs_max_receive_count" {
  type        = number
  description = "Number of receives before message goes to DLQ"
  default     = 4
}

# ------------------- Lambda Configuration -------------------
variable "lambda_timeout" {
  type        = number
  description = "Lambda function timeout in seconds"
  default     = 900
}

variable "lambda_memory_size" {
  type        = number
  description = "Lambda function memory in MB"
  default     = 3008
}

# ------------------- Secrets (NO DEFAULTS) -------------------
variable "openai_api_key" {
  type        = string
  description = "OpenAI API key for AI processing"
  sensitive   = true
  # No default - must be provided via tfvars or environment
}
