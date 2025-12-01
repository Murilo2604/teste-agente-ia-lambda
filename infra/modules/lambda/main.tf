# Definition of Role as identity that will be assumed by the Lambda function;
# Resource to create the Lambda role;
resource "aws_iam_role" "gcb_ai_agent_lambda_role" {
  name = var.gcb_ai_agent_lambda_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com" # Indicate which service can assume this role;
        }
      }
    ]
  })

  tags = {
    Name        = "${var.gcb_ai_agent_lambda_role_name}-${var.environment}"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# Give basic permissions - Like logging with CloudWatch;
# Resource to attach the basic execution policy to the Lambda role;
resource "aws_iam_role_policy_attachment" "gcb_ai_agent_lambda_basic_execution_policy" {
  role       = aws_iam_role.gcb_ai_agent_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" 
  # Its essential;
  # policy_arn: Basic permission config guaranteed by AWS -> Every Lambda function depends on this policy to work;
  # Ensure Lambda can write logs to CloudWatch (Logs are essential for debugging and monitoring and represent the execution of the Lambda function);
}

# REMOVIDO: Data source para ZIP file
# Agora usamos imagem de container do ECR ao invés de ZIP

# In this case allow JUST THIS ONE Lambda function to access the SQS queue;
# That policy define and control what Lambda function can, independently of queue policy ("gcb_ai_agent_sqs_queue_fifo_policy");
# Attach permission to the Lambda role to access the SQS queue;
resource "aws_iam_role_policy" "gcb_ai_agent_lambda_sqs_access" {
  name = "gcb_ai_agent_lambda_sqs_access"
  role = aws_iam_role.gcb_ai_agent_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:GetQueueUrl"
        ],
        # Passes the SQS queue ARN output from the SQS module to the Lambda function;
        Resource = var.gcb_ai_agent_sqs_fifo_queue_arn
      }
    ]
  })
}

# Permissão para ler imagens do ECR
resource "aws_iam_role_policy_attachment" "lambda_ecr_readonly" {
  role       = aws_iam_role.gcb_ai_agent_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# Permissão para publicar no SNS (notificações de sucesso)
resource "aws_iam_role_policy" "gcb_ai_agent_lambda_sns_publish" {
  name = "gcb_ai_agent_lambda_sns_publish"
  role = aws_iam_role.gcb_ai_agent_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "sns:Publish"
        ],
        Resource = var.sns_topic_arn
      }
    ]
  })
}

# Permissão para acessar S3 (download de PDFs e upload de cutouts)
resource "aws_iam_role_policy" "gcb_ai_agent_lambda_s3_access" {
  name = "gcb_ai_agent_lambda_s3_access"
  role = aws_iam_role.gcb_ai_agent_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:PutObjectAcl"
        ],
        Resource = "arn:aws:s3:::${var.s3_bucket_name}/*"
      },
      {
        Effect = "Allow",
        Action = [
          "s3:ListBucket"
        ],
        Resource = "arn:aws:s3:::${var.s3_bucket_name}"
      }
    ]
  })
}

# Resource to create the Lambda function using Container Image;
resource "aws_lambda_function" "gcb_ai_agent_lambda_function" {
  function_name = var.gcb_ai_agent_lambda_function_name
  role          = var.gcb_ai_agent_lambda_role_arn
  
  # Usar container image ao invés de ZIP
  package_type = "Image"
  image_uri    = var.gcb_ai_agent_ecr_image_uri

  # Timeout e memória aumentados para processamento de PDF com Docling
  timeout     = 900  # 15 minutos (máximo para Lambda)
  memory_size = 3008 # 3GB (ajuste conforme necessário)

  # Configuração de ambiente
  environment {
    variables = {
      # Passes the SQS queue URL output from the SQS module to the Lambda function
      OPENAI_API_KEY = var.openai_api_key
      
      S3_ENDPOINT = var.s3_endpoint
      S3_BUCKET_NAME = var.s3_bucket_name

      SNS_TOPIC_ARN = var.sns_topic_arn
      SQS_QUEUE_URL = var.gcb_ai_agent_sqs_fifo_queue_url
      
      # Variáveis adicionais para o processamento
      PYTHONUNBUFFERED = "1"
    }
  }

  tags = {
    Name        = "${var.gcb_ai_agent_lambda_function_name}-${var.environment}"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Project     = "GCB-AI-Agent"
  }
}

# Resource to create the Lambda event source mapping (trigger);
# This resource connects the Lambda function to the SQS queue;
# When a message is sent to the SQS queue, the Lambda function will be invoked;
resource "aws_lambda_event_source_mapping" "gcb_ai_agent_lambda_sqs_trigger" {
  event_source_arn = var.gcb_ai_agent_sqs_fifo_queue_arn
  function_name    = aws_lambda_function.gcb_ai_agent_lambda_function.arn
  
  # Batch size: Number of messages to process in a single invocation (1-10 for FIFO queues);
  batch_size = 1
  
  # Maximum batching window in seconds (0-300);
  # Time to wait for accumulating messages before invoking the Lambda;
  maximum_batching_window_in_seconds = 0
  
  # Enable the event source mapping;
  enabled = true

  # Destination configuration: Envia detalhes de falhas para SQS DLQ (já configurado no próprio SQS)
  # destination_config {
  #   on_failure {
  #     destination_arn = var.gcb_ai_agent_sqs_dlq_queue_fifo_arn
  #   }
  # }
}

# Lambda Function Event Invoke Config - Destino SNS para sucessos
resource "aws_lambda_function_event_invoke_config" "gcb_ai_agent_lambda_invoke_config" {
  function_name = aws_lambda_function.gcb_ai_agent_lambda_function.function_name

  # Maximum event age in seconds (1-21600)
  maximum_event_age_in_seconds = 21600  # 6 horas

  # Maximum retry attempts (0-2)
  maximum_retry_attempts = 2

  # Destination configuration
  destination_config {
    # On success: Envia notificação para SNS
    on_success {
      destination = var.sns_topic_arn
    }

    # On failure: Já tratado pelo DLQ do SQS
    # on_failure {
    #   destination = var.gcb_ai_agent_sqs_dlq_queue_fifo_arn
    # }
  }
}