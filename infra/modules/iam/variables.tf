# ================================================================================
# IAM Module Variables - GCB AI Agent
# ================================================================================

# ------------------- Naming -------------------
variable "name_prefix" {
  type        = string
  description = "Prefix for naming IAM resources"
}

variable "environment" {
  type        = string
  description = "Environment (dev, staging, prod)"
}

# ------------------- Resource ARNs for Policies -------------------
variable "sqs_queue_arn" {
  type        = string
  description = "ARN of the SQS queue for Lambda access policy"
}

variable "s3_bucket_arn" {
  type        = string
  description = "ARN of the S3 bucket for Lambda access policy"
}
