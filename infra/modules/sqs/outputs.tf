# ================================================================================
# SQS Module Outputs - GCB AI Agent
# ================================================================================

# ------------------- Main Queue -------------------
output "queue_arn" {
  value       = aws_sqs_queue.main.arn
  description = "ARN of the main SQS queue"
}

output "queue_url" {
  value       = aws_sqs_queue.main.url
  description = "URL of the main SQS queue"
}

output "queue_name" {
  value       = aws_sqs_queue.main.name
  description = "Name of the main SQS queue"
}

# ------------------- Dead Letter Queue -------------------
output "dlq_arn" {
  value       = aws_sqs_queue.dlq.arn
  description = "ARN of the dead letter queue"
}

output "dlq_url" {
  value       = aws_sqs_queue.dlq.url
  description = "URL of the dead letter queue"
}

output "dlq_name" {
  value       = aws_sqs_queue.dlq.name
  description = "Name of the dead letter queue"
}

# ------------------- SSM Parameters -------------------
output "ssm_queue_url_path" {
  value       = aws_ssm_parameter.queue_url.name
  description = "SSM parameter path for queue URL"
}

output "ssm_dlq_url_path" {
  value       = aws_ssm_parameter.dlq_url.name
  description = "SSM parameter path for DLQ URL"
}
