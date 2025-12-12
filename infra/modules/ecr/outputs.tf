# ================================================================================
# ECR Module Outputs - GCB AI Agent
# ================================================================================

# ------------------- Repository Information -------------------
output "repository_url" {
  value       = aws_ecr_repository.main.repository_url
  description = "URL of the ECR repository"
}

output "repository_arn" {
  value       = aws_ecr_repository.main.arn
  description = "ARN of the ECR repository"
}

output "repository_name" {
  value       = aws_ecr_repository.main.name
  description = "Name of the ECR repository"
}

output "registry_id" {
  value       = aws_ecr_repository.main.registry_id
  description = "Registry ID (AWS Account ID)"
}

# ------------------- Image URI (for Lambda) -------------------
output "image_uri" {
  value       = "${aws_ecr_repository.main.repository_url}:${var.image_tag}"
  description = "Full image URI with tag (use this for Lambda function)"
}

# ------------------- AWS Context -------------------
output "aws_account_id" {
  value       = data.aws_caller_identity.current.account_id
  description = "AWS Account ID"
}

output "aws_region" {
  value       = data.aws_region.current.name
  description = "AWS Region"
}
