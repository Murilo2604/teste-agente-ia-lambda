# ================================================================================
# GCB AI Agent - Dev Environment Outputs
# ================================================================================
# Comprehensive outputs for all infrastructure components.
# These can be used by CI/CD pipelines and other systems.
# ================================================================================

# ------------------- AWS Context -------------------
output "aws_account_id" {
  value       = data.aws_caller_identity.current.account_id
  description = "AWS Account ID"
}

output "aws_region" {
  value       = data.aws_region.current.name
  description = "AWS Region"
}

output "environment" {
  value       = var.environment
  description = "Environment name"
}

# ------------------- ECR -------------------
output "ecr_repository_url" {
  value       = module.ecr.repository_url
  description = "URL of the ECR repository (for docker push)"
}

output "ecr_repository_name" {
  value       = module.ecr.repository_name
  description = "Name of the ECR repository"
}

output "ecr_image_uri" {
  value       = module.ecr.image_uri
  description = "Full image URI with tag (used by Lambda)"
}

# ------------------- IAM -------------------
output "lambda_role_arn" {
  value       = module.iam.lambda_execution_role_arn
  description = "ARN of the Lambda execution role"
}

output "lambda_role_name" {
  value       = module.iam.lambda_execution_role_name
  description = "Name of the Lambda execution role"
}

# ------------------- Lambda -------------------
output "lambda_function_arn" {
  value       = module.lambda.function_arn
  description = "ARN of the Lambda function"
}

output "lambda_function_name" {
  value       = module.lambda.function_name
  description = "Name of the Lambda function"
}

# ------------------- SQS -------------------
output "sqs_queue_url" {
  value       = module.sqs.queue_url
  description = "URL of the SQS queue"
}

output "sqs_queue_arn" {
  value       = module.sqs.queue_arn
  description = "ARN of the SQS queue"
}

output "sqs_queue_name" {
  value       = module.sqs.queue_name
  description = "Name of the SQS queue"
}

output "sqs_dlq_url" {
  value       = module.sqs.dlq_url
  description = "URL of the SQS dead letter queue"
}

output "sqs_dlq_arn" {
  value       = module.sqs.dlq_arn
  description = "ARN of the SQS dead letter queue"
}

# ------------------- S3 (existing) -------------------
output "s3_bucket_name" {
  value       = data.aws_s3_bucket.existing.bucket
  description = "Name of the S3 bucket"
}

output "s3_bucket_arn" {
  value       = data.aws_s3_bucket.existing.arn
  description = "ARN of the S3 bucket"
}

# ------------------- CI/CD Helpers -------------------
output "docker_login_command" {
  value       = "aws ecr get-login-password --region ${data.aws_region.current.name} | docker login --username AWS --password-stdin ${module.ecr.repository_url}"
  description = "Command to login to ECR (for CI/CD)"
}

output "docker_build_and_push_commands" {
  value       = <<-EOT
    # Build
    docker build --platform linux/amd64 -t ${module.ecr.repository_name}:latest .
    
    # Tag
    docker tag ${module.ecr.repository_name}:latest ${module.ecr.repository_url}:latest
    
    # Push
    docker push ${module.ecr.repository_url}:latest
    
    # Update Lambda
    aws lambda update-function-code --function-name ${module.lambda.function_name} --image-uri ${module.ecr.image_uri}
  EOT
  description = "Commands to build, push, and update Lambda (for CI/CD)"
}
