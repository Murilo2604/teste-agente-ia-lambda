# ECR Module - GCB AI Agent

This module creates and manages the ECR repository for Lambda container images.

## Overview

- Creates ECR repository with security scanning enabled
- Configures lifecycle policies to manage image retention
- Sets up repository policies for Lambda and account access
- Outputs image URI for use by Lambda module

## CI/CD Integration

**Important**: This module only creates the repository infrastructure. The actual Docker images must be pushed by your CI/CD pipeline.

### Workflow

1. Terraform creates the ECR repository
2. CI/CD builds Docker image from application code
3. CI/CD authenticates and pushes image to ECR
4. Lambda references the image URI from this module's outputs

### Example CI/CD Commands

```bash
# Get ECR login
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_REGISTRY

# Build and push
docker build -t $REPOSITORY_URL:latest .
docker push $REPOSITORY_URL:latest

# Update Lambda (optional - if not using Terraform for deploys)
aws lambda update-function-code \
  --function-name $LAMBDA_NAME \
  --image-uri $REPOSITORY_URL:latest
```

## Usage

```hcl
module "ecr" {
  source = "../../modules/ecr"

  name_prefix = "gcb-ai-agent"
  environment = "dev"
  image_tag   = "latest"
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| name_prefix | Prefix for naming ECR repository | string | "gcb-ai-agent" | no |
| environment | Environment (dev, staging, prod) | string | - | yes |
| image_tag | Docker image tag to reference | string | "latest" | no |

## Outputs

| Name | Description |
|------|-------------|
| repository_url | URL of the ECR repository |
| repository_arn | ARN of the ECR repository |
| repository_name | Name of the ECR repository |
| registry_id | Registry ID (AWS Account ID) |
| image_uri | Full image URI with tag (use this for Lambda) |
| aws_account_id | AWS Account ID |
| aws_region | AWS Region |
