# ================================================================================
# Lambda Module - GCB AI Agent
# ================================================================================
# This module creates the Lambda function and its event source mapping.
# IAM roles and policies are managed by the IAM module.
# ================================================================================

# ------------------- Lambda Function -------------------
resource "aws_lambda_function" "main" {
  function_name = "${var.name_prefix}-lambda-${var.environment}"
  role          = var.lambda_role_arn

  # Container Image configuration
  package_type = "Image"
  image_uri    = var.ecr_image_uri

  # Performance settings for PDF processing with Docling
  timeout     = var.timeout
  memory_size = var.memory_size

  # Environment variables
  environment {
    variables = {
      OPENAI_API_KEY   = var.openai_api_key
      S3_ENDPOINT      = var.s3_endpoint
      S3_BUCKET_NAME   = var.s3_bucket_name
      SQS_QUEUE_URL    = var.sqs_queue_url
      PYTHONUNBUFFERED = "1"
    }
  }

  tags = {
    Name        = "${var.name_prefix}-lambda-${var.environment}"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Project     = "GCB-AI-Agent"
  }
}

# ------------------- SQS Event Source Mapping -------------------
resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn = var.sqs_queue_arn
  function_name    = aws_lambda_function.main.arn

  # FIFO queue settings
  batch_size                         = 1
  maximum_batching_window_in_seconds = 0

  enabled = true
}
