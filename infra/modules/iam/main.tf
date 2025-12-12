# ================================================================================
# IAM Module - GCB AI Agent
# ================================================================================
# This module manages all IAM resources for the GCB AI Agent infrastructure.
# It creates the Lambda execution role and all necessary policies.
# ================================================================================

# ------------------- Lambda Execution Role -------------------
resource "aws_iam_role" "lambda_execution_role" {
  name = "${var.name_prefix}-lambda-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "${var.name_prefix}-lambda-role-${var.environment}"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Project     = "GCB-AI-Agent"
  }
}

# ------------------- CloudWatch Logs Policy (AWS Managed) -------------------
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ------------------- ECR Read-Only Policy (AWS Managed) -------------------
resource "aws_iam_role_policy_attachment" "lambda_ecr_readonly" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# ------------------- SQS Access Policy -------------------
resource "aws_iam_role_policy" "lambda_sqs_access" {
  name = "${var.name_prefix}-lambda-sqs-access-${var.environment}"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:GetQueueUrl"
        ]
        Resource = var.sqs_queue_arn
      }
    ]
  })
}

# ------------------- S3 Access Policy -------------------
resource "aws_iam_role_policy" "lambda_s3_access" {
  name = "${var.name_prefix}-lambda-s3-access-${var.environment}"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:PutObjectAcl"
        ]
        Resource = "${var.s3_bucket_arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = var.s3_bucket_arn
      }
    ]
  })
}
