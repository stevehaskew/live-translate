variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "domain_name" {
  description = "Domain name for the static website (e.g., translate.example.com)"
  type        = string
}

variable "api_domain_name" {
  description = "Domain name for the API Gateway WebSocket endpoint. If not provided, defaults to 'api.' prefix on domain_name"
  type        = string
  default     = ""
}

variable "api_key" {
  description = "API key for authenticating speech-to-text client communication"
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, production)"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "live-translate"
}

variable "lambda_zip_path" {
  description = "Path to the Lambda deployment package (zip file)"
  type        = string
  default     = "../lambda_deployment.zip"
}
