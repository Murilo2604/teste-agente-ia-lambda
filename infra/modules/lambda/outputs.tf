# ================================================================================
# Lambda Module Outputs - GCB AI Agent
# ================================================================================

# ------------------- Lambda Function -------------------
output "function_arn" {
  value       = aws_lambda_function.main.arn
  description = "ARN of the Lambda function"
}

output "function_name" {
  value       = aws_lambda_function.main.function_name
  description = "Name of the Lambda function"
}

output "invoke_arn" {
  value       = aws_lambda_function.main.invoke_arn
  description = "Invoke ARN of the Lambda function"
}

output "function_version" {
  value       = aws_lambda_function.main.version
  description = "Version of the Lambda function"
}

# ------------------- Event Source Mapping -------------------
output "event_source_mapping_uuid" {
  value       = aws_lambda_event_source_mapping.sqs_trigger.uuid
  description = "UUID of the SQS event source mapping"
}




