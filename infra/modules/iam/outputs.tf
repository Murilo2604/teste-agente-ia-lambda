# ================================================================================
# IAM Module Outputs - GCB AI Agent
# ================================================================================

# ------------------- Lambda Execution Role -------------------
output "lambda_execution_role_arn" {
  value       = aws_iam_role.lambda_execution_role.arn
  description = "ARN of the Lambda execution role"
}

output "lambda_execution_role_name" {
  value       = aws_iam_role.lambda_execution_role.name
  description = "Name of the Lambda execution role"
}

output "lambda_execution_role_id" {
  value       = aws_iam_role.lambda_execution_role.id
  description = "ID of the Lambda execution role"
}




