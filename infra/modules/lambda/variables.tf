# ================================================================================
# Lambda Module Variables - GCB AI Agent
# ================================================================================

# ------------------- Naming -------------------
variable "name_prefix" {
  type        = string
  description = "Prefix for naming Lambda resources"
  default     = "gcb-ai-agent"
}

variable "environment" {
  type        = string
  description = "Environment (dev, staging, prod)"
}

# ------------------- IAM Role (from IAM module) -------------------
variable "lambda_role_arn" {
  type        = string
  description = "ARN of the Lambda execution role (from IAM module)"
}

# ------------------- ECR Image (from ECR module) -------------------
variable "ecr_image_uri" {
  type        = string
  description = "Full ECR image URI with tag (from ECR module)"
}

# ------------------- SQS Configuration (from SQS module) -------------------
variable "sqs_queue_arn" {
  type        = string
  description = "ARN of the SQS queue for event source mapping"
}

variable "sqs_queue_url" {
  type        = string
  description = "URL of the SQS queue for environment variable"
}

# ------------------- S3 Configuration -------------------
variable "s3_bucket_name" {
  type        = string
  description = "Name of the S3 bucket for PDFs and results"
}

variable "s3_endpoint" {
  type        = string
  description = "S3 endpoint URL"
  default     = "https://s3.amazonaws.com"
}

# ------------------- API Keys -------------------
variable "openai_api_key" {
  type        = string
  description = "OpenAI API key for AI processing"
  sensitive   = true
}

# ------------------- Performance Settings -------------------
variable "timeout" {
  type        = number
  description = "Lambda function timeout in seconds"
  default     = 900 # 15 minutes (maximum for Lambda)
}

variable "memory_size" {
  type        = number
  description = "Lambda function memory in MB"
  default     = 3008 # 3GB
}
