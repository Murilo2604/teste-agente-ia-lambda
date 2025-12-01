resource "aws_ssm_parameter" "sqs_queue_ssm" {
  name  = var.gcb_ai_agent_sqs_fifo_queue_ssm
  type  = "String"
  value = aws_sqs_queue.gcb_ai_agent_sqs_queue_fifo.url

  tags = {
    Name        = "${var.gcb_ai_agent_sqs_fifo_queue_ssm_name}-${var.environment}"
    Description = "SSM-Parameter-Store-Key-Exposes-the-SQS-Queue-URL"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_ssm_parameter" "sqs_dlq_queue_ssm" {
  name  = var.gcb_ai_agent_sqs_dlq_queue_fifo_ssm
  type  = "String"
  value = aws_sqs_queue.gcb_ai_agent_sqs_dlq_fifo_queue.url

  tags = {
    Name        = "${var.gcb_ai_agent_sqs_dlq_queue_fifo_ssm_name}-${var.environment}"
    Description = "SSM-Parameter-Store-Key-Exposes-the-SQS-DLQ-URL"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_sqs_queue" "gcb_ai_agent_sqs_queue_fifo" {
  name                        = var.gcb_ai_agent_sqs_fifo_queue_name
  fifo_queue                  = true
  delay_seconds               = 10
  visibility_timeout_seconds  = 960  # 16 minutes (slightly more than Lambda timeout of 15 minutes)
  content_based_deduplication = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.gcb_ai_agent_sqs_dlq_fifo_queue.arn
    maxReceiveCount     = 4
  })

  tags = {
    Name        = "${var.gcb_ai_agent_sqs_fifo_queue_name}-${var.environment}"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_sqs_queue" "gcb_ai_agent_sqs_dlq_fifo_queue" {
  name       = var.gcb_ai_agent_sqs_dlq_queue_fifo_name
  fifo_queue = true

  tags = {
    Name        = "${var.gcb_ai_agent_sqs_dlq_queue_fifo_name}-${var.environment}"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# Define which/who can access the SQS queue;
# In this case allow every Lambda function to access the SQS queue and consume messages;
# Resource to allow the Lambda function to access the SQS queue and consume messages;
resource "aws_sqs_queue_policy" "gcb_ai_agent_sqs_queue_fifo_policy" {
  # Reference the SQS queue;
  queue_url = aws_sqs_queue.gcb_ai_agent_sqs_queue_fifo.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          # Who can execute the actions on the SQS queue;
          Service = "lambda.amazonaws.com"
        }
        # What actions can be executed on the SQS queue;
        Action = [
          "sqs:ReceiveMessage", # Allow the Lambda function to receive messages from the SQS queue;
          "sqs:DeleteMessage", # Allow the Lambda function to delete messages from the SQS queue (after processing);
          "sqs:GetQueueAttributes", # Allow the Lambda function to get the attributes of the SQS queue;
          "sqs:GetQueueUrl" # Allow the Lambda function to get the URL of the SQS queue;
        ]
        # Which resource this policy gonna affect;
        Resource = aws_sqs_queue.gcb_ai_agent_sqs_queue_fifo.arn
      }
    ]
  })
}
