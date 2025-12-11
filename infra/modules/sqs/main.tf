# ================================================================================
# SQS Module - GCB AI Agent
# ================================================================================
# This module creates SQS FIFO queues with dead-letter queue and SSM parameters.
# ================================================================================

# ------------------- Locals for Dynamic Naming -------------------
locals {
  queue_name     = "${var.name_prefix}-queue-${var.environment}.fifo"
  dlq_name       = "${var.name_prefix}-dlq-${var.environment}.fifo"
  ssm_queue_path = "/${var.name_prefix}/${var.environment}/sqs/queue_url"
  ssm_dlq_path   = "/${var.name_prefix}/${var.environment}/sqs/dlq_url"
}

# ------------------- Dead Letter Queue -------------------
resource "aws_sqs_queue" "dlq" {
  name       = local.dlq_name
  fifo_queue = true

  # Message retention: 14 days (maximum)
  message_retention_seconds = 1209600

  tags = {
    Name        = local.dlq_name
    Environment = var.environment
    ManagedBy   = "Terraform"
    Project     = "GCB-AI-Agent"
    Type        = "DeadLetterQueue"
  }
}

# ------------------- Main Queue -------------------
resource "aws_sqs_queue" "main" {
  name                        = local.queue_name
  fifo_queue                  = true
  delay_seconds               = var.delay_seconds
  content_based_deduplication = true

  # Visibility timeout should be >= Lambda timeout
  visibility_timeout_seconds = var.visibility_timeout_seconds

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })

  tags = {
    Name        = local.queue_name
    Environment = var.environment
    ManagedBy   = "Terraform"
    Project     = "GCB-AI-Agent"
    Type        = "MainQueue"
  }
}

# ------------------- Queue Policy -------------------
resource "aws_sqs_queue_policy" "main" {
  queue_url = aws_sqs_queue.main.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowLambdaAccess"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:GetQueueUrl"
        ]
        Resource = aws_sqs_queue.main.arn
      }
    ]
  })
}

# ------------------- SSM Parameters -------------------
resource "aws_ssm_parameter" "queue_url" {
  name  = local.ssm_queue_path
  type  = "String"
  value = aws_sqs_queue.main.url

  tags = {
    Name        = "${var.name_prefix}-sqs-queue-url-${var.environment}"
    Description = "SQS Queue URL for GCB AI Agent"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_ssm_parameter" "dlq_url" {
  name  = local.ssm_dlq_path
  type  = "String"
  value = aws_sqs_queue.dlq.url

  tags = {
    Name        = "${var.name_prefix}-sqs-dlq-url-${var.environment}"
    Description = "SQS DLQ URL for GCB AI Agent"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}
