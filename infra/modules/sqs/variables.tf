# ================================================================================
# SQS Module Variables - GCB AI Agent
# ================================================================================

# ------------------- Naming -------------------
variable "name_prefix" {
  type        = string
  description = "Prefix for naming SQS resources"
  default     = "gcb-ai-agent"
}

variable "environment" {
  type        = string
  description = "Environment (dev, staging, prod)"
}

# ------------------- Queue Configuration -------------------
variable "delay_seconds" {
  type        = number
  description = "Delay in seconds before messages become available"
  default     = 10
}

variable "visibility_timeout_seconds" {
  type        = number
  description = "Visibility timeout (should be >= Lambda timeout)"
  default     = 900 # 15 minutes
}

variable "max_receive_count" {
  type        = number
  description = "Number of receives before message goes to DLQ"
  default     = 4
}
